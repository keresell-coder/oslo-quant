"""Experimental adapted Ohlson index, not a calibrated bankruptcy probability.

Coefficients and current USD-millions SIZE arithmetic are retained for continuity.
The original SIZE/GNP convention is unauthenticated; no replacement is asserted.
Current FX applied to historical assets is an adaptation. No risk bands/calibration
or predictive validity for this population/horizon is established.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework
from oslo_quant.frameworks.methodology import VERSION

_GNP_DIVISOR = 1_000_000  # retained adaptation; original SIZE authentication remains open


class OhlsonFramework(BaseFramework):
    name = "ohlson"

    # Ohlson (1980) logistic coefficients
    _COEF = {
        "intercept": -1.32,
        "log_ta_gnp":  -0.407,
        "tl_ta":        6.03,
        "wc_ta":       -1.43,
        "cl_ca":        0.0757,
        "oeneg":       -1.72,
        "ni_ta":       -2.37,
        "cfo_tl":      -1.83,
        "intwo":        0.285,
        "chin":        -0.521,
    }

    def compute(self, stmts: Statements, ticker: str) -> dict[str, Any]:
        bs  = stmts["balance_sheet"]
        inc = stmts["income_stmt"]
        cf  = stmts["cash_flow"]

        # FX for the SIZE term (2026-08 fix): assets must be expressed in a
        # common currency before taking logs, otherwise USD/EUR reporters carry
        # a structural O-score penalty (~+0.96 for USD, ~+1.00 for EUR at 2026
        # rates) purely from currency units. The pipeline supplies the current
        # reporting-currency→USD rate; USD is the model's original basis.
        # Applying today's spot rate to historical years is a disclosed
        # approximation, not authenticated historical SIZE or predictive calibration.
        fx_to_usd = stmts.get("meta", {}).get("fx_to_usd")  # type: ignore[union-attr]

        periods = self._periods(inc, anchor="Total Revenue")
        results: dict[str, Any] = {}

        for period in periods:
            all_periods = self._periods(inc, anchor="Total Revenue")
            try:
                prev_period = all_periods[all_periods.index(period) + 1]
            except (ValueError, IndexError):
                prev_period = None

            metrics = self._compute_period(bs, inc, cf, period, prev_period, fx_to_usd)
            if metrics:
                results[period] = metrics

        return {
            "ticker":      ticker,
            "framework":   self.name,
            "computed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "methodology_version": VERSION,
            "periods":     results,
        }

    # ------------------------------------------------------------------

    def _compute_period(
        self,
        bs: Any, inc: Any, cf: Any,
        period: str, prev_period: str | None,
        fx_to_usd: float | None = None,
    ) -> dict[str, Any] | None:
        total_assets = self._get(bs, "Total Assets", col=period)
        total_liab   = self._get(
            bs, "Total Liabilities Net Minority Interest", "Total Liabilities", col=period
        )
        current_assets = self._get(bs, "Current Assets", "Total Current Assets", col=period)
        current_liab   = self._get(
            bs, "Current Liabilities", "Total Current Liabilities", col=period
        )
        net_income = self._get(inc, "Net Income", col=period)
        net_income_prev = (
            self._get(inc, "Net Income", col=prev_period) if prev_period else float("nan")
        )
        cfo = self._get(
            cf, "Operating Cash Flow", "Total Cash From Operating Activities",
            "Cash Flow From Continuing Operating Activities", col=period
        )

        tl_ta  = self._safe_div(total_liab, total_assets)
        # No zero-substitution — missing current assets/liabilities means
        # working capital is unknown, not zero (2026-08 restatement).
        wc = (
            current_assets - current_liab
            if not math.isnan(current_assets) and not math.isnan(current_liab)
            else float("nan")
        )
        wc_ta  = self._safe_div(wc, total_assets)
        cl_ca  = self._safe_div(current_liab, current_assets)
        ni_ta  = self._safe_div(net_income, total_assets)
        cfo_tl = self._safe_div(cfo, total_liab)

        # OENEG: 1 if total liabilities exceed total assets
        oeneg = int(tl_ta > 1) if math.isfinite(tl_ta) else None

        # INTWO: 1 if net income negative in both current and prior year
        intwo = None
        if not math.isnan(net_income) and not math.isnan(net_income_prev):
            intwo = 1 if (net_income < 0 and net_income_prev < 0) else 0

        # CHIN: normalised change in net income
        chin = float("nan")
        if not math.isnan(net_income) and not math.isnan(net_income_prev):
            denom = abs(net_income) + abs(net_income_prev)
            chin = self._safe_div(net_income - net_income_prev, denom) if denom != 0 else float("nan")

        # Retained experimental SIZE = ln(Total Assets in millions of USD).
        # Original SIZE/GNP convention remains open; this arithmetic is retained
        # solely as the existing experimental adaptation.
        # converting to USD first keeps the term comparable across NOK/SEK/EUR/USD
        # reporters. No FX rate → SIZE unknown → score Not assessable.
        log_ta_gnp = (
            math.log(total_assets * fx_to_usd / _GNP_DIVISOR)
            if (fx_to_usd is not None and not math.isnan(total_assets)
                and total_assets > 0 and fx_to_usd > 0)
            else float("nan")
        )

        # Missing-input policy (2026-08 restatement): the logistic score is
        # only computed when every continuous term is present. Substituting 0
        # for missing terms previously produced an identical default
        # probability (21.08%) for every company with an empty period —
        # a model artifact presented as company information.
        c = self._COEF
        required = (log_ta_gnp, tl_ta, wc_ta, cl_ca, ni_ta, cfo_tl, chin)
        if any(math.isnan(v) for v in required):
            if all(math.isnan(v) for v in (tl_ta, wc_ta, cl_ca, ni_ta, cfo_tl)):
                return None  # nothing assessable at all — drop the period
            o_score = float("nan")
        else:
            o_score = (
                c["intercept"]
                + c["log_ta_gnp"] * log_ta_gnp
                + c["tl_ta"]      * tl_ta
                + c["wc_ta"]      * wc_ta
                + c["cl_ca"]      * cl_ca
                + c["oeneg"]      * oeneg
                + c["ni_ta"]      * ni_ta
                + c["cfo_tl"]     * cfo_tl
                + c["intwo"]      * intwo
                + c["chin"]       * chin
            )

        return {
            "o_score":                self._fmt(o_score),
            "bankruptcy_probability": None,
            "probability_status": "withheld: uncalibrated adaptation; no population/event/horizon validation",
            "size_authentication": "open: retained USD-millions/current-FX convention is not authenticated as original SIZE",
            "interpretation": "Not assessable" if math.isnan(o_score) else "Experimental adapted index; no probability or risk band",
            "inputs": {
                "tl_ta":  self._fmt(tl_ta),
                "wc_ta":  self._fmt(wc_ta),
                "cl_ca":  self._fmt(cl_ca),
                "oeneg":  oeneg,
                "ni_ta":  self._fmt(ni_ta),
                "cfo_tl": self._fmt(cfo_tl),
                "intwo":  intwo,
                "chin":   self._fmt(chin),
            },
        }

    def _interpret(self, value):
        return "Not assessable" if math.isnan(value) else "Experimental adapted index; uncalibrated"
