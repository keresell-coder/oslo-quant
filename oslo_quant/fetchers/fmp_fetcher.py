"""Optional FMP (Financial Modeling Prep) fetcher — supplemental layer."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from oslo_quant.config import FMP_API_KEY
from oslo_quant.fetchers.base import BaseFetcher, Statements

log = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"


class NotConfiguredError(RuntimeError):
    """Raised when FMP_API_KEY is not set."""


class FmpFetcher(BaseFetcher):
    def __init__(self) -> None:
        if not FMP_API_KEY:
            raise NotConfiguredError("FMP_API_KEY not set — FMP fetcher disabled")
        self._key = FMP_API_KEY

    def fetch(self, ticker: str, force_refresh: bool = False) -> Statements:
        # FMP uses bare ticker for US-listed names; .OL suffix works for Norwegian stocks
        # but some tickers may need the alt_ticker override (handled in pipeline)
        log.info("[%s] Fetching supplemental data from FMP", ticker)
        return {
            "balance_sheet": self._statement(ticker, "balance-sheet-statement"),
            "income_stmt": self._statement(ticker, "income-statement"),
            "cash_flow": self._statement(ticker, "cash-flow-statement"),
            "prices": pd.DataFrame(),  # prices come from yfinance; FMP is statement-only
        }

    # ------------------------------------------------------------------
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict]:
        url = f"{FMP_BASE}/{endpoint}"
        p = {"apikey": self._key, "limit": 10, **(params or {})}
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            log.warning("FMP error: %s", data["Error Message"])
            return []
        return data if isinstance(data, list) else []

    def _statement(self, ticker: str, endpoint: str) -> pd.DataFrame:
        rows = self._get(f"{endpoint}/{ticker}")
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if "date" not in df.columns:
            return pd.DataFrame()
        df["period"] = pd.to_datetime(df["date"]).dt.year.astype(str)
        df = df.set_index("period").T
        # Drop metadata rows that are not numeric
        df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
        return df
