"""Conservative input contracts. Passing checks never verifies accounting definitions."""
from datetime import date, datetime, timezone

# Manually observed issuer release; not a forecast or an automatic primary-data replacement.
KNOWN_FILINGS = {"NOD.OL": {
    "period_end": "2026-09-30", "published_on": "2026-10-22",
    "observed_at": "2026-10-24T20:54:00+00:00",
    "source_url": "https://www.nordicsemi.com/Investor-Relations/Reports/Quarterly",
    "scope": "Issuer release availability only; values and accounting definitions unverified",
}}


def filing_coverage(symbol, periods, now=None):
    today = (now or datetime.now(timezone.utc)).date()
    valid = []
    for value in periods:
        try:
            end = date.fromisoformat(value)
            if end > today:
                raise ValueError("future")
            valid.append(end.isoformat())
        except (ValueError, TypeError):
            return {"status": "invalid-period", "latest_period_end": None, "issuer_release": None}
    release = KNOWN_FILINGS.get(symbol)
    active = release if release and date.fromisoformat(release["published_on"]) <= today else None
    latest = max(valid) if valid else None
    status = "unverified"
    if active:
        status = "provider-covers-known-release" if latest and latest >= active["period_end"] else "behind-known-release"
    return {"status": status, "latest_period_end": latest, "issuer_release": active,
            "limitation": "Retrieval time is separate from filing coverage. Coverage does not verify values or definitions; unknown issuer dates remain unverified."}

