"""Fictional vendors and what they sell.

All names are invented. VAT rates follow German rules as of 2026 and are
illustrative only: most goods/services 19 %, books, local transport, long-distance
rail and hotel nights 7 %, restaurant food 7 % but drinks 19 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ledgerpilot.schemas import Category, Currency

R19 = Decimal("19")
R7 = Decimal("7")
R0 = Decimal("0")


@dataclass(frozen=True)
class Product:
    de: str
    en: str
    min_price: Decimal
    max_price: Decimal
    vat_rate: Decimal
    max_qty: int = 1


@dataclass(frozen=True)
class Vendor:
    name: str
    street: str
    city: str
    country: str  # ISO code
    language: str  # language the vendor writes invoices in
    currency: Currency
    category: Category
    products: tuple[Product, ...]
    kind: str = "invoice"  # "invoice" (payment term, IBAN) or "receipt" (paid on the spot)
    payment_days: int = 14
    layouts: tuple[str, ...] = ("din_letter", "modern", "minimal")
    reverse_charge: bool = False  # foreign B2B service: no German VAT on the invoice
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def address(self) -> str:
        return f"{self.street}, {self.city}"


def _p(de: str, en: str, lo: str, hi: str, rate: Decimal = R19, max_qty: int = 1) -> Product:
    return Product(de, en, Decimal(lo), Decimal(hi), rate, max_qty)


VENDORS: tuple[Vendor, ...] = (
    Vendor(
        "Nordlicht Software GmbH",
        "Hafenstraße 21",
        "20457 Hamburg",
        "DE",
        "de",
        Currency.EUR,
        Category.SOFTWARE,
        (
            _p(
                "Lizenz Projektmanagement-Suite (Monat)",
                "Project suite licence (month)",
                "19",
                "89",
                max_qty=5,
            ),
            _p("Zusatzmodul Zeiterfassung", "Time tracking add-on", "9", "29", max_qty=5),
            _p("Premium-Support (Monat)", "Premium support (month)", "49", "149"),
        ),
    ),
    Vendor(
        "Wolkenwerk Hosting GmbH",
        "Speicherweg 4",
        "90402 Nürnberg",
        "DE",
        "de",
        Currency.EUR,
        Category.HOSTING,
        (
            _p("Cloud-Server CX31 (Monat)", "Cloud server CX31 (month)", "12", "45", max_qty=3),
            _p("Backup-Speicher 500 GB", "Backup storage 500 GB", "4", "15"),
            _p("Domain .de (Jahr)", "Domain .de (year)", "8", "15", max_qty=3),
            _p("Managed Datenbank (Monat)", "Managed database (month)", "25", "90"),
        ),
    ),
    Vendor(
        "TeleNetz Kommunikation AG",
        "Funkturmallee 7",
        "40210 Düsseldorf",
        "DE",
        "de",
        Currency.EUR,
        Category.TELECOM,
        (
            _p("Mobilfunk Business L (Monat)", "Mobile Business L (month)", "25", "60"),
            _p("Glasfaser 500 Mbit/s (Monat)", "Fibre 500 Mbit/s (month)", "39", "79"),
        ),
        payment_days=30,
    ),
    Vendor(
        "Papierkram Bürobedarf GmbH",
        "Industriestraße 88",
        "50735 Köln",
        "DE",
        "de",
        Currency.EUR,
        Category.OFFICE,
        (
            _p("Kopierpapier A4, 500 Blatt", "Copy paper A4, 500 sheets", "4.5", "7.9", max_qty=10),
            _p("Toner schwarz", "Black toner", "39", "89", max_qty=2),
            _p("Ordner breit, 10 Stk.", "Lever arch files, 10 pcs", "14", "24", max_qty=3),
            _p("Haftnotizen, 12 Blöcke", "Sticky notes, 12 pads", "6", "12", max_qty=4),
        ),
        layouts=("din_letter", "minimal"),
    ),
    Vendor(
        "Technikhaus Becker KG",
        "Elektronring 3",
        "80335 München",
        "DE",
        "de",
        Currency.EUR,
        Category.HARDWARE,
        (
            _p('Notebook 14" 16 GB RAM', 'Laptop 14" 16 GB RAM', "899", "1899"),
            _p('Monitor 27" 4K', 'Monitor 27" 4K', "249", "549", max_qty=2),
            _p("USB-C Dockingstation", "USB-C docking station", "89", "229"),
            _p("Funktastatur und Maus", "Wireless keyboard and mouse", "39", "99"),
        ),
    ),
    Vendor(
        "Rheinblick Hotel GmbH",
        "Uferpromenade 12",
        "53111 Bonn",
        "DE",
        "de",
        Currency.EUR,
        Category.TRAVEL,
        (
            _p("Übernachtung Einzelzimmer", "Single room, one night", "89", "149", R7, max_qty=3),
            _p("Frühstück", "Breakfast", "14", "22", R19, max_qty=3),
        ),
        kind="receipt",
        layouts=("din_letter", "receipt"),
    ),
    Vendor(
        "Stadtflitzer Taxi e.K.",
        "Bahnhofsplatz 1",
        "60329 Frankfurt am Main",
        "DE",
        "de",
        Currency.EUR,
        Category.TRAVEL,
        (_p("Taxifahrt Nahverkehr", "Taxi ride (local)", "11", "38", R7),),
        kind="receipt",
        layouts=("receipt",),
    ),
    Vendor(
        "Schienenweg Fernverkehr AG",
        "Gleisstraße 100",
        "10557 Berlin",
        "DE",
        "de",
        Currency.EUR,
        Category.TRAVEL,
        (_p("Fahrkarte Fernverkehr 2. Klasse", "Long-distance train ticket, 2nd class", "29", "139", R7),),
        kind="receipt",
        layouts=("minimal", "receipt"),
    ),
    Vendor(
        "Café Morgenrot",
        "Lindenstraße 5",
        "04109 Leipzig",
        "DE",
        "de",
        Currency.EUR,
        Category.MEALS,
        (
            _p("Mittagstisch", "Lunch special", "9.5", "16.9", R7, max_qty=4),
            _p("Kaffee / Getränke", "Coffee / drinks", "2.8", "5.5", R19, max_qty=4),
        ),
        kind="receipt",
        layouts=("receipt",),
    ),
    Vendor(
        "Buchhandlung Seitenwind",
        "Marktgasse 9",
        "79098 Freiburg",
        "DE",
        "de",
        Currency.EUR,
        Category.BOOKS,
        (
            _p("Fachbuch Steuerrecht", "Tax law handbook", "29", "69", R7),
            _p("Fachbuch Softwarearchitektur", "Software architecture book", "35", "59", R7),
        ),
        kind="receipt",
        layouts=("receipt", "minimal"),
    ),
    Vendor(
        "Pixelhafen Design Studio",
        "Kreativkai 2",
        "28195 Bremen",
        "DE",
        "de",
        Currency.EUR,
        Category.MARKETING,
        (
            _p("Gestaltung Social-Media-Grafiken", "Social media graphics design", "180", "480"),
            _p("Logo-Überarbeitung", "Logo refresh", "350", "900"),
        ),
        payment_days=30,
    ),
    Vendor(
        "Kanzlei Hartmann & Vogel",
        "Justizplatz 4",
        "70173 Stuttgart",
        "DE",
        "de",
        Currency.EUR,
        Category.PROFESSIONAL_SERVICES,
        (
            _p(
                "Rechtsberatung Vertragsprüfung (Std.)",
                "Legal advice, contract review (hour)",
                "180",
                "260",
                max_qty=3,
            ),
        ),
        payment_days=30,
        layouts=("din_letter",),
    ),
    # English-language vendors
    Vendor(
        "Brightloop Analytics GmbH",
        "Torstraße 140",
        "10119 Berlin",
        "DE",
        "en",
        Currency.EUR,
        Category.SOFTWARE,
        (
            _p("Analytics Pro plan (month)", "Analytics Pro plan (month)", "29", "99"),
            _p("Additional seats", "Additional seats", "8", "15", max_qty=5),
        ),
        layouts=("modern",),
    ),
    Vendor(
        "Cloudspan Inc.",
        "500 Market Street",
        "San Francisco, CA 94105",
        "US",
        "en",
        Currency.USD,
        Category.HOSTING,
        (
            _p("Compute instances (usage)", "Compute instances (usage)", "20", "180"),
            _p("Object storage (usage)", "Object storage (usage)", "2", "30"),
        ),
        layouts=("modern",),
        reverse_charge=True,
        payment_days=0,
    ),
    Vendor(
        "Quillwright Ltd",
        "22 Clerkenwell Road",
        "London EC1M 5RN",
        "GB",
        "en",
        Currency.GBP,
        Category.SOFTWARE,
        (
            _p(
                "Writing assistant, Team plan (month)",
                "Writing assistant, Team plan (month)",
                "15",
                "60",
                R19,
                max_qty=4,
            ),
        ),
        layouts=("modern", "minimal"),
        reverse_charge=True,
        payment_days=0,
    ),
    Vendor(
        "Alpenroute Consulting AG",
        "Bahnhofstrasse 30",
        "8001 Zürich",
        "CH",
        "en",
        Currency.CHF,
        Category.PROFESSIONAL_SERVICES,
        (_p("Workshop facilitation (day)", "Workshop facilitation (day)", "900", "1600"),),
        layouts=("din_letter",),
        reverse_charge=True,
        payment_days=30,
    ),
)

KNOWN_VENDORS = tuple(v for v in VENDORS if v.currency == Currency.EUR)
FOREIGN_VENDORS = tuple(v for v in VENDORS if v.currency != Currency.EUR)

# Fictional vendors that are *not* in the vendor master (unknown_vendor scenario)
UNKNOWN_VENDORS: tuple[Vendor, ...] = (
    Vendor(
        "Fuchsbau Webagentur UG",
        "Am Anger 17",
        "99084 Erfurt",
        "DE",
        "de",
        Currency.EUR,
        Category.MARKETING,
        (_p("Landingpage-Optimierung", "Landing page optimisation", "120", "240"),),
    ),
    Vendor(
        "Datenquelle Systemhaus GmbH",
        "Rechenzentrumstr. 9",
        "01067 Dresden",
        "DE",
        "de",
        Currency.EUR,
        Category.HOSTING,
        (_p("Server-Wartung (Monat)", "Server maintenance (month)", "60", "180"),),
    ),
    Vendor(
        "Lumen Desk Ltd",
        "8 Harbour Way",
        "Bristol BS1 5TY",
        "GB",
        "en",
        Currency.EUR,
        Category.SOFTWARE,
        (_p("Helpdesk Starter (month)", "Helpdesk Starter (month)", "19", "49"),),
        layouts=("modern",),
    ),
)

# The invoice recipient: our own (fictional) small business.
RECIPIENT = ("Freiraum Studio UG (haftungsbeschränkt)", "Musterstraße 12", "10115 Berlin")
