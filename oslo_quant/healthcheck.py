"""Post-run health check: assert the pipeline actually produced fresh results.

The dashboard commits `data/results/` to the repository, so the JSON files are
always present even when a run fetches nothing at all. Counting files therefore
proves nothing. This module counts companies whose results were *recomputed by
the current run*, using the `computed_at` stamp each framework writes, and exits
non-zero when that count falls below a floor.

Rationale: `continue-on-error: true` on the fetch step means a run in which every
ticker failed still reports success and still commits. Without this check there is
no signal — the dashboard silently serves stale numbers while Actions stays green.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys

from oslo_quant.config import ALL_FRAMEWORKS, COMPANIES, DATA_RESULTS

# Fraction of configured companies that must be fresh for a run to count as healthy.
_DEFAULT_FLOOR_RATIO = 0.8

# A result is "fresh" if recomputed within this window. Generously wider than a
# normal run (minutes) so a slow fetch never trips a false alarm.
_DEFAULT_WITHIN_HOURS = 6.0


def _parse_computed_at(raw: str) -> datetime.datetime | None:
    """Parse the `computed_at` stamp into an aware UTC datetime."""
    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):          # fromisoformat() only accepts 'Z' on 3.11+
        text = text[:-1]
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _scan(ticker: str) -> tuple[datetime.datetime | None, int]:
    """Return (newest `computed_at`, max period count) across a ticker's frameworks.

    The period count matters as much as the timestamp. A fetch that returns empty
    statements still computes "successfully" with zero periods and still writes a
    fresh `computed_at`, overwriting good data. Recency alone would wave that
    through, so an empty result must not be allowed to count as healthy.
    """
    result_dir = DATA_RESULTS / ticker
    if not result_dir.is_dir():
        return None, 0

    stamps: list[datetime.datetime] = []
    max_periods = 0
    for framework in ALL_FRAMEWORKS:
        path = result_dir / f"{framework}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = _parse_computed_at(payload.get("computed_at", ""))
        if stamp is not None:
            stamps.append(stamp)
        periods = payload.get("periods")
        if isinstance(periods, dict):
            max_periods = max(max_periods, len(periods))

    return (max(stamps) if stamps else None), max_periods


def _classify(
    within_hours: float,
) -> tuple[list[str], list[tuple[str, float]], list[str], list[str]]:
    """Split configured companies into (fresh, stale, empty, missing)."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=within_hours)

    fresh: list[str] = []
    stale: list[tuple[str, float]] = []
    empty: list[str] = []
    missing: list[str] = []

    for company in COMPANIES:
        newest, periods = _scan(company.ticker)
        if newest is None:
            missing.append(company.ticker)
        elif newest < cutoff:
            age_hours = (now - newest).total_seconds() / 3600.0
            stale.append((company.ticker, age_hours))
        elif periods == 0:
            empty.append(company.ticker)
        else:
            fresh.append(company.ticker)

    return fresh, stale, empty, missing


def _emit(line: str, summary_lines: list[str]) -> None:
    print(line)
    summary_lines.append(line)


def _write_step_summary(lines: list[str]) -> None:
    """Mirror the report into the GitHub Actions run summary, when available."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _build_parser() -> argparse.ArgumentParser:
    total = len(COMPANIES)
    default_floor = max(1, math.floor(_DEFAULT_FLOOR_RATIO * total))
    parser = argparse.ArgumentParser(
        prog="oslo-quant-check",
        description="Fail if the latest run did not refresh enough companies.",
    )
    parser.add_argument(
        "--min-fresh",
        type=int,
        default=default_floor,
        metavar="N",
        help=(
            f"Minimum companies that must have been recomputed "
            f"(default: {default_floor}, i.e. {_DEFAULT_FLOOR_RATIO:.0%} of {total})"
        ),
    )
    parser.add_argument(
        "--within-hours",
        type=float,
        default=_DEFAULT_WITHIN_HOURS,
        metavar="H",
        help=f"Treat results older than this as stale (default: {_DEFAULT_WITHIN_HOURS:g})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    total = len(COMPANIES)
    fresh, stale, empty, missing = _classify(args.within_hours)

    summary: list[str] = []
    _emit("## Oslo Quant health check", summary)
    _emit("", summary)
    _emit(
        f"Refreshed **{len(fresh)} of {total}** companies with usable data "
        f"within the last {args.within_hours:g}h (floor: {args.min_fresh}).",
        summary,
    )

    if stale:
        _emit("", summary)
        _emit("Stale (not recomputed by this run):", summary)
        for ticker, age_hours in sorted(stale, key=lambda item: -item[1]):
            _emit(f"- `{ticker}` — last computed {age_hours:.1f}h ago", summary)

    if empty:
        _emit("", summary)
        _emit(
            "Recomputed but **empty** (0 periods — fetch returned no statements, "
            "good data may have been overwritten): "
            + ", ".join(f"`{t}`" for t in empty),
            summary,
        )

    if missing:
        _emit("", summary)
        _emit("No results at all: " + ", ".join(f"`{t}`" for t in missing), summary)

    healthy = len(fresh) >= args.min_fresh
    _emit("", summary)
    _emit("Result: **PASS**" if healthy else "Result: **FAIL**", summary)
    _write_step_summary(summary)

    if not healthy:
        # ::error:: surfaces as an annotation on the Actions run.
        print(
            f"::error::Only {len(fresh)} of {total} companies were refreshed "
            f"(minimum {args.min_fresh}). The dashboard is serving stale data.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
