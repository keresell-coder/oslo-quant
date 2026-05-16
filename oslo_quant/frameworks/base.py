"""Base framework class and shared helpers."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from oslo_quant.fetchers.base import Statements


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

        If *col* is None, use the first (most-recent) column.
        Returns NaN when not found.
        """
        if df is None or df.empty:
            return float("nan")
        target_col = col if col is not None else df.columns[0]
        if target_col not in df.columns:
            return float("nan")
        for name in row_names:
            matches = [idx for idx in df.index if name.lower() in str(idx).lower()]
            if matches:
                val = df.loc[matches[0], target_col]
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return float("nan")

    def _periods(self, df: pd.DataFrame) -> list[str]:
        """Return sorted period labels (descending) from a statement DataFrame."""
        if df is None or df.empty:
            return []
        return sorted(df.columns.tolist(), reverse=True)

    def _safe_div(self, num: float, den: float) -> float:
        if math.isnan(num) or math.isnan(den) or den == 0:
            return float("nan")
        return num / den

    def _fmt(self, value: float, decimals: int = 4) -> float | None:
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, decimals)
