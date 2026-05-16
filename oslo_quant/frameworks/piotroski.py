"""Piotroski F-Score — 9 binary signals."""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework


class PiotroskiFramework(BaseFramework):
    name = "piotroski"

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs = stmts["balance_sheet"]
        inc = stmts["income_stmt"]
        cf = stmts["cash_flow"]

        periods = self._periods(inc)
        results: dict[str, Any] = {}

        for i, period in enumerate(periods):
            all_bs_periods = self._periods(bs)
            try:
                prev_idx = all_bs_periods.index(period) + 1
                prev_period = all_bs_periods[prev_idx] if prev_idx < len(all_bs_periods) else None
            except ValueError:
                prev_period = None

            metrics = self._compute_period(bs, inc, cf, period, prev_period)
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
        self, bs: Any, inc: Any, cf: Any, period: str, prev_period: str | None
    ) -> dict[str, Any] | None:
        # ---- Profitability signals (F1–F4) ----
        net_income = self._get(inc, "Net Income", col=period)
        total_assets = self._get(bs, "Total Assets", col=period)
        total_assets_prev = (
            self._get(bs, "Total Assets", col=prev_period) if prev_period else total_assets
        )

        roa = self._safe_div(net_income, (total_assets + total_assets_prev) / 2)
        cfo = self._get(
            cf, "Operating Cash Flow", "Total Cash From Operating Activities",
            "Cash Flow From Continuing Operating Activities", col=period
        )
        cfo_to_assets = self._safe_div(cfo, total_assets)

        roa_prev = None
        if prev_period:
            ni_prev = self._get(inc, "Net Income", col=prev_period)
            ta_prev2_periods = self._periods(bs)
            try:
                pi = ta_prev2_periods.index(prev_period)
                prev2 = ta_prev2_periods[pi + 1] if pi + 1 < len(ta_prev2_periods) else None
            except ValueError:
                prev2 = None
            ta_prev2 = self._get(bs, "Total Assets", col=prev2) if prev2 else total_assets_prev
            roa_prev = self._safe_div(ni_prev, (total_assets_prev + ta_prev2) / 2)

        f1 = int(roa > 0) if not math.isnan(roa) else 0
        f2 = int(cfo > 0) if not math.isnan(cfo) else 0
        f3 = int(roa > roa_prev) if (roa_prev is not None and not math.isnan(roa) and not math.isnan(roa_prev)) else 0
        f4 = int(cfo_to_assets > roa) if (not math.isnan(cfo_to_assets) and not math.isnan(roa)) else 0

        # ---- Leverage / Liquidity signals (F5–F7) ----
        long_term_debt = self._get(
            bs, "Long Term Debt", "Long-Term Debt And Capital Lease Obligation", col=period
        )
        ltd_prev = self._get(
            bs, "Long Term Debt", "Long-Term Debt And Capital Lease Obligation", col=prev_period
        ) if prev_period else long_term_debt

        current_assets = self._get(bs, "Current Assets", "Total Current Assets", col=period)
        current_liabilities = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=period
        )
        current_assets_prev = self._get(
            bs, "Current Assets", "Total Current Assets", col=prev_period
        ) if prev_period else current_assets
        current_liabilities_prev = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=prev_period
        ) if prev_period else current_liabilities

        current_ratio = self._safe_div(current_assets, current_liabilities)
        current_ratio_prev = self._safe_div(current_assets_prev, current_liabilities_prev)

        shares = self._get(
            bs, "Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding",
            col=period
        )
        shares_prev = self._get(
            bs, "Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding",
            col=prev_period
        ) if prev_period else shares

        leverage = self._safe_div(long_term_debt, total_assets)
        leverage_prev = self._safe_div(ltd_prev, total_assets_prev)

        f5 = int(leverage < leverage_prev) if (not math.isnan(leverage) and not math.isnan(leverage_prev)) else 0
        f6 = int(current_ratio > current_ratio_prev) if (not math.isnan(current_ratio) and not math.isnan(current_ratio_prev)) else 0
        f7 = int(shares <= shares_prev) if (not math.isnan(shares) and not math.isnan(shares_prev)) else 0

        # ---- Operating efficiency signals (F8–F9) ----
        gross_profit = self._get(inc, "Gross Profit", col=period)
        gross_profit_prev = self._get(inc, "Gross Profit", col=prev_period) if prev_period else gross_profit
        revenue = self._get(inc, "Total Revenue", "Revenue", col=period)
        revenue_prev = self._get(inc, "Total Revenue", "Revenue", col=prev_period) if prev_period else revenue

        gross_margin = self._safe_div(gross_profit, revenue)
        gross_margin_prev = self._safe_div(gross_profit_prev, revenue_prev)

        asset_turnover = self._safe_div(revenue, total_assets)
        asset_turnover_prev = self._safe_div(revenue_prev, total_assets_prev)

        f8 = int(gross_margin > gross_margin_prev) if (not math.isnan(gross_margin) and not math.isnan(gross_margin_prev)) else 0
        f9 = int(asset_turnover > asset_turnover_prev) if (not math.isnan(asset_turnover) and not math.isnan(asset_turnover_prev)) else 0

        f_score = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9

        return {
            "f_score": f_score,
            "signals": {
                "F1_positive_roa": f1,
                "F2_positive_cfo": f2,
                "F3_roa_increasing": f3,
                "F4_accruals_quality": f4,
                "F5_leverage_decreasing": f5,
                "F6_liquidity_improving": f6,
                "F7_no_dilution": f7,
                "F8_gross_margin_improving": f8,
                "F9_asset_turnover_improving": f9,
            },
            "interpretation": self._interpret(f_score),
            "roa": self._fmt(roa),
            "cfo_to_assets": self._fmt(cfo_to_assets),
            "current_ratio": self._fmt(current_ratio),
            "gross_margin": self._fmt(gross_margin),
            "asset_turnover": self._fmt(asset_turnover),
        }

    def _interpret(self, score: int) -> str:
        if score >= 8:
            return "Strong"
        if score >= 5:
            return "Moderate"
        return "Weak"
