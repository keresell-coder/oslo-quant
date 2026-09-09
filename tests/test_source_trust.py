"""Regression cases for stale caches and retained publication, not formula mirrors."""
import datetime as dt
import json

import pandas as pd
import pytest

from oslo_quant import healthcheck
from oslo_quant import report
from oslo_quant.config import ALL_FRAMEWORKS, COMPANIES, RAW_FILES
from oslo_quant.fetchers.yfinance_fetcher import YFinanceFetcher
from oslo_quant.publish import promote
from oslo_quant.trust import provenance, stamp, utc_now
from tests.test_healthcheck import _write_results


@pytest.mark.parametrize("kind", ["legacy", "expired", "future", "tampered"])
def test_invalid_raw_cache_forces_upstream_refresh(tmp_path, kind):
    fetcher = YFinanceFetcher()
    frames = {key: pd.DataFrame({pd.Timestamp("2025-12-31"): [1]}, index=["Total Assets"])
              for key in RAW_FILES}
    fetcher._save_cache(tmp_path, frames)
    fetcher._record("TEST", tmp_path, "annual", frames)
    assert fetcher._cache_complete(tmp_path)
    path = tmp_path / "annual_source.json"
    meta = json.loads(path.read_text())
    if kind == "legacy":
        path.unlink()
    elif kind == "tampered":
        (tmp_path / RAW_FILES["income_stmt"]).write_bytes(b"partial failed write")
    else:
        meta["source_fetched_at"] = (utc_now() + dt.timedelta(hours=1 if kind == "future" else -25)).isoformat()
        path.write_text(json.dumps(meta))
    assert not fetcher._cache_complete(tmp_path)


@pytest.mark.parametrize("kind", ["cached", "legacy", "future_fetch", "future_period", "different_run", "different_snapshot", "missing_framework"])
def test_recomputed_files_do_not_create_false_freshness(tmp_path, kind):
    _write_results(tmp_path, ["fresh"] * len(COMPANIES))
    for company in COMPANIES:
        for index, framework in enumerate(ALL_FRAMEWORKS):
            path = tmp_path / company.ticker / f"{framework}.json"
            payload = json.loads(path.read_text())
            source = payload["source_metadata"]
            if kind == "cached":
                source["groups"]["annual"]["cache_used"] = True
            elif kind == "legacy":
                payload.pop("source_metadata")
            elif kind == "future_fetch":
                source["groups"]["annual"]["source_fetched_at"] = (utc_now() + dt.timedelta(hours=1)).isoformat()
            elif kind == "future_period":
                source["groups"]["annual"]["statement_period_ends"]["income_stmt"] = ["2999-12-31"]
            elif kind == "different_run" and index == 0:
                source["run_id"] = "prior-run"
            elif kind == "different_snapshot" and index == 0:
                source["snapshot_id"] = "different"
            if kind == "missing_framework" and index == 0:
                path.unlink()
            else:
                path.write_text(json.dumps(payload))
    result = healthcheck.build_health(results_dir=tmp_path)
    assert result["status"] == "blocked"
    assert result["coverage"]["refreshed"] == 0


def test_dates_do_not_imply_primary_verification():
    metadata = {"source_fetched_at": stamp(), "cache_used": False,
                "statement_period_ends": {"income_stmt": ["2026-06-30"]}}
    result = provenance(metadata, metadata, {"counts": {}}, "test")
    assert result["primary_ledger"]["status"] == "unverified"
    assert result["filing_publication_date"] is None
    assert result["missing_statement_tables"]


def test_failed_attempt_preserves_previous_report_and_data(tmp_path):
    root = tmp_path / "public"
    (root / "data" / "results").mkdir(parents=True)
    (root / "index.html").write_text("last good report")
    (root / "data" / "results" / "good.json").write_text("old data")
    (root / "health.json").write_text(json.dumps({"snapshot_id": "prior-good"}))
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    assert not promote(candidate, {"status": "blocked", "snapshot_id": "failed-attempt"}, root)
    assert (root / "index.html").read_text() == "last good report"
    assert (root / "data" / "results" / "good.json").read_text() == "old data"
    assert json.loads((root / "health.json").read_text())["last_good_snapshot_id"] == "prior-good"


def test_withheld_company_never_renders_prior_scores_as_fresh():
    previous = {"publication_health": {"status": "blocked", "publication_snapshot_id": "new"},
                "dupont": {"periods": {"2025": {"roe_3factor": 987654}}}}
    assert "987654" not in report._summary_row("MOWI.OL", previous)
    assert "987654" not in report._detail_card("MOWI.OL", previous)
    page = report._build_html({"MOWI.OL": previous})
    assert "const reportSnapshotId = \"new\"" in page
    assert "reportSnapshotId === h.snapshot_id" in page
    assert "fetch('health.json'" in page
    assert "Previous report retained after a failed refresh" in page
    assert "Live publication health not yet verified" in page


def test_legacy_results_are_withheld_without_a_health_record(tmp_path, monkeypatch):
    company = tmp_path / "MOWI.OL"
    company.mkdir()
    (company / "dupont.json").write_text(json.dumps({"computed_at": stamp(), "periods": {"2025": {"roe_3factor": 1}}}))
    monkeypatch.setattr(report, "DATA_RESULTS", tmp_path)
    data = report._load_results()
    assert data["MOWI.OL"]["publication_health"]["status"] == "blocked"
