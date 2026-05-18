"""Altman Z-Score — original 1968 model + Z'' non-manufacturing variant (1995)."""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework


class AltmanFramework(BaseFramework):
    name = "altman"

    # Original 1968 public-company model (US manufacturing)
    _W = {"x1": 1.2, "x2": 1.4, "x3": 3.3, "x4": 0.6, "x5": 1.0}

    # Z'' non-manufacturing / non-US model (Altman 1995)
    # Drops X5 (revenue/assets) to remove asset-turnover bias that penalises
    # capital-intensive sectors (shipping, offshore, aquaculture, real estate).
    # Thresholds: Safe > 2.6 | Grey 1.1–2.6 | Distress ≤ 1.1
    _W_PP = {"x1": 6.56, "x2": 3.26, "x3": 6.72, "x4": 1.05}

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs     = stmts["balance_sheet"]
        inc    = stmts["income_stmt"]
        prices = stmts["prices"]

        periods = self._periods(inc)
        results: dict[str, Any] = {}

        for period in periods:
            metrics = self._compute_period(bs, inc, prices, period)
            if metrics:
                results[period] = metrics

        return {
            "ticker":      ticker,
            "framework":   self.name,
            "computed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "periods":     results,
        }

    # ------------------------------------------------------------------

    def _compute_period(
        self, bs: Any, inc: Any, prices: Any, period: str
    ) -> dict[str, Any] | None:
        total_assets = self._get(bs, "Total Assets", col=period)
        total_liab   = self._get(
            bs, "Total Liabilities Net Minority Interest", "Total Liabilities", col=period
        )
        current_assets = self._get(bs, "Current Assets", "Total Current Assets", col=period)
        current_liab   = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=period
        )
        retained_earnings = self._get(
            bs, "Retained Earnings", "Retained Earnings Deficit", col=period
        )
        ebit    = self._get(inc, "EBIT", "Operating Income", col=period)
        revenue = self._get(inc, "Total Revenue", "Revenue", col=period)

        # X1: Working Capital / Total Assets
        wc = (current_assets if not math.isnan(current_assets) else 0) - \
             (current_liab   if not math.isnan(current_liab)   else 0)
        x1 = self._safe_div(wc, total_assets)

        # X2: Retained Earnings / Total Assets
        x2 = self._safe_div(retained_earnings, total_assets)

        # X3: EBIT / Total Assets
        x3 = self._safe_div(ebit, total_assets)

        # X4: Book Equity / Total Liabilities
        # Book equity is used throughout — market cap (NOK) ÷ liabilities (USD/EUR)
        # would inflate X4 ~10× for dual-listed companies.
        book_equity = self._get(
            bs, "Stockholders Equity", "Total Stockholders Equity",
            "Common Stock Equity", col=period
        )
        x4 = self._safe_div(book_equity, total_liab)

        # X5: Revenue / Total Assets (asset turnover) — original model only
        x5 = self._safe_div(revenue, total_assets)

        def _v(x: float) -> float:
            return x if not math.isnan(x) else 0.0

        # ── Original Z-Score (manufacturing / public companies) ──────
        w  = self._W
        z  = (w["x1"]*_v(x1) + w["x2"]*_v(x2) + w["x3"]*_v(x3)
              + w["x4"]*_v(x4) + w["x5"]*_v(x5))

        # ── Z'' Score (non-manufacturing, sector-neutral) ─────────────
        wp = self._W_PP
        zpp = (wp["x1"]*_v(x1) + wp["x2"]*_v(x2) + wp["x3"]*_v(x3)
               + wp["x4"]*_v(x4))

        return {
            "z_score":                      self._fmt(z),
            "zone":                         self._zone(z),
            "z_score_prime":                self._fmt(zpp),
            "zone_prime":                   self._zone_prime(zpp),
            "x1_working_capital_to_assets": self._fmt(x1),
            "x2_retained_earnings_to_assets": self._fmt(x2),
            "x3_ebit_to_assets":            self._fmt(x3),
            "x4_book_equity_to_liabilities": self._fmt(x4),
            "x5_revenue_to_assets":         self._fmt(x5),
        }

    def _zone(self, z: float) -> str:
        if math.isnan(z):
            return "Unknown"
        if z > 2.99:
            return "Safe"
        if z > 1.81:
            return "Grey"
        return "Distress"

    def _zone_prime(self, z: float) -> str:
        """Z'' thresholds (Altman 1995): Safe > 2.6 | Grey 1.1–2.6 | Distress ≤ 1.1"""
        if math.isnan(z):
            return "Unknown"
        if z > 2.6:
            return "Safe"
        if z > 1.1:
            return "Grey"
        return "Distress"
