"""HTML dashboard generator — reads data/results/ and writes report.html."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Any

from oslo_quant.config import COMPANIES, DATA_RESULTS, ROOT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(output_path: Path | None = None) -> Path:
    """Build report.html from all computed JSON results."""
    if output_path is None:
        output_path = ROOT / "report.html"

    data = _load_results()
    output_path.write_text(_build_html(data), encoding="utf-8")
    return output_path


def main() -> None:
    path = generate()
    print(f"Report written to {path}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_results() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for company in COMPANIES:
        ticker = company.ticker
        result_dir = DATA_RESULTS / ticker
        if not result_dir.exists():
            continue
        out[ticker] = {}
        for fw_file in sorted(result_dir.glob("*.json")):
            try:
                out[ticker][fw_file.stem] = json.loads(fw_file.read_text())
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(v: Any, decimals: int = 1) -> str:
    try:
        return f"{float(v) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(v: Any, decimals: int = 2) -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _large(v: Any) -> str:
    try:
        n = float(v)
        if abs(n) >= 1_000_000_000:
            return f"{n / 1_000_000_000:.1f}B"
        if abs(n) >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        return f"{n:,.0f}"
    except (TypeError, ValueError):
        return "—"


def _badge(text: str, color: str) -> str:
    palette = {
        "green":  "#16a34a",
        "yellow": "#d97706",
        "red":    "#dc2626",
        "blue":   "#2563eb",
        "gray":   "#6b7280",
    }
    bg = palette.get(color, palette["gray"])
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'font-size:0.78rem;font-weight:600;color:#fff;background:{bg}">{text}</span>'
    )


def _latest(fw: dict) -> tuple[str, dict] | tuple[None, None]:
    periods = fw.get("periods", {})
    if not periods:
        return None, None
    key = sorted(periods.keys(), reverse=True)[0]
    return key, periods[key]


# ---------------------------------------------------------------------------
# Summary table row
# ---------------------------------------------------------------------------

def _summary_row(ticker: str, fws: dict) -> str:
    # DuPont
    roe = npm = "—"
    if "dupont" in fws:
        _, p = _latest(fws["dupont"])
        if p:
            roe = _pct(p.get("roe_3factor"))
            npm = _pct(p.get("net_profit_margin"))

    # Piotroski
    piotroski = "—"
    if "piotroski" in fws:
        _, p = _latest(fws["piotroski"])
        if p:
            s = p.get("f_score", 0)
            c = "green" if s >= 8 else ("yellow" if s >= 5 else "red")
            piotroski = _badge(f"F{s} · {p.get('interpretation', '')}", c)

    # Sloan
    sloan = "—"
    if "sloan" in fws:
        _, p = _latest(fws["sloan"])
        if p:
            q = p.get("earnings_quality", "Unknown")
            c = "green" if q == "High" else ("yellow" if q == "Moderate" else "red")
            sloan = _badge(f"{q} ({_pct(p.get('cfo_accrual_ratio'))})", c)

    # Ohlson
    ohlson = "—"
    if "ohlson" in fws:
        _, p = _latest(fws["ohlson"])
        if p:
            prob = p.get("bankruptcy_probability")
            if prob is not None:
                c = "green" if prob < 0.10 else ("yellow" if prob < 0.30 else "red")
                label = p.get("interpretation", "").replace(" distress risk", "")
                ohlson = _badge(f"{_pct(prob)} · {label}", c)

    # Altman
    altman = "—"
    if "altman" in fws:
        _, p = _latest(fws["altman"])
        if p:
            z = _num(p.get("z_score"))
            zone = p.get("zone", "Unknown")
            c = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else "red")
            altman = _badge(f"Z={z} · {zone}", c)

    return (
        f"<tr>"
        f"<td class='tk'>{ticker}</td>"
        f"<td>{roe}</td><td>{npm}</td>"
        f"<td>{piotroski}</td>"
        f"<td>{sloan}</td>"
        f"<td>{ohlson}</td>"
        f"<td>{altman}</td>"
        f"</tr>"
    )


# ---------------------------------------------------------------------------
# Detail accordion per company
# ---------------------------------------------------------------------------

def _detail_card(ticker: str, fws: dict) -> str:
    sections = "".join(
        _fw_section(name, fws[name])
        for name in ["dupont", "piotroski", "sloan", "ohlson", "altman"]
        if name in fws and fws[name].get("periods")
    )
    return (
        f"<details class='card'>"
        f"<summary>{ticker}</summary>"
        f"<div class='card-body'>{sections}</div>"
        f"</details>"
    )


def _fw_section(name: str, fw: dict) -> str:
    titles = {
        "dupont": "DuPont Decomposition",
        "piotroski": "Piotroski F-Score",
        "sloan": "Sloan Accruals",
        "ohlson": "Ohlson O-Score",
        "altman": "Altman Z-Score",
    }
    periods = fw.get("periods", {})
    cols = sorted(periods.keys(), reverse=True)
    th = "".join(f"<th>{c}</th>" for c in cols)
    builders = {
        "dupont": _dupont_rows,
        "piotroski": _piotroski_rows,
        "sloan": _sloan_rows,
        "ohlson": _ohlson_rows,
        "altman": _altman_rows,
    }
    rows = builders[name](periods, cols)
    return (
        f"<div class='fw'><h4>{titles[name]}</h4>"
        f"<div class='tscroll'><table>"
        f"<thead><tr><th>Metric</th>{th}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div></div>"
    )


# ---------------------------------------------------------------------------
# Per-framework row builders
# ---------------------------------------------------------------------------

def _row(label: str, cols: list[str], data: dict, key: str, fmt=_num) -> str:
    cells = "".join(
        f"<td>{fmt(data.get(c, {}).get(key))}</td>" for c in cols
    )
    return f"<tr><td class='ml'>{label}</td>{cells}</tr>"


def _dupont_rows(periods: dict, cols: list[str]) -> str:
    r = ""
    r += _row("ROE (3-factor)", cols, periods, "roe_3factor", _pct)
    r += _row("Net Profit Margin", cols, periods, "net_profit_margin", _pct)
    r += _row("Asset Turnover", cols, periods, "asset_turnover")
    r += _row("Equity Multiplier", cols, periods, "equity_multiplier")
    r += _row("EBIT Margin", cols, periods, "ebit_margin", _pct)
    r += _row("Tax Burden", cols, periods, "tax_burden")
    r += _row("Interest Burden", cols, periods, "interest_burden")
    r += _row("ROE (5-factor)", cols, periods, "roe_5factor", _pct)
    return r


def _piotroski_rows(periods: dict, cols: list[str]) -> str:
    # Total score with badge
    cells = ""
    for c in cols:
        s = periods.get(c, {}).get("f_score")
        if s is not None:
            color = "green" if s >= 8 else ("yellow" if s >= 5 else "red")
            cells += f"<td>{_badge(str(s), color)}</td>"
        else:
            cells += "<td>—</td>"
    r = f"<tr><td class='ml'>F-Score (0–9)</td>{cells}</tr>"

    signals = [
        ("F1_positive_roa", "F1 Positive ROA"),
        ("F2_positive_cfo", "F2 Positive CFO"),
        ("F3_roa_increasing", "F3 ROA Increasing"),
        ("F4_accruals_quality", "F4 Accruals Quality"),
        ("F5_leverage_decreasing", "F5 Leverage ↓"),
        ("F6_liquidity_improving", "F6 Liquidity ↑"),
        ("F7_no_dilution", "F7 No Dilution"),
        ("F8_gross_margin_improving", "F8 Gross Margin ↑"),
        ("F9_asset_turnover_improving", "F9 Asset Turnover ↑"),
    ]
    for key, label in signals:
        cells = ""
        for c in cols:
            v = periods.get(c, {}).get("signals", {}).get(key)
            cells += f"<td>{'✓' if v == 1 else ('✗' if v == 0 else '—')}</td>"
        r += f"<tr><td class='ml sig'>{label}</td>{cells}</tr>"

    r += _row("Current Ratio", cols, periods, "current_ratio")
    r += _row("Gross Margin", cols, periods, "gross_margin", _pct)
    return r


def _sloan_rows(periods: dict, cols: list[str]) -> str:
    # Quality badge
    cells = ""
    for c in cols:
        q = periods.get(c, {}).get("earnings_quality", "Unknown")
        color = "green" if q == "High" else ("yellow" if q == "Moderate" else ("red" if q == "Low" else "gray"))
        cells += f"<td>{_badge(q, color)}</td>"
    r = f"<tr><td class='ml'>Earnings Quality</td>{cells}</tr>"
    r += _row("CFO Accrual Ratio", cols, periods, "cfo_accrual_ratio", _pct)
    r += _row("BS Accrual Ratio", cols, periods, "bs_accrual_ratio", _pct)
    r += _row("Operating Cash Flow", cols, periods, "operating_cash_flow", _large)
    r += _row("Net Income", cols, periods, "net_income", _large)
    return r


def _ohlson_rows(periods: dict, cols: list[str]) -> str:
    r = _row("O-Score", cols, periods, "o_score")
    # Probability badge
    cells = ""
    for c in cols:
        prob = periods.get(c, {}).get("bankruptcy_probability")
        if prob is not None:
            color = "green" if prob < 0.10 else ("yellow" if prob < 0.30 else "red")
            cells += f"<td>{_badge(_pct(prob), color)}</td>"
        else:
            cells += "<td>—</td>"
    r += f"<tr><td class='ml'>Bankruptcy Probability</td>{cells}</tr>"

    inp_cols = {c: periods.get(c, {}).get("inputs", {}) for c in cols}
    r += _row("TL / TA (Leverage)", cols, inp_cols, "tl_ta")
    r += _row("WC / TA", cols, inp_cols, "wc_ta")
    r += _row("NI / TA (ROA)", cols, inp_cols, "ni_ta", _pct)
    r += _row("CFO / TL", cols, inp_cols, "cfo_tl")
    return r


def _altman_rows(periods: dict, cols: list[str]) -> str:
    # Zone badge
    cells = ""
    for c in cols:
        z = periods.get(c, {}).get("z_score")
        zone = periods.get(c, {}).get("zone", "Unknown")
        color = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else "red")
        cells += f"<td>{_badge(f'Z={_num(z)} · {zone}', color)}</td>"
    r = f"<tr><td class='ml'>Z-Score &amp; Zone</td>{cells}</tr>"
    r += _row("X1  WC / Assets", cols, periods, "x1_working_capital_to_assets")
    r += _row("X2  RE / Assets", cols, periods, "x2_retained_earnings_to_assets")
    r += _row("X3  EBIT / Assets", cols, periods, "x3_ebit_to_assets", _pct)
    r += _row("X4  Equity / Liab", cols, periods, "x4_equity_to_liabilities")
    r += _row("X5  Revenue / Assets", cols, periods, "x5_revenue_to_assets")
    return r


# ---------------------------------------------------------------------------
# Full HTML template
# ---------------------------------------------------------------------------

def _build_html(data: dict) -> str:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    n_ok = sum(1 for fws in data.values() if fws)

    summary_rows = "\n".join(_summary_row(t, fws) for t, fws in data.items())
    detail_cards = "\n".join(_detail_card(t, fws) for t, fws in data.items() if fws)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oslo Quant Dashboard</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#f1f5f9;color:#1e293b;font-size:14px;line-height:1.5}}
a{{color:inherit}}

/* Header */
header{{background:#0f172a;color:#f8fafc;padding:24px 32px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
header h1{{font-size:1.4rem;font-weight:700;letter-spacing:-0.3px}}
header h1 span{{color:#38bdf8}}
.meta{{font-size:0.8rem;color:#94a3b8}}

/* Layout */
main{{max-width:1400px;margin:0 auto;padding:24px 16px}}

/* Section headings */
h2{{font-size:1.05rem;font-weight:700;color:#0f172a;margin:32px 0 12px;
  padding-bottom:6px;border-bottom:2px solid #e2e8f0}}
h4{{font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
  color:#475569;margin:16px 0 6px}}

/* Summary table */
.tscroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;white-space:nowrap}}
thead th{{background:#1e293b;color:#f1f5f9;padding:8px 12px;text-align:left;
  font-size:0.75rem;text-transform:uppercase;letter-spacing:.5px;position:sticky;top:0}}
tbody tr:nth-child(even){{background:#f8fafc}}
tbody tr:hover{{background:#e0f2fe}}
td{{padding:7px 12px;border-bottom:1px solid #e2e8f0;vertical-align:middle}}
td.tk{{font-weight:700;font-size:0.85rem;color:#0f172a;white-space:nowrap}}

/* Accordion cards */
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  margin-bottom:10px;overflow:hidden}}
.card summary{{padding:14px 18px;font-weight:700;font-size:0.95rem;cursor:pointer;
  user-select:none;list-style:none;display:flex;align-items:center;gap:8px;
  background:#f8fafc}}
.card summary::before{{content:"▶";font-size:0.6rem;color:#94a3b8;
  transition:transform .2s;display:inline-block}}
.card[open] summary::before{{transform:rotate(90deg)}}
.card-body{{padding:16px 18px;border-top:1px solid #e2e8f0}}

/* Framework sections */
.fw{{margin-bottom:20px}}
.fw table thead th{{background:#334155}}
.fw table td,.fw table th{{padding:5px 10px}}
td.ml{{font-size:0.8rem;color:#334155;min-width:160px}}
td.ml.sig{{padding-left:20px;color:#64748b}}

/* Footer */
footer{{text-align:center;padding:24px;color:#94a3b8;font-size:0.75rem}}
</style>
</head>
<body>

<header>
  <h1>Oslo <span>Quant</span> Dashboard</h1>
  <div class="meta">
    {n_ok} of {len(COMPANIES)} companies computed &nbsp;·&nbsp;
    Last updated: {now}
  </div>
</header>

<main>

<h2>Summary — Most Recent Annual Period</h2>
<div class="tscroll">
<table>
  <thead>
    <tr>
      <th>Company</th>
      <th>ROE</th>
      <th>Net Margin</th>
      <th>Piotroski F-Score</th>
      <th>Sloan Earnings Quality</th>
      <th>Ohlson Bankruptcy Risk</th>
      <th>Altman Z-Score</th>
    </tr>
  </thead>
  <tbody>
{summary_rows}
  </tbody>
</table>
</div>

<h2>Company Details — All Periods</h2>
{detail_cards}

</main>
<footer>Generated by oslo-quant &nbsp;·&nbsp; Data sourced from Yahoo Finance</footer>
</body>
</html>"""
