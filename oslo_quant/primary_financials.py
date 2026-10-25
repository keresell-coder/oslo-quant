"""Audited primary statement ingestion, separate from provider observations.

Document hashes prove artifact identity, not transcription accuracy. Only reviewed
mappings enter effective inputs; unreviewed and unresolved facts remain audit data.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import calendar
import hashlib
import json
import math
from pathlib import Path
import urllib.parse
import urllib.request

STATEMENTS = {"income_stmt", "balance_sheet", "cash_flow"}
SCALES = {"units": 1, "thousands": 1000, "millions": 1000000}
SCOPES = {"quarter", "year_to_date", "annual", "instant"}
ISSUER_HOSTS = {"www.nordicsemi.com", "nordicsemi.com", "www.dof.com", "dof.com", "mowi.com", "www.mowi.com"}


class PrimaryInputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PrimaryInputError(message)


def timestamp(value):
    require(isinstance(value, str), "missing retrieval timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "retrieval timezone missing")
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise PrimaryInputError("invalid retrieval timestamp") from exc


def source_available_on(source):
    """Known publication date, or explicitly observed availability; never invent one."""
    if source.get("published_on") is not None:
        return date.fromisoformat(source["published_on"])
    require(source.get("availability_basis") == "first-documented-observation",
            "unknown publication needs explicit observed availability")
    return date.fromisoformat(source["available_on"])


def validate(document, now=None):
    now = now or datetime.now(timezone.utc)
    require(document.get("schema_version") == 1, "unsupported primary schema")
    require(bool(document.get("ticker")), "missing ticker")
    currency = document.get("currency")
    require(isinstance(currency, str) and len(currency) == 3 and currency.isupper(), "invalid primary currency")
    sources = {}
    for source in document.get("sources", []):
        key = source.get("id")
        require(key and key not in sources, "missing/duplicate source id")
        url = urllib.parse.urlsplit(source.get("url", ""))
        require(url.scheme == "https" and url.hostname in ISSUER_HOSTS and not url.username and not url.password, "source must be an allowlisted issuer HTTPS URL")
        digest = source.get("sha256", "")
        require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid source SHA-256")
        published = source_available_on(source)
        retrieved = timestamp(source.get("retrieved_at"))
        require(published <= retrieved.date() <= now.date() and retrieved <= now, "invalid publication/retrieval chronology")
        require(bool(source.get("title")), "missing report title")
        require(source.get("ticker") == document["ticker"], "source issuer mismatch")
        expected_host = "nordicsemi.com" if document["ticker"] == "NOD.OL" else "dof.com" if document["ticker"] == "DOFG.OL" else "mowi.com" if document["ticker"] == "MOWI.OL" else None
        require(expected_host is not None and url.hostname.removeprefix("www.") == expected_host, "issuer/source host mismatch")
        sources[key] = source
    records = {}
    identities = set()
    for record in document.get("records", []):
        key = record.get("id")
        require(key and key not in records, "missing/duplicate record id")
        require(record.get("source_id") in sources, "unknown source reference")
        require(record.get("statement") in STATEMENTS, "unknown statement")
        require(record.get("scope") in SCOPES, "unknown period scope")
        require(record.get("aggregation") in {"flow", "stock", "non-additive"}, "missing aggregation semantics")
        require(record.get("currency") == currency, "record currency mismatch")
        require(record.get("scale") in SCALES, "unknown scale")
        require(record.get("accounting_basis") == "IFRS-consolidated", "unsupported accounting basis")
        require(isinstance(record.get("page"), int) and not isinstance(record["page"], bool) and record["page"] > 0, "invalid PDF page")
        require(bool(record.get("source_label")) and bool(record.get("table")) and bool(record.get("row")), "missing table/field mapping")
        require(record.get("consolidation_basis") in {"group", "owners-of-parent"}, "missing consolidation basis")
        identity = (document["ticker"], record["statement"], record["row"], record.get("period_start"), record.get("period_end"), record["scope"], record["accounting_basis"], record["consolidation_basis"])
        require(identity not in identities, "conflicting duplicate issuer/field/period/basis")
        identities.add(identity)
        value = record.get("value")
        require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), "nonfinite or missing primary value")
        end = date.fromisoformat(record["period_end"])
        require(end <= source_available_on(sources[record["source_id"]]), "statement end after publication")
        if record["scope"] == "instant":
            require(record.get("aggregation") == "stock" and record.get("period_start") is None and record["statement"] == "balance_sheet", "instant must be balance-sheet point in time")
        else:
            start = date.fromisoformat(record["period_start"])
            require(start <= end and record["statement"] != "balance_sheet", "invalid flow period")
            days = (end-start).days+1
            if record["scope"] == "quarter":
                require(80 <= days <= 100 and start.day == 1 and start.month in (1,4,7,10) and end.month == start.month+2 and end.day == calendar.monthrange(end.year,end.month)[1], "quarter is not a standalone quarter")
            if record["scope"] in {"annual", "year_to_date"}:
                require(start.month == start.day == 1 and start.year == end.year, "only calendar-year cumulative periods supported")
            if record["scope"] == "annual":
                require(end.month == 12 and end.day == 31, "annual period is incomplete")
        require(record.get("review_status") in {"reviewed-transcription", "unreviewed"}, "missing transcription review state")
        require(math.isfinite(value*SCALES[record["scale"]]), "scaled primary value is nonfinite")
        records[key] = {**record, "value_units": value*SCALES[record["scale"]],
                        "source": sources[record["source_id"]]}
    require(bool(sources) and bool(records), "primary ledger has no source facts")
    return sources, records


def derive_ttm(records, recipe):
    """FY + current YTD - comparable prior YTD; never EPS or mixed scope."""
    refs = recipe.get("records", [])
    require(len(refs) == 3 and len(set(refs)) == 3, "TTM needs three distinct source records")
    require(all(key in records for key in refs), "missing TTM source record")
    annual, current, prior = (records[key] for key in refs)
    require([r["scope"] for r in (annual, current, prior)] == ["annual", "year_to_date", "year_to_date"], "incompatible TTM scopes")
    require(all(r["review_status"] == "reviewed-transcription" for r in (annual, current, prior)), "TTM source mapping not reviewed")
    for field in ("currency", "statement", "row", "accounting_basis", "consolidation_basis"):
        require(len({r[field] for r in (annual, current, prior)}) == 1, "TTM incompatible "+field)
    require(all(r.get("aggregation") == "flow" for r in (annual,current,prior)), "TTM source is non-additive or a stock")
    require(not any(token in annual["row"].lower() for token in ("eps", "per share", "weighted", "shares", "cash at beginning", "cash at end")), "EPS, shares and cash stock balances must not be bridged")
    a, c, p = (date.fromisoformat(r["period_end"]) for r in (annual, current, prior))
    require(a.year == p.year == c.year-1 and (c.month,c.day)==(p.month,p.day) and c.month < 12, "TTM comparable periods do not align")
    value = annual["value_units"]+current["value_units"]-prior["value_units"]
    require(math.isfinite(value), "TTM bridge produced nonfinite value")
    return {"id": recipe["id"], "statement": annual["statement"], "row": annual["row"],
            "period_end": current["period_end"], "scope": "ttm", "currency": annual["currency"],
            "scale": "units", "accounting_basis": annual["accounting_basis"],
            "consolidation_basis": annual["consolidation_basis"],
            "value_units": value,
            "method": "annual + current year-to-date - comparable prior year-to-date",
            "source_records": refs, "review_status": "reviewed-transcription"}


def verify_artifact(source, cache_dir, download=True):
    cache_dir = Path(cache_dir)
    supplied = source.get("artifact_file")
    if supplied:
        require(supplied == source["sha256"]+".pdf", "artifact filename must match immutable source hash")
        path = cache_dir.parent / "artifacts" / supplied
        require(path.is_file(), "committed primary source artifact missing")
    else:
        path = cache_dir / (source["sha256"]+".pdf")
    cache_used = path.exists()
    if not cache_used:
        require(download, "primary source artifact unavailable offline")
        request = urllib.request.Request(source["url"], headers={"User-Agent": "Oslo-financial-source-audit/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            target = urllib.parse.urlsplit(response.url)
            require(target.scheme == "https" and target.hostname in ISSUER_HOSTS, "source redirected outside approved issuer")
            data = response.read(25*1024*1024+1)
        require(len(data) <= 25*1024*1024 and data.startswith(b"%PDF"), "invalid or oversized issuer PDF")
        require(hashlib.sha256(data).hexdigest() == source["sha256"], "issuer artifact hash changed")
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    artifact = path.read_bytes()
    require(artifact.startswith(b"%PDF"), "cached source is not a PDF")
    require(hashlib.sha256(artifact).hexdigest() == source["sha256"], "cached issuer artifact hash mismatch")
    return {"source_id": source["id"], "sha256": source["sha256"], "artifact_cache_used": cache_used,
            "source_retrieved_at": source["retrieved_at"], "hash_checked_at": datetime.now(timezone.utc).isoformat()}


def load_primary(ticker, root, now=None, download=True):
    path = Path(root)/f"{ticker}.json"
    if not path.exists():
        return {"status": "not-configured", "ticker": ticker, "records": [], "derived": [], "issues": []}
    try:
        document = json.loads(path.read_text())
        require(document.get("ticker") == ticker, "primary ledger ticker mismatch")
        sources, records = validate(document, now)
        artifacts = [verify_artifact(s, Path(root)/"cache", download) for s in sources.values()]
        derived = [derive_ttm(records, recipe) for recipe in document.get("ttm_recipes", [])]
        keys = [(r["statement"],r["row"],r["period_end"],r["consolidation_basis"]) for r in derived]
        require(len(keys) == len(set(keys)) and len({r["id"] for r in derived}) == len(derived), "conflicting duplicate TTM bridge")
        return {"status": "reviewed-line-items" if all(r["review_status"] == "reviewed-transcription" for r in records.values()) else "partial-unreviewed", "ticker": ticker, "currency": document["currency"],
                "input_policy": document.get("input_policy", "audit-only"), "current_period_end": document.get("current_period_end"),
                "ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "records": list(records.values()),
                "derived": derived, "artifacts": artifacts, "issues": document.get("unresolved", []),
                "limitation": "Reviewed transcriptions and explicit bridges only; no whole-report or accounting-definition verification implied."}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "blocked", "ticker": ticker, "records": [], "derived": [], "issues": [str(exc)]}
