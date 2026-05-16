"""Central configuration: tickers, paths, environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    alt_ticker: str | None = None  # ticker without exchange suffix for FMP


COMPANIES: list[CompanyConfig] = [
    CompanyConfig("DOFG.OL"),
    CompanyConfig("BRG.OL"),
    CompanyConfig("ODL.OL"),
    CompanyConfig("ELK.OL"),
    CompanyConfig("NOD.OL"),
    CompanyConfig("VEND.OL"),
    CompanyConfig("PUBLI.OL"),
    CompanyConfig("MOWI.OL"),
    CompanyConfig("TEL.OL"),
    CompanyConfig("KOG.OL"),
    CompanyConfig("KMAR.OL"),
    CompanyConfig("BORR.OL", alt_ticker="BORR"),
    CompanyConfig("FRO.OL"),
    CompanyConfig("HAFNI.OL"),
]

TICKER_MAP: dict[str, CompanyConfig] = {c.ticker: c for c in COMPANIES}

ALL_FRAMEWORKS = ["dupont", "piotroski", "sloan", "ohlson", "altman"]

# Parquet filenames stored under data/raw/{TICKER}/
RAW_FILES = {
    "balance_sheet": "balance_sheet.parquet",
    "income_stmt": "income_stmt.parquet",
    "cash_flow": "cash_flow.parquet",
    "prices": "prices.parquet",
}
