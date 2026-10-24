"""Exact field resolution and explicit period contracts for bounded method repair."""

import math

VERSION = "2026-10-24-methodology-v2"


def exact(frame, labels, period):
    if period is None or frame is None or frame.empty or period not in frame.columns:
        return float("nan"), None
    index = {str(i).lower(): i for i in frame.index}
    for label in labels:
        row = index.get(label.lower())
        if row is not None:
            try:
                value = float(frame.loc[row, period])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return value, str(row)
    return float("nan"), None


def prior(period, columns):
    if str(period).isdigit() and len(str(period)) == 4:
        value = str(int(period) - 1)
        return value if value in columns else None
    if str(period).startswith("LTM "):
        years = [
            str(c)
            for c in columns
            if str(c).isdigit() and len(str(c)) == 4 and str(c) < str(period)[4:8]
        ]
        return max(years) if years else None
    return None


def basis(period):
    return (
        "overlapping interim adaptation: LTM versus latest FY"
        if str(period).startswith("LTM ")
        else "annual signals; source proxies and turnover convention disclosed"
    )


def ratio(numerator, denominator):
    return (
        numerator / denominator
        if math.isfinite(numerator) and math.isfinite(denominator) and denominator > 0
        else float("nan")
    )
