"""Shared test fixtures — minimal synthetic financial statements."""

from __future__ import annotations

import numpy as np
import pandas as pd

from oslo_quant.fetchers.base import Statements


def make_statements(periods: list[str] | None = None) -> Statements:
    """Return a minimal Statements dict with plausible values."""
    if periods is None:
        periods = ["2023", "2022"]

    n = len(periods)

    # Base values for each row, scaled by period index so earlier periods are smaller
    def _col(base: float, growth: float = 0.1) -> list[float]:
        return [base * (1 - growth * i) for i in range(n)]

    bs_data = {
        "Total Assets": _col(5_000_000),
        "Current Assets": _col(1_500_000),
        "Current Liabilities": _col(800_000),
        "Total Liabilities Net Minority Interest": _col(2_500_000),
        "Stockholders Equity": _col(2_500_000),
        "Retained Earnings": _col(1_200_000),
        "Long Term Debt": _col(1_200_000),
        "Cash And Cash Equivalents": _col(400_000),
        "Ordinary Shares Number": _col(100_000_000, growth=0.0),
    }

    inc_data = {
        "Total Revenue": _col(3_000_000),
        "Gross Profit": _col(1_200_000),
        "EBIT": _col(500_000),
        "Pretax Income": _col(420_000),
        "Net Income": _col(320_000),
        "Interest Expense": _col(-80_000),
    }

    cf_data = {
        "Operating Cash Flow": _col(480_000),
        "Capital Expenditure": _col(-150_000),
    }

    bs = pd.DataFrame(bs_data, index=periods).T
    inc = pd.DataFrame(inc_data, index=periods).T
    cf = pd.DataFrame(cf_data, index=periods).T

    prices_idx = pd.date_range("2022-01-01", "2024-01-01", freq="ME")
    prices = pd.DataFrame(
        {
            "Open": np.full(len(prices_idx), 45.0),
            "High": np.full(len(prices_idx), 50.0),
            "Low": np.full(len(prices_idx), 40.0),
            "Close": np.full(len(prices_idx), 47.0),
            "Volume": np.full(len(prices_idx), 1_000_000),
        },
        index=prices_idx,
    )

    return {
        "balance_sheet": bs,
        "income_stmt": inc,
        "cash_flow": cf,
        "prices": prices,
    }
