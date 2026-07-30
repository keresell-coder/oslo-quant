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
    sector: str = ""                     # sector label for context and model caveats
    notes: str = ""                      # free-text notes surfaced in the dashboard


# Reporting currencies verified against official annual reports.
# Price currency for all .OL tickers is NOK (Oslo Børs).
COMPANIES: list[CompanyConfig] = [
    CompanyConfig("DOFG.OL",  reporting_currency="USD", full_name="DOF Group ASA",
                  sector="Offshore / Marine Services"),
    CompanyConfig("BRG.OL",   reporting_currency="NOK", full_name="Borregaard ASA",
                  sector="Specialty Chemicals / Biorefinery"),
    CompanyConfig("ODL.OL",   reporting_currency="USD", full_name="Odfjell Drilling Ltd",
                  sector="Offshore Drilling",
                  notes="Operates harsh-environment semi-submersibles and drillships in the North Sea and internationally. Not a jack-up driller (jack-ups = BORR.OL)."),
    CompanyConfig("ELK.OL",   reporting_currency="NOK", full_name="Elkem ASA",
                  sector="Silicon & Specialty Chemicals"),
    CompanyConfig("NOD.OL",   reporting_currency="USD", full_name="Nordic Semiconductor ASA",
                  sector="Semiconductors"),
    CompanyConfig("VEND.OL",  reporting_currency="NOK", full_name="Vend Marketplaces ASA",
                  sector="Media / Online Classifieds",
                  notes="Online classifieds and marketplaces business carved out from Schibsted ASA and separately listed on Oslo Børs in May 2025. Operates major Nordic classified platforms."),
    CompanyConfig("PUBLI.OL", reporting_currency="NOK", full_name="Public Property Invest ASA",
                  sector="Real Estate",
                  notes="Redomiciling to Sweden; primary listing on Nasdaq Stockholm from May 2026, secondary listing on Oslo Børs continues."),
    CompanyConfig("MOWI.OL",  reporting_currency="EUR", full_name="Mowi ASA",
                  sector="Aquaculture / Salmon Farming",
                  notes="Biological assets carried at IAS 41 fair value — unrealised fair-value movements flow through EBIT, creating non-cash earnings volatility that inflates Altman/Ohlson distress signals."),
    CompanyConfig("TEL.OL",   reporting_currency="NOK", full_name="Telenor ASA",
                  sector="Telecommunications"),
    CompanyConfig("KOG.OL",   reporting_currency="NOK", full_name="Kongsberg Gruppen ASA",
                  sector="Defence / Technology"),
    CompanyConfig("KMAR.OL",  reporting_currency="NOK", full_name="Kongsberg Maritime ASA",
                  sector="Maritime Technology",
                  notes="Carved out from Kongsberg Gruppen (KOG.OL) and listed separately on 23 April 2026. All framework scores are based on limited standalone history; multi-year comparisons and year-on-year signals are not yet meaningful."),
    CompanyConfig("BORR.OL",  reporting_currency="USD", full_name="Borr Drilling Ltd",
                  sector="Offshore Drilling", alt_ticker="BORR"),
    CompanyConfig("FRO.OL",   reporting_currency="USD", full_name="Frontline plc",
                  sector="Crude Oil Tankers"),
    CompanyConfig("HAFNI.OL", reporting_currency="USD", full_name="Hafnia Ltd",
                  sector="Product Tankers"),
    CompanyConfig("NORBT.OL", reporting_currency="NOK", full_name="Norbit ASA",
                  alt_ticker="NORBT",
                  sector="Technology / Sensing & Connectivity",
                  notes="Develops multibeam sonar, underwater imaging, and telematics/IoT products. Operates three segments: Oceans (sonar/sensors), Connectivity (cable/telematics), and Product Innovation. Listed June 2019, headquartered in Trondheim."),
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
