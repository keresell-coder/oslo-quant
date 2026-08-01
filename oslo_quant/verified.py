"""Report-verified fundamentals ledger.

`data/verified/<TICKER>.json` holds line items transcribed from the company's
own annual/interim reports, with a source citation per item. Historical
reporting data is static: once a fiscal year is etched here from the annual
report, it never changes.

The ledger has two jobs in the pipeline, applied after fetching and before
the frameworks run:

1. **Verify** — where yfinance also has the item, compare. Deviation beyond
   tolerance is logged and recorded in `data/results/<TICKER>/verification.json`.
   yfinance's value is NOT overwritten on mismatch (the mismatch is surfaced
   for a human decision instead — silent "corrections" would hide provider
   drift).
2. **Fill** — where yfinance has no value (missing row or NaN), the
   report-sourced value is injected so frameworks can use it. Fills are
   recorded in the same verification report.

File format::

    {
      "ticker": "MOWI.OL",
      "currency": "EUR",
      "periods": {
        "2025": {
          "balance_sheet": {
            "Retained Earnings": {"value": 1234000000,
                                   "source": "Mowi Annual Report 2025, p. NN"}
          },
          "income_stmt": {...},
          "cash_flow": {...}
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from oslo_quant.config import DATA_VERIFIED
from oslo_quant.fetchers.base import Statements

log = logging.getLogger(__name__)

_STATEMENTS = ("balance_sheet", "income_stmt", "cash_flow")
_TOLERANCE = 0.02   # 2% relative deviation


def load_ledger(ticker: str) -> dict | None:
    path = DATA_VERIFIED / f"{ticker}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("[%s] Could not read verified ledger: %s", ticker, exc)
        return None


def apply_ledger(
    stmts: Statements, ticker: str, statement_currency: str
) -> tuple[Statements, dict[str, Any] | None]:
    """Verify statements against the ledger and fill gaps.

    Returns (possibly-updated statements, verification report or None when no
    ledger exists).
    """
    ledger = load_ledger(ticker)
    if ledger is None:
        return stmts, None

    entries: list[dict[str, Any]] = []
    counts = {"verified": 0, "mismatch": 0, "filled": 0, "skipped": 0}

    ledger_ccy = ledger.get("currency", "")
    if ledger_ccy and statement_currency and ledger_ccy != statement_currency:
        log.warning(
            "[%s] Ledger currency %s != statement currency %s — ledger NOT applied",
            ticker, ledger_ccy, statement_currency,
        )
        return stmts, {
            "ticker": ticker,
            "status": "currency_mismatch",
            "ledger_currency": ledger_ccy,
            "statement_currency": statement_currency,
            "entries": [],
            "counts": counts,
        }

    out: Statements = dict(stmts)  # type: ignore[assignment]
    dfs: dict[str, pd.DataFrame] = {}
    for key in _STATEMENTS:
        df = stmts.get(key)
        dfs[key] = df.copy() if df is not None and not df.empty else pd.DataFrame()

    for period, statements in ledger.get("periods", {}).items():
        for stmt_key in _STATEMENTS:
            for row_name, item in statements.get(stmt_key, {}).items():
                value = item.get("value")
                source = item.get("source", "unspecified")
                if value is None:
                    continue
                df = dfs[stmt_key]
                entry = {
                    "period": period, "statement": stmt_key, "item": row_name,
                    "ledger_value": value, "source": source,
                }
                if period not in df.columns:
                    # Ledger year outside the fetched window — nothing to
                    # verify or fill against; note and move on.
                    entry.update(status="skipped",
                                 note="period not in fetched statements")
                    counts["skipped"] += 1
                    entries.append(entry)
                    continue

                existing = float("nan")
                if row_name in df.index:
                    try:
                        existing = float(df.loc[row_name, period])
                    except (TypeError, ValueError):
                        existing = float("nan")

                if pd.isna(existing):
                    # Fill: yfinance has no value here.
                    if row_name not in df.index:
                        df = df.reindex(df.index.union([row_name], sort=False))
                        dfs[stmt_key] = df
                    df.loc[row_name, period] = float(value)
                    entry.update(status="filled")
                    counts["filled"] += 1
                    log.info("[%s] Ledger fill: %s %s %s = %s (%s)",
                             ticker, period, stmt_key, row_name, value, source)
                else:
                    rel = abs(existing - float(value)) / max(abs(float(value)), 1e-9)
                    if rel <= _TOLERANCE:
                        entry.update(status="verified",
                                     yfinance_value=existing,
                                     relative_diff=round(rel, 4))
                        counts["verified"] += 1
                    else:
                        entry.update(status="MISMATCH",
                                     yfinance_value=existing,
                                     relative_diff=round(rel, 4))
                        counts["mismatch"] += 1
                        log.warning(
                            "[%s] Ledger MISMATCH: %s %s %s — yfinance %.4g vs "
                            "report %.4g (%.1f%% off; %s)",
                            ticker, period, stmt_key, row_name,
                            existing, float(value), rel * 100, source,
                        )
                entries.append(entry)

    for key in _STATEMENTS:
        out[key] = dfs[key]  # type: ignore[literal-required]

    report = {
        "ticker": ticker,
        "status": "ok",
        "ledger_currency": ledger_ccy,
        "statement_currency": statement_currency,
        "counts": counts,
        "entries": entries,
    }
    return out, report
