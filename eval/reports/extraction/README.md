# Extraction eval: findings

Run with `make eval-extract MODEL=<litellm model>`. Per-model reports are in the subfolders,
and the side-by-side table is in [`comparison.md`](comparison.md).

## gemini-3.5-flash-lite (free tier), 60 invoices

99% of fields correct, and 93% of invoices (56/60) fully correct. Zero failed extractions and
zero validation retries were needed.

All four remaining errors, explained:

| Invoice | Field | Cause | Whose fault |
|---|---|---|---|
| INV-006, INV-045 | line_items | Café receipts print the **gross** amount per line, and our schema asks for the net amount. The model reported the printed figure. | Spec ambiguity (schema) |
| INV-039, INV-042 | vendor_vat_id | The VAT ID is 7-pt grey footer text, which the blur makes unreadable. The model returned `null` and didn't guess. | Vision limit, handled safely |

Errors found and fixed while building the eval:

1. **Ground-truth bug.** Two invoices had an IBAN in the truth that was never printed.
   `test_synth.py` now asserts every ground-truth identifier is in the PDF text.
2. **Schema-valid nonsense.** On a scan, the model started reasoning *inside* the
   `vendor_vat_id` string, then closed the JSON early. `max_length` limits on ID fields
   prevent it, because Gemini enforces them during decoding.
3. **Cropping scans.** Vision models shrink each image to a fixed token budget. Cropping
   the empty paper off a scan took it from mostly-null output to fully correct.

## gemini-3.5-flash: not run yet

The free tier allows only **20 requests per model per day** for this model, and the run
stopped at invoice 13. The client now stops on daily-quota errors instead of retrying, and
the response cache makes the next attempt resume for free.
