"""Offline preview over frozen actual provider frames; no production writes."""

from pathlib import Path
import json, sys, hashlib
from datetime import datetime
import pandas as pd
from yfinance.utils import camel2title

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oslo_quant.primary_financials import load_primary
from oslo_quant.debt_components import qualify_debt
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant import report


def frozen_statements(ticker):
    root = ROOT / "tests/fixtures/debt_provider_20261025" / ticker
    out = {}
    for key in ["balance_sheet", "income_stmt", "cash_flow"]:
        raw = json.loads((root / f"yearly_{key}.json").read_text())
        frame = pd.DataFrame(
            raw["data"],
            index=raw["index"],
            columns=[p[:4] for p in raw["columns"]],
            dtype=float,
        )
        frame.index = camel2title(
            frame.index,
            sep=" ",
            acronyms=(
                ["PPE"] if key == "balance_sheet" else ["EBIT", "EBITDA", "EPS", "NI"]
            ),
        )
        out[key] = frame
    out["prices"] = pd.DataFrame()
    balance = json.loads((root / "yearly_balance_sheet.json").read_text())
    out["meta"] = {
        "annual_balance_period_ends": [value[:10] for value in balance["columns"]]
    }
    return out, json.loads((root / "currency.json").read_text())["financialCurrency"]


def preview(ticker):
    statements, currency = frozen_statements(ticker)
    primary = load_primary(ticker, ROOT / "data/debt", download=False)
    before = PiotroskiFramework().compute(statements, ticker)
    before.pop("computed_at")
    observations = [r["source"]["retrieved_at"] for r in primary.get("records", [])]
    observations.append(
        json.loads(
            (
                ROOT
                / "tests/fixtures/debt_provider_20261025"
                / ticker
                / "currency.json"
            ).read_text()
        )["observed_at"]
    )
    evaluation = max(datetime.fromisoformat(value) for value in observations)
    audit = qualify_debt(primary, statements, ticker, currency, evaluation)
    statements["meta"] = {"reporting_currency": currency, "debt_inputs": audit}
    after = PiotroskiFramework().compute(statements, ticker)
    after.pop("computed_at")
    return {
        "scope": "Actual frozen provider annual frames; primary overlay only for explicitly qualified debt pairs. Not a live publication or full-company verification.",
        "financial_currency": currency,
        "before": before,
        "after": after,
        "debt_inputs": audit,
    }


if __name__ == "__main__":
    out = ROOT / "docs/review-evidence/debt-reconciliation"
    out.mkdir(parents=True, exist_ok=True)
    results = {
        ticker: preview(ticker)
        for ticker in ["NOD.OL", "MOWI.OL", "DOFG.OL", "PUBLI.OL"]
    }
    (out / "before-after.json").write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n"
    )
    for t, x in results.items():
        print(
            t,
            "source",
            x["debt_inputs"]["status"],
            "FY2025 F5",
            x["before"]["periods"]
            .get("2025", {})
            .get("signals", {})
            .get("F5_leverage_decreasing"),
            "->",
            x["after"]["periods"]
            .get("2025", {})
            .get("signals", {})
            .get("F5_leverage_decreasing"),
            "full score",
            x["after"]["periods"].get("2025", {}).get("f_score"),
        )

    panels = []
    for ticker in ["NOD.OL", "MOWI.OL"]:
        result = results[ticker]
        panels.append(
            "<h2>"
            + ticker
            + " — frozen annual source preview</h2>"
            + report._debt_inputs(result["debt_inputs"])
            + "<table>"
            + report._piotroski_rows(result["after"]["periods"], ["2025", "2024"])
            + "</table>"
        )
    text = (
        "<!doctype html><meta charset=utf-8><title>Debt source review</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;vertical-align:top}details{margin:20px 0}.tscroll{overflow:auto}h1{color:#7c2d12}</style><h1>OFFLINE REVIEW — actual frozen annual provider frames; selected primary debt. Not live output or current-interim score.</h1>"
        + "".join(panels)
    )
    text = text.replace(
        '<details class="primary-inputs">', '<details class="primary-inputs" open>'
    )
    (out / "source-preview.html").write_text(text)
