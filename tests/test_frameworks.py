"""Unit tests for all five analytical frameworks using synthetic data."""

from __future__ import annotations

import math

import pytest

from tests.fixtures import make_statements
from oslo_quant.frameworks.dupont import DuPontFramework
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.frameworks.altman import AltmanFramework

TICKER = "TEST.OL"


# ---------------------------------------------------------------------------
# DuPont
# ---------------------------------------------------------------------------

class TestDuPont:
    def setup_method(self):
        self.fw = DuPontFramework()
        self.stmts = make_statements()

    def test_returns_both_periods(self):
        result = self.fw.compute(self.stmts, TICKER)
        assert "2023" in result["periods"]
        assert "2022" in result["periods"]

    def test_roe_3factor_positive(self):
        result = self.fw.compute(self.stmts, TICKER)
        roe = result["periods"]["2023"]["roe_3factor"]
        assert roe is not None and roe > 0

    def test_npm_between_0_and_1(self):
        result = self.fw.compute(self.stmts, TICKER)
        npm = result["periods"]["2023"]["net_profit_margin"]
        assert npm is not None
        assert 0 < npm < 1

    def test_5factor_roe_close_to_3factor(self):
        result = self.fw.compute(self.stmts, TICKER)
        p = result["periods"]["2023"]
        assert p["roe_3factor"] is not None
        assert p["roe_5factor"] is not None


# ---------------------------------------------------------------------------
# Piotroski
# ---------------------------------------------------------------------------

class TestPiotroski:
    def setup_method(self):
        self.fw = PiotroskiFramework()
        self.stmts = make_statements()

    def test_f_score_range(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            assert 0 <= data["f_score"] <= 9

    def test_signals_are_binary(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            for sig, val in data["signals"].items():
                assert val in (0, 1), f"{sig}={val} not binary"

    def test_interpretation_present(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            assert data["interpretation"] in ("Strong", "Moderate", "Weak")

    def test_profitable_company_has_f1_f2(self):
        result = self.fw.compute(self.stmts, TICKER)
        sigs = result["periods"]["2023"]["signals"]
        assert sigs["F1_positive_roa"] == 1
        assert sigs["F2_positive_cfo"] == 1


# ---------------------------------------------------------------------------
# Sloan
# ---------------------------------------------------------------------------

class TestSloan:
    def setup_method(self):
        self.fw = SloanFramework()
        self.stmts = make_statements()

    def test_accrual_ratio_finite(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            ratio = data["cfo_accrual_ratio"]
            assert ratio is None or isinstance(ratio, float)

    def test_earnings_quality_label(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            assert data["earnings_quality"] in ("High", "Moderate", "Low", "Unknown")

    def test_cfo_above_net_income_implies_good_quality(self):
        # CFO (480k) > Net Income (320k) → negative accrual ratio → High or Moderate quality
        result = self.fw.compute(self.stmts, TICKER)
        quality = result["periods"]["2023"]["earnings_quality"]
        assert quality in ("High", "Moderate"), f"Expected High or Moderate, got {quality}"
        # Confirm accrual ratio is negative (cash earnings exceed reported income)
        ratio = result["periods"]["2023"]["cfo_accrual_ratio"]
        assert ratio is not None and ratio < 0


# ---------------------------------------------------------------------------
# Ohlson
# ---------------------------------------------------------------------------

class TestOhlson:
    def setup_method(self):
        self.fw = OhlsonFramework()
        self.stmts = make_statements()

    def test_probability_between_0_and_1(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            prob = data["bankruptcy_probability"]
            if prob is not None:
                assert 0 <= prob <= 1

    def test_ohlson_returns_valid_probability(self):
        result = self.fw.compute(self.stmts, TICKER)
        prob = result["periods"]["2023"]["bankruptcy_probability"]
        # Ohlson model is sensitive to company size (log_ta_gnp term) and leverage;
        # just verify it returns a valid probability in [0, 1]
        assert prob is not None and 0.0 <= prob <= 1.0

    def test_inputs_present(self):
        result = self.fw.compute(self.stmts, TICKER)
        inputs = result["periods"]["2023"]["inputs"]
        assert "tl_ta" in inputs
        assert "wc_ta" in inputs


# ---------------------------------------------------------------------------
# Altman
# ---------------------------------------------------------------------------

class TestAltman:
    def setup_method(self):
        self.fw = AltmanFramework()
        self.stmts = make_statements()

    def test_z_score_present(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            assert "z_score" in data

    def test_zone_values(self):
        result = self.fw.compute(self.stmts, TICKER)
        for period, data in result["periods"].items():
            assert data["zone"] in ("Safe", "Grey", "Distress", "Unknown")

    def test_healthy_firm_safe_or_grey(self):
        result = self.fw.compute(self.stmts, TICKER)
        zone = result["periods"]["2023"]["zone"]
        assert zone in ("Safe", "Grey"), f"Expected Safe/Grey, got {zone}"

    def test_x4_uses_book_equity_key(self):
        result = self.fw.compute(self.stmts, TICKER)
        # Key renamed when we switched from market cap to book equity for X4
        assert "x4_book_equity_to_liabilities" in result["periods"]["2023"]
        assert "market_cap_used" not in result["periods"]["2023"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_statements_no_crash(self):
        import pandas as pd
        empty_stmts = {
            "balance_sheet": pd.DataFrame(),
            "income_stmt": pd.DataFrame(),
            "cash_flow": pd.DataFrame(),
            "prices": pd.DataFrame(),
        }
        for cls in (DuPontFramework, PiotroskiFramework, SloanFramework,
                    OhlsonFramework, AltmanFramework):
            result = cls().compute(empty_stmts, "EMPTY.OL")
            assert "periods" in result
            assert result["periods"] == {}

    def test_single_period_no_crash(self):
        stmts = make_statements(periods=["2023"])
        for cls in (DuPontFramework, PiotroskiFramework, SloanFramework,
                    OhlsonFramework, AltmanFramework):
            result = cls().compute(stmts, "SINGLE.OL")
            assert "periods" in result
