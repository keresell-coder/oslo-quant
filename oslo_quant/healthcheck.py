"""Publication gate based on actual retrievals, coverage and coherent results."""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
from pathlib import Path

from oslo_quant.config import ALL_FRAMEWORKS, COMPANIES, DATA_RESULTS
from oslo_quant.trust import parse_stamp, recent, stamp, utc_now


def _parse_computed_at(raw):
    # Display-only compatibility; source times require a timezone.
    if isinstance(raw, str) and raw and not raw.endswith("Z") and "+" not in raw[10:]:
        raw += "+00:00"
    return parse_stamp(raw)


def build_health(within_hours=6, min_fresh=None, results_dir=None) -> dict:
    root = Path(results_dir or DATA_RESULTS)
    total = len(COMPANIES)
    floor = min_fresh if min_fresh is not None else max(1, math.ceil(0.8 * total))
    try:
        run = json.loads((root / "run.json").read_text())
    except (OSError, ValueError):
        run = {}
    run_id = run.get("run_id")
    rows = []
    fetched_times = []
    now = utc_now()
    for company in COMPANIES:
        errors = []
        payloads = []
        for framework in ALL_FRAMEWORKS:
            try:
                payload = json.loads((root / company.ticker / f"{framework}.json").read_text())
                payloads.append(payload)
            except (OSError, ValueError):
                errors.append(f"missing {framework} result")
        sources = [p.get("source_metadata", {}) for p in payloads]
        if not run_id or any(s.get("run_id") != run_id for s in sources):
            errors.append("missing provenance or results retained from another run")
        if len({s.get("snapshot_id") for s in sources}) != 1:
            errors.append("frameworks use different source snapshots")
        if any(not p.get("periods") for p in payloads):
            errors.append("empty framework result")
        source = sources[0] if sources else {}
        annual_periods = source.get("groups", {}).get("annual", {}).get("statement_period_ends", {})
        if not all(annual_periods.get(k) for k in ("income_stmt", "balance_sheet")):
            errors.append("missing annual income/balance-sheet period coverage")
        for group in source.get("groups", {}).values():
            for periods in group.get("statement_period_ends", {}).values():
                for period in periods:
                    try:
                        if datetime.date.fromisoformat(period) > now.date():
                            errors.append("future provider observation date")
                    except (ValueError, TypeError):
                        errors.append("invalid provider observation date")
        source_times = []
        for group in ("annual", "quarterly"):
            meta = source.get("groups", {}).get(group, {})
            if meta.get("cache_used") is not False:
                errors.append(f"{group}: no new provider retrieval (cache or missing)")
            fetched = meta.get("source_fetched_at")
            if not recent(fetched, within_hours, now):
                errors.append(f"{group}: retrieval time missing, stale or future")
            elif fetched:
                source_times.append(fetched)
        if source.get("statement_status") == "invalid-future-period":
            errors.append("future statement period")
        row = {
            "ticker": company.ticker, "status": "blocked" if errors else "current",
            "withheld_reasons": errors,
            "source_fetched_at": min(source_times) if len(source_times) == 2 else None,
            "latest_statement_period_end": source.get("latest_statement_period_end"),
            "statement_age_days": source.get("statement_age_days"),
            "statement_status": source.get("statement_status", "unverified"),
            "missing_statement_tables": source.get("missing_statement_tables", []),
            "primary_ledger": source.get("primary_ledger", {"status": "unverified"}),
            "filing_publication_date": None, "filing_date_status": "unverified",
        }
        if not errors and (row["statement_status"] in {"aged", "missing"}
                           or row["missing_statement_tables"]
                           or row["primary_ledger"].get("status") != "partial-line-items"
                           or row["primary_ledger"].get("mismatches", 0)):
            row["status"] = "degraded"
        if not errors:
            fetched_times.extend(source_times)
        rows.append(row)
    refreshed = sum(not row["withheld_reasons"] for row in rows)
    status = "blocked" if refreshed < floor else (
        "degraded" if any(r["status"] != "current" for r in rows) else "current")
    periods = sorted(r["latest_statement_period_end"] for r in rows if r["latest_statement_period_end"])
    issues = [f"{r['ticker']}: {', '.join(r['withheld_reasons'])}" for r in rows if r["withheld_reasons"]]
    unverified = sum(r["primary_ledger"].get("status") != "partial-line-items" for r in rows)
    if unverified:
        issues.append(f"{unverified} companies have no primary-ledger line-item coverage; filing dates remain unverified for all companies")
    return {
        "schema_version": 1, "snapshot_id": run_id, "generated_at": stamp(),
        "status": status, "source_fetched_at": min(fetched_times) if fetched_times else None,
        "market_data_as_of": None, "expected_session": None,
        "data_kind": "financial-statements", "source_freshness_limit_hours": within_hours,
        "source_observation_start": periods[0] if periods else None,
        "source_observation_end": periods[-1] if periods else None,
        "issues": issues, "reasons": issues,
        "coverage": {"expected": total, "refreshed": refreshed,
                     "withheld": total - refreshed, "minimum_refreshed": floor,
                     "primary_ledger_companies": sum(r["primary_ledger"].get("status") == "partial-line-items" for r in rows)},
        "withheld_reasons": [f"{r['ticker']}: {', '.join(r['withheld_reasons'])}"
                             for r in rows if r["withheld_reasons"]],
        "companies": rows,
        "limitations": [
            "Provider retrieval freshness does not prove that the latest filing is available.",
            "Statement period ends are provider observations; filing publication dates remain unverified.",
            "Primary ledgers verify selected annual line items only; no whole-report verification is implied.",
            "180 days is a disclosed statement-age warning, not a regulatory filing deadline.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--within-hours", type=float, default=6)
    parser.add_argument("--min-fresh", type=int)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.within_hours <= 0 or (args.min_fresh is not None and not 1 <= args.min_fresh <= len(COMPANIES)):
        parser.error("Use positive hours and a minimum between 1 and the configured company count")
    health = build_health(args.within_hours, args.min_fresh)
    if args.json:
        args.json.write_text(json.dumps(health, indent=2) + "\n")
    lines = [f"Source retrieval gate: {health['status'].upper()}",
             f"New retrievals: {health['coverage']['refreshed']}/{health['coverage']['expected']}",
             *health["withheld_reasons"]]
    if health["coverage"]["refreshed"] == 0:
        lines.append("No results at all qualified as newly retrieved.")
    print("\n".join(lines))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write("\n".join(lines) + "\n")
    return int(health["status"] == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())
