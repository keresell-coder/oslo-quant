"""Piotroski-inspired annual signals with explicit proxies; interim is an adaptation."""

from __future__ import annotations
import datetime
import math
from oslo_quant.frameworks.base import BaseFramework
from oslo_quant.frameworks.methodology import VERSION, exact, prior, basis, ratio


class PiotroskiFramework(BaseFramework):
    name = "piotroski"

    def compute(self, stmts, ticker):
        bs, inc, cf = (stmts[k] for k in ("balance_sheet", "income_stmt", "cash_flow"))
        results = {}
        for period in self._periods(inc, anchor="Total Revenue"):
            value = self._compute_period(
                bs,
                inc,
                cf,
                period,
                prior(period, bs.columns),
                stmts.get("meta", {}).get("debt_inputs"),
            )
            if value:
                results[period] = value
        return {
            "ticker": ticker,
            "framework": self.name,
            "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "methodology_version": VERSION,
            "periods": results,
        }

    def _compute_period(self, bs, inc, cf, period, prev_period, debt_inputs=None):
        # Annual comparisons require the actual adjacent FY; no current=prior fallback.
        previous = prior(period, bs.columns)
        prev_period = prev_period if prev_period == previous else None
        prev2 = prior(prev_period, bs.columns) if prev_period else None
        sources = {}

        def get(frame, labels, col, key):
            value, row = exact(frame, labels, col)
            sources[key] = row
            return value

        def assets(col, key):
            return get(bs, ["Total Assets"], col, key)

        def income(col, key):
            return get(
                inc,
                [
                    "Net Income Before Extraordinary Items",
                    "Net Income Before Extraordinary",
                    "Net Income",
                ],
                col,
                key,
            )

        ta = assets(period, "assets")
        opening = assets(prev_period, "opening_assets")
        prior_opening = assets(prev2, "prior_opening_assets")
        avg = (ta + opening) / 2
        prior_avg = (opening + prior_opening) / 2
        ni = income(period, "income")
        ni_prev = income(prev_period, "prior_income")
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
        roa = ratio(ni, opening)
        roa_prev = ratio(ni_prev, prior_opening)
        cfo_ratio = ratio(cfo, opening)

        def positive(value):
            return int(value > 0) if math.isfinite(value) else None

        def compare(a, b):
            return int(a > b) if math.isfinite(a) and math.isfinite(b) else None

        f1 = positive(roa)
        f2 = positive(cfo_ratio)
        f3 = compare(roa, roa_prev)
        f4 = compare(cfo_ratio, roa)

        # Original leverage includes the current portion of long-term debt. Unknown != zero.
        debt_audit = {}

        def debt(col, prefix):
            sources[prefix + "long_debt"] = None
            sources[prefix + "current_portion"] = None
            selected = (
                (debt_inputs or {}).get("periods", {}).get(col)
                if (debt_inputs or {}).get("status") == "qualified-selected-debt"
                else None
            )
            if selected is not None:
                debt_audit[str(col)] = selected
                controls = (
                    selected.get("provider_asset_control"),
                    selected.get("opening_provider_asset_control"),
                )
                if not all(controls):
                    debt_audit[str(col)] = {
                        **selected,
                        "ratio_status": "withheld: provider asset basis not tied to primary controls",
                    }
                    return float("nan")
                expected = (
                    assets(col, prefix + "debt_assets"),
                    assets(prior(col, bs.columns), prefix + "debt_opening_assets"),
                )
                if (
                    tuple(control["provider_assets"] for control in controls)
                    != expected
                ):
                    return float("nan")
                sources[prefix + "long_debt"] = "selected-primary: " + ", ".join(
                    selected["source_records"]
                )
                sources[prefix + "current_portion"] = "selected-primary: " + ", ".join(
                    selected["source_records"]
                )
                return selected["noncurrent_long_term"] + selected["current_maturities"]
            long = get(bs, ["Long Term Debt"], col, prefix + "long_debt")
            current = get(
                bs,
                [
                    "Current Portion Of Long Term Debt",
                    "Current Portion Of Long-Term Debt",
                ],
                col,
                prefix + "current_portion",
            )
            return long + current

        leverage = ratio(debt(period, ""), avg)
        leverage_prev = ratio(debt(prev_period, "prior_"), prior_avg)
        f5 = compare(leverage_prev, leverage)
        ca = get(
            bs, ["Current Assets", "Total Current Assets"], period, "current_assets"
        )
        cl = get(
            bs,
            ["Current Liabilities", "Total Current Liabilities"],
            period,
            "current_liabilities",
        )
        ca_prev = get(
            bs,
            ["Current Assets", "Total Current Assets"],
            prev_period,
            "prior_current_assets",
        )
        cl_prev = get(
            bs,
            ["Current Liabilities", "Total Current Liabilities"],
            prev_period,
            "prior_current_liabilities",
        )
        liquidity = ratio(ca, cl)
        f6 = compare(liquidity, ratio(ca_prev, cl_prev))
        issued = get(
            cf,
            ["Issuance Of Capital Stock", "Common Stock Issuance"],
            period,
            "gross_equity_issuance",
        )
        f7 = int(issued == 0) if math.isfinite(issued) and issued >= 0 else None
        gp = get(inc, ["Gross Profit"], period, "gross_profit")
        gp_prev = get(inc, ["Gross Profit"], prev_period, "prior_gross_profit")
        revenue = get(inc, ["Total Revenue", "Revenue"], period, "revenue")
        revenue_prev = get(
            inc, ["Total Revenue", "Revenue"], prev_period, "prior_revenue"
        )
        margin = ratio(gp, revenue)
        f8 = compare(margin, ratio(gp_prev, revenue_prev))
        # Paper prose says opening assets; Table1 says average. Choose Table1 explicitly.
        turnover = ratio(revenue, avg)
        f9 = compare(turnover, ratio(revenue_prev, prior_avg))
        signals = dict(
            zip(
                [
                    "F1_positive_roa",
                    "F2_positive_cfo",
                    "F3_roa_increasing",
                    "F4_accruals_quality",
                    "F5_leverage_decreasing",
                    "F6_liquidity_improving",
                    "F7_no_dilution",
                    "F8_gross_margin_improving",
                    "F9_asset_turnover_improving",
                ],
                [f1, f2, f3, f4, f5, f6, f7, f8, f9],
            )
        )
        known = [v for v in signals.values() if v is not None]
        if not known and not any(math.isfinite(v) for v in (ni, ta, cfo)):
            return None
        score = sum(known) if len(known) == 9 else None
        return {
            "f_score": score,
            "f_score_partial": sum(known),
            "signals_assessable": len(known),
            "signals": signals,
            "interpretation": (
                self._interpret(score)
                if score is not None
                else f"Not assessable ({len(known)} of 9 signals)"
            ),
            "roa": self._fmt(roa),
            "cfo_to_assets": self._fmt(cfo_ratio),
            "current_ratio": self._fmt(liquidity),
            "gross_margin": self._fmt(margin),
            "asset_turnover": self._fmt(turnover),
            "period_basis": basis(period),
            "turnover_convention": "average total assets (Table1); paper prose uses opening assets, not uniquely settled",
            "input_proxies": (
                ["Net Income proxy for pre-extraordinary income"]
                if sources["income"] == "Net Income"
                else []
            )
            + [
                "Gross reported equity cash proceeds proxy; noncash issuance is not established by this row"
            ],
            "signal_definitions": {
                "F7_no_dilution": "Legacy key: no gross reported equity cash proceeds (proxy); noncash issuance not established; share-count/net-issuance proxies are not used"
            },
            "denominators": {
                "opening_assets": self._fmt(opening, 0),
                "prior_opening_assets": self._fmt(prior_opening, 0),
                "average_assets": self._fmt(avg, 0),
                "prior_average_assets": self._fmt(prior_avg, 0),
            },
            "source_rows": sources,
            "debt_input_audit": debt_audit,
            "leverage_input_status": (
                "Selected non-lease primary debt; provider average-assets controls matched; source availability recorded"
                if debt_audit
                and math.isfinite(leverage)
                and math.isfinite(leverage_prev)
                else (
                    "Withheld: selected debt needs compatible adjacent asset/debt controls"
                    if debt_audit
                    else "Exact provider maturity rows required; generic Current Debt/leases are not aliases"
                )
            ),
        }

    def _interpret(self, score):
        return "Strong" if score >= 8 else "Moderate" if score >= 5 else "Weak"
