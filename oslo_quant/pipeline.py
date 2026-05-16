"""Orchestration pipeline: fetch → compute → persist."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from oslo_quant.config import (
    TICKER_MAP,
    ALL_FRAMEWORKS,
    DATA_RESULTS,
    FMP_API_KEY,
    COMPANIES,
)
from oslo_quant.fetchers.base import Statements
from oslo_quant.fetchers.yfinance_fetcher import YFinanceFetcher
from oslo_quant.frameworks import FRAMEWORK_REGISTRY

log = logging.getLogger(__name__)


def run(
    tickers: list[str] | None = None,
    frameworks: list[str] | None = None,
    force_refresh: bool = False,
    period: str = "annual",
) -> dict[str, Any]:
    """Run the pre-computation pipeline.

    Args:
        tickers: List of ticker strings, or None for all 14 companies.
        frameworks: List of framework names, or None for all five.
        force_refresh: Re-fetch from APIs even if cache exists.
        period: "annual", "ttm", or "both" (reserved for future TTM support).

    Returns:
        Nested dict ``{ticker: {framework: result_dict}}``.
    """
    target_tickers = tickers or [c.ticker for c in COMPANIES]
    target_frameworks = frameworks or ALL_FRAMEWORKS

    _validate_tickers(target_tickers)
    _validate_frameworks(target_frameworks)

    yf_fetcher = YFinanceFetcher()
    fmp_fetcher = _init_fmp()

    summary: dict[str, Any] = {}

    for ticker in target_tickers:
        log.info("=== Processing %s ===", ticker)
        company = TICKER_MAP[ticker]

        # --- Fetch ---
        try:
            stmts = yf_fetcher.fetch(ticker, force_refresh=force_refresh)
        except Exception as exc:
            log.error("[%s] yfinance fetch failed: %s", ticker, exc)
            summary[ticker] = {"error": str(exc)}
            continue

        if fmp_fetcher is not None:
            fmp_ticker = company.alt_ticker or ticker
            try:
                fmp_stmts = fmp_fetcher.fetch(fmp_ticker, force_refresh=force_refresh)
                stmts = _merge_statements(stmts, fmp_stmts)
            except Exception as exc:
                log.warning("[%s] FMP supplemental fetch failed (skipped): %s", ticker, exc)

        # --- Compute ---
        ticker_results: dict[str, Any] = {}
        for fw_name in target_frameworks:
            framework_cls = FRAMEWORK_REGISTRY[fw_name]
            framework = framework_cls()
            try:
                result = framework.compute(stmts, ticker)
                ticker_results[fw_name] = result
                _persist(ticker, fw_name, result)
                log.info("[%s] %s — OK (%d periods)", ticker, fw_name, len(result.get("periods", {})))
            except Exception as exc:
                log.error("[%s] %s failed: %s", ticker, fw_name, exc)
                ticker_results[fw_name] = {"error": str(exc)}

        summary[ticker] = ticker_results

    return summary


# ---------------------------------------------------------------------------

def _validate_tickers(tickers: list[str]) -> None:
    unknown = [t for t in tickers if t not in TICKER_MAP]
    if unknown:
        raise ValueError(f"Unknown tickers: {unknown}. Valid: {list(TICKER_MAP.keys())}")


def _validate_frameworks(fws: list[str]) -> None:
    unknown = [f for f in fws if f not in FRAMEWORK_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown frameworks: {unknown}. Valid: {ALL_FRAMEWORKS}")


def _init_fmp():
    if not FMP_API_KEY:
        return None
    try:
        from oslo_quant.fetchers.fmp_fetcher import FmpFetcher
        return FmpFetcher()
    except Exception as exc:
        log.warning("FMP fetcher init failed: %s", exc)
        return None


def _merge_statements(primary: Statements, supplemental: Statements) -> Statements:
    """Fill gaps in *primary* from *supplemental* — primary wins on overlapping columns."""
    import pandas as pd

    merged: Statements = dict(primary)  # type: ignore[assignment]
    for key in ("balance_sheet", "income_stmt", "cash_flow"):
        p: pd.DataFrame = primary[key]  # type: ignore[assignment]
        s: pd.DataFrame = supplemental[key]  # type: ignore[assignment]
        if s is None or s.empty:
            continue
        if p is None or p.empty:
            merged[key] = s  # type: ignore[assignment]
            continue
        # Add columns from supplemental that are missing in primary
        extra_cols = [c for c in s.columns if c not in p.columns]
        if extra_cols:
            merged[key] = pd.concat([p, s[extra_cols]], axis=1)  # type: ignore[assignment]
    return merged


def _persist(ticker: str, framework: str, result: dict) -> None:
    out_dir: Path = DATA_RESULTS / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{framework}.json"
    with out_file.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
