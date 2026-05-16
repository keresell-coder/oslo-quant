"""Abstract fetcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict

import pandas as pd


class Statements(TypedDict):
    balance_sheet: pd.DataFrame   # columns = periods, index = line items
    income_stmt: pd.DataFrame
    cash_flow: pd.DataFrame
    prices: pd.DataFrame          # columns: Open High Low Close Volume, index = date


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self, ticker: str, force_refresh: bool = False) -> Statements:
        """Return normalized financial statements for *ticker*."""
