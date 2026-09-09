"""Provider retrieval provenance; statement dates never imply filing verification."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

CACHE_TTL_HOURS = 24


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def stamp() -> str:
    return utc_now().isoformat()


def parse_stamp(value) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Unknown timezone is not evidence of retrieval time.
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def recent(value, hours=CACHE_TTL_HOURS, now=None) -> bool:
    parsed = parse_stamp(value)
    age = ((now or utc_now()) - parsed).total_seconds() if parsed else -1
    return 0 <= age <= hours * 3600


def period_ends(frame) -> list[str]:
    if frame is None or frame.empty:
        return []
    return sorted(str(c.date()) if hasattr(c, "date") else str(c)
                  for c in frame.columns if frame[c].notna().any())


def provenance(annual, quarterly, verification, run_id: str) -> dict:
    groups = {"annual": annual, "quarterly": quarterly}
    ends = sorted({p for group in groups.values()
                   for periods in group.get("statement_period_ends", {}).values()
                   for p in periods if len(p) == 10})
    latest = ends[-1] if ends else None
    age = None
    invalid_period = False
    if latest:
        try:
            age = (utc_now().date() - dt.date.fromisoformat(latest)).days
            invalid_period = age < 0
        except ValueError:
            invalid_period = True
    counts = (verification or {}).get("counts", {})
    verified = counts.get("verified", 0)
    filled = counts.get("filled", 0)
    missing = [f"{group}.{statement}" for group, value in groups.items()
               for statement in ("balance_sheet", "income_stmt", "cash_flow")
               if not value.get("statement_period_ends", {}).get(statement)]
    source_id = hashlib.sha256(json.dumps({k: {a: b for a, b in v.items() if a != "cache_used"}
                                           for k, v in groups.items()}, sort_keys=True).encode()).hexdigest()[:20]
    return {
        "schema_version": 1, "run_id": run_id, "snapshot_id": source_id,
        "provider": "Yahoo Finance via yfinance", "groups": groups,
        "latest_statement_period_end": latest,
        "statement_age_days": age,
        "statement_status": "invalid-future-period" if invalid_period else
            ("missing" if latest is None else "aged" if age > 180 else "available"),
        "missing_statement_tables": missing,
        "filing_publication_date": None,
        "filing_date_status": "unverified: provider period ends are not filing publication dates",
        "primary_ledger": {
            "status": "partial-line-items" if verified + filled else "unverified",
            "verified_items": verified, "filled_items": filled,
            "mismatches": counts.get("mismatch", 0),
            "scope": "Selected annual line items only; interim periods and whole reports are not verified.",
        },
    }
