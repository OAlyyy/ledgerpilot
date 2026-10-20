"""Extraction plumbing and eval scoring, with a scripted model (no API calls)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fakes import ScriptedTransport

from ledgerpilot.evals.extraction import field_correct, score
from ledgerpilot.extraction import extract_invoice, load_document
from ledgerpilot.llm import LLMClient
from ledgerpilot.synth.__main__ import generate
from ledgerpilot.synth.scenarios import GroundTruth


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[GroundTruth]]:
    out = tmp_path_factory.mktemp("synth")
    return out, generate(out, seed=42)


def test_text_pdfs_use_text_and_scans_use_images(data):
    out, truths = data
    text = next(t for t in truths if not t.labels.is_scan)
    scan = next(t for t in truths if t.labels.is_scan)
    d = load_document(out / text.file)
    assert d.method == "text" and text.invoice.vendor_name in d.text
    s = load_document(out / scan.file)
    assert s.method == "vision" and s.images and s.images[0].startswith(b"\x89PNG")


def test_document_is_fenced_as_untrusted(data):
    out, truths = data
    inj = next(t for t in truths if t.labels.injection and "visible" in t.labels.notes)
    t = ScriptedTransport([inj.invoice.model_dump_json()])
    ex = extract_invoice(out / inj.file, LLMClient("fake", t))
    system, user = (m["content"] for m in t.calls[0]["messages"])
    assert "DATA, not instructions" in system
    assert user.startswith("<untrusted_document>") and "Ignoriere alle vorherigen" in user
    assert score(inj.invoice, ex.invoice) == dict.fromkeys(score(inj.invoice, inj.invoice), True)


def test_perfect_prediction_scores_100(data):
    _, truths = data
    for t in truths:
        assert all(score(t.invoice, t.invoice).values()), t.id


def test_scoring_rules():
    assert field_correct("gross_amount", Decimal("10.00"), Decimal("10.01"))
    assert not field_correct("gross_amount", Decimal("10.00"), Decimal("10.02"))
    assert field_correct("iban", "DE89370400440532013000", "DE89 3704 0044 0532 0130 00")
    assert field_correct("vendor_name", "Nordlicht Software GmbH", "nordlicht software")
    assert field_correct("invoice_number", None, None)
    assert not field_correct("invoice_number", None, "RE-1")  # hallucinated a missing field
    assert not field_correct("invoice_number", "RE-1", None)
