"""Tests for HTML report generator."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from oslo_quant.report import generate, _load_results, _summary_row, _detail_card


def _fake_results():
    return {
        "TEL.OL": {
            "dupont": {
                "ticker": "TEL.OL", "framework": "dupont",
                "periods": {
                    "2023": {
                        "roe_3factor": 0.12, "net_profit_margin": 0.08,
                        "asset_turnover": 0.45, "equity_multiplier": 3.2,
                        "ebit_margin": 0.11, "tax_burden": 0.78, "interest_burden": 0.92,
                        "roe_5factor": 0.12,
                    }
                },
            },
            "piotroski": {
                "ticker": "TEL.OL", "framework": "piotroski",
                "periods": {
                    "2023": {
                        "f_score": 7, "interpretation": "Moderate",
                        "signals": {
                            "F1_positive_roa": 1, "F2_positive_cfo": 1,
                            "F3_roa_increasing": 1, "F4_accruals_quality": 1,
                            "F5_leverage_decreasing": 1, "F6_liquidity_improving": 0,
                            "F7_no_dilution": 1, "F8_gross_margin_improving": 1,
                            "F9_asset_turnover_improving": 0,
                        },
                        "current_ratio": 1.5, "gross_margin": 0.40,
                    }
                },
            },
            "sloan": {
                "ticker": "TEL.OL", "framework": "sloan",
                "periods": {
                    "2023": {
                        "earnings_quality": "High",
                        "cfo_accrual_ratio": -0.03,
                        "bs_accrual_ratio": -0.02,
                        "operating_cash_flow": 5_000_000,
                        "net_income": 3_000_000,
                    }
                },
            },
            "ohlson": {
                "ticker": "TEL.OL", "framework": "ohlson",
                "periods": {
                    "2023": {
                        "o_score": -2.1,
                        "bankruptcy_probability": 0.11,
                        "interpretation": "Moderate distress risk",
                        "inputs": {"tl_ta": 0.5, "wc_ta": 0.12, "ni_ta": 0.05, "cfo_tl": 0.18},
                    }
                },
            },
            "altman": {
                "ticker": "TEL.OL", "framework": "altman",
                "periods": {
                    "2023": {
                        "z_score": 2.5, "zone": "Grey",
                        "x1_working_capital_to_assets": 0.14,
                        "x2_retained_earnings_to_assets": 0.22,
                        "x3_ebit_to_assets": 0.08,
                        "x4_equity_to_liabilities": 0.6,
                        "x5_revenue_to_assets": 0.45,
                        "market_cap_used": True, "market_cap": 50_000_000,
                    }
                },
            },
        }
    }


class TestReportGeneration:
    def test_generate_creates_file(self, tmp_path):
        fake = _fake_results()
        with patch("oslo_quant.report._load_results", return_value=fake):
            out = generate(output_path=tmp_path / "index.html")
        assert out.exists()
        assert out.stat().st_size > 0

    def test_html_has_expected_content(self, tmp_path):
        fake = _fake_results()
        with patch("oslo_quant.report._load_results", return_value=fake):
            out = generate(output_path=tmp_path / "index.html")
        html = out.read_text()
        assert "TEL.OL" in html
        assert "Oslo Quant Dashboard" in html
        assert "Piotroski" in html
        assert "Altman" in html
        assert "DuPont" in html

    def test_badges_rendered(self, tmp_path):
        fake = _fake_results()
        with patch("oslo_quant.report._load_results", return_value=fake):
            out = generate(output_path=tmp_path / "index.html")
        html = out.read_text()
        assert "F7" in html       # piotroski score badge
        assert "Grey" in html     # altman zone
        assert "High" in html     # sloan quality

    def test_empty_results_no_crash(self, tmp_path):
        with patch("oslo_quant.report._load_results", return_value={}):
            out = generate(output_path=tmp_path / "index.html")
        assert out.exists()
