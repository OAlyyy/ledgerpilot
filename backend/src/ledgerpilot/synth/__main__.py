"""``python -m ledgerpilot.synth --out data/synth --seed 42``

Writes, for each invoice:
  pdf/INV-001.pdf          the document
  truth/INV-001.json       ground truth (Invoice as printed + labels)
plus
  manifest.json            one summary row per invoice, in processing order
  vendor_master.json       vendors the business already knows (seeds the DB)
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path

from ledgerpilot.synth.degrade import degrade_to_scan
from ledgerpilot.synth.render import render_pdf
from ledgerpilot.synth.scenarios import REFERENCE_DATE, Generator, GroundTruth
from ledgerpilot.synth.vendors import KNOWN_VENDORS


def generate(out: Path, seed: int) -> list[GroundTruth]:
    if out.exists():
        shutil.rmtree(out)
    (out / "pdf").mkdir(parents=True)
    (out / "truth").mkdir()

    specs = Generator(seed).dataset()
    scan_rng = random.Random(seed + 1)
    truths: list[GroundTruth] = []
    for spec in specs:
        pdf_path = out / "pdf" / f"{spec.id}.pdf"
        render_pdf(spec, pdf_path)
        if spec.labels.is_scan:
            degrade_to_scan(pdf_path, scan_rng)
        gt = GroundTruth(
            id=spec.id,
            file=f"pdf/{spec.id}.pdf",
            layout=spec.layout,
            invoice=spec.invoice,
            labels=spec.labels,
        )
        (out / "truth" / f"{spec.id}.json").write_text(gt.model_dump_json(indent=2))
        truths.append(gt)

    manifest = {
        "seed": seed,
        "reference_date": REFERENCE_DATE.isoformat(),
        "invoices": [
            {
                "id": t.id,
                "file": t.file,
                "scenario": t.labels.scenario,
                "vendor": t.invoice.vendor_name,
                "gross": str(t.invoice.gross_amount),
                "currency": t.invoice.currency.value,
                "should_escalate": t.labels.should_escalate,
                "expected_issues": [i.value for i in t.labels.expected_issues],
            }
            for t in truths
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    vendor_master = [
        {"name": v.name, "address": v.address, "default_category": v.category.value} for v in KNOWN_VENDORS
    ]
    (out / "vendor_master.json").write_text(json.dumps(vendor_master, indent=2, ensure_ascii=False))
    return truths


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/synth"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    truths = generate(args.out, args.seed)
    counts = Counter(t.labels.scenario for t in truths)
    escalate = sum(t.labels.should_escalate for t in truths)
    print(f"wrote {len(truths)} invoices to {args.out}")
    for scenario, n in sorted(counts.items()):
        print(f"  {scenario:<18} {n}")
    print(f"  should escalate:   {escalate}/{len(truths)}")


if __name__ == "__main__":
    main()
