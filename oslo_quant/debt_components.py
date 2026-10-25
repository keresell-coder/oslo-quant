"""Field-scoped, source-qualified debt inputs for the existing F5 formula.

No generic Current Debt alias is assumed. A reviewed source record must identify
current maturities separately from other borrowing, interest and leases. The
provider frame stays immutable; qualified pairs are consumed only by F5.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from oslo_quant.primary_financials import SCALES, source_available_on


def finite_value(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and not isinstance(value, bool) else None
    except (ValueError, TypeError):
        return None


ROLES = {"current_maturities", "noncurrent_long_term"}
CANONICAL_ROWS = {
    "current_maturities": "Current Portion Of Long Term Debt",
    "noncurrent_long_term": "Long Term Debt",
}
SCOPES = {"bank-and-bond-excluding-leases"}
BASIS = "carrying-amount-excluding-accrued-interest"


def qualify_debt(
    primary, statements, ticker, currency, as_of=None, provider_period_ends=None
):
    """Return independently usable period pairs, retaining all rejected evidence.

    `primary` is the hash-validated primary loader result, not an unchecked JSON
    document. A selected current/noncurrent pair must have the same scope/basis
    and explicit non-overlap evidence. Publication availability is checked again
    at the evaluation time, so a current report cannot qualify an earlier run.
    """
    as_of = as_of or datetime.now(timezone.utc)
    audit = {
        "status": "not-configured",
        "contract_version": "2026-10-25-debt-v1",
        "evaluation_as_of": as_of.isoformat(),
        "ticker": ticker,
        "currency": currency,
        "unit": "currency units",
        "periods": {},
        "records": [],
        "provider_frames_preserved": True,
        "limitation": "Selected debt fields only; no whole-company or full-score verification.",
    }
    if primary.get("input_policy") != "selected-debt-components":
        return audit
    audit["status"] = "blocked"
    if (
        primary.get("status") != "reviewed-line-items"
        or primary.get("ticker") != ticker
    ):
        audit["reason"] = (
            "Debt source/hash/issuer or transcription review is not qualified"
        )
        return audit
    if currency != primary.get("currency") or currency in {None, "", "Unknown"}:
        audit["reason"] = "Debt/provider reporting currency mismatch or unknown"
        return audit
    groups = {}
    rejected_periods = set()
    identities = [
        (r.get("period_end"), r.get("debt_role"))
        for r in primary.get("records", [])
        if r.get("debt_role") in ROLES
    ]
    duplicates = {key for key in identities if identities.count(key) > 1}
    bs = statements["balance_sheet"]
    audit["provider_debt_observations"] = {
        str(col): {
            str(row): finite_value(bs.loc[row, col])
            for row in [
                "Long Term Debt",
                "Current Debt",
                "Long Term Debt And Capital Lease Obligation",
                "Current Debt And Capital Lease Obligation",
                "Long Term Capital Lease Obligation",
                "Current Capital Lease Obligation",
                "Total Debt",
            ]
            if row in bs.index
        }
        for col in bs.columns
    }

    for record in primary.get("records", []):
        role = record.get("debt_role")
        if role not in ROLES:
            continue
        entry = {
            "record_id": record.get("id"),
            "role": role,
            "source_id": record.get("source_id"),
            "source": record.get("source"),
            "page": record.get("page"),
            "table": record.get("table"),
            "source_label": record.get("source_label"),
            "period_end": record.get("period_end"),
            "primary_value": record.get("value_units"),
            "classification_evidence": record.get("classification_evidence"),
            "zero_disclosure_context": record.get("zero_disclosure_context"),
            "selected_value": None,
            "provider_row": record.get("provider_row", CANONICAL_ROWS[role]),
            "provider_value": None,
            "status": "blocked",
        }
        audit["records"].append(entry)
        try:
            end = date.fromisoformat(record["period_end"])
            period = str(end.year)
            if (record["period_end"], role) in duplicates:
                raise ValueError("Duplicate debt role/period")
            if record.get("row") != CANONICAL_ROWS[role]:
                raise ValueError("Debt role/canonical row mismatch")
            row = entry["provider_row"]
            if row in bs.index and period in bs.columns:
                value = bs.loc[row, period]
                if math.isfinite(float(value)):
                    entry["provider_value"] = float(value)
            value = float(record["value_units"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Debt amount must be finite and nonnegative")
            if record.get("scope") != "instant" or end.month != 12 or end.day != 31:
                raise ValueError("Only explicit annual balance-date debt is eligible")
            if (
                record.get("currency") != currency
                or record.get("consolidation_basis") != "group"
            ):
                raise ValueError("Debt currency/consolidation basis mismatch")
            if (
                record.get("debt_instrument_scope") not in SCOPES
                or record.get("debt_measurement_basis") != BASIS
            ):
                raise ValueError("Debt instrument/interest/lease scope is unqualified")
            if record.get("mutually_exclusive_classification") is not True:
                raise ValueError("Current/noncurrent non-overlap is not evidenced")
            if not record.get("classification_evidence"):
                raise ValueError("Debt maturity classification evidence missing")
            if value == 0 and record.get("zero_evidence") != "explicit-nil-disclosure":
                raise ValueError(
                    "Zero needs an explicit nil disclosure; missing/dash is not zero"
                )
            published = source_available_on(record["source"])
            if end > published or published > as_of.date():
                raise ValueError("Debt record not available at evaluation time")
            if record.get("review_status") != "reviewed-transcription":
                raise ValueError("Debt transcription is not reviewed")
            identity = (period, role)
            if identity in groups:
                raise ValueError("Duplicate debt role/period")
            groups[identity] = (record, entry)
            entry.update(
                status="eligible-field",
                selected_value=value,
                difference_vs_provider=(
                    value - entry["provider_value"]
                    if entry["provider_value"] is not None
                    else None
                ),
                replacement_reason=record.get(
                    "selection_reason",
                    "Explicit selected primary debt field; provider row retained",
                ),
            )
        except (ValueError, KeyError, TypeError) as exc:
            entry["reason"] = str(exc)
            if record.get("period_end"):
                rejected_periods.add(str(record["period_end"])[:4])
    provider_dates = set(
        provider_period_ends
        if provider_period_ends is not None
        else statements.get("meta", {}).get("annual_balance_period_ends", [])
    )
    audit["provider_annual_balance_period_ends"] = sorted(provider_dates)
    asset_controls = {}
    for record in primary.get("records", []):
        if record.get("row") != "Total Assets":
            continue
        try:
            end = date.fromisoformat(record["period_end"])
            period = str(end.year)
            value = float(record["value_units"])
            published = source_available_on(record["source"])
            if (
                record.get("currency") != currency
                or record.get("scope") != "instant"
                or record.get("consolidation_basis") != "group"
                or record.get("review_status") != "reviewed-transcription"
                or end.isoformat() != period + "-12-31"
                or end.isoformat() not in provider_dates
                or published > as_of.date()
                or not math.isfinite(value)
                or value <= 0
            ):
                continue
            if period in asset_controls:
                asset_controls[period] = None
                continue
            provider = float(bs.loc["Total Assets", period])
            increment = float(record.get("rounding_increment", 1))
            if not math.isfinite(increment) or increment <= 0:
                continue
            tolerance = SCALES[record["scale"]] * increment / 2
            if not math.isfinite(provider) or abs(provider - value) > tolerance:
                continue
            asset_controls[period] = {
                "record_id": record["id"],
                "provider_assets": provider,
                "primary_assets": value,
                "difference": provider - value,
                "rounding_tolerance": tolerance,
                "source": record["source"],
                "page": record.get("page"),
            }
        except (ValueError, KeyError, TypeError):
            continue
    for period in sorted({key[0] for key in groups}, reverse=True):
        pair = [groups.get((period, role)) for role in sorted(ROLES)]
        if period in rejected_periods or not all(pair):
            continue
        records = [item[0] for item in pair]
        if (
            len(
                {
                    (r["debt_instrument_scope"], r["debt_measurement_basis"])
                    for r in records
                }
            )
            != 1
        ):
            continue
        audit["periods"][period] = {
            role: groups[(period, role)][1]["selected_value"] for role in ROLES
        }
        audit["periods"][period].update(
            source_records=[r["id"] for r in records],
            instrument_scope=records[0]["debt_instrument_scope"],
            measurement_basis=records[0]["debt_measurement_basis"],
            period_end=records[0]["period_end"],
            currency=currency,
            provider_asset_control=asset_controls.get(period),
            opening_provider_asset_control=asset_controls.get(str(int(period) - 1)),
            available_on=max(
                source_available_on(r["source"]).isoformat() for r in records
            ),
        )
    audit["status"] = "qualified-selected-debt" if audit["periods"] else "blocked"
    if not audit["periods"]:
        audit["reason"] = (
            "No complete current/noncurrent pair qualifies; F5 remains unknown"
        )
    return audit
