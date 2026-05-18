"""Altman Z-Score — financial distress prediction (original 1968 model)."""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework


class AltmanFramework(BaseFramework):
    name = "altman"

    # Original 1968 coefficients (public-company model)
    _WEIGHTS = {"x1": 1.2, "x2": 1.4, "x3": 3.3, "x4": 0.6, "x5": 1.0}

    # Z' model for private firms
    _WEIGHTS_PRIVATE = {"x1": 0.717, "x2": 0.847, "x3": 3.107, "x4": 0.420, "x5": 0.998}

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs = stmts["balance_sheet"]
        inc = stmts["income_stmt"]
        prices = stmts["prices"]

        periods = self._periods(inc)
        results: dict[str, Any] = {}

        for period in periods:
            metrics = self._compute_period(bs, inc, prices, period)
            if metrics:
                results[period] = metrics

        return {
            "ticker": ticker,
            "framework": self.name,
            "computed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "periods": results,
        }

    # ------------------------------------------------------------------

    def _compute_period(
        self, bs: Any, inc: Any, prices: Any, period: str
    ) -> dict[str, Any] | None:
        total_assets = self._get(bs, "Total Assets", col=period)
        total_liab = self._get(
            bs, "Total Liabilities Net Minority Interest", "Total Liabilities", col=period
        )
        current_assets = self._get(bs, "Current Assets", "Total Current Assets", col=period)
        current_liab = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=period
        )
        retained_earnings = self._get(
            bs, "Retained Earnings", "Retained Earnings Deficit", col=period
        )
        ebit = self._get(inc, "EBIT", "Operating Income", col=period)
        revenue = self._get(inc, "Total Revenue", "Revenue", col=period)

        # X1: Working Capital / Total Assets
        wc = (current_assets if not math.isnan(current_assets) else 0) - \
             (current_liab if not math.isnan(current_liab) else 0)
        x1 = self._safe_div(wc, total_assets)

        # X2: Retained Earnings / Total Assets
        x2 = self._safe_div(retained_earnings, total_assets)

        # X3: EBIT / Total Assets
        x3 = self._safe_div(ebit, total_assets)

        # X4: Book Equity / Total Liabilities
        # We use book equity rather than market cap to avoid currency-mismatch
        # errors on Oslo-listed companies that report financial statements in USD
        # (e.g. Frontline, Borr Drilling, Hafnia). Market cap is in NOK but
        # balance-sheet liabilities are in USD, which would inflate X4 ~10x.
        book_equity = self._get(
            bs, "Stockholders Equity", "Total Stockholders Equity",
            "Common Stock Equity", col=period
        )
        x4 = self._safe_div(book_equity, total_liab)

        # X5: Revenue / Total Assets (asset turnover)
        x5 = self._safe_div(revenue, total_assets)

        w = self._WEIGHTS
        z = (
            w["x1"] * (x1 if not math.isnan(x1) else 0)
            + w["x2"] * (x2 if not math.isnan(x2) else 0)
            + w["x3"] * (x3 if not math.isnan(x3) else 0)
            + w["x4"] * (x4 if not math.isnan(x4) else 0)
            + w["x5"] * (x5 if not math.isnan(x5) else 0)
        )

        zone = self._zone(z)

        return {
            "z_score": self._fmt(z),
            "zone": zone,
            "x1_working_capital_to_assets": self._fmt(x1),
            "x2_retained_earnings_to_assets": self._fmt(x2),
            "x3_ebit_to_assets": self._fmt(x3),
            "x4_book_equity_to_liabilities": self._fmt(x4),
            "x5_revenue_to_assets": self._fmt(x5),
        }

    def _zone(self, z: float) -> str:
        if math.isnan(z):
            return "Unknown"
        if z > 2.99:
            return "Safe"
        if z > 1.81:
            return "Grey"
        return "Distress"
