"""Ohlson O-Score — bankruptcy probability (logistic model, 1980).

Key calibration notes
---------------------
* Calibrated on US industrial firms 1970–1976 (Compustat). Not designed for
  Scandinavian / European companies or capital-intensive sectors.

* SIZE variable fix: the original formula uses ln(Total Assets / GNP price-level
  index), where the GNP deflator ≈ 1.0–1.5 over the sample period (base 1968).
  Assets were expressed in raw dollars, so SIZE ≈ ln(dollars) − small constant.
  For modern companies this is approximated as ln(Total Assets in millions),
  i.e. dividing by 1e6.  Using 1e9 (a common implementation error) understates
  SIZE by ln(1000) ≈ 6.9 points, inflating the O-Score by ~2.8 and driving
  apparent bankruptcy probabilities 35–60 percentage points too high.
  (Begley, Ming & Watts 1996; Hillegeist et al. 2004; Chava & Jarrow 2004)

* Structural overestimation for capital-intensive sectors: shipping, offshore
  drilling, real estate, and aquaculture companies carry high leverage by design
  (secured against physical assets), so the TLTA term (+6.03) systematically
  overstates distress risk. Treat O-Score as a relative, directional signal
  within a peer group — not as an absolute bankruptcy probability.

* Interpretation thresholds are set conservatively relative to the original model
  to reflect the lower empirical base rate of bankruptcy for large listed
  Norwegian companies (< 1% p.a.) vs Ohlson's training sample (~7%).
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from oslo_quant.fetchers.base import Statements
from oslo_quant.frameworks.base import BaseFramework

# SIZE = ln(Total Assets / GNP deflator).
# Academic replications express Total Assets in millions of dollars (÷1e6).
# This is consistent with Begley et al. (1996) and most peer-reviewed work.
_GNP_DIVISOR = 1_000_000  # express assets in millions


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

        periods = self._periods(inc)
        results: dict[str, Any] = {}

        for period in periods:
            all_periods = self._periods(inc)
            try:
                prev_period = all_periods[all_periods.index(period) + 1]
            except (ValueError, IndexError):
                prev_period = None

            metrics = self._compute_period(bs, inc, cf, period, prev_period)
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
        self,
        bs: Any, inc: Any, cf: Any,
        period: str, prev_period: str | None,
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
        wc     = (current_assets if not math.isnan(current_assets) else 0) - \
                 (current_liab   if not math.isnan(current_liab)   else 0)
        wc_ta  = self._safe_div(wc, total_assets)
        cl_ca  = self._safe_div(current_liab, current_assets)
        ni_ta  = self._safe_div(net_income, total_assets)
        cfo_tl = self._safe_div(cfo, total_liab)

        # OENEG: 1 if total liabilities exceed total assets
        oeneg = 1 if (not math.isnan(tl_ta) and tl_ta > 1) else 0

        # INTWO: 1 if net income negative in both current and prior year
        intwo = 0
        if not math.isnan(net_income) and not math.isnan(net_income_prev):
            intwo = 1 if (net_income < 0 and net_income_prev < 0) else 0

        # CHIN: normalised change in net income
        chin = float("nan")
        if not math.isnan(net_income) and not math.isnan(net_income_prev):
            denom = abs(net_income) + abs(net_income_prev)
            chin = self._safe_div(net_income - net_income_prev, denom) if denom != 0 else float("nan")

        # SIZE = ln(Total Assets in millions).
        # Original formula: ln(TA / GNP_deflator). With the 1970s deflator ≈ 1.0,
        # this was effectively ln(TA in raw dollars). Expressing in millions is the
        # standard modern approximation (Begley et al. 1996).
        log_ta_gnp = (
            math.log(total_assets / _GNP_DIVISOR)
            if not math.isnan(total_assets) and total_assets > 0
            else float("nan")
        )

        c = self._COEF
        o_score = (
            c["intercept"]
            + c["log_ta_gnp"] * (log_ta_gnp if not math.isnan(log_ta_gnp) else 0)
            + c["tl_ta"]      * (tl_ta      if not math.isnan(tl_ta)      else 0)
            + c["wc_ta"]      * (wc_ta      if not math.isnan(wc_ta)      else 0)
            + c["cl_ca"]      * (cl_ca      if not math.isnan(cl_ca)      else 0)
            + c["oeneg"]      * oeneg
            + c["ni_ta"]      * (ni_ta      if not math.isnan(ni_ta)      else 0)
            + c["cfo_tl"]     * (cfo_tl     if not math.isnan(cfo_tl)     else 0)
            + c["intwo"]      * intwo
            + c["chin"]       * (chin       if not math.isnan(chin)       else 0)
        )

        prob = 1 / (1 + math.exp(-o_score)) if not math.isnan(o_score) else float("nan")

        return {
            "o_score":                self._fmt(o_score),
            "bankruptcy_probability": self._fmt(prob),
            "interpretation":         self._interpret(prob),
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

    def _interpret(self, prob: float) -> str:
        if math.isnan(prob):
            return "Unknown"
        if prob < 0.05:
            return "Low distress risk"
        if prob < 0.20:
            return "Moderate distress risk"
        return "High distress risk"
