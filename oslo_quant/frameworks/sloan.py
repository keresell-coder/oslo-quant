"""Sloan Accruals — earnings quality via balance-sheet accrual ratio."""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework


class SloanFramework(BaseFramework):
    name = "sloan"

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs = stmts["balance_sheet"]
        inc = stmts["income_stmt"]
        cf = stmts["cash_flow"]

        periods = self._periods(inc)
        results: dict[str, Any] = {}

        for period in periods:
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
        net_income = self._get(inc, "Net Income", col=period)

        # Cash-flow method: Accruals = Net Income - Cash from Operations
        cfo = self._get(
            cf, "Operating Cash Flow", "Total Cash From Operating Activities",
            "Cash Flow From Continuing Operating Activities", col=period
        )

        total_assets = self._get(bs, "Total Assets", col=period)
        total_assets_prev = (
            self._get(bs, "Total Assets", col=prev_period) if prev_period else total_assets
        )
        avg_assets = (total_assets + total_assets_prev) / 2

        # Balance-sheet method (Sloan 1996): ΔOperating Assets - ΔOperating Liabilities
        # Operating Assets = Total Assets - Cash - Short-term Investments
        cash = self._get(bs, "Cash And Cash Equivalents", "Cash Equivalents", col=period)
        cash_prev = (
            self._get(bs, "Cash And Cash Equivalents", "Cash Equivalents", col=prev_period)
            if prev_period else cash
        )
        current_liab = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=period
        )
        current_liab_prev = (
            self._get(
                bs, "Current Liabilities", "Total Current Liabilities", col=prev_period
            )
            if prev_period else current_liab
        )
        long_term_debt = self._get(bs, "Long Term Debt", col=period)
        long_term_debt_prev = (
            self._get(bs, "Long Term Debt", col=prev_period) if prev_period else long_term_debt
        )

        oa = total_assets - (cash if not math.isnan(cash) else 0)
        oa_prev = total_assets_prev - (cash_prev if not math.isnan(cash_prev) else 0)

        ol = (
            (current_liab if not math.isnan(current_liab) else 0)
            + (long_term_debt if not math.isnan(long_term_debt) else 0)
        )
        ol_prev = (
            (current_liab_prev if not math.isnan(current_liab_prev) else 0)
            + (long_term_debt_prev if not math.isnan(long_term_debt_prev) else 0)
        )

        bs_accruals = (oa - oa_prev) - (ol - ol_prev)
        bs_accrual_ratio = self._safe_div(bs_accruals, avg_assets)

        # CFO-based accrual
        cfo_accruals = net_income - (cfo if not math.isnan(cfo) else 0)
        cfo_accrual_ratio = self._safe_div(cfo_accruals, avg_assets)

        # Earnings quality flag: low accruals = higher quality
        quality = self._quality_flag(cfo_accrual_ratio)

        return {
            "cfo_accruals": self._fmt(cfo_accruals, 0),
            "cfo_accrual_ratio": self._fmt(cfo_accrual_ratio),
            "bs_accruals": self._fmt(bs_accruals, 0),
            "bs_accrual_ratio": self._fmt(bs_accrual_ratio),
            "earnings_quality": quality,
            "net_income": self._fmt(net_income, 0),
            "operating_cash_flow": self._fmt(cfo, 0),
            "avg_total_assets": self._fmt(avg_assets, 0),
        }

    def _quality_flag(self, ratio: float) -> str:
        if math.isnan(ratio):
            return "Unknown"
        if ratio < -0.05:
            return "High"       # cash earnings well above reported income
        if ratio < 0.05:
            return "Moderate"
        return "Low"            # earnings heavily accrual-based
