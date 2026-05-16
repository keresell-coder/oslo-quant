"""DuPont decomposition — 3-factor and 5-factor."""

from __future__ import annotations

import datetime
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework


class DuPontFramework(BaseFramework):
    name = "dupont"

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs = stmts["balance_sheet"]
        inc = stmts["income_stmt"]
        periods = self._periods(inc)

        results: dict[str, Any] = {}
        for period in periods:
            metrics = self._compute_period(bs, inc, period)
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
        self, bs: Any, inc: Any, period: str
    ) -> dict[str, Any] | None:
        # Income statement items
        net_income = self._get(inc, "Net Income", col=period)
        revenue = self._get(
            inc, "Total Revenue", "Revenue", "Total Revenues", col=period
        )
        ebit = self._get(inc, "EBIT", "Operating Income", col=period)
        pretax_income = self._get(inc, "Pretax Income", "Income Before Tax", col=period)
        interest_expense = self._get(
            inc, "Interest Expense", "Interest And Debt Expense", col=period
        )

        # Balance sheet items — use the same period if available, else first col
        total_assets_curr = self._get(bs, "Total Assets", col=period)
        total_equity_curr = self._get(
            bs, "Stockholders Equity", "Total Stockholders Equity",
            "Common Stock Equity", col=period
        )

        # Try previous period for average calculations
        all_periods = self._periods(bs)
        try:
            idx = all_periods.index(period)
            prev_period = all_periods[idx + 1] if idx + 1 < len(all_periods) else None
        except ValueError:
            prev_period = None

        total_assets_prev = (
            self._get(bs, "Total Assets", col=prev_period) if prev_period else total_assets_curr
        )
        total_equity_prev = (
            self._get(
                bs, "Stockholders Equity", "Total Stockholders Equity",
                "Common Stock Equity", col=prev_period
            )
            if prev_period
            else total_equity_curr
        )

        avg_assets = (total_assets_curr + total_assets_prev) / 2
        avg_equity = (total_equity_curr + total_equity_prev) / 2

        # 3-Factor DuPont: ROE = NPM x Asset Turnover x Equity Multiplier
        npm = self._safe_div(net_income, revenue)          # Net Profit Margin
        asset_turnover = self._safe_div(revenue, avg_assets)
        equity_multiplier = self._safe_div(avg_assets, avg_equity)
        roe_3f = self._safe_div(net_income, avg_equity)

        # 5-Factor DuPont: adds tax burden and interest burden
        # ROE = Tax Burden x Interest Burden x EBIT Margin x Asset Turnover x Equity Multiplier
        tax_burden = self._safe_div(net_income, pretax_income)
        interest_burden = self._safe_div(
            pretax_income,
            ebit if not self._isnan(ebit) else pretax_income + abs(interest_expense or 0),
        )
        ebit_margin = self._safe_div(ebit, revenue)
        roe_5f = self._safe_div(net_income, avg_equity)  # should equal roe_3f numerically

        return {
            # 3-factor
            "net_profit_margin": self._fmt(npm),
            "asset_turnover": self._fmt(asset_turnover),
            "equity_multiplier": self._fmt(equity_multiplier),
            "roe_3factor": self._fmt(roe_3f),
            # 5-factor
            "tax_burden": self._fmt(tax_burden),
            "interest_burden": self._fmt(interest_burden),
            "ebit_margin": self._fmt(ebit_margin),
            "roe_5factor": self._fmt(roe_5f),
            # Raw inputs
            "net_income": self._fmt(net_income, 0),
            "revenue": self._fmt(revenue, 0),
            "avg_total_assets": self._fmt(avg_assets, 0),
            "avg_equity": self._fmt(avg_equity, 0),
        }

    def _isnan(self, v: float) -> bool:
        import math
        return math.isnan(v)
