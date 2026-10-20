# Synthetic dataset

`make synth` writes 60 invoices to `data/synth/` (seed 42, reference date 2026-10-15).
Everything is fictional: vendors, IBANs, VAT IDs, amounts.

| Scenario | n | What a correct system does |
|---|---|---|
| clean | 26 | books automatically (≤ 250 € gross, known vendor, maths correct) |
| high_amount | 3 | asks a human (above the auto-book threshold); one is a 2-page invoice |
| vat_error | 4 | flags `vat_mismatch` (16 % applied while 19 % is printed, or digits transposed) |
| total_error | 3 | flags `total_mismatch` (gross ≠ net + VAT, or line items ≠ net) |
| duplicate_exact | 3 | flags `duplicate` (same vendor + number, sometimes another layout, stamped COPY) |
| duplicate_near | 2 | flags `duplicate` (same vendor and amount, new number, 1–4 days later) |
| missing_field | 4 | flags `missing_field` (no invoice number / no invoice date) |
| foreign_currency | 4 | asks a human (USD / GBP / CHF, reverse charge, 0 % VAT) |
| scan | 4 | image-only PDF, blurred, rotated, noisy; needs the vision path. One has a VAT error |
| implausible_date | 2 | flags `implausible_date` (2031 and 2009) |
| unknown_vendor | 3 | flags `unknown_vendor` (not in `vendor_master.json`) |
| prompt_injection | 2 | flags `injection_suspected` and **never auto-books**. One visible note, one white 1-pt text |

Files: `pdf/INV-xxx.pdf`, `truth/INV-xxx.json` (the `Invoice` as printed plus `Labels`),
`manifest.json`, `vendor_master.json`. Invoices are numbered in **processing order**; a
duplicate always comes after its original.

Ground truth is what is **printed**, errors included. Validation, not extraction, decides
that 16 % VAT is wrong.

Layouts: `din_letter` (classic German business letter), `modern` (SaaS-style, coloured band),
`minimal` (plain, used for the multi-page case), `receipt` (80 mm till receipt with A/B VAT codes).

`backend/tests/test_synth.py` re-derives every label from the printed numbers, so a labelling
bug fails CI instead of quietly corrupting eval results.
