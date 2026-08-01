"""Tests for LTM construction, the verified ledger, and the Ohlson FX fix."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from tests.fixtures import make_statements, make_yfinance_like_statements
from oslo_quant.ltm import build_ltm
from oslo_quant.verified import apply_ledger
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.altman import AltmanFramework

TICKER = "TEST.OL"


def _q_frames(dates: list[str], rev_per_q: float = 800_000):
    """Quarterly statements with the given period-end dates (newest first ok)."""
    inc = pd.DataFrame(
        {d: {"Total Revenue": rev_per_q, "EBIT": rev_per_q * 0.15,
             "Net Income": rev_per_q * 0.10, "Pretax Income": rev_per_q * 0.13,
             "Gross Profit": rev_per_q * 0.4} for d in dates}
    )
    cf = pd.DataFrame(
        {d: {"Operating Cash Flow": rev_per_q * 0.12,
             "Capital Expenditure": -rev_per_q * 0.05} for d in dates}
    )
    bs = pd.DataFrame(
        {d: {"Total Assets": 5_200_000, "Current Assets": 1_600_000,
             "Current Liabilities": 820_000,
             "Total Liabilities Net Minority Interest": 2_600_000,
             "Stockholders Equity": 2_600_000, "Retained Earnings": 1_250_000,
             "Long Term Debt": 1_150_000,
             "Cash And Cash Equivalents": 420_000,
             "Ordinary Shares Number": 100_000_000} for d in dates}
    )
    return {"income_stmt": inc, "cash_flow": cf, "balance_sheet": bs}


CONTIGUOUS = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]
GAPPED     = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"]  # Q3'25 missing
HALF_YEARS = ["2026-06-30", "2025-12-31", "2025-06-30"]
FY_IS_LATEST = ["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"]


class TestLtmConstruction:
    def setup_method(self):
        # Annual statements end FY2025 (fixture periods are labeled years).
        self.annual = make_yfinance_like_statements(periods=["2025", "2024"])

    def test_contiguous_quarters_build_ltm(self):
        stmts, status = build_ltm(self.annual, _q_frames(CONTIGUOUS), TICKER)
        assert status["built"] is True
        assert status["label"] == "LTM 2026-06"
        inc = stmts["income_stmt"]
        assert "LTM 2026-06" in inc.columns
        # 4 quarters × 800k
        assert inc.loc["Total Revenue", "LTM 2026-06"] == pytest.approx(3_200_000)
        # Balance sheet is point-in-time, not summed
        assert stmts["balance_sheet"].loc["Total Assets", "LTM 2026-06"] == 5_200_000

    def test_gapped_quarters_refuse_ltm(self):
        # KIT.OL case: missing Q3 2025 — a naive last-4 sum would be wrong.
        stmts, status = build_ltm(self.annual, _q_frames(GAPPED), TICKER)
        assert status["built"] is False
        assert "not contiguous" in status["detail"]
        assert not any(str(c).startswith("LTM") for c in stmts["income_stmt"].columns)

    def test_half_year_reporters_supported(self):
        stmts, status = build_ltm(self.annual, _q_frames(HALF_YEARS, rev_per_q=1_600_000), TICKER)
        assert status["built"] is True
        assert stmts["income_stmt"].loc["Total Revenue", "LTM 2026-06"] == pytest.approx(3_200_000)

    def test_fy_end_is_latest_skips_ltm(self):
        # The user-flagged instance: FY Q4 is the newest report; no new interim.
        stmts, status = build_ltm(self.annual, _q_frames(FY_IS_LATEST), TICKER)
        assert status["built"] is False
        assert "does not extend beyond FY2025" in status["detail"]

    def test_ltm_sorts_first_and_compares_against_fy(self):
        stmts, status = build_ltm(self.annual, _q_frames(CONTIGUOUS), TICKER)
        result = PiotroskiFramework().compute(stmts, TICKER)
        periods = sorted(result["periods"], reverse=True)
        assert periods[0] == "LTM 2026-06"   # virtual current year
        # LTM row exists and its YoY comparisons resolved against FY2025
        ltm = result["periods"]["LTM 2026-06"]
        assert ltm["signals"]["F6_liquidity_improving"] is not None

    def test_sloan_bs_method_suppressed_for_ltm(self):
        stmts, status = build_ltm(self.annual, _q_frames(CONTIGUOUS), TICKER)
        result = SloanFramework().compute(stmts, TICKER)
        ltm = result["periods"]["LTM 2026-06"]
        assert ltm["bs_accrual_ratio"] is None        # mismatched window
        assert ltm["cfo_accrual_ratio"] is not None   # 12-month flows fine


class TestVerifiedLedger:
    def _write_ledger(self, tmp_path, monkeypatch, ledger: dict):
        import oslo_quant.verified as verified
        monkeypatch.setattr(verified, "DATA_VERIFIED", tmp_path)
        (tmp_path / f"{TICKER}.json").write_text(json.dumps(ledger))

    def test_fill_missing_retained_earnings(self, tmp_path, monkeypatch):
        stmts = make_yfinance_like_statements(periods=["2025", "2024"])
        bs = stmts["balance_sheet"].drop(
            index=["Retained Earnings", "Gains Losses Not Affecting Retained Earnings"]
        )
        stmts = dict(stmts, balance_sheet=bs)
        # Without the ledger: Altman Not assessable (MOWI case)
        p = AltmanFramework().compute(stmts, TICKER)["periods"]["2025"]
        assert p["zone_prime"] == "Not assessable"

        self._write_ledger(tmp_path, monkeypatch, {
            "ticker": TICKER, "currency": "USD",
            "periods": {"2025": {"balance_sheet": {
                "Retained Earnings": {"value": 1_200_000,
                                       "source": "Annual Report 2025, p. 99"}}}},
        })
        stmts2, report = apply_ledger(stmts, TICKER, "USD")
        assert report["counts"]["filled"] == 1
        p2 = AltmanFramework().compute(stmts2, TICKER)["periods"]["2025"]
        assert p2["zone_prime"] in ("Safe", "Grey", "Distress")

    def test_verify_within_tolerance(self, tmp_path, monkeypatch):
        stmts = make_yfinance_like_statements(periods=["2025", "2024"])
        self._write_ledger(tmp_path, monkeypatch, {
            "ticker": TICKER, "currency": "USD",
            "periods": {"2025": {"income_stmt": {
                "Total Revenue": {"value": 3_010_000,   # 0.3% off — fine
                                   "source": "AR 2025"}}}},
        })
        _, report = apply_ledger(stmts, TICKER, "USD")
        assert report["counts"]["verified"] == 1
        assert report["counts"]["mismatch"] == 0

    def test_mismatch_is_flagged_not_overwritten(self, tmp_path, monkeypatch):
        stmts = make_yfinance_like_statements(periods=["2025", "2024"])
        self._write_ledger(tmp_path, monkeypatch, {
            "ticker": TICKER, "currency": "USD",
            "periods": {"2025": {"income_stmt": {
                "Total Revenue": {"value": 4_000_000,   # 25% off
                                   "source": "AR 2025"}}}},
        })
        stmts2, report = apply_ledger(stmts, TICKER, "USD")
        assert report["counts"]["mismatch"] == 1
        # yfinance value stays — mismatches are surfaced, not silently patched
        assert stmts2["income_stmt"].loc["Total Revenue", "2025"] == 3_000_000

    def test_currency_mismatch_blocks_ledger(self, tmp_path, monkeypatch):
        stmts = make_yfinance_like_statements(periods=["2025", "2024"])
        self._write_ledger(tmp_path, monkeypatch, {
            "ticker": TICKER, "currency": "NOK",
            "periods": {"2025": {"income_stmt": {
                "Total Revenue": {"value": 30_000_000, "source": "AR"}}}},
        })
        stmts2, report = apply_ledger(stmts, TICKER, "EUR")
        assert report["status"] == "currency_mismatch"
        assert stmts2["income_stmt"].loc["Total Revenue", "2025"] == 3_000_000


class TestOhlsonCurrency:
    def test_usd_and_nok_reporters_score_identically(self):
        """Same economics in different reporting currencies → same O-score."""
        usd = make_statements()
        usd["meta"] = {"fx_to_usd": 1.0, "reporting_currency": "USD"}
        p_usd = OhlsonFramework().compute(usd, TICKER)["periods"]["2023"]

        rate = 10.5  # NOK per USD
        nok = make_statements()
        for key in ("balance_sheet", "income_stmt", "cash_flow"):
            nok[key] = nok[key] * rate
        nok["meta"] = {"fx_to_usd": 1 / rate, "reporting_currency": "NOK"}
        p_nok = OhlsonFramework().compute(nok, TICKER)["periods"]["2023"]

        assert p_usd["o_score"] == pytest.approx(p_nok["o_score"], abs=1e-3)
        assert p_usd["bankruptcy_probability"] == pytest.approx(
            p_nok["bankruptcy_probability"], abs=1e-4)

    def test_missing_fx_means_not_assessable(self):
        stmts = make_statements()
        stmts["meta"] = {"fx_to_usd": None, "reporting_currency": "NOK"}
        p = OhlsonFramework().compute(stmts, TICKER)["periods"]["2023"]
        assert p["bankruptcy_probability"] is None
        assert p["interpretation"] == "Not assessable"


class TestLtmHollowColumn:
    def test_column_present_but_empty_refuses_ltm(self):
        """NOD.OL case: the Q3 date exists but its values are NaN."""
        annual = make_yfinance_like_statements(periods=["2025", "2024"])
        q = _q_frames(CONTIGUOUS)
        q["income_stmt"].loc[:, "2025-09-30"] = np.nan
        stmts, status = build_ltm(annual, q, TICKER)
        assert status["built"] is False
        assert "empty in at least one quarter" in status["detail"]
