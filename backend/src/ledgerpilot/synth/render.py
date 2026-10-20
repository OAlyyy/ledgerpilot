"""Turn a ``Spec`` into a PDF with one of four layouts.

The renderer prints *only* what is in ``spec.invoice``: a field that is ``None``
is simply absent from the page. That keeps ground truth and document in sync by
construction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ledgerpilot.schemas import Currency, Invoice
from ledgerpilot.synth.scenarios import Spec
from ledgerpilot.synth.vendors import RECIPIENT

rl_config.invariant = 1  # no timestamps/random ids in the PDF: same seed, same bytes

LABELS = {
    "de": {
        "invoice": "Rechnung",
        "receipt": "Beleg",
        "number": "Rechnungsnummer",
        "receipt_no": "Beleg-Nr.",
        "date": "Rechnungsdatum",
        "due": "Zahlbar bis",
        "customer": "Kundennummer",
        "pos": "Pos.",
        "desc": "Bezeichnung",
        "qty": "Menge",
        "unit": "Einzelpreis",
        "vat": "USt.",
        "amount": "Betrag",
        "net": "Nettobetrag",
        "vat_line": "zzgl. {rate} USt. auf {net}",
        "gross": "Gesamtbetrag",
        "pay": "Bitte überweisen Sie den Betrag bis zum {due} ohne Abzug auf folgendes Konto:",
        "pay_no_date": "Bitte überweisen Sie den Betrag ohne Abzug auf folgendes Konto:",
        "pay_now": "Der Betrag wurde per Kreditkarte beglichen.",
        "vat_id": "USt-IdNr.",
        "thanks": "Vielen Dank für Ihren Einkauf!",
        "total": "SUMME",
        "bill_to": "Rechnungsempfänger",
    },
    "en": {
        "invoice": "Invoice",
        "receipt": "Receipt",
        "number": "Invoice No.",
        "receipt_no": "Receipt No.",
        "date": "Invoice date",
        "due": "Due date",
        "customer": "Customer ID",
        "pos": "#",
        "desc": "Description",
        "qty": "Qty",
        "unit": "Unit price",
        "vat": "VAT",
        "amount": "Amount",
        "net": "Subtotal",
        "vat_line": "VAT {rate} on {net}",
        "gross": "Total",
        "pay": "Please transfer the amount by {due} to:",
        "pay_no_date": "Please transfer the amount to:",
        "pay_now": "Paid by credit card. No action required.",
        "vat_id": "VAT ID",
        "thanks": "Thank you!",
        "total": "TOTAL",
        "bill_to": "Bill to",
    },
}

SYMBOL = {Currency.EUR: "€", Currency.USD: "$", Currency.GBP: "£", Currency.CHF: "CHF "}


def fmt_money(value: Decimal, currency: Currency, lang: str) -> str:
    if lang == "de":
        s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {'€' if currency == Currency.EUR else currency.value}"
    return f"{SYMBOL[currency]}{value:,.2f}"


def fmt_qty(q: Decimal) -> str:
    return f"{q:f}".rstrip("0").rstrip(".") if "." in f"{q:f}" else f"{q}"


def fmt_rate(rate: Decimal, lang: str) -> str:
    r = fmt_qty(rate)
    return f"{r} %" if lang == "de" else f"{r}%"


def fmt_date(d: date, lang: str, layout: str) -> str:
    if lang == "de":
        return d.strftime("%d.%m.%Y")
    return d.strftime("%d %b %Y") if layout == "modern" else d.isoformat()


# ---------------------------------------------------------------------- page decor


def _decorate(spec: Spec):  # type: ignore[no-untyped-def]
    """Canvas callback: hidden prompt-injection text and the 'COPY' stamp."""

    def draw(canvas: Canvas, doc: object) -> None:
        canvas.saveState()
        if spec.hidden_text:
            # White, 1 pt: invisible to a human, present in the text layer.
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica", 1)
            canvas.drawString(20 * mm, 8 * mm, spec.hidden_text)
        if spec.stamp:
            canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.55))
            canvas.setFont("Helvetica-Bold", 44)
            canvas.translate(125 * mm, 120 * mm)  # empty area below the totals
            canvas.rotate(25)
            canvas.drawCentredString(0, 0, spec.stamp)
        canvas.restoreState()

    return draw


# ------------------------------------------------------------------------ helpers

BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=7, leading=9, textColor=colors.grey)
BOLD = ParagraphStyle("bold", parent=BASE, fontName="Helvetica-Bold")
TITLE = ParagraphStyle("title", parent=BASE, fontName="Helvetica-Bold", fontSize=16, leading=20)
RIGHT = ParagraphStyle("right", parent=BASE, alignment=TA_RIGHT)


def _items_table(inv: Invoice, lang: str, header_bg: colors.Color, with_pos: bool = True) -> Table:
    L = LABELS[lang]
    cur = inv.currency
    head = ([L["pos"]] if with_pos else []) + [L["desc"], L["qty"], L["unit"], L["vat"], L["amount"]]
    rows: list[list[object]] = [head]
    for i, it in enumerate(inv.line_items, start=1):
        rows.append(
            ([str(i)] if with_pos else [])
            + [
                Paragraph(it.description, BASE),
                fmt_qty(it.quantity),
                fmt_money(it.unit_price, cur, lang),
                fmt_rate(it.vat_rate, lang),
                fmt_money(it.net_amount, cur, lang),
            ]
        )
    widths = ([10 * mm] if with_pos else []) + [72 * mm, 14 * mm, 27 * mm, 15 * mm, 28 * mm]
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("ALIGN", (-4, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.3, colors.grey),
            ]
        )
    )
    return t


def _totals_table(inv: Invoice, lang: str) -> Table:
    L = LABELS[lang]
    cur = inv.currency
    rows: list[list[str]] = []
    if inv.net_amount is not None:
        rows.append([L["net"], fmt_money(inv.net_amount, cur, lang)])
    for b in inv.vat_breakdown:
        label = L["vat_line"].format(rate=fmt_rate(b.rate, lang), net=fmt_money(b.net_amount, cur, lang))
        rows.append([label, fmt_money(b.vat_amount, cur, lang)])
    if inv.gross_amount is not None:
        rows.append([L["gross"], fmt_money(inv.gross_amount, cur, lang)])
    t = Table(rows, colWidths=[110 * mm, 32 * mm], hAlign="RIGHT")
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
            ]
        )
    )
    return t


def _payment_block(spec: Spec) -> list[object]:
    inv, lang = spec.invoice, spec.vendor.language
    L = LABELS[lang]
    out: list[object] = []
    if inv.iban:
        if inv.due_date:
            out.append(Paragraph(L["pay"].format(due=fmt_date(inv.due_date, lang, spec.layout)), BASE))
        else:
            out.append(Paragraph(L["pay_no_date"], BASE))
        out.append(Paragraph(f"IBAN: {_group_iban(inv.iban)}", BOLD))
    elif inv.due_date:
        out.append(Paragraph(f"{L['due']}: {fmt_date(inv.due_date, lang, spec.layout)}", BASE))
        out.append(Paragraph(L["pay_now"], BASE))
    for note in spec.footer_notes:
        out += [Spacer(1, 3 * mm), Paragraph(note, BASE)]
    return out


def _group_iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _legal_footer(spec: Spec) -> Paragraph:
    inv, v = spec.invoice, spec.vendor
    parts = [v.name, v.address]
    if inv.vendor_vat_id:
        parts.append(f"{LABELS[v.language]['vat_id']} {inv.vendor_vat_id}")
    return Paragraph(" · ".join(parts), SMALL)


def _meta_rows(spec: Spec) -> list[list[str]]:
    inv, lang = spec.invoice, spec.vendor.language
    L = LABELS[lang]
    rows = []
    if inv.invoice_number:
        rows.append([L["number"], inv.invoice_number])
    if inv.invoice_date:
        rows.append([L["date"], fmt_date(inv.invoice_date, lang, spec.layout)])
    # stable across runs (built-in hash() is randomised per process)
    rows.append([L["customer"], f"K-{sum(map(ord, spec.vendor.name)) * 37 % 90000 + 10000}"])
    return rows


# ------------------------------------------------------------------------ layouts


def _din_letter(spec: Spec) -> list[object]:
    inv, v, lang = spec.invoice, spec.vendor, spec.vendor.language
    L = LABELS[lang]
    head = Table(
        [[Paragraph(f"<b>{v.name}</b><br/>{v.street}<br/>{v.city}", RIGHT)]],
        colWidths=[170 * mm],
    )
    sender_line = Paragraph(f"<u>{v.name} · {v.street} · {v.city}</u>", SMALL)
    recipient = Paragraph("<br/>".join(RECIPIENT), BASE)
    meta = Table(_meta_rows(spec), colWidths=[35 * mm, 40 * mm])
    meta.setStyle(
        TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    )
    address_row = Table([[[sender_line, Spacer(1, 2 * mm), recipient], meta]], colWidths=[95 * mm, 75 * mm])
    address_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        head,
        Spacer(1, 12 * mm),
        address_row,
        Spacer(1, 12 * mm),
        Paragraph(L["invoice"], TITLE),
        Spacer(1, 4 * mm),
        _items_table(inv, lang, colors.Color(0.92, 0.92, 0.92)),
        Spacer(1, 3 * mm),
        _totals_table(inv, lang),
        Spacer(1, 8 * mm),
        *_payment_block(spec),
        Spacer(1, 10 * mm),
        _legal_footer(spec),
    ]


def _modern(spec: Spec) -> list[object]:
    inv, v, lang = spec.invoice, spec.vendor, spec.vendor.language
    L = LABELS[lang]
    accent = colors.Color(0.16, 0.24, 0.55)
    band = Table(
        [
            [
                Paragraph(f"<font color='white' size='18'><b>{v.name}</b></font>", BASE),
                Paragraph(f"<font color='white' size='22'><b>{L['invoice'].upper()}</b></font>", RIGHT),
            ]
        ],
        colWidths=[110 * mm, 60 * mm],
        rowHeights=[22 * mm],
    )
    band.setStyle(
        TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
    )
    bill_to = Paragraph(f"<b>{L['bill_to']}</b><br/>" + "<br/>".join(RECIPIENT), BASE)
    details = "<br/>".join(f"<b>{k}:</b> {val}" for k, val in _meta_rows(spec))
    if inv.due_date:
        details += f"<br/><b>{L['due']}:</b> {fmt_date(inv.due_date, lang, spec.layout)}"
    cols = Table([[bill_to, Paragraph(details, BASE)]], colWidths=[95 * mm, 75 * mm])
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        band,
        Spacer(1, 4 * mm),
        Paragraph(f"{v.street}, {v.city}", SMALL),
        Spacer(1, 8 * mm),
        cols,
        Spacer(1, 10 * mm),
        _items_table(inv, lang, colors.Color(0.85, 0.88, 0.96), with_pos=False),
        Spacer(1, 3 * mm),
        _totals_table(inv, lang),
        Spacer(1, 8 * mm),
        *_payment_block(spec),
        Spacer(1, 10 * mm),
        _legal_footer(spec),
    ]


def _minimal(spec: Spec) -> list[object]:
    inv, v, lang = spec.invoice, spec.vendor, spec.vendor.language
    L = LABELS[lang]
    lines = [f"<b>{v.name}</b>", v.address]
    if inv.vendor_vat_id:
        lines.append(f"{L['vat_id']}: {inv.vendor_vat_id}")
    meta = "  |  ".join(f"{k}: {val}" for k, val in _meta_rows(spec))
    return [
        Paragraph("<br/>".join(lines), BASE),
        Spacer(1, 8 * mm),
        Paragraph(f"{L['invoice']}", TITLE),
        Paragraph(meta, BASE),
        Spacer(1, 2 * mm),
        Paragraph(f"{L['bill_to']}: {', '.join(RECIPIENT)}", BASE),
        Spacer(1, 6 * mm),
        _items_table(inv, lang, colors.white),
        Spacer(1, 3 * mm),
        _totals_table(inv, lang),
        Spacer(1, 6 * mm),
        *_payment_block(spec),
    ]


def _receipt(spec: Spec, path: Path) -> None:
    """A narrow till receipt (Kassenbon), drawn directly on the canvas."""
    inv, v, lang = spec.invoice, spec.vendor, spec.vendor.language
    L = LABELS[lang]
    cur = inv.currency
    width = 80 * mm
    n_lines = 22 + 2 * len(inv.line_items) + len(inv.vat_breakdown) + 3 * len(spec.footer_notes)
    height = n_lines * 4.2 * mm + 20 * mm
    c = Canvas(str(path), pagesize=(width, height), invariant=1)
    y = height - 10 * mm

    def line(text: str, size: float = 7.5, bold: bool = False, center: bool = False) -> None:
        nonlocal y
        c.setFont("Courier-Bold" if bold else "Courier", size)
        if center:
            c.drawCentredString(width / 2, y, text)
        else:
            c.drawString(4 * mm, y, text)
        y -= size * 1.45

    def lr(left: str, right: str, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Courier-Bold" if bold else "Courier", 7.5)
        c.drawString(4 * mm, y, left[:30])
        c.drawRightString(width - 4 * mm, y, right)
        y -= 7.5 * 1.45

    line(v.name, 9, bold=True, center=True)
    line(v.street, center=True)
    line(v.city, center=True)
    if inv.vendor_vat_id:
        line(f"{L['vat_id']} {inv.vendor_vat_id}", center=True)
    line("-" * 42)
    rate_code = {r.rate: "AB"[i] for i, r in enumerate(inv.vat_breakdown[:2])}
    for it in inv.line_items:
        line(it.description[:40])
        gross_line = it.net_amount * (1 + it.vat_rate / 100)
        lr(
            f"  {fmt_qty(it.quantity)} x {fmt_money(it.unit_price, cur, lang)} netto",
            f"{fmt_money(gross_line.quantize(Decimal('0.01')), cur, lang)} {rate_code.get(it.vat_rate, '')}",
        )
    line("-" * 42)
    if inv.gross_amount is not None:
        lr(f"{L['total']} {cur.value}", fmt_money(inv.gross_amount, cur, lang), bold=True)
    line("")
    for b in inv.vat_breakdown:
        code, net = rate_code.get(b.rate, ""), fmt_money(b.net_amount, cur, lang)
        lr(f"{code} {fmt_rate(b.rate, lang)} Netto {net}", f"MwSt {fmt_money(b.vat_amount, cur, lang)}")
    if inv.net_amount is not None:
        lr("Netto gesamt" if lang == "de" else "Net total", fmt_money(inv.net_amount, cur, lang))
    if inv.vat_amount is not None:
        lr("MwSt gesamt" if lang == "de" else "VAT total", fmt_money(inv.vat_amount, cur, lang))
    line("-" * 42)
    if inv.invoice_number:
        line(f"{L['receipt_no']} {inv.invoice_number}")
    if inv.invoice_date:
        till_time = f"{10 + len(v.name) % 9}:{len(v.street) * 3 % 60:02d}"  # stable fake time
        line(f"{fmt_date(inv.invoice_date, lang, 'receipt')}  {till_time}")
    for note in spec.footer_notes:
        for chunk in _wrap(note, 42):
            line(chunk, 6.5)
    line("")
    line(L["thanks"], center=True)
    if spec.hidden_text:
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 1)
        c.drawString(4 * mm, 4 * mm, spec.hidden_text)
    c.showPage()
    c.save()


def _wrap(text: str, width: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return out + [cur] if cur else out


LAYOUTS = {"din_letter": _din_letter, "modern": _modern, "minimal": _minimal}


def render_pdf(spec: Spec, path: Path) -> None:
    if spec.layout == "receipt":
        _receipt(spec, path)
        return
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=f"{spec.vendor.name} {spec.invoice.invoice_number or ''}".strip(),
    )
    decorate = _decorate(spec)
    doc.build(LAYOUTS[spec.layout](spec), onFirstPage=decorate, onLaterPages=decorate)
