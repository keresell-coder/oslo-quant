"""Regression tests for the 2026-08 field-resolution restatement.

These tests use the real yfinance row vocabulary and row order (see
``make_yfinance_like_statements``). Every test here fails against the old
substring-first resolver — they lock in exact-match-first resolution and the
missing-input ("Not assessable", never zero) policy.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tests.fixtures import make_yfinance_like_statements
from oslo_quant.frameworks.base import BaseFramework
from oslo_quant.frameworks.dupont import DuPontFramework
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.frameworks.altman import AltmanFramework

TICKER = "TEST.OL"


class _Dummy(BaseFramework):
    def compute(self, stmts, ticker):  # pragma: no cover
        return {}


class TestGetResolution:
    """BaseFramework._get must prefer exact row names over substrings."""

    def setup_method(self):
        self.fw = _Dummy()
        self.inc = make_yfinance_like_statements()["income_stmt"]
        self.bs = make_yfinance_like_statements()["balance_sheet"]

    def test_ebit_is_not_normalized_ebitda(self):
        assert self.fw._get(self.inc, "EBIT", "Operating Income") == 500_000

    def test_current_assets_is_not_non_current(self):
        assert self.fw._get(self.bs, "Current Assets", "Total Current Assets") == 1_500_000

    def test_current_liabilities_is_not_non_current(self):
        assert self.fw._get(
            self.bs, "Current Liabilities", "Total Current Liabilities"
        ) == 800_000

    def test_net_income_is_not_continuing_operations(self):
        assert self.fw._get(self.inc, "Net Income") == 320_000

    def test_retained_earnings_is_not_gains_losses_row(self):
        assert self.fw._get(
            self.bs, "Retained Earnings", "Retained Earnings Deficit"
        ) == 1_200_000

    def test_substring_fallback_still_available(self):
        df = pd.DataFrame({"2023": [700.0]}, index=["EBIT (adjusted)"])
        assert self.fw._get(df, "EBIT") == 700.0

    def test_all_nan_column_dropped_from_periods(self):
        df = pd.DataFrame(
            {"2023": [1.0, 2.0], "2021": [float("nan"), float("nan")]},
            index=["A", "B"],
        )
        assert self.fw._periods(df) == ["2023"]


class TestFrameworksOnRealVocabulary:
    """End-to-end: each framework must produce exact-field outputs."""

    def setup_method(self):
        self.stmts = make_yfinance_like_statements()

    def test_dupont_ebit_margin_uses_exact_ebit(self):
        p = DuPontFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["ebit_margin"] - 500_000 / 3_000_000) < 1e-4
        assert p["net_income"] == 320_000

    def test_dupont_5factor_is_consistency_check(self):
        p = DuPontFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        # product of the five factors must reproduce NI / avg equity
        assert abs(p["roe_5factor"] - p["roe_3factor"]) < 1e-3

    def test_altman_x1_uses_true_working_capital(self):
        p = AltmanFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["x1_working_capital_to_assets"] - (1_500_000 - 800_000) / 5_000_000) < 1e-4

    def test_altman_x2_uses_true_retained_earnings(self):
        p = AltmanFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["x2_retained_earnings_to_assets"] - 1_200_000 / 5_000_000) < 1e-4

    def test_altman_x3_uses_exact_ebit(self):
        p = AltmanFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["x3_ebit_to_assets"] - 500_000 / 5_000_000) < 1e-4

    def test_ohlson_wc_ta_uses_current_rows(self):
        p = OhlsonFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["inputs"]["wc_ta"] - (1_500_000 - 800_000) / 5_000_000) < 1e-4
        assert abs(p["inputs"]["cl_ca"] - 800_000 / 1_500_000) < 1e-4

    def test_piotroski_current_ratio_is_current(self):
        p = PiotroskiFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert abs(p["current_ratio"] - 1_500_000 / 800_000) < 1e-4

    def test_sloan_net_income_is_total(self):
        p = SloanFramework().compute(self.stmts, TICKER)["periods"]["2023"]
        assert p["net_income"] == 320_000


class TestMissingInputPolicy:
    """Missing data must yield Not assessable — never zero or a default."""

    def test_altman_missing_retained_earnings_not_safe(self):
        stmts = make_yfinance_like_statements()
        bs = stmts["balance_sheet"].drop(
            index=["Retained Earnings", "Gains Losses Not Affecting Retained Earnings"]
        )
        stmts = dict(stmts, balance_sheet=bs)
        p = AltmanFramework().compute(stmts, TICKER)["periods"]["2023"]
        assert p["z_score_prime"] is None
        assert p["zone_prime"] == "Not assessable"
        assert p["z_score"] is None

    def test_empty_period_produces_no_distress_row(self):
        stmts = make_yfinance_like_statements(periods=["2023", "2022", "2021"])
        for key in ("balance_sheet", "income_stmt", "cash_flow"):
            df = stmts[key].copy()
            df["2021"] = np.nan
            stmts[key] = df
        for cls in (AltmanFramework, OhlsonFramework, DuPontFramework,
                    SloanFramework, PiotroskiFramework):
            result = cls().compute(stmts, TICKER)
            assert "2021" not in result["periods"], cls.__name__

    def test_ohlson_first_period_not_a_probability(self):
        # Oldest period has no prior year → CHIN/INTWO unavailable → no score.
        stmts = make_yfinance_like_statements()
        p = OhlsonFramework().compute(stmts, TICKER)["periods"]["2022"]
        assert p["bankruptcy_probability"] is None
        assert p["interpretation"] == "Not assessable"

    def test_piotroski_first_period_not_scored_zero(self):
        stmts = make_yfinance_like_statements()
        p = PiotroskiFramework().compute(stmts, TICKER)["periods"]["2022"]
        assert p["f_score"] is None
        assert p["signals_assessable"] < 9
        assert p["signals"]["F3_roa_increasing"] is None  # unavailable ≠ failed

    def test_piotroski_full_history_scores_all_nine(self):
        stmts = make_yfinance_like_statements()
        p = PiotroskiFramework().compute(stmts, TICKER)["periods"]["2023"]
        assert p["signals_assessable"] == 9
        assert p["f_score"] is not None
        assert 0 <= p["f_score"] <= 9

    def test_sloan_missing_cfo_is_unknown_not_scored(self):
        stmts = make_yfinance_like_statements()
        cf = stmts["cash_flow"].drop(
            index=["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]
        )
        stmts = dict(stmts, cash_flow=cf)
        p = SloanFramework().compute(stmts, TICKER)["periods"]["2023"]
        assert p["cfo_accrual_ratio"] is None
        assert p["earnings_quality"] == "Unknown"
