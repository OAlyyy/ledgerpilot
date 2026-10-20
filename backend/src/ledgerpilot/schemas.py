"""Pydantic models shared by every part of LedgerPilot.

These are the contract between the LLM, the tools, the database and the eval.
Two rules hold throughout:

* Money is ``Decimal``, never ``float`` (0.1 + 0.2 != 0.3 in binary floats).
* ``Invoice`` describes what is *printed* on the document, mistakes included.
  Extraction reads; validation judges. Mixing the two would let the model
  silently "fix" a wrong VAT amount and hide the very error we want to flag.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Round to cents the way German invoices do (kaufmännisch: half up)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"


class Category(StrEnum):
    SOFTWARE = "software"
    HOSTING = "hosting"
    TELECOM = "telecom"
    OFFICE = "office_supplies"
    HARDWARE = "hardware"
    TRAVEL = "travel"
    MEALS = "meals"
    BOOKS = "books"
    PROFESSIONAL_SERVICES = "professional_services"
    MARKETING = "marketing"


class IssueType(StrEnum):
    VAT_MISMATCH = "vat_mismatch"  # VAT amount does not match net x rate
    TOTAL_MISMATCH = "total_mismatch"  # net + VAT != gross, or line items != net
    DUPLICATE = "duplicate"  # same vendor + number, or near-identical amount/date
    IMPLAUSIBLE_DATE = "implausible_date"  # in the future or far in the past
    MISSING_FIELD = "missing_field"  # a required field is not on the document
    UNKNOWN_VENDOR = "unknown_vendor"  # vendor not in the vendor master
    INJECTION_SUSPECTED = "injection_suspected"  # document text tries to instruct the AI


class LineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal = Field(description="Net price per unit")
    vat_rate: Decimal = Field(description="Percent, e.g. 19 or 7")
    net_amount: Decimal


class VatLine(BaseModel):
    """One row of the VAT summary; invoices with mixed rates have several."""

    rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal


class Invoice(BaseModel):
    """Structured data as printed on one invoice or receipt.

    Every field is optional because real documents omit things; a missing
    required field is reported by validation, not by a parsing failure.
    """

    model_config = ConfigDict(use_enum_values=False)

    # Length limits are a cheap semantic check: constrained decoding guarantees
    # well-formed JSON, not sensible values, and a model that starts "thinking"
    # inside a string field produces a schema-valid but useless answer.
    vendor_name: str | None = Field(None, max_length=120)
    vendor_address: str | None = Field(None, max_length=200)
    vendor_vat_id: str | None = Field(None, max_length=32, description="USt-IdNr., e.g. DE123456789")
    invoice_number: str | None = Field(None, max_length=40)
    invoice_date: date | None = None
    due_date: date | None = None
    currency: Currency = Currency.EUR
    net_amount: Decimal | None = None
    vat_amount: Decimal | None = None
    gross_amount: Decimal | None = None
    vat_breakdown: list[VatLine] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    iban: str | None = Field(None, max_length=42)
    language: str | None = Field(None, max_length=2, description="'de' or 'en'")
