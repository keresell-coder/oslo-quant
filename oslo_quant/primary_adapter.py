"""Select a separately audited primary current column; never mutate provider frames."""
from __future__ import annotations
import calendar
import pandas as pd

from oslo_quant.primary_financials import PrimaryInputError, require

CORE = {"income_stmt": {"Total Revenue", "Gross Profit", "Net Income"},
        "balance_sheet": {"Total Assets", "Stockholders Equity", "Current Assets", "Current Liabilities", "Total Liabilities Net Minority Interest"},
        "cash_flow": {"Operating Cash Flow"}}


def apply_primary_current(statements, primary, currency, provider_periods=None):
    audit = {"status": "not-applied", "reason": "No eligible selected primary current inputs", "selected": [],
             "provider_values_preserved": True, "unavailable": ["standardized EBIT", "TTM EPS", "generic free cash flow"]}
    if primary.get("status") != "reviewed-line-items" or primary.get("input_policy") != "selected-current-primary":
        return statements, audit
    try:
        require(primary.get("currency") == currency, "primary/provider reporting currency mismatch")
        end = primary.get("current_period_end")
        require(isinstance(end,str), "missing selected current period")
        provider_dates = [p for values in (provider_periods or {}).values() for p in values]
        for frame in (statements[key] for key in CORE):
            for col in frame.columns:
                text = str(col)
                if text.isdigit() and len(text) == 4:
                    provider_dates.append(text+"-12-31")
                elif text.startswith("LTM "):
                    year,month = map(int,text[4:11].split("-"))
                    provider_dates.append(f"{year:04}-{month:02}-{calendar.monthrange(year,month)[1]:02}")
        require(not provider_dates or max(provider_dates) <= end, "primary override is older than provider observations")
        selected = [r for r in primary.get("derived", []) if r["period_end"] == end and r.get("consolidation_basis") == "group"]
        selected += [r for r in primary.get("records", []) if r["scope"] == "instant" and r["period_end"] == end and r["review_status"] == "reviewed-transcription" and r.get("consolidation_basis") == "group"]
        for statement, rows in CORE.items():
            available = {r["row"] for r in selected if r["statement"] == statement}
            require(rows <= available, "primary current inputs incomplete: "+statement+": "+', '.join(sorted(rows-available)))
        identities = [(r["statement"],r["row"]) for r in selected]
        require(len(identities) == len(set(identities)), "conflicting selected primary field/basis")
        label = "LTM "+end[:7]
        output = dict(statements)
        for statement in CORE:
            frame = statements[statement].copy()
            # Exactly one virtual current period; annual provider columns remain unchanged.
            frame = frame.drop(columns=[c for c in frame.columns if str(c).startswith('LTM ')])
            facts = [r for r in selected if r["statement"] == statement]
            frame = frame.reindex(frame.index.union([r["row"] for r in facts],sort=False))
            frame[label] = float('nan')
            for fact in facts:
                frame.loc[fact['row'],label]=fact['value_units']
            output[statement]=frame
        provider_virtual = {key: {str(col): {str(row): float(value) if pd.notna(value) else None for row,value in statements[key][col].items()}
                                  for col in statements[key].columns if str(col).startswith("LTM ")}
                            for key in CORE}
        comparisons = []
        for fact in selected:
            frame = statements[fact["statement"]]
            comparable = frame.loc[fact["row"],label] if fact["row"] in frame.index and label in frame.columns else None
            comparisons.append({"primary_record_id":fact["id"], "primary_value":fact["value_units"],
                "provider_period":label if comparable is not None else None,
                "provider_value":float(comparable) if comparable is not None and pd.notna(comparable) else None,
                "difference":float(comparable)-fact["value_units"] if comparable is not None and pd.notna(comparable) else None,
                "reason":"Explicit selected primary current period; not an unlabeled provider overwrite",
                "scope_verification":"Primary mapping reviewed; provider definition not independently confirmed"})
        audit.update(status="applied-selected-primary", provider_virtual_current=provider_virtual, provider_comparisons=comparisons, reason="Primary TTM flow bridge and same-date primary balance sheet; provider annual columns retained", period_end=end, label=label,
            selected=[{"id":r["id"],"statement":r["statement"],"row":r["row"],"value":r["value_units"],"scope":r["scope"],"source_records":r.get("source_records",[r["id"]])} for r in selected],
            coverage={k:[end] for k in CORE})
        return output,audit
    except (ValueError,KeyError,TypeError) as exc:
        audit.update(status="blocked",reason=str(exc))
        return statements,audit
