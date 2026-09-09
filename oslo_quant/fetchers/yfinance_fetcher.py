"""yfinance-based fetcher — primary data source."""

from __future__ import annotations

import json
import logging
import hashlib
from pathlib import Path

import pandas as pd
import yfinance as yf

from oslo_quant.config import DATA_RAW, RAW_FILES
from oslo_quant.fetchers.base import BaseFetcher, Statements
from oslo_quant.trust import recent, stamp, period_ends

log = logging.getLogger(__name__)

METADATA_FILE = "metadata.json"


class YFinanceFetcher(BaseFetcher):
    def __init__(self):
        self.provenance: dict[str, dict] = {}

    def _metadata(self, cache_dir, group):
        try:
            return json.loads((cache_dir / f"{group}_source.json").read_text())
        except (OSError, ValueError):
            return {}

    def _record(self, ticker, cache_dir, group, frames):
        files = RAW_FILES if group == "annual" else self._Q_FILES
        meta = {
            "source_fetched_at": stamp(),
            "statement_period_ends": {k: period_ends(v) for k, v in frames.items()
                                      if k != "prices"},
            "cache_hashes": {name: hashlib.sha256((cache_dir / name).read_bytes()).hexdigest()
                             for name in files.values()},
        }
        (cache_dir / f"{group}_source.json").write_text(json.dumps(meta, indent=2))
        self.provenance.setdefault(ticker, {})[group] = {**meta, "cache_used": False}

    def _cache_valid(self, cache_dir, group, files):
        meta = self._metadata(cache_dir, group)
        if not recent(meta.get("source_fetched_at")):
            return False
        try:
            return all(meta.get("cache_hashes", {}).get(name) ==
                       hashlib.sha256((cache_dir / name).read_bytes()).hexdigest()
                       for name in files.values())
        except OSError:
            return False

    def fetch(self, ticker: str, force_refresh: bool = False) -> Statements:
        cache_dir = DATA_RAW / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)

        if not force_refresh and self._cache_complete(cache_dir):
            log.info("[%s] Loading from cache", ticker)
            self.provenance.setdefault(ticker, {})["annual"] = {
                **self._metadata(cache_dir, "annual"), "cache_used": True}
            return self._load_cache(cache_dir)

        log.info("[%s] Fetching from yfinance", ticker)
        tk = yf.Ticker(ticker)

        frames = {"balance_sheet": tk.balance_sheet,
                  "income_stmt": tk.income_stmt, "cash_flow": tk.cashflow}
        stmts: Statements = {
            **{key: self._annual(frame) for key, frame in frames.items()},
            "prices":        self._prices(tk),
        }

        # Detect and cache currency metadata while we have the Ticker object
        self._detect_and_cache_currency(tk, ticker, cache_dir, True)

        self._save_cache(cache_dir, stmts)
        self._record(ticker, cache_dir, "annual", frames)
        return stmts

    # Quarterly statements, cached separately from the annual files.
    # Columns keep their full period-end date ("2026-06-30") because LTM
    # construction needs to check window contiguity, not just the year.
    _Q_FILES = {
        "balance_sheet": "quarterly_balance_sheet.parquet",
        "income_stmt":   "quarterly_income_stmt.parquet",
        "cash_flow":     "quarterly_cash_flow.parquet",
    }

    def fetch_quarterly(self, ticker: str, force_refresh: bool = False) -> dict:
        """Return quarterly balance_sheet / income_stmt / cash_flow DataFrames."""
        cache_dir = DATA_RAW / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)

        if not force_refresh and self._cache_valid(cache_dir, "quarterly", self._Q_FILES):
            self.provenance.setdefault(ticker, {})["quarterly"] = {
                **self._metadata(cache_dir, "quarterly"), "cache_used": True}
            return {
                key: pd.read_parquet(cache_dir / fname)
                for key, fname in self._Q_FILES.items()
            }

        log.info("[%s] Fetching quarterly statements from yfinance", ticker)
        tk = yf.Ticker(ticker)
        out = {
            "balance_sheet": self._q_normalize(tk.quarterly_balance_sheet),
            "income_stmt":   self._q_normalize(tk.quarterly_income_stmt),
            "cash_flow":     self._q_normalize(tk.quarterly_cashflow),
        }
        for key, fname in self._Q_FILES.items():
            out[key].to_parquet(cache_dir / fname)
        self._record(ticker, cache_dir, "quarterly", out)
        return out

    def _q_normalize(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.columns = [
            c.date().isoformat() if hasattr(c, "date") else str(c)[:10]
            for c in df.columns
        ]
        return df

    def fetch_fx_rate(self, from_ccy: str, to_ccy: str) -> float | None:
        """Return most-recent closing rate: 1 *from_ccy* = ? *to_ccy*.

        Uses yfinance FX pairs (e.g. NOKUSD=X for NOK→USD).
        Returns None if the rate cannot be fetched.
        """
        if from_ccy == to_ccy:
            return 1.0
        fx_symbol = f"{from_ccy}{to_ccy}=X"
        try:
            hist = yf.Ticker(fx_symbol).history(period="5d", auto_adjust=True)
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            log.warning("FX rate fetch failed (%s→%s): %s", from_ccy, to_ccy, exc)
        return None

    def fetch_currency_info(self, ticker: str, force_refresh: bool = False) -> dict:
        """Return currency metadata for *ticker*.

        Returns a dict with:
            price_currency      — currency of the Oslo Børs share price (always NOK for .OL)
            financial_currency  — currency used in the financial statements
            source              — "yfinance" | "fallback"
        """
        cache_dir = DATA_RAW / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)
        meta_path = cache_dir / METADATA_FILE

        if not force_refresh and meta_path.exists():
            try:
                return json.loads(meta_path.read_text())
            except Exception:
                pass

        tk = yf.Ticker(ticker)
        return self._detect_and_cache_currency(tk, ticker, cache_dir, force_refresh)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_and_cache_currency(
        self, tk: yf.Ticker, ticker: str, cache_dir: Path, force_refresh: bool
    ) -> dict:
        meta_path = cache_dir / METADATA_FILE
        if not force_refresh and meta_path.exists():
            try:
                return json.loads(meta_path.read_text())
            except Exception:
                pass

        result: dict = {
            "price_currency":     "NOK",
            "financial_currency": "Unknown",
            "source":             "fallback",
        }
        try:
            info = tk.info or {}
            price_ccy = info.get("currency") or "NOK"
            fin_ccy   = info.get("financialCurrency") or info.get("currency") or "Unknown"
            result = {
                "price_currency":     price_ccy,
                "financial_currency": fin_ccy,
                "source":             "yfinance",
            }
            log.info("[%s] Currency: price=%s  statements=%s", ticker, price_ccy, fin_ccy)
        except Exception as exc:
            log.warning("[%s] Currency detection failed — using fallback: %s", ticker, exc)

        try:
            meta_path.write_text(json.dumps(result, indent=2))
        except Exception:
            pass
        return result

    def _annual(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
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
        return self._cache_valid(cache_dir, "annual", RAW_FILES)

    def _load_cache(self, cache_dir: Path) -> Statements:
        return {
            key: pd.read_parquet(cache_dir / fname)
            for key, fname in RAW_FILES.items()
        }  # type: ignore[return-value]

    def _save_cache(self, cache_dir: Path, stmts: Statements) -> None:
        for key, fname in RAW_FILES.items():
            df: pd.DataFrame = stmts[key]  # type: ignore[assignment]
            df.to_parquet(cache_dir / fname)
