"""Extraction eval: per-field accuracy against the synthetic ground truth.

    python -m ledgerpilot.evals.extraction --model gemini/gemini-3.5-flash-lite [--limit 20]

Scoring rules (one point per field per invoice):
* strings: equal after normalisation (case, whitespace, and for IDs/IBANs all
  separators). Vendor names allow a missing legal form ("GmbH") to count as equal.
* amounts: equal to the cent (|diff| <= 0.01, i.e. rounding tolerance).
* dates and currency: exact.
* absent fields: predicting ``None`` when the truth is ``None`` is correct, and
  any value there is a hallucination and counts as wrong. This matters for the
  missing-field invoices.
* vat_breakdown: the set of (rate, net, vat) rows must match exactly.
* line_items: correct if the count matches and every truth line's net amount is
  found among the predicted lines.

Writes ``eval/reports/extraction/<model>/{results.csv,summary.json,summary.md}``
and refreshes ``eval/reports/extraction/comparison.md`` across all models run so far.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from ledgerpilot.config import REPO_ROOT, get_settings
from ledgerpilot.extraction import extract_invoice
from ledgerpilot.llm import LLMClient, QuotaExhaustedError, StructuredOutputError, Usage
from ledgerpilot.schemas import Invoice
from ledgerpilot.synth.scenarios import GroundTruth

FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "net_amount",
    "vat_amount",
    "gross_amount",
    "vendor_vat_id",
    "iban",
    "vat_breakdown",
    "line_items",
)
AMOUNT_FIELDS = {"net_amount", "vat_amount", "gross_amount"}
ID_FIELDS = {"invoice_number", "vendor_vat_id", "iban"}
TOLERANCE = Decimal("0.01")
LEGAL_FORMS = re.compile(r"\b(gmbh|ag|kg|ug|e\.k\.|inc\.?|ltd\.?)\b|\(haftungsbeschränkt\)")


# ------------------------------------------------------------------------ scoring


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold()).strip(" .,")


def _norm_id(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.casefold())


def _norm_vendor(s: str) -> str:
    return _norm_text(LEGAL_FORMS.sub("", _norm_text(s)))


def field_correct(name: str, truth: Any, pred: Any) -> bool:
    if truth is None or pred is None or truth == [] or pred == []:
        return (truth in (None, [])) and (pred in (None, []))
    if name in AMOUNT_FIELDS:
        return abs(Decimal(truth) - Decimal(pred)) <= TOLERANCE
    if name in ID_FIELDS:
        return _norm_id(truth) == _norm_id(pred)
    if name == "vendor_name":
        return _norm_vendor(truth) == _norm_vendor(pred)
    if name == "vat_breakdown":
        key = lambda b: (Decimal(b.rate), b.net_amount, b.vat_amount)  # noqa: E731
        return sorted(map(key, truth)) == sorted(map(key, pred))
    if name == "line_items":
        if len(truth) != len(pred):
            return False
        remaining = [p.net_amount for p in pred]
        for t in truth:
            match = next((p for p in remaining if abs(p - t.net_amount) <= TOLERANCE), None)
            if match is None:
                return False
            remaining.remove(match)
        return True
    return bool(truth == pred)


def score(truth: Invoice, pred: Invoice | None) -> dict[str, bool]:
    if pred is None:
        return dict.fromkeys(FIELDS, False)
    return {f: field_correct(f, getattr(truth, f), getattr(pred, f)) for f in FIELDS}


# --------------------------------------------------------------------------- runs


@dataclass
class Row:
    id: str
    scenario: str
    method: str
    language: str
    attempts: int
    ok: bool
    error: str
    usage: Usage
    fields: dict[str, bool] = field(default_factory=dict)


def load_truths(data_dir: Path) -> list[GroundTruth]:
    files = sorted((data_dir / "truth").glob("INV-*.json"))
    return [GroundTruth.model_validate_json(p.read_text()) for p in files]


def run(
    model: str,
    data_dir: Path,
    limit: int | None,
    client: LLMClient | None = None,
    ids: list[str] | None = None,
) -> list[Row]:
    settings = get_settings()
    client = client or LLMClient(
        model,
        cache_dir=settings.cache_dir,
        max_retries=settings.llm_max_retries,
        min_interval_s=settings.llm_min_interval_s,
    )
    truths = load_truths(data_dir)
    if ids:
        truths = [t for t in truths if t.id in ids]
    if limit:
        truths = _stratified(truths, limit)
    rows = []
    for t in truths:
        pred: Invoice | None = None
        method = "vision" if t.labels.is_scan else "text"
        attempts, error, usage = 0, "", Usage()
        try:
            ex = extract_invoice(data_dir / t.file, client)
            pred, method, attempts, usage = ex.invoice, ex.method, ex.attempts, ex.usage
        except StructuredOutputError as e:
            attempts, error, usage = len(e.errors), "invalid_output", e.usage
        except QuotaExhaustedError:
            # Not the model's fault: abort instead of scoring the rest as failures.
            # Re-running later is free for invoices already done (response cache).
            print(f"  quota exhausted at {t.id} after {len(rows)} invoices; no report written")
            raise
        except Exception as e:  # provider error after retries: count as a failed invoice
            error = f"{type(e).__name__}: {str(e)[:120]}"
        row = Row(
            id=t.id,
            scenario=t.labels.scenario,
            method=method,
            language=t.invoice.language or "",
            attempts=attempts,
            ok=pred is not None,
            error=error,
            usage=usage,
            fields=score(t.invoice, pred),
        )
        rows.append(row)
        status = "ok" if row.ok else f"FAIL {error}"
        right = sum(row.fields.values())
        print(
            f"  {t.id} {method:<6} {right:>2}/{len(FIELDS)} fields  {usage.latency_ms / 1000:5.1f}s  {status}"
        )
    return rows


def _stratified(truths: list[GroundTruth], limit: int) -> list[GroundTruth]:
    """Take a subset that keeps every scenario represented (round-robin)."""
    by_scenario: dict[str, list[GroundTruth]] = defaultdict(list)
    for t in truths:
        by_scenario[t.labels.scenario].append(t)
    picked: list[GroundTruth] = []
    while len(picked) < limit and any(by_scenario.values()):
        for group in by_scenario.values():
            if group and len(picked) < limit:
                picked.append(group.pop(0))
    return sorted(picked, key=lambda t: t.id)


# ------------------------------------------------------------------------ reports


def _pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}%" if values else "–"


def _percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def summarise(model: str, rows: list[Row]) -> dict[str, Any]:
    subsets = {
        "all": rows,
        "text": [r for r in rows if r.method == "text"],
        "vision": [r for r in rows if r.method == "vision"],
        "de": [r for r in rows if r.language == "de"],
        "en": [r for r in rows if r.language == "en"],
    }
    per_field = {f: {k: _pct([r.fields[f] for r in rs]) for k, rs in subsets.items()} for f in FIELDS}
    all_fields = [v for r in rows for v in r.fields.values()]
    latencies = [r.usage.latency_ms / 1000 for r in rows if r.ok]
    costs = [r.usage.cost_usd for r in rows]
    return {
        "model": model,
        "n": len(rows),
        "n_text": len(subsets["text"]),
        "n_vision": len(subsets["vision"]),
        "failures": sum(not r.ok for r in rows),
        "field_accuracy": _pct(all_fields),
        "perfect_invoices": _pct([all(r.fields.values()) for r in rows]),
        "invoices_needing_retry": sum(r.attempts > 1 for r in rows),
        "per_field": per_field,
        "latency_p50_s": round(_percentile(latencies, 0.5), 2),
        "latency_p95_s": round(_percentile(latencies, 0.95), 2),
        "tokens_in_avg": round(statistics.mean(r.usage.input_tokens for r in rows)) if rows else 0,
        "tokens_out_avg": round(statistics.mean(r.usage.output_tokens for r in rows)) if rows else 0,
        "list_price_usd_per_1000": round(1000 * statistics.mean(costs), 2) if costs else 0,
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
    }


def summary_markdown(s: dict[str, Any]) -> str:
    lines = [
        f"# Extraction eval: `{s['model']}`",
        "",
        f"{s['n']} invoices ({s['n_text']} text, {s['n_vision']} scans), generated {s['generated_at']}.",
        "",
        f"- Field accuracy (all fields, all invoices): **{s['field_accuracy']}**",
        f"- Invoices with every field correct: **{s['perfect_invoices']}**",
        f"- Failed extractions: {s['failures']}; invoices that needed a validation retry: "
        f"{s['invoices_needing_retry']}",
        f"- Latency p50 / p95: {s['latency_p50_s']} s / {s['latency_p95_s']} s",
        f"- Tokens per invoice (avg in / out): {s['tokens_in_avg']} / {s['tokens_out_avg']}",
        f"- List-price cost per 1,000 invoices: ${s['list_price_usd_per_1000']} "
        "(actually paid: $0, free tier)",
        "",
        "| Field | All | Text | Scans | DE | EN |",
        "|---|---|---|---|---|---|",
    ]
    for f, v in s["per_field"].items():
        lines.append(f"| {f} | {v['all']} | {v['text']} | {v['vision']} | {v['de']} | {v['en']} |")
    return "\n".join(lines) + "\n"


def write_reports(model: str, rows: list[Row], out_root: Path) -> Path:
    out = out_root / re.sub(r"[^A-Za-z0-9.-]+", "_", model)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "scenario", "method", "language", "ok", "attempts", "error", "latency_s",
                    "tokens_in", "tokens_out", *FIELDS])  # fmt: skip
        for r in rows:
            w.writerow([r.id, r.scenario, r.method, r.language, r.ok, r.attempts, r.error,
                        round(r.usage.latency_ms / 1000, 2), r.usage.input_tokens, r.usage.output_tokens,
                        *(int(r.fields[f]) for f in FIELDS)])  # fmt: skip
    s = summarise(model, rows)
    (out / "summary.json").write_text(json.dumps(s, indent=2))
    (out / "summary.md").write_text(summary_markdown(s))
    write_comparison(out_root)
    return out


def write_comparison(out_root: Path) -> None:
    summaries = [json.loads(p.read_text()) for p in sorted(out_root.glob("*/summary.json"))]
    if not summaries:
        return
    head = "| Field | " + " | ".join(f"`{s['model']}`" for s in summaries) + " |"
    lines = ["# Extraction eval: model comparison", "", head, "|---|" + "---|" * len(summaries)]
    for f in FIELDS:
        lines.append(f"| {f} | " + " | ".join(s["per_field"][f]["all"] for s in summaries) + " |")
    for label, key in [
        ("**all fields**", "field_accuracy"),
        ("perfect invoices", "perfect_invoices"),
        ("n invoices", "n"),
        ("failures", "failures"),
        ("needed retry", "invoices_needing_retry"),
        ("latency p50 (s)", "latency_p50_s"),
        ("latency p95 (s)", "latency_p95_s"),
        ("list $ / 1k invoices", "list_price_usd_per_1000"),
    ]:
        lines.append(f"| {label} | " + " | ".join(str(s[key]) for s in summaries) + " |")
    (out_root / "comparison.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Extraction eval against synthetic ground truth")
    ap.add_argument("--model", default=None, help="LiteLLM model name (default: LLM_MODEL)")
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "synth")
    ap.add_argument("--limit", type=int, default=None, help="stratified subset size")
    ap.add_argument("--ids", nargs="*", help="only these invoice ids")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "eval" / "reports" / "extraction")
    args = ap.parse_args()
    model = args.model or get_settings().llm_model
    print(f"extraction eval: {model}")
    try:
        rows = run(model, args.data, args.limit, ids=args.ids)
    except QuotaExhaustedError as e:
        raise SystemExit(
            f"stopped: {e.model} free-tier quota exhausted; re-run later (finished invoices are cached)"
        ) from None
    out = write_reports(model, rows, args.out)
    print()
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
