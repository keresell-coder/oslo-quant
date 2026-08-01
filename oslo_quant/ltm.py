"""LTM ("last twelve months") construction from quarterly statements.

Policy (agreed 2026-08-01):

* The LTM column acts as a *virtual current year*, appended after the latest
  full fiscal year. Because "LTM …" sorts after "2025" in the frameworks'
  descending period sort, every year-over-year signal automatically compares
  **LTM vs the latest full FY** — an overlapping window, accepted by design as
  a development tracker.
* Flow statements (income, cash flow) are the sum of the last 4 quarters, or
  the last 2 half-years for semi-annual reporters. The window must be
  **contiguous** — yfinance quarterly data has gaps (e.g. KIT.OL is missing
  Q3 2025), and a naive "last four columns" sum over a broken window produces
  a wrong LTM. A broken window means *no* LTM, never a silently wrong one.
* The balance sheet is the latest quarterly column as-is (point in time).
* If the latest available quarter end coincides with the latest fiscal
  year end (i.e. the FY report is the newest information and no new interim
  has been published), LTM would equal the FY — it is skipped with an
  explicit status instead of duplicating the year.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import pandas as pd

from oslo_quant.fetchers.base import Statements

log = logging.getLogger(__name__)

# Acceptable day-gaps between consecutive period-end dates.
_QUARTER_GAP = (80, 100)
_HALF_GAP = (170, 195)


def _parse(d: str) -> datetime.date:
    return datetime.date.fromisoformat(str(d)[:10])


def _window(cols: list[str]) -> tuple[list[str], str] | tuple[None, str]:
    """Pick a contiguous trailing 12-month window from period-end columns.

    Returns (columns_newest_first, kind) where kind is "4 quarters" or
    "2 half-years", or (None, reason).
    """
    dates = sorted((_parse(c), c) for c in cols)
    if len(dates) < 2:
        return None, "fewer than 2 quarterly periods available"

    newest_first = [c for _, c in reversed(dates)]

    def gaps(sel: list[str]) -> list[int]:
        ds = [_parse(c) for c in sel]
        return [(ds[i] - ds[i + 1]).days for i in range(len(ds) - 1)]

    # Try 4 contiguous quarters.
    if len(newest_first) >= 4:
        sel = newest_first[:4]
        if all(_QUARTER_GAP[0] <= g <= _QUARTER_GAP[1] for g in gaps(sel)):
            return sel, "4 quarters"

    # Try 2 contiguous half-years.
    sel = newest_first[:2]
    if all(_HALF_GAP[0] <= g <= _HALF_GAP[1] for g in gaps(sel)):
        return sel, "2 half-years"

    return None, (
        "quarterly history is not contiguous "
        f"(period ends: {', '.join(newest_first[:5])})"
    )


def build_ltm(annual: Statements, quarterly: dict[str, pd.DataFrame],
              ticker: str) -> tuple[Statements, dict[str, Any]]:
    """Append an LTM column to *annual* statements when feasible.

    Returns (statements, status) where status = {"built": bool, "label": str|None,
    "detail": str}. On any infeasibility the annual statements are returned
    unchanged — an LTM is never approximated over a broken window.
    """
    qi = quarterly.get("income_stmt")
    qb = quarterly.get("balance_sheet")
    qc = quarterly.get("cash_flow")

    def _skip(detail: str) -> tuple[Statements, dict[str, Any]]:
        log.info("[%s] LTM skipped: %s", ticker, detail)
        return annual, {"built": False, "label": None, "detail": detail}

    if qi is None or qi.empty or qc is None or qc.empty or qb is None or qb.empty:
        return _skip("no quarterly statements available")

    ann_inc = annual["income_stmt"]
    if ann_inc is None or ann_inc.empty:
        return _skip("no annual statements to anchor against")

    # The user-flagged instance: latest quarter == latest FY end. The FY
    # report is the newest information; an LTM would just duplicate it.
    latest_q = max(_parse(c) for c in qi.columns)
    latest_fy_year = max(int(str(c)[:4]) for c in ann_inc.columns)
    fy_end = datetime.date(latest_fy_year, 12, 31)
    if latest_q <= fy_end:
        return _skip(
            f"latest interim period ({latest_q}) does not extend beyond "
            f"FY{latest_fy_year} — LTM would equal the annual figures"
        )

    sel, kind = _window(list(qi.columns))
    if sel is None:
        return _skip(kind)
    # The cash-flow statement must cover the same window.
    if not all(c in qc.columns for c in sel):
        return _skip(f"cash-flow statement missing periods for the LTM window {sel}")

    label = f"LTM {sel[0][:7]}"

    # Flows: sum across the window; a row must be present in every period of
    # the window or the LTM value is NaN (min_count) — no partial sums.
    ltm_inc = qi[sel].sum(axis=1, min_count=len(sel))
    ltm_cf = qc[sel].sum(axis=1, min_count=len(sel))

    # Balance sheet: latest quarter, point-in-time.
    bs_col = sel[0] if sel[0] in qb.columns else None
    if bs_col is None:
        return _skip(f"balance sheet missing the latest quarter {sel[0]}")
    ltm_bs = qb[bs_col]

    # A column can exist while carrying no data (NOD.OL's Q3 2025 is a real
    # example: the date is present, the values are NaN). Anchor rows must
    # survive the min_count sum or the LTM is refused outright.
    rev = ltm_inc.get("Total Revenue")
    if rev is None or pd.isna(rev):
        return _skip(
            "LTM window dates are contiguous but Total Revenue is empty in at "
            "least one quarter — refusing a partial sum"
        )
    ta = ltm_bs.get("Total Assets")
    if ta is None or pd.isna(ta):
        return _skip(f"latest quarter balance sheet ({sel[0]}) has no Total Assets")

    out: Statements = dict(annual)  # type: ignore[assignment]
    for key, series in (("income_stmt", ltm_inc),
                        ("cash_flow", ltm_cf),
                        ("balance_sheet", ltm_bs)):
        df: pd.DataFrame = annual[key]  # type: ignore[assignment]
        df = df.copy() if df is not None and not df.empty else pd.DataFrame()
        merged = df.reindex(df.index.union(series.index, sort=False))
        merged[label] = series.reindex(merged.index)
        out[key] = merged  # type: ignore[literal-required]

    detail = f"built from {kind} through {sel[0]}"
    log.info("[%s] LTM %s", ticker, detail)
    return out, {"built": True, "label": label, "detail": detail}
