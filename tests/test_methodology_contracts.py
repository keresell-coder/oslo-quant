"""Independent arithmetic and presentation acceptance for versioned method correction."""

import math
from copy import deepcopy
from pathlib import Path
import json
import pandas as pd
import pytest
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.altman import AltmanFramework
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.primary_financials import load_primary
from oslo_quant.primary_adapter import apply_primary_current
from oslo_quant import report


def statements():
    bs = pd.DataFrame(
        {
            "2024": {
                "Total Assets": 150,
                "Current Assets": 70,
                "Cash And Cash Equivalents": 15,
                "Current Liabilities": 35,
                "Current Debt": 5,
                "Income Tax Payable": 3,
                "Long Term Debt": 15,
                "Current Portion Of Long Term Debt": 3,
                "Stockholders Equity": 75,
                "Total Liabilities Net Minority Interest": 75,
                "Retained Earnings": 30,
            },
            "2023": {
                "Total Assets": 100,
                "Current Assets": 50,
                "Cash And Cash Equivalents": 10,
                "Current Liabilities": 30,
                "Current Debt": 8,
                "Income Tax Payable": 2,
                "Long Term Debt": 20,
                "Current Portion Of Long Term Debt": 5,
                "Stockholders Equity": 60,
                "Total Liabilities Net Minority Interest": 40,
                "Retained Earnings": 20,
            },
            "2022": {"Total Assets": 80},
        }
    )
    inc = pd.DataFrame(
        {
            "2024": {
                "Total Revenue": 160,
                "Gross Profit": 80,
                "Net Income": 12,
                "EBIT": 20,
            },
            "2023": {
                "Total Revenue": 100,
                "Gross Profit": 40,
                "Net Income": 7,
                "EBIT": 12,
            },
        }
    )
    cf = pd.DataFrame(
        {
            "2024": {
                "Operating Cash Flow": 15,
                "Issuance Of Capital Stock": 0,
                "Depreciation And Amortization": 4,
            },
            "2023": {
                "Operating Cash Flow": 10,
                "Issuance Of Capital Stock": 0,
                "Depreciation And Amortization": 3,
            },
        }
    )
    return dict(
        balance_sheet=bs,
        income_stmt=inc,
        cash_flow=cf,
        prices=pd.DataFrame(),
        meta={"fx_to_usd": 1},
    )


def test_piotroski_independent_nine_signal_control():
    p = PiotroskiFramework().compute(statements(), "CONTROL")["periods"]["2024"]
    # Opening assets100 gives ROA.12/CFO.15; prior ROA7/80=.0875.
    assert p["roa"] == 0.12 and p["cfo_to_assets"] == 0.15
    assert p["denominators"] == {
        "opening_assets": 100.0,
        "prior_opening_assets": 80.0,
        "average_assets": 125.0,
        "prior_average_assets": 90.0,
    }
    assert p["asset_turnover"] == pytest.approx(160 / 125, abs=0.0001)
    assert p["signals"] == dict(zip(p["signals"], [1] * 9)) and p["f_score"] == 9
    assert "average total assets" in p["turnover_convention"]
    assert "Net Income proxy" in p["input_proxies"][0]


def test_no_current_equals_previous_or_skipped_year_fallback():
    s = statements()
    s["balance_sheet"] = s["balance_sheet"].drop(columns="2023")
    p = PiotroskiFramework().compute(s, "CONTROL")["periods"]["2024"]
    for key in [
        "F1_positive_roa",
        "F3_roa_increasing",
        "F4_accruals_quality",
        "F5_leverage_decreasing",
        "F6_liquidity_improving",
        "F8_gross_margin_improving",
        "F9_asset_turnover_improving",
    ]:
        assert p["signals"][key] is None
    assert p["f_score"] is None


def test_share_count_and_net_issuance_cannot_prove_no_equity_offer():
    s = statements()
    s["cash_flow"] = s["cash_flow"].drop(index="Issuance Of Capital Stock")
    s["balance_sheet"].loc["Share Issued"] = [100, 100, 100]
    s["cash_flow"].loc["Net Common Stock Issuance"] = [-5, -10]
    assert (
        PiotroskiFramework().compute(s, "CONTROL")["periods"]["2024"]["signals"][
            "F7_no_dilution"
        ]
        is None
    )


def test_original_sloan_bs_identity_and_exact_missing_components():
    s = statements()
    p = SloanFramework().compute(s, "CONTROL")["periods"]["2024"]
    # delta CA20-cash5; minus(delta CL5-debt(-3)-tax1); minusD&A4 =4; avgTA125.
    assert p["bs_accruals"] == 4 and p["bs_accrual_ratio"] == 0.032
    assert p["cfo_accrual_ratio"] == -0.024
    assert p["earnings_quality"] == "Unrated diagnostic"
    s["balance_sheet"] = s["balance_sheet"].drop(index="Income Tax Payable")
    p = SloanFramework().compute(s, "CONTROL")["periods"]["2024"]
    assert p["bs_accrual_ratio"] is None and "income_taxes_payable" in p["bs_status"]


def test_equivalents_only_cannot_establish_total_cash_for_sloan_bs():
    s = statements()
    # Cash equivalents can exclude cash itself, so this is not a total-cash alias.
    s["balance_sheet"] = s["balance_sheet"].rename(
        index={"Cash And Cash Equivalents": "Cash Equivalents"}
    )
    p = SloanFramework().compute(s, "CONTROL")["periods"]["2024"]
    assert p["bs_accruals"] is None
    assert p["bs_accrual_ratio"] is None
    assert p["bs_status"].startswith("withheld:")
    assert "cash" in p["bs_status"] and "prior_cash" in p["bs_status"]
    assert p["source_rows"]["cash"] is None
    assert p["source_rows"]["prior_cash"] is None
    # The independent NI-minus-CFO diagnostic remains usable.
    assert p["cfo_accruals"] == -3
    assert p["cfo_accrual_ratio"] == -.024
    assert p["methods_divergence"] is None
    assert p["methods_diverge_materially"] is False


def test_sloan_warning_in_summary_detail_and_guide_even_legacy_data():
    p = {
        "2024": {
            "cfo_accrual_ratio": -0.02,
            "bs_accrual_ratio": 0.15,
            "methods_divergence": 0.17,
            "methods_diverge_materially": True,
            "bs_status": "available exact-component identity",
        }
    }
    data = {"sloan": {"periods": p}}
    assert "Methods diverge" in report._summary_row("NOD.OL", data)
    assert "Methods diverge" in report._sloan_rows(p, ["2024"])
    assert "methods diverge" in report._company_summary("NOD.OL", data)
    assert "durable" in report._sloan_rows(p, ["2024"])


def test_altman_active_double_prime_exactly_preserved_original_withheld():
    p = AltmanFramework().compute(statements(), "CONTROL")["periods"]["2024"]
    expected = (
        6.56 * (70 - 35) / 150 + 3.26 * 30 / 150 + 6.72 * 20 / 150 + 1.05 * 75 / 75
    )
    assert p["z_score_prime"] == pytest.approx(expected, abs=0.0001)
    assert p["z_score"] is None and "market equity" in p["original_reference_status"]
    assert "Withheld" in report._altman_rows({"2024": {**p, "z_score": 999}}, ["2024"])


def test_ohlson_no_probability_or_risk_band_even_legacy_saved_data():
    p = OhlsonFramework().compute(statements(), "CONTROL")["periods"]["2024"]
    assert p["o_score"] is not None and p["bankruptcy_probability"] is None
    assert p["size_authentication"].startswith("open:")
    old = {
        "2024": {
            "o_score": -3.4484,
            "bankruptcy_probability": 0.0308,
            "interpretation": "Low distress risk",
        }
    }
    assert "3.1%" not in report._ohlson_rows(old, ["2024"])
    assert "risk band" in report._ohlson_rows(old, ["2024"])
    assert "low distress" not in report._company_summary(
        "NOD.OL", {"ohlson": {"periods": old}}
    )


def test_nod_interim_real_primary_numbers_common_opening_denominator():
    primary = load_primary(
        "NOD.OL", Path(__file__).parents[1] / "data/primary", download=False
    )
    annual = {
        key: pd.DataFrame() for key in ["income_stmt", "balance_sheet", "cash_flow"]
    }
    for r in primary["records"]:
        if r["period_end"] == "2025-12-31" and r["scope"] in ["annual", "instant"]:
            annual[r["statement"]].loc[r["row"], "2025"] = r["value_units"]
    annual["prices"] = pd.DataFrame()
    selected, _ = apply_primary_current(annual, primary, "USD")
    p = PiotroskiFramework().compute(selected, "NOD.OL")["periods"]["LTM 2026-09"]
    assert p["roa"] == pytest.approx(58174000 / 983361000, abs=0.0001)
    assert p["cfo_to_assets"] == pytest.approx(39938000 / 983361000, abs=0.0001)
    assert "overlapping" in p["period_basis"]
    assert p["signals"]["F5_leverage_decreasing"] is None


def test_publi_currency_invariance_and_missing_opening_balance():
    # Issuer FY25 group NI485/CFO825/assets51714m SEK; opening/other rows are
    # explicitly synthetic controls, not claimed reconciled issuer comparatives.
    s = statements()
    s["income_stmt"].loc["Net Income", "2024"] = 485
    s["cash_flow"].loc["Operating Cash Flow", "2024"] = 825
    s["balance_sheet"].loc["Total Assets", "2024"] = 51714
    s["balance_sheet"].loc["Total Assets", "2023"] = 40000
    for key, value in s.items():
        if isinstance(value, pd.DataFrame):
            s[key] = value.rename(
                columns={"2024": "2025", "2023": "2024", "2022": "2023"}
            )
    a = PiotroskiFramework().compute(s, "PUBLI.OL")["periods"]["2025"]
    assert a["roa"] == pytest.approx(485 / 40000, abs=0.0001)
    assert a["cfo_to_assets"] == pytest.approx(825 / 40000, abs=0.0001)
    scaled = {
        k: v * 1000000 if isinstance(v, pd.DataFrame) else v for k, v in s.items()
    }
    b = PiotroskiFramework().compute(scaled, "PUBLI.OL")["periods"]["2025"]
    assert a["signals"] == b["signals"]
