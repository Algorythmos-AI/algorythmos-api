"""Synthetic telecom invoices for extractor tests.

Every value here is fictional. The PDFs are generated at test time with
PyMuPDF (already a runtime dependency) so no real customer document is ever
committed. The text mirrors the phrases the Orange extractor looks for
(``pdf_usage_extractor/extractors/orange.py``): the provider name, the
invoice date, the billing period and a "Connexion Internet France
métropolitaine" usage line.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import fitz  # type: ignore[import-untyped]


@dataclass(frozen=True)
class SyntheticInvoice:
    filename: str
    invoice_date: dt.date
    period_start: dt.date
    period_end: dt.date
    internet_gb: float


SYNTHETIC_INVOICES: tuple[SyntheticInvoice, ...] = (
    SyntheticInvoice("synthetic_orange_invoice_01.pdf", dt.date(2030, 1, 6), dt.date(2030, 1, 2), dt.date(2030, 2, 1), 12.5),
    SyntheticInvoice("synthetic_orange_invoice_02.pdf", dt.date(2030, 2, 6), dt.date(2030, 2, 2), dt.date(2030, 3, 1), 23.75),
    SyntheticInvoice("synthetic_orange_invoice_03.pdf", dt.date(2030, 3, 6), dt.date(2030, 3, 2), dt.date(2030, 4, 1), 34.0),
    SyntheticInvoice("synthetic_orange_invoice_04.pdf", dt.date(2030, 4, 6), dt.date(2030, 4, 2), dt.date(2030, 5, 1), 45.25),
    SyntheticInvoice("synthetic_orange_invoice_05.pdf", dt.date(2030, 5, 6), dt.date(2030, 5, 2), dt.date(2030, 6, 1), 56.5),
)


def _invoice_text(invoice: SyntheticInvoice) -> str:
    usage = f"{invoice.internet_gb:g}".replace(".", ",")
    return "\n".join(
        [
            "Orange",
            "Votre facture - document de test synthétique",
            f"Date de facture : {invoice.invoice_date:%d/%m/%y}",
            "Client : TEST-0000000000",
            f"Période du {invoice.period_start:%d.%m.%Y} au {invoice.period_end:%d.%m.%Y}",
            "Détail de vos consommations",
            "Connexion Internet France métropolitaine",
            f"{usage} Go",
        ]
    )


def write_synthetic_invoices(dest: Path) -> list[SyntheticInvoice]:
    """Write the synthetic invoice PDFs into ``dest`` and return their expected values."""
    dest.mkdir(parents=True, exist_ok=True)
    for invoice in SYNTHETIC_INVOICES:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), _invoice_text(invoice), fontsize=11)
        doc.save(dest / invoice.filename)
        doc.close()
    return list(SYNTHETIC_INVOICES)
