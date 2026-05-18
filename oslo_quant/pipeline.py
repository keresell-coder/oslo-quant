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
    _fx_cache: dict[str, float | None] = {}   # "NOKUSD" → rate, shared across tickers

    for ticker in target_tickers:
        log.info("=== Processing %s ===", ticker)
        company = TICKER_MAP[ticker]

        # --- Fetch statements ---
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

        # --- Resolve and cross-check currency ---
        currency_info = _resolve_currency(yf_fetcher, ticker, company, force_refresh)

        # --- Convert prices from NOK to the reporting currency ---
        price_ccy = currency_info["price_currency"]
        fin_ccy   = currency_info["financial_currency"]
        stmts = _convert_prices(stmts, price_ccy, fin_ccy, yf_fetcher, _fx_cache)

        # --- Compute frameworks ---
        ticker_results: dict[str, Any] = {}
        for fw_name in target_frameworks:
            framework_cls = FRAMEWORK_REGISTRY[fw_name]
            framework = framework_cls()
            try:
                result = framework.compute(stmts, ticker)
                # Embed currency context in every result file
                result["financial_currency"] = currency_info["financial_currency"]
                result["price_currency"]     = currency_info["price_currency"]
                ticker_results[fw_name] = result
                _persist(ticker, fw_name, result)
                log.info(
                    "[%s] %s — OK (%d periods, statements in %s)",
                    ticker, fw_name,
                    len(result.get("periods", {})),
                    currency_info["financial_currency"],
                )
            except Exception as exc:
                log.error("[%s] %s failed: %s", ticker, fw_name, exc)
                ticker_results[fw_name] = {"error": str(exc)}

        # Save a dedicated currency verification file per company
        _persist(ticker, "currency", currency_info)
        summary[ticker] = ticker_results

    return summary


# ---------------------------------------------------------------------------
# Currency resolution
# ---------------------------------------------------------------------------

def _resolve_currency(yf_fetcher: YFinanceFetcher, ticker: str, company, force_refresh: bool) -> dict:
    """Fetch currency from yfinance, cross-check with config, return verified dict."""
    config_ccy = company.reporting_currency  # researched value in config.py

    try:
        detected = yf_fetcher.fetch_currency_info(ticker, force_refresh=force_refresh)
        yf_ccy    = detected.get("financial_currency", "Unknown")
        price_ccy = detected.get("price_currency", "NOK")
        source    = detected.get("source", "fallback")
    except Exception as exc:
        log.warning("[%s] Currency fetch failed: %s", ticker, exc)
        yf_ccy = "Unknown"
        price_ccy = "NOK"
        source = "fallback"

    # Determine final currency: prefer yfinance if available, else config
    if yf_ccy and yf_ccy not in ("Unknown", ""):
        final_ccy = yf_ccy
    else:
        final_ccy = config_ccy
        source = "config_fallback"

    match_status = _match_status(yf_ccy, config_ccy)
    if match_status == "mismatch":
        log.warning(
            "[%s] Currency mismatch — config says %s, yfinance says %s. Using yfinance.",
            ticker, config_ccy, yf_ccy,
        )

    return {
        "ticker":              ticker,
        "full_name":           company.full_name,
        "price_currency":      price_ccy,
        "financial_currency":  final_ccy,
        "config_currency":     config_ccy,
        "yfinance_currency":   yf_ccy,
        "detection_source":    source,
        "verification_status": match_status,
    }


def _match_status(yf_ccy: str, config_ccy: str) -> str:
    if yf_ccy in ("Unknown", ""):
        return "unverified"
    if yf_ccy == config_ccy:
        return "verified"
    return "mismatch"


# ---------------------------------------------------------------------------
# Helpers
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
        extra_cols = [c for c in s.columns if c not in p.columns]
        if extra_cols:
            merged[key] = pd.concat([p, s[extra_cols]], axis=1)  # type: ignore[assignment]
    return merged


def _convert_prices(
    stmts: Statements,
    price_ccy: str,
    reporting_ccy: str,
    yf_fetcher: YFinanceFetcher,
    fx_cache: dict,
) -> Statements:
    """Return *stmts* with the prices DataFrame converted from *price_ccy* to *reporting_ccy*.

    The raw Oslo Børs prices are always in NOK. For companies that report financial
    statements in USD or EUR we convert so that any price-based metric (P/E, P/B, …)
    divides values in the same currency.
    """
    import pandas as pd

    if price_ccy == reporting_ccy:
        return stmts

    prices: pd.DataFrame = stmts.get("prices")  # type: ignore[assignment]
    if prices is None or prices.empty:
        return stmts

    fx_key = f"{price_ccy}{reporting_ccy}"
    if fx_key not in fx_cache:
        fx_cache[fx_key] = yf_fetcher.fetch_fx_rate(price_ccy, reporting_ccy)

    rate = fx_cache[fx_key]
    if rate is None:
        log.warning(
            "FX rate %s→%s unavailable; prices remain in %s",
            price_ccy, reporting_ccy, price_ccy,
        )
        return stmts

    converted = prices.copy()
    for col in ("Open", "High", "Low", "Close"):
        if col in converted.columns:
            converted[col] = converted[col] * rate

    log.info(
        "Converted prices %s→%s (rate=%.6f)", price_ccy, reporting_ccy, rate
    )
    merged = dict(stmts)  # type: ignore[assignment]
    merged["prices"] = converted  # type: ignore[assignment]
    return merged  # type: ignore[return-value]


def _persist(ticker: str, name: str, result: dict) -> None:
    out_dir: Path = DATA_RESULTS / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"{name}.json").open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
