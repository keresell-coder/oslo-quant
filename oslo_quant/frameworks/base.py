"""Base framework class and shared helpers."""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from oslo_quant.fetchers.base import Statements

log = logging.getLogger(__name__)


class BaseFramework(ABC):
    name: str = ""

    @abstractmethod
    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        """Compute framework metrics.

        Returns a dict keyed by period label (e.g. "2023", "TTM") where each
        value is a dict of named metrics plus a ``_meta`` sub-dict.
        """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get(self, df: pd.DataFrame, *row_names: str, col: str | None = None) -> float:
        """Extract a scalar from *df* trying *row_names* in order.

        Resolution is **exact-match first** (case-insensitive), across all
        *row_names* in order. Only if no exact match exists anywhere does it
        fall back to substring matching — and that fallback is logged, because
        substring-first resolution against the yfinance vocabulary selects
        wrong rows ("EBIT" → "Normalized EBITDA", "Current Assets" →
        "Total Non Current Assets", "Net Income" → continuing-operations
        income). See the 2026-08 restatement.

        If *col* is None, use the first (most-recent) column.
        Returns NaN when not found — never a value from a different row.
        """
        if df is None or df.empty:
            return float("nan")
        target_col = col if col is not None else df.columns[0]
        if target_col not in df.columns:
            return float("nan")

        index_lower = {str(idx).lower(): idx for idx in df.index}

        # Pass 1 — exact match (case-insensitive), first row_name wins.
        for name in row_names:
            idx = index_lower.get(name.lower())
            if idx is not None:
                try:
                    return float(df.loc[idx, target_col])
                except (TypeError, ValueError):
                    return float("nan")

        # Pass 2 — substring fallback, logged so it is visible in run output.
        for name in row_names:
            matches = [idx for idx in df.index if name.lower() in str(idx).lower()]
            if matches:
                log.warning(
                    "Field '%s' resolved by SUBSTRING fallback to row '%s' — "
                    "verify this mapping.", name, matches[0]
                )
                val = df.loc[matches[0], target_col]
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return float("nan")

    def _periods(self, df: pd.DataFrame, anchor: str | None = None) -> list[str]:
        """Return sorted period labels (descending) from a statement DataFrame.

        Columns that contain no data at all are excluded: yfinance regularly
        returns a trailing annual column that is entirely NaN, and computing
        "results" from it produced false Z=0.00 Distress rows and identical
        default Ohlson probabilities for every company (2026-08 restatement).

        When *anchor* is given (e.g. "Total Assets" for a balance sheet,
        "Total Revenue" for an income statement), a column only counts as a
        usable period if the anchor row has a value in it. The provider also
        returns *stub* columns carrying a handful of minor rows but no totals
        — those are not usable statement periods and silently degraded
        prior-year comparisons.
        """
        if df is None or df.empty:
            return []
        if anchor is not None:
            anchor_lower = anchor.lower()
            anchor_idx = next(
                (idx for idx in df.index if str(idx).lower() == anchor_lower), None
            )
            if anchor_idx is not None:
                cols = [c for c in df.columns if pd.notna(df.loc[anchor_idx, c])]
                return sorted(cols, reverse=True)
        cols = [c for c in df.columns if df[c].notna().any()]
        return sorted(cols, reverse=True)

    def _isnan(self, v: float) -> bool:
        try:
            return math.isnan(v)
        except TypeError:
            return v is None

    def _safe_div(self, num: float, den: float) -> float:
        if math.isnan(num) or math.isnan(den) or den == 0:
            return float("nan")
        return num / den

    def _fmt(self, value: float, decimals: int = 4) -> float | None:
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, decimals)
