# Extraction eval: `gemini/gemini-3.5-flash-lite`

60 invoices (56 text, 4 scans), generated 2026-10-20 21:01.

- Field accuracy (all fields, all invoices): **99%**
- Invoices with every field correct: **93%**
- Failed extractions: 0; invoices that needed a validation retry: 0
- Latency p50 / p95: 2.17 s / 6.68 s
- Tokens per invoice (avg in / out): 707 / 398
- List-price cost per 1,000 invoices: $1.21 (actually paid: $0, free tier)

| Field | All | Text | Scans | DE | EN |
|---|---|---|---|---|---|
| vendor_name | 100% | 100% | 100% | 100% | 100% |
| invoice_number | 100% | 100% | 100% | 100% | 100% |
| invoice_date | 100% | 100% | 100% | 100% | 100% |
| due_date | 100% | 100% | 100% | 100% | 100% |
| currency | 100% | 100% | 100% | 100% | 100% |
| net_amount | 100% | 100% | 100% | 100% | 100% |
| vat_amount | 100% | 100% | 100% | 100% | 100% |
| gross_amount | 100% | 100% | 100% | 100% | 100% |
| vendor_vat_id | 97% | 100% | 50% | 96% | 100% |
| iban | 100% | 100% | 100% | 100% | 100% |
| vat_breakdown | 100% | 100% | 100% | 100% | 100% |
| line_items | 97% | 96% | 100% | 96% | 100% |
