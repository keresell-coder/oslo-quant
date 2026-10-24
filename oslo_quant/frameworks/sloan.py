"""Cash/accrual diagnostics; original Sloan BS identity requires exact components."""

from __future__ import annotations
import datetime
import math
from oslo_quant.frameworks.base import BaseFramework
from oslo_quant.frameworks.methodology import VERSION, exact, prior, basis, ratio


class SloanFramework(BaseFramework):
    name = "sloan"

    def compute(self, stmts, ticker):
        bs, inc, cf = (stmts[k] for k in ("balance_sheet", "income_stmt", "cash_flow"))
        results = {}
        for period in self._periods(inc, anchor="Total Revenue"):
            value = self._compute_period(bs, inc, cf, period, prior(period, bs.columns))
            if value:
                results[period] = value
        return {
            "ticker": ticker,
            "framework": self.name,
            "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "methodology_version": VERSION,
            "periods": results,
        }

    def _compute_period(self, bs, inc, cf, period, prev_period):
        prev_period = prev_period if prev_period == prior(period, bs.columns) else None
        sources = {}

        def get(frame, labels, col, key):
            value, row = exact(frame, labels, col)
            sources[key] = row
            return value

        ni = get(inc, ["Net Income"], period, "net_income")
        cfo = get(
            cf,
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
            period,
            "cfo",
        )
        assets = get(bs, ["Total Assets"], period, "assets")
        opening = get(bs, ["Total Assets"], prev_period, "opening_assets")
        avg = (assets + opening) / 2
        parts = {}
        labels = {
            "current_assets": ["Current Assets", "Total Current Assets"],
            "cash": ["Cash And Cash Equivalents", "Cash Equivalents"],
            "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
            "current_debt": ["Current Debt"],
            "income_taxes_payable": ["Income Tax Payable", "Income Taxes Payable"],
        }
        for key, rows in labels.items():
            parts[key] = get(bs, rows, period, key)
            parts["prior_" + key] = get(bs, rows, prev_period, "prior_" + key)
        depreciation = get(
            cf, ["Depreciation And Amortization"], period, "depreciation_amortization"
        )
        missing = [key for key, value in parts.items() if not math.isfinite(value)]
        if not math.isfinite(depreciation) or depreciation < 0:
            missing.append("nonnegative depreciation/amortization expense")
        if not prev_period:
            missing.append("adjacent prior annual period")
        if str(period).startswith("LTM "):
            missing.append("BS delta window does not match overlapping LTM flows")
        if missing:
            bs_accruals = float("nan")
        else:
            delta = lambda key: parts[key] - parts["prior_" + key]
            bs_accruals = (
                (delta("current_assets") - delta("cash"))
                - (
                    delta("current_liabilities")
                    - delta("current_debt")
                    - delta("income_taxes_payable")
                )
                - depreciation
            )
        bs_ratio = ratio(bs_accruals, avg)
        cfo_accruals = ni - cfo
        cfo_ratio = ratio(cfo_accruals, avg)
        if not math.isfinite(cfo_ratio) and not math.isfinite(bs_ratio):
            return None
        divergence = (
            bs_ratio - cfo_ratio
            if math.isfinite(bs_ratio) and math.isfinite(cfo_ratio)
            else None
        )
        return {
            "cfo_accruals": self._fmt(cfo_accruals, 0),
            "cfo_accrual_ratio": self._fmt(cfo_ratio),
            "bs_accruals": self._fmt(bs_accruals, 0),
            "bs_accrual_ratio": self._fmt(bs_ratio),
            "earnings_quality": "Unrated diagnostic",
            "cash_conversion_description": self._quality_flag(cfo_ratio),
            "methods_divergence": (
                self._fmt(divergence) if divergence is not None else None
            ),
            "methods_diverge_materially": divergence is not None
            and abs(divergence) > 0.10,
            "net_income": self._fmt(ni, 0),
            "operating_cash_flow": self._fmt(cfo, 0),
            "avg_total_assets": self._fmt(avg, 0),
            "period_basis": basis(period),
            "bs_status": (
                "available exact-component identity"
                if math.isfinite(bs_ratio)
                else "withheld: " + ", ".join(missing)
            ),
            "definitions": {
                "cfo": "(Net Income - Operating Cash Flow) / average total assets; diagnostic, not original Sloan earnings definition",
                "bs": "[(delta current assets - delta cash) - (delta current liabilities - delta current debt - delta income taxes payable) - depreciation/amortization] / average total assets",
            },
            "warning": "Sign alone is not durable earnings quality; acquisitions/discontinued operations can distort BS deltas. Neither method establishes a trading edge.",
            "source_rows": sources,
            "bs_components": {key: self._fmt(value, 0) for key, value in parts.items()},
        }

    def _quality_flag(self, value):
        if not math.isfinite(value):
            return "Unavailable cash-conversion diagnostic"
        return (
            "Operating cash flow exceeds net income"
            if value < 0
            else (
                "Net income exceeds operating cash flow"
                if value > 0
                else "Net income equals operating cash flow"
            )
        )
