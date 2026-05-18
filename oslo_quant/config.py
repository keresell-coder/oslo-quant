"""Central configuration: tickers, paths, environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_RESULTS = ROOT / "data" / "results"

DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_RESULTS.mkdir(parents=True, exist_ok=True)

FMP_API_KEY: str | None = os.getenv("FMP_API_KEY") or None


@dataclass
class CompanyConfig:
    ticker: str
    alt_ticker: str | None = None        # ticker without exchange suffix for FMP
    reporting_currency: str = "NOK"      # currency used in financial statements
    full_name: str = ""                  # human-readable company name


# Reporting currencies verified against official 2024 annual reports.
# Price currency for all .OL tickers is NOK (Oslo Børs).
COMPANIES: list[CompanyConfig] = [
    CompanyConfig("DOFG.OL",  reporting_currency="USD", full_name="DOF Group ASA"),
    CompanyConfig("BRG.OL",   reporting_currency="NOK", full_name="Borregaard ASA"),
    CompanyConfig("ODL.OL",   reporting_currency="USD", full_name="Odfjell SE"),
    CompanyConfig("ELK.OL",   reporting_currency="NOK", full_name="Elkem ASA"),
    CompanyConfig("NOD.OL",   reporting_currency="USD", full_name="Nordic Semiconductor ASA"),
    CompanyConfig("VEND.OL",  reporting_currency="NOK", full_name="Vend Marketplaces ASA"),
    CompanyConfig("PUBLI.OL", reporting_currency="NOK", full_name="Public Property Invest ASA"),
    CompanyConfig("MOWI.OL",  reporting_currency="EUR", full_name="Mowi ASA"),
    CompanyConfig("TEL.OL",   reporting_currency="NOK", full_name="Telenor ASA"),
    CompanyConfig("KOG.OL",   reporting_currency="NOK", full_name="Kongsberg Gruppen ASA"),
    CompanyConfig("KMAR.OL",  reporting_currency="NOK", full_name="Kongsberg Maritime ASA"),
    CompanyConfig("BORR.OL",  reporting_currency="USD", full_name="Borr Drilling Ltd",
                  alt_ticker="BORR"),
    CompanyConfig("FRO.OL",   reporting_currency="USD", full_name="Frontline plc"),
    CompanyConfig("HAFNI.OL", reporting_currency="USD", full_name="Hafnia Ltd"),
]

TICKER_MAP: dict[str, CompanyConfig] = {c.ticker: c for c in COMPANIES}

ALL_FRAMEWORKS = ["dupont", "piotroski", "sloan", "ohlson", "altman"]

# Parquet filenames stored under data/raw/{TICKER}/
RAW_FILES = {
    "balance_sheet": "balance_sheet.parquet",
    "income_stmt":   "income_stmt.parquet",
    "cash_flow":     "cash_flow.parquet",
    "prices":        "prices.parquet",
}
