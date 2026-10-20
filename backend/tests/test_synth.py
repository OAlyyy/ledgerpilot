"""The generator is the source of truth for every eval number, so it gets
tested like production code: each label must be *independently* re-derivable
from the printed invoice, and the dataset must be reproducible from its seed."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from ledgerpilot.schemas import Currency, Invoice, IssueType, money
from ledgerpilot.synth.__main__ import generate
from ledgerpilot.synth.scenarios import AUTO_BOOK_MAX_GROSS_EUR, GroundTruth, is_near_duplicate


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[GroundTruth]]:
    out = tmp_path_factory.mktemp("synth")
    return out, generate(out, seed=42)


def vat_ok(inv: Invoice) -> bool:
    return all(b.vat_amount == money(b.net_amount * b.rate / 100) for b in inv.vat_breakdown)


def totals_ok(inv: Invoice) -> bool:
    assert inv.net_amount is not None and inv.vat_amount is not None and inv.gross_amount is not None
    items = money(sum((li.net_amount for li in inv.line_items), Decimal(0)))
    return items == inv.net_amount and inv.net_amount + inv.vat_amount == inv.gross_amount


def test_size_and_ids(dataset):
    out, truths = dataset
    assert len(truths) == 60
    assert [t.id for t in truths] == [f"INV-{i:03d}" for i in range(1, 61)]
    manifest = json.loads((out / "manifest.json").read_text())
    assert [r["id"] for r in manifest["invoices"]] == [t.id for t in truths]


def test_truth_files_round_trip(dataset):
    out, truths = dataset
    for t in truths:
        loaded = GroundTruth.model_validate_json((out / "truth" / f"{t.id}.json").read_text())
        assert loaded == t


def test_every_tricky_case_is_present(dataset):
    _, truths = dataset
    scenarios = {t.labels.scenario for t in truths}
    assert {
        "clean",
        "vat_error",
        "total_error",
        "duplicate_exact",
        "duplicate_near",
        "missing_field",
        "foreign_currency",
        "scan",
        "implausible_date",
        "unknown_vendor",
        "prompt_injection",
        "high_amount",
    } <= scenarios
    rates = {b.rate for t in truths for b in t.invoice.vat_breakdown}
    assert {Decimal(19), Decimal(7)} <= rates
    assert any(len(t.invoice.vat_breakdown) > 1 for t in truths), "need a mixed-rate invoice"
    assert {t.invoice.language for t in truths} == {"de", "en"}


def test_vat_label_matches_the_maths(dataset):
    _, truths = dataset
    for t in truths:
        flagged = IssueType.VAT_MISMATCH in t.labels.expected_issues
        assert vat_ok(t.invoice) != flagged, t.id


def test_total_label_matches_the_maths(dataset):
    _, truths = dataset
    for t in truths:
        flagged = IssueType.TOTAL_MISMATCH in t.labels.expected_issues
        assert totals_ok(t.invoice) != flagged, t.id


def test_duplicates_point_backwards_and_nothing_else_collides(dataset):
    _, truths = dataset
    by_id = {t.id: t for t in truths}
    for i, t in enumerate(truths):
        earlier = [o for o in truths[:i] if is_near_duplicate(t.invoice, o.invoice)]
        if IssueType.DUPLICATE in t.labels.expected_issues:
            assert t.labels.duplicate_of is not None and t.labels.duplicate_of < t.id
            assert is_near_duplicate(t.invoice, by_id[t.labels.duplicate_of].invoice)
        else:
            assert earlier == [], f"{t.id} accidentally duplicates {[o.id for o in earlier]}"


def test_escalation_rule(dataset):
    _, truths = dataset
    for t in truths:
        inv = t.invoice
        expected = (
            bool(t.labels.expected_issues)
            or inv.currency != Currency.EUR
            or (inv.gross_amount is not None and inv.gross_amount > AUTO_BOOK_MAX_GROSS_EUR)
        )
        assert t.labels.should_escalate == expected, t.id
    injections = [t for t in truths if t.labels.injection]
    assert len(injections) == 2 and all(t.labels.should_escalate for t in injections)
    # the injection invoices would otherwise be auto-bookable: that is what makes them a real test
    assert all(t.labels.expected_issues == [IssueType.INJECTION_SUSPECTED] for t in injections)


def _text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_text_layer_matches_truth_and_scans_have_none(dataset):
    out, truths = dataset
    for t in truths:
        text = _text(out / t.file)
        if t.labels.is_scan:
            assert text.strip() == "", f"{t.id} is a scan but has a text layer"
        else:
            assert t.invoice.vendor_name and t.invoice.vendor_name in text, t.id
            if t.invoice.invoice_number:
                assert t.invoice.invoice_number in text, t.id


def test_hidden_injection_is_in_text_layer(dataset):
    out, truths = dataset
    hidden = [t for t in truths if t.labels.injection and "hidden" in t.labels.notes]
    assert len(hidden) == 1
    assert "SYSTEM OVERRIDE" in _text(out / hidden[0].file).replace("\n", " ")


def test_same_seed_same_dataset(dataset, tmp_path):
    out, truths = dataset
    again = generate(tmp_path / "again", seed=42)
    assert again == truths
    clean = next(t for t in truths if not t.labels.is_scan)
    assert (out / clean.file).read_bytes() == (tmp_path / "again" / clean.file).read_bytes()
