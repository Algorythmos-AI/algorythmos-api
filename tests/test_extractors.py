from __future__ import annotations

from pathlib import Path

import pytest

from pdf_usage_extractor.extractors.orange import OrangeExtractor
from pdf_usage_extractor.logging_utils import get_logger

TEST_PATH = Path("tests/resources/sample.pdf")


def _extract(text: str):
    extractor = OrangeExtractor()
    logger = get_logger(debug=True)
    return extractor.extract(path=TEST_PATH, text=text, debug=True, logger=logger)


def test_orange_extractor_filters_allowance_noise() -> None:
    text = (
        "Orange Facture\n"
        "Connexion internet France métropolitaine\n"
        "Volume consommé\n"
        "50 Go\n"
        "Votre offre 170 Go en EU\n"
        "Date de facture : 06/09/25\n"
        "Période du 02.09.2025 au 01.10.2025\n"
    )
    record = _extract(text)
    assert record is not None
    assert record.internet_gb == 50


def test_orange_extractor_negative_lookahead_skips_allowances() -> None:
    text = (
        "Orange Facture\n"
        "Connexion internet France métropolitaine\n"
        "Données utilisées : 88,2 Mo\n"
        "Détails et conditions : 170 Go en EU\n"
        "10 Mo en EU/DOM\n"
        "Date de facture : 08/09/25\n"
        "Période du 02.09.2025 au 01.10.2025\n"
    )
    record = _extract(text)
    assert record is not None
    assert pytest.approx(record.internet_gb, rel=0.01) == 0.086  # 88.2 Mo -> 0.086 GB


def test_orange_extractor_supports_unicode_normalisation() -> None:
    text = (
        "Orange\n"
        "Connexion internet France métropolitaine\n"
        "Utilisation\u00a0: 81,6 Go\n"
        "Date de facture : 07/07/25\n"
        "Période du 02.07.2025 au 01.08.2025\n"
    )
    record = _extract(text)
    assert record is not None
    assert record.internet_gb == 81.6


def test_orange_extractor_invoice_date_formats() -> None:
    text_alt = (
        "Orange\n"
        "Connexion internet France métropolitaine\n"
        "Internet consommé : 99 Go\n"
        "Votre facture mobile du 08.09.2025\n"
        "Période du 02.09.2025 au 01.10.2025\n"
    )
    record_alt = _extract(text_alt)
    assert record_alt is not None
    assert str(record_alt.invoice_date) == "2025-09-08"

    text_primary = (
        "Orange\n"
        "Connexion internet France métropolitaine\n"
        "Internet consommé : 41,4 Go\n"
        "Date de facture : 06/06/25\n"
        "Période du 02.05.2025 au 01.06.2025\n"
    )
    record_primary = _extract(text_primary)
    assert record_primary is not None
    assert str(record_primary.invoice_date) == "2025-06-06"
