"""yfinance-based fetcher — primary data source."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

from oslo_quant.config import DATA_RAW, RAW_FILES
from oslo_quant.fetchers.base import BaseFetcher, Statements

log = logging.getLogger(__name__)


class YFinanceFetcher(BaseFetcher):
    def fetch(self, ticker: str, force_refresh: bool = False) -> Statements:
        cache_dir = DATA_RAW / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)

        if not force_refresh and self._cache_complete(cache_dir):
            log.info("[%s] Loading from cache", ticker)
            return self._load_cache(cache_dir)

        log.info("[%s] Fetching from yfinance", ticker)
        tk = yf.Ticker(ticker)

        stmts: Statements = {
            "balance_sheet": self._annual(tk.balance_sheet),
            "income_stmt": self._annual(tk.income_stmt),
            "cash_flow": self._annual(tk.cashflow),
            "prices": self._prices(tk),
        }

        self._save_cache(cache_dir, stmts)
        return stmts

    # ------------------------------------------------------------------
    def _annual(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        # yfinance returns columns as Timestamps — convert to year strings
        df = df.copy()
        df.columns = [str(c.year) if hasattr(c, "year") else str(c) for c in df.columns]
        return df

    def _prices(self, tk: yf.Ticker) -> pd.DataFrame:
        hist = tk.history(period="5y", auto_adjust=True)
        if hist is None or hist.empty:
            return pd.DataFrame()
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]]

    def _cache_complete(self, cache_dir: Path) -> bool:
        return all((cache_dir / fname).exists() for fname in RAW_FILES.values())

    def _load_cache(self, cache_dir: Path) -> Statements:
        return {
            key: pd.read_parquet(cache_dir / fname)
            for key, fname in RAW_FILES.items()
        }  # type: ignore[return-value]

    def _save_cache(self, cache_dir: Path, stmts: Statements) -> None:
        for key, fname in RAW_FILES.items():
            df: pd.DataFrame = stmts[key]  # type: ignore[assignment]
            if not df.empty:
                df.to_parquet(cache_dir / fname)
