"""Synthetic qualification controls, not issuer primary mappings."""

from copy import deepcopy
from datetime import datetime, timezone
import pandas as pd
import pytest
from oslo_quant.debt_components import qualify_debt, CANONICAL_ROWS, BASIS
from oslo_quant.frameworks.piotroski import PiotroskiFramework

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def inputs():
    records = []
    for year, current, long, assets in [
        (2025, 10, 50, 150),
        (2024, 20, 60, 100),
        (2023, None, None, 80),
    ]:
        common = dict(
            period_end=f"{year}-12-31",
            scope="instant",
            currency="USD",
            scale="units",
            consolidation_basis="group",
            review_status="reviewed-transcription",
            source_id="synthetic-report",
            source={"published_on": "2026-03-01", "sha256": "0" * 64},
            page=1,
            table="Synthetic debt control",
            source_label="Test only",
        )
        records.append(
            dict(common, id=f"assets-{year}", row="Total Assets", value_units=assets)
        )
        if current is None:
            continue
        for role, value in [
            ("current_maturities", current),
            ("noncurrent_long_term", long),
        ]:
            records.append(
                dict(
                    common,
                    id=f"{role}-{year}",
                    row=CANONICAL_ROWS[role],
                    value_units=value,
                    debt_role=role,
                    debt_instrument_scope="bank-and-bond-excluding-leases",
                    debt_measurement_basis=BASIS,
                    mutually_exclusive_classification=True,
                    classification_evidence="Synthetic table explicitly distinguishes current maturities and noncurrent debt",
                )
            )
    primary = dict(
        status="reviewed-line-items",
        ticker="TEST.OL",
        currency="USD",
        input_policy="selected-debt-components",
        records=records,
    )
    bs = pd.DataFrame(
        {
            "2025": {"Total Assets": 150, "Long Term Debt": 51, "Current Debt": 15},
            "2024": {"Total Assets": 100, "Long Term Debt": 61, "Current Debt": 23},
            "2023": {"Total Assets": 80},
        }
    )
    statements = dict(
        balance_sheet=bs,
        income_stmt=pd.DataFrame(
            {
                "2025": {"Total Revenue": 160, "Net Income": 12},
                "2024": {"Total Revenue": 100, "Net Income": 7},
            }
        ),
        cash_flow=pd.DataFrame({"2025": {"Operating Cash Flow": 15}}),
        prices=pd.DataFrame(),
        meta={"annual_balance_period_ends": ["2025-12-31", "2024-12-31", "2023-12-31"]},
    )
    return primary, statements


def qualify(p, s):
    return qualify_debt(p, s, "TEST.OL", "USD", NOW)


def test_selected_fields_preserve_provider_and_use_existing_average_assets_formula():
    p, s = inputs()
    original = s["balance_sheet"].copy()
    audit = qualify(p, s)
    assert audit["status"] == "qualified-selected-debt"
    assert audit["periods"]["2025"]["current_maturities"] == 10
    assert s["balance_sheet"].equals(original)
    before = PiotroskiFramework().compute(s, "TEST.OL")["periods"]["2025"]
    s["meta"] = {"debt_inputs": audit}
    after = PiotroskiFramework().compute(s, "TEST.OL")["periods"]["2025"]
    # (50+10)/125 < (60+20)/90; same average-assets convention.
    assert before["signals"]["F5_leverage_decreasing"] is None
    assert after["signals"]["F5_leverage_decreasing"] == 1
    assert after["signals"]["F7_no_dilution"] is None and after["f_score"] is None
    record = next(
        r for r in audit["records"] if r["record_id"] == "noncurrent_long_term-2025"
    )
    assert (
        record["provider_value"] == 51
        and record["selected_value"] == 50
        and record["difference_vs_provider"] == -1
    )
    assert record["source"]["sha256"] == "0" * 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("value_units", None),
        ("value_units", -1),
        ("currency", "NOK"),
        ("scope", "annual"),
        ("debt_instrument_scope", "bank-bond-and-leases"),
        ("debt_measurement_basis", "includes-accrued-interest"),
        ("mutually_exclusive_classification", False),
        ("classification_evidence", ""),
        ("review_status", "unreviewed"),
        ("row", "Current Debt"),
        ("period_end", "2025-06-30"),
    ],
)
def test_ambiguous_or_incompatible_current_component_is_not_selected(field, value):
    p, s = inputs()
    r = next(r for r in p["records"] if r["id"] == "current_maturities-2025")
    r[field] = value
    assert "2025" not in qualify(p, s)["periods"]


def test_missing_component_and_duplicate_role_cannot_promote_complete_pair():
    p, s = inputs()
    p["records"] = [r for r in p["records"] if r["id"] != "current_maturities-2025"]
    assert "2025" not in qualify(p, s)["periods"]
    p, s = inputs()
    duplicate = deepcopy(
        next(r for r in p["records"] if r["id"] == "current_maturities-2025")
    )
    duplicate["id"] = "conflicting"
    p["records"].append(duplicate)
    assert "2025" not in qualify(p, s)["periods"]


def test_zero_requires_explicit_nil_disclosure_not_provider_absence_or_dash():
    p, s = inputs()
    r = next(r for r in p["records"] if r["id"] == "current_maturities-2025")
    r["value_units"] = 0
    assert "2025" not in qualify(p, s)["periods"]
    r["zero_evidence"] = "explicit-nil-disclosure"
    assert qualify(p, s)["periods"]["2025"]["current_maturities"] == 0


def test_unknown_currency_unreviewed_source_and_prepublication_asof_stay_blocked():
    p, s = inputs()
    assert qualify_debt(p, s, "TEST.OL", "Unknown", NOW)["status"] == "blocked"
    assert qualify_debt(p, s, "OTHER.OL", "USD", NOW)["status"] == "blocked"
    p["status"] = "blocked"
    assert qualify(p, s)["status"] == "blocked"
    p, s = inputs()
    assert (
        qualify_debt(
            p, s, "TEST.OL", "USD", datetime(2026, 2, 28, tzinfo=timezone.utc)
        )["periods"]
        == {}
    )


def test_incompatible_provider_asset_basis_withholds_ratio_without_overwriting_assets():
    p, s = inputs()
    s["balance_sheet"].loc["Total Assets", "2025"] = 200
    audit = qualify(p, s)
    assert audit["periods"]["2025"]["provider_asset_control"] is None
    s["meta"] = {"debt_inputs": audit}
    row = PiotroskiFramework().compute(s, "TEST.OL")["periods"]["2025"]
    assert row["signals"]["F5_leverage_decreasing"] is None
    assert s["balance_sheet"].loc["Total Assets", "2025"] == 200


def test_missing_opening_asset_control_and_interim_cannot_reuse_annual_maturities():
    p, s = inputs()
    p["records"] = [r for r in p["records"] if r["id"] != "assets-2023"]
    s["meta"] = {"debt_inputs": qualify(p, s)}
    assert (
        PiotroskiFramework().compute(s, "TEST.OL")["periods"]["2025"]["signals"][
            "F5_leverage_decreasing"
        ]
        is None
    )
    for name in ["balance_sheet", "income_stmt", "cash_flow"]:
        s[name]["LTM 2026-06"] = s[name]["2025"]
    row = PiotroskiFramework().compute(s, "TEST.OL")["periods"]["LTM 2026-06"]
    assert (
        row["signals"]["F5_leverage_decreasing"] is None
        and "overlapping" in row["period_basis"]
    )


def test_actual_frozen_provider_nod_mowi_annual_only_and_other_unknowns():
    from scripts.preview_debt_reconciliation import preview, frozen_statements

    for ticker in ["NOD.OL", "MOWI.OL"]:
        result = preview(ticker)
        before = result["before"]["periods"]
        after = result["after"]["periods"]
        assert after["2025"]["signals"]["F5_leverage_decreasing"] == 0
        for period, row in after.items():
            for signal, value in row["signals"].items():
                if period == "2025" and signal == "F5_leverage_decreasing":
                    continue
                assert value == before[period]["signals"][signal]
        assert after["2024"]["signals"]["F5_leverage_decreasing"] is None
    assert preview("NOD.OL")["after"]["periods"]["2025"]["f_score"] == 6
    mowi = preview("MOWI.OL")["after"]["periods"]["2025"]
    assert mowi["f_score"] is None and mowi["signals"]["F7_no_dilution"] is None
    for ticker in ["DOFG.OL", "PUBLI.OL"]:
        result = preview(ticker)
        assert result["before"]["periods"] == result["after"]["periods"]


def test_observed_availability_is_not_invented_publication_date():
    from pathlib import Path
    from oslo_quant.primary_financials import load_primary

    primary = load_primary(
        "NOD.OL", Path(__file__).parents[1] / "data/debt", download=False
    )
    source = next(
        r["source"] for r in primary["records"] if r["source_id"] == "NOD2024"
    )
    assert source["published_on"] is None
    assert source["availability_basis"] == "first-documented-observation"
    assert source["available_on"] == "2026-10-25"
    from scripts.preview_debt_reconciliation import frozen_statements

    statements, currency = frozen_statements("NOD.OL")
    old = qualify_debt(
        primary,
        statements,
        "NOD.OL",
        currency,
        datetime(2026, 10, 24, tzinfo=timezone.utc),
    )
    assert "2024" not in old["periods"]
    now = qualify_debt(primary, statements, "NOD.OL", currency, NOW)
    assert now["periods"]["2024"]["available_on"] == "2026-10-25"


@pytest.mark.parametrize("difference,qualified", [(0.5, True), (0.5001, False)])
def test_asset_compatibility_respects_explicit_source_rounding_boundary(
    difference, qualified
):
    p, s = inputs()
    s["balance_sheet"] = s["balance_sheet"].astype(float)
    s["balance_sheet"].loc["Total Assets", "2025"] += difference
    control = qualify(p, s)["periods"]["2025"]["provider_asset_control"]
    assert bool(control) == qualified


def test_bad_provider_debt_observation_is_preserved_as_missing_not_crash_or_zero():
    p, s = inputs()
    s["balance_sheet"] = s["balance_sheet"].astype(object)
    s["balance_sheet"].loc["Current Debt", "2025"] = "unknown"
    audit = qualify(p, s)
    assert audit["provider_debt_observations"]["2025"]["Current Debt"] is None
    assert audit["periods"]["2025"]["current_maturities"] == 10


def test_current_nordic_primary_interim_is_not_backfilled_from_annual_debt():
    from pathlib import Path
    from scripts.preview_debt_reconciliation import frozen_statements
    from oslo_quant.primary_financials import load_primary
    from oslo_quant.primary_adapter import apply_primary_current

    root = Path(__file__).parents[1]
    statements, currency = frozen_statements("NOD.OL")
    selected, _ = apply_primary_current(
        statements,
        load_primary("NOD.OL", root / "data/primary", download=False),
        currency,
    )
    debt = qualify_debt(
        load_primary("NOD.OL", root / "data/debt", download=False),
        selected,
        "NOD.OL",
        currency,
        NOW,
    )
    selected["meta"] = {"debt_inputs": debt}
    result = PiotroskiFramework().compute(selected, "NOD.OL")["periods"]
    assert result["2025"]["f_score"] == 6
    assert result["LTM 2026-09"]["f_score"] is None
    assert result["LTM 2026-09"]["signals"]["F5_leverage_decreasing"] is None
    assert result["LTM 2026-09"]["signals"]["F7_no_dilution"] is None
    assert "overlapping" in result["LTM 2026-09"]["period_basis"]


def test_rendered_debt_sources_disclose_unknown_publication_and_provider_absence():
    from pathlib import Path
    from scripts.preview_debt_reconciliation import frozen_statements
    from oslo_quant.primary_financials import load_primary
    from oslo_quant import report

    s, c = frozen_statements("NOD.OL")
    audit = qualify_debt(
        load_primary("NOD.OL", Path(__file__).parents[1] / "data/debt", download=False),
        s,
        "NOD.OL",
        c,
        NOW,
    )
    text = report._debt_inputs(audit)
    assert "Unknown; documented availability 2026-10-25" in text
    assert "Unavailable" in text and "selected fields only" in text
    assert "Current Debt alias" in text and "bond principal" in text


@pytest.mark.parametrize("dates", [[], ["2025-06-30", "2024-12-31", "2023-12-31"]])
def test_unknown_or_incompatible_provider_balance_date_cannot_qualify_denominator(
    dates,
):
    p, s = inputs()
    audit = qualify_debt(p, s, "TEST.OL", "USD", NOW, provider_period_ends=dates)
    assert audit["periods"]["2025"]["provider_asset_control"] is None
    s["meta"] = {"debt_inputs": audit}
    assert (
        PiotroskiFramework().compute(s, "TEST.OL")["periods"]["2025"]["signals"][
            "F5_leverage_decreasing"
        ]
        is None
    )
