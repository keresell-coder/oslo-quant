"""Tests for the post-run freshness assertion.

This check is the project's only alerting channel — if it stops discriminating,
silent staleness returns undetected. The empty-results case matters most: a fetch
returning no statements still writes a fresh `computed_at`, so recency alone would
wave a total fetch failure through.
"""

from __future__ import annotations

import datetime
import json

import pytest

from oslo_quant import healthcheck
from oslo_quant.config import ALL_FRAMEWORKS, COMPANIES

TOTAL = len(COMPANIES)


def _write_results(root, kinds: list[str]) -> None:
    """Materialise a fake data/results tree, one `kind` per configured company."""
    now = datetime.datetime.now(datetime.timezone.utc)
    old = now - datetime.timedelta(days=9)

    for company, kind in zip(COMPANIES, kinds):
        if kind == "missing":
            continue
        stamp = (old if kind == "stale" else now).replace(tzinfo=None).isoformat() + "Z"
        periods = {} if kind == "empty" else {"2025-12-31": {"roe_3factor": 0.1}}
        ticker_dir = root / company.ticker
        ticker_dir.mkdir(parents=True)
        for framework in ALL_FRAMEWORKS:
            (ticker_dir / f"{framework}.json").write_text(
                json.dumps({"computed_at": stamp, "periods": periods}),
                encoding="utf-8",
            )


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    """Point the healthcheck at a temporary results tree."""
    def _make(kinds: list[str]):
        kinds = kinds + ["fresh"] * (TOTAL - len(kinds))
        _write_results(tmp_path, kinds)
        monkeypatch.setattr(healthcheck, "DATA_RESULTS", tmp_path)
        return tmp_path
    return _make


def test_all_fresh_passes(results_dir, capsys):
    results_dir([])
    assert healthcheck.main([]) == 0


def test_at_floor_passes(results_dir, capsys):
    """Exactly min-fresh companies is healthy — the floor is inclusive."""
    results_dir(["stale"] * (TOTAL - 12))
    assert healthcheck.main(["--min-fresh", "12"]) == 0


def test_below_floor_fails(results_dir, capsys):
    results_dir(["stale"] * (TOTAL - 11))
    assert healthcheck.main(["--min-fresh", "12"]) == 1


def test_empty_results_do_not_count_as_fresh(results_dir, capsys):
    """Zero-period results carry a fresh timestamp but must not pass."""
    results_dir(["empty"] * TOTAL)
    assert healthcheck.main([]) == 1
    assert "empty" in capsys.readouterr().out.lower()


def test_total_fetch_failure_fails(results_dir, capsys):
    """The scenario that motivated the check: everything recomputed, all of it empty."""
    results_dir(["empty"] * TOTAL)
    assert healthcheck.main(["--min-fresh", "1"]) == 1


def test_missing_results_reported(results_dir, capsys):
    results_dir(["missing"] * TOTAL)
    assert healthcheck.main([]) == 1
    assert "No results at all" in capsys.readouterr().out


def test_within_hours_widens_window(results_dir):
    """A 9-day-old tree passes only if the staleness window is wide enough."""
    results_dir(["stale"] * TOTAL)
    assert healthcheck.main([]) == 1
    assert healthcheck.main(["--within-hours", str(24 * 30)]) == 0


@pytest.mark.parametrize(
    "raw,expected_none",
    [
        ("2026-07-27T10:02:34.564556Z", False),   # normal stamp, 'Z' suffix
        ("2026-07-27T10:02:34.564556", False),    # naive, treated as UTC
        ("", True),
        ("not-a-date", True),
    ],
)
def test_parse_computed_at(raw, expected_none):
    assert (healthcheck._parse_computed_at(raw) is None) is expected_none


def test_parsed_stamps_are_utc_aware():
    parsed = healthcheck._parse_computed_at("2026-07-27T10:02:34Z")
    assert parsed is not None and parsed.tzinfo is not None
