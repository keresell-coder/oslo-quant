"""Tests for config module."""

from oslo_quant.config import COMPANIES, TICKER_MAP, ALL_FRAMEWORKS


def test_company_count():
    assert len(COMPANIES) == 14


def test_all_tickers_in_map():
    for company in COMPANIES:
        assert company.ticker in TICKER_MAP


def test_borr_has_alt_ticker():
    borr = TICKER_MAP["BORR.OL"]
    assert borr.alt_ticker == "BORR"


def test_all_frameworks_list():
    assert set(ALL_FRAMEWORKS) == {"dupont", "piotroski", "sloan", "ohlson", "altman"}


def test_expected_tickers():
    expected = {
        "DOFG.OL", "BRG.OL", "ODL.OL", "ELK.OL", "NOD.OL", "VEND.OL",
        "PUBLI.OL", "MOWI.OL", "TEL.OL", "KOG.OL", "KMAR.OL", "BORR.OL",
        "FRO.OL", "HAFNI.OL",
    }
    assert set(TICKER_MAP.keys()) == expected
