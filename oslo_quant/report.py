"""HTML dashboard generator — reads data/results/ and writes index.html."""

from __future__ import annotations

import datetime
import json
import math
import sys
from pathlib import Path
from typing import Any

from oslo_quant.config import COMPANIES, DATA_RESULTS, ROOT, TICKER_MAP


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(output_path: Path | None = None) -> Path:
    """Build index.html from all computed JSON results."""
    if output_path is None:
        output_path = ROOT / "index.html"
    data = _load_results()
    output_path.write_text(_build_html(data), encoding="utf-8")
    return output_path


def main() -> None:
    path = generate()
    print(f"Dashboard written to {path}")


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
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "—"
        return f"{f * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(v: Any, decimals: int = 2) -> str:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "—"
        return f"{f:.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _large(v: Any) -> str:
    try:
        n = float(v)
        if math.isnan(n) or math.isinf(n):
            return "—"
        if abs(n) >= 1_000_000_000:
            return f"{n / 1_000_000_000:.1f}B"
        if abs(n) >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        return f"{n:,.0f}"
    except (TypeError, ValueError):
        return "—"


def _large_ccy(ccy: str):
    """Return a _large formatter that appends the currency label."""
    def fmt(v: Any) -> str:
        s = _large(v)
        if s == "—" or not ccy:
            return s
        return f'{s}&thinsp;<span style="font-size:0.65rem;color:var(--slate)">{ccy}</span>'
    return fmt


def _ccy_badge(ccy: str) -> str:
    color = {"NOK": "blue", "USD": "green", "EUR": "yellow"}.get(ccy, "gray")
    return _badge(ccy or "?", color)


def _badge(text: str, color: str) -> str:
    palette = {
        "green":  ("#166534", "#dcfce7"),
        "yellow": ("#92400e", "#fef3c7"),
        "red":    ("#991b1b", "#fee2e2"),
        "blue":   ("#1e40af", "#dbeafe"),
        "gray":   ("#374151", "#f3f4f6"),
    }
    fg, bg = palette.get(color, palette["gray"])
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:99px;'
        f'font-size:0.73rem;font-weight:600;color:{fg};background:{bg};'
        f'border:1px solid {fg}22;white-space:nowrap">{text}</span>'
    )


def _latest(fw: dict) -> tuple[str, dict] | tuple[None, None]:
    periods = fw.get("periods", {})
    if not periods:
        return None, None
    key = sorted(periods.keys(), reverse=True)[0]
    return key, periods[key]


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _summary_row(ticker: str, fws: dict) -> str:
    period_cell = "—"

    # --- currency ---
    ccy_info = fws.get("currency", {})
    company = TICKER_MAP.get(ticker)
    fin_ccy = ccy_info.get("financial_currency") or (company.reporting_currency if company else "?")
    ccy_cell = _ccy_badge(fin_ccy)

    roe = npm = "—"
    if "dupont" in fws:
        yr, p = _latest(fws["dupont"])
        if p:
            period_cell = yr or "—"
            roe = _pct(p.get("roe_3factor"))
            npm = _pct(p.get("net_profit_margin"))

    piotroski = "—"
    if "piotroski" in fws:
        _, p = _latest(fws["piotroski"])
        if p:
            s = p.get("f_score", 0)
            c = "green" if s >= 8 else ("yellow" if s >= 5 else "red")
            piotroski = _badge(f"F{s} &nbsp;{p.get('interpretation','')}", c)

    sloan = "—"
    if "sloan" in fws:
        _, p = _latest(fws["sloan"])
        if p:
            q = p.get("earnings_quality", "Unknown")
            c = "green" if q == "High" else ("yellow" if q == "Moderate" else ("red" if q == "Low" else "gray"))
            sloan = _badge(f"{q} &nbsp;({_pct(p.get('cfo_accrual_ratio'))})", c)

    ohlson = "—"
    if "ohlson" in fws:
        _, p = _latest(fws["ohlson"])
        if p:
            prob = p.get("bankruptcy_probability")
            if prob is not None:
                c = "green" if prob < 0.10 else ("yellow" if prob < 0.30 else "red")
                label = p.get("interpretation", "").replace(" distress risk", "")
                ohlson = _badge(f"{_pct(prob)} &nbsp;{label}", c)

    altman = "—"
    if "altman" in fws:
        _, p = _latest(fws["altman"])
        if p:
            z = _num(p.get("z_score"))
            zone = p.get("zone", "Unknown")
            c = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else ("red" if zone == "Distress" else "gray"))
            altman = _badge(f"Z={z} &nbsp;{zone}", c)

    return (
        f'<tr onclick="toggleCard(\'{ticker}\')" style="cursor:pointer">'
        f'<td class="tk">{ticker}<div class="period-lbl">{period_cell}</div></td>'
        f'<td style="white-space:nowrap">{ccy_cell}</td>'
        f'<td>{roe}</td><td>{npm}</td>'
        f'<td>{piotroski}</td>'
        f'<td>{sloan}</td>'
        f'<td>{ohlson}</td>'
        f'<td>{altman}</td>'
        f'</tr>'
    )


# ---------------------------------------------------------------------------
# Detail cards
# ---------------------------------------------------------------------------

def _detail_card(ticker: str, fws: dict) -> str:
    company = TICKER_MAP.get(ticker)
    ccy_info = fws.get("currency", {})
    fin_ccy  = ccy_info.get("financial_currency") or (company.reporting_currency if company else "?")
    full_name = company.full_name if company else ""

    sections = "".join(
        _fw_section(name, fws[name], fin_ccy)
        for name in ["dupont", "piotroski", "sloan", "ohlson", "altman"]
        if name in fws and fws[name].get("periods")
    )
    if not sections:
        return ""
    name_html = (
        f'<span class="card-company">{full_name}</span>' if full_name else ""
    )
    return (
        f'<div id="card-{ticker}" class="detail-card" style="display:none">'
        f'<div class="card-header">'
        f'<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">'
        f'<span class="card-ticker">{ticker}</span>'
        f'{name_html}'
        f'<span>{_ccy_badge(fin_ccy)}</span>'
        f'</div>'
        f'<button class="card-close" onclick="toggleCard(\'{ticker}\')" '
        f'aria-label="Close">✕</button>'
        f'</div>'
        f'<div class="card-body">{sections}</div>'
        f'</div>'
    )


def _fw_section(name: str, fw: dict, ccy: str = "") -> str:
    titles = {
        "dupont":    "DuPont Decomposition",
        "piotroski": "Piotroski F-Score",
        "sloan":     "Sloan Accruals",
        "ohlson":    "Ohlson O-Score",
        "altman":    "Altman Z-Score",
    }
    periods = fw.get("periods", {})
    cols = sorted(periods.keys(), reverse=True)
    th = "".join(f"<th>{c}</th>" for c in cols)
    if name == "sloan":
        rows = _sloan_rows(periods, cols, ccy)
    else:
        builders = {
            "dupont":    _dupont_rows,
            "piotroski": _piotroski_rows,
            "ohlson":    _ohlson_rows,
            "altman":    _altman_rows,
        }
        rows = builders[name](periods, cols)
    return (
        f'<div class="fw-block">'
        f'<h4 class="fw-title">{titles[name]}</h4>'
        f'<div class="tscroll"><table class="fw-table">'
        f'<thead><tr><th>Metric</th>{th}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div></div>'
    )


# ---------------------------------------------------------------------------
# Per-framework row builders
# ---------------------------------------------------------------------------

def _row(label: str, cols: list[str], src: dict, key: str, fmt=_num, indent: bool = False) -> str:
    cells = "".join(f"<td>{fmt(src.get(c, {}).get(key))}</td>" for c in cols)
    cls = ' class="indent"' if indent else ""
    return f"<tr><td{cls}>{label}</td>{cells}</tr>"


def _dupont_rows(periods: dict, cols: list[str]) -> str:
    r = ""
    r += _row("ROE (3-factor)", cols, periods, "roe_3factor", _pct)
    r += _row("Net Profit Margin", cols, periods, "net_profit_margin", _pct)
    r += _row("Asset Turnover", cols, periods, "asset_turnover")
    r += _row("Equity Multiplier", cols, periods, "equity_multiplier")
    r += _row("EBIT Margin", cols, periods, "ebit_margin", _pct)
    r += _row("Tax Burden", cols, periods, "tax_burden")
    r += _row("Interest Burden", cols, periods, "interest_burden")
    r += _row("ROE (5-factor check)", cols, periods, "roe_5factor", _pct)
    return r


def _piotroski_rows(periods: dict, cols: list[str]) -> str:
    cells = ""
    for c in cols:
        s = periods.get(c, {}).get("f_score")
        if s is not None:
            color = "green" if s >= 8 else ("yellow" if s >= 5 else "red")
            cells += f"<td>{_badge(str(s), color)}</td>"
        else:
            cells += "<td>—</td>"
    r = f"<tr><td><strong>F-Score (0–9)</strong></td>{cells}</tr>"

    signals = [
        ("F1_positive_roa",            "F1 · Positive ROA"),
        ("F2_positive_cfo",            "F2 · Positive operating cash flow"),
        ("F3_roa_increasing",          "F3 · ROA improving year-on-year"),
        ("F4_accruals_quality",        "F4 · Cash flow exceeds net income"),
        ("F5_leverage_decreasing",     "F5 · Long-term debt ratio falling"),
        ("F6_liquidity_improving",     "F6 · Current ratio improving"),
        ("F7_no_dilution",             "F7 · No share issuance (no dilution)"),
        ("F8_gross_margin_improving",  "F8 · Gross margin improving"),
        ("F9_asset_turnover_improving","F9 · Asset turnover improving"),
    ]
    for key, label in signals:
        cells = ""
        for c in cols:
            v = periods.get(c, {}).get("signals", {}).get(key)
            if v == 1:
                cells += '<td style="color:#166534;font-weight:600">✓</td>'
            elif v == 0:
                cells += '<td style="color:#9ca3af">✗</td>'
            else:
                cells += "<td>—</td>"
        r += f'<tr><td class="indent">{label}</td>{cells}</tr>'

    r += _row("Current Ratio", cols, periods, "current_ratio")
    r += _row("Gross Margin", cols, periods, "gross_margin", _pct)
    r += _row("Asset Turnover", cols, periods, "asset_turnover")
    return r


def _sloan_rows(periods: dict, cols: list[str], ccy: str = "") -> str:
    cells = ""
    for c in cols:
        q = periods.get(c, {}).get("earnings_quality", "Unknown")
        color = "green" if q == "High" else ("yellow" if q == "Moderate" else ("red" if q == "Low" else "gray"))
        cells += f"<td>{_badge(q, color)}</td>"
    r = f"<tr><td><strong>Earnings Quality</strong></td>{cells}</tr>"
    r += _row("CFO Accrual Ratio", cols, periods, "cfo_accrual_ratio", _pct)
    r += _row("BS Accrual Ratio",  cols, periods, "bs_accrual_ratio",  _pct)
    fmt_abs = _large_ccy(ccy) if ccy else _large
    r += _row("Operating Cash Flow", cols, periods, "operating_cash_flow", fmt_abs)
    r += _row("Net Income",          cols, periods, "net_income",          fmt_abs)
    return r


def _ohlson_rows(periods: dict, cols: list[str]) -> str:
    r = _row("O-Score", cols, periods, "o_score")
    cells = ""
    for c in cols:
        prob = periods.get(c, {}).get("bankruptcy_probability")
        if prob is not None:
            color = "green" if prob < 0.10 else ("yellow" if prob < 0.30 else "red")
            cells += f"<td>{_badge(_pct(prob), color)}</td>"
        else:
            cells += "<td>—</td>"
    r += f"<tr><td><strong>Bankruptcy Probability</strong></td>{cells}</tr>"
    inp = {c: periods.get(c, {}).get("inputs", {}) for c in cols}
    r += _row("Total Liabilities / Total Assets", cols, inp, "tl_ta")
    r += _row("Working Capital / Total Assets",   cols, inp, "wc_ta")
    r += _row("Net Income / Total Assets (ROA)",  cols, inp, "ni_ta", _pct)
    r += _row("CFO / Total Liabilities",          cols, inp, "cfo_tl")
    return r


def _altman_rows(periods: dict, cols: list[str]) -> str:
    cells = ""
    for c in cols:
        z = periods.get(c, {}).get("z_score")
        zone = periods.get(c, {}).get("zone", "Unknown")
        color = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else ("red" if zone == "Distress" else "gray"))
        cells += f"<td>{_badge(f'Z={_num(z)} · {zone}', color)}</td>"
    r = f"<tr><td><strong>Z-Score &amp; Zone</strong></td>{cells}</tr>"
    r += _row("X1  Working Capital / Assets",    cols, periods, "x1_working_capital_to_assets")
    r += _row("X2  Retained Earnings / Assets",  cols, periods, "x2_retained_earnings_to_assets")
    r += _row("X3  EBIT / Assets",               cols, periods, "x3_ebit_to_assets", _pct)
    r += _row("X4  Book Equity / Liabilities",   cols, periods, "x4_book_equity_to_liabilities")
    r += _row("X5  Revenue / Assets",            cols, periods, "x5_revenue_to_assets")
    return r


# ---------------------------------------------------------------------------
# Currency verification table
# ---------------------------------------------------------------------------

def _currency_table(data: dict) -> str:
    rows = ""
    for company in COMPANIES:
        ticker = company.ticker
        ccy_info = data.get(ticker, {}).get("currency", {})

        fin_ccy   = ccy_info.get("financial_currency") or company.reporting_currency
        price_ccy = ccy_info.get("price_currency", "NOK")
        config_ccy = ccy_info.get("config_currency") or company.reporting_currency
        yf_ccy    = ccy_info.get("yfinance_currency") or "—"
        status    = ccy_info.get("verification_status", "pending")

        status_badge = {
            "verified":   _badge("✓ Verified", "green"),
            "mismatch":   _badge("⚠ Mismatch", "red"),
            "unverified": _badge("? Unverified", "yellow"),
            "pending":    _badge("— Pending", "gray"),
        }.get(status, _badge(status, "gray"))

        yf_cell = _ccy_badge(yf_ccy) if yf_ccy not in ("—", "", "Unknown") else "—"

        rows += (
            f"<tr>"
            f'<td class="tk">{ticker}</td>'
            f"<td>{company.full_name}</td>"
            f"<td style='white-space:nowrap'>{_ccy_badge(price_ccy)}</td>"
            f"<td style='white-space:nowrap'>{_ccy_badge(fin_ccy)}</td>"
            f"<td style='white-space:nowrap'>{_ccy_badge(config_ccy)}</td>"
            f"<td style='white-space:nowrap'>{yf_cell}</td>"
            f"<td>{status_badge}</td>"
            f"</tr>"
        )

    return (
        f'<div class="tscroll">'
        f"<table>"
        f"<thead><tr>"
        f"<th>Ticker</th><th>Company</th>"
        f"<th>Price&nbsp;Currency</th>"
        f"<th>Stmt&nbsp;Currency&nbsp;(used)</th>"
        f"<th>Config&nbsp;(hardcoded)</th>"
        f"<th>yfinance&nbsp;detected</th>"
        f"<th>Verification</th>"
        f"</tr></thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


# ---------------------------------------------------------------------------
# Full HTML
# ---------------------------------------------------------------------------

def _build_html(data: dict) -> str:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    n_ok = sum(1 for fws in data.values() if fws)

    summary_rows  = "\n".join(_summary_row(t, fws) for t, fws in data.items())
    detail_cards  = "\n".join(_detail_card(t, fws) for t, fws in data.items() if fws)
    currency_html = _currency_table(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oslo Quant — Financial Dashboard</title>
<style>
/* ── Reset & base ─────────────────────────────────────────── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --navy:#0f172a; --navy2:#1e293b; --navy3:#334155;
  --slate:#64748b; --muted:#94a3b8; --border:#e2e8f0;
  --bg:#f8fafc; --white:#ffffff;
  --green-fg:#166534; --green-bg:#dcfce7;
  --yellow-fg:#92400e; --yellow-bg:#fef3c7;
  --red-fg:#991b1b; --red-bg:#fee2e2;
  --accent:#2563eb;
}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  background:var(--bg);color:var(--navy2);font-size:14px;line-height:1.6}}

/* ── Header ───────────────────────────────────────────────── */
header{{
  background:var(--navy);
  border-bottom:3px solid var(--accent);
  padding:20px 32px;
  display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px
}}
.logo{{display:flex;align-items:baseline;gap:10px}}
.logo h1{{font-size:1.5rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px}}
.logo h1 span{{color:#60a5fa}}
.logo .tagline{{font-size:0.78rem;color:var(--muted);font-style:italic}}
.meta-pill{{
  background:var(--navy2);border:1px solid var(--navy3);border-radius:8px;
  padding:6px 14px;font-size:0.75rem;color:var(--muted);text-align:right;line-height:1.8
}}
.meta-pill strong{{color:#f8fafc}}

/* ── Layout ───────────────────────────────────────────────── */
main{{max-width:1440px;margin:0 auto;padding:28px 20px 60px}}

/* ── Section headings ─────────────────────────────────────── */
.section-title{{
  font-size:0.7rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--slate);margin:32px 0 10px;
  display:flex;align-items:center;gap:10px
}}
.section-title::after{{content:"";flex:1;height:1px;background:var(--border)}}

/* ── Legend panel ─────────────────────────────────────────── */
.legend-panel{{
  background:var(--white);border:1px solid var(--border);border-radius:12px;
  margin-bottom:24px;overflow:hidden
}}
.legend-toggle{{
  width:100%;border:none;background:none;cursor:pointer;
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 20px;font-weight:700;font-size:0.88rem;color:var(--navy2);
  text-align:left
}}
.legend-toggle .arrow{{transition:transform .25s;font-size:0.75rem;color:var(--slate)}}
.legend-toggle[aria-expanded="true"] .arrow{{transform:rotate(180deg)}}
.legend-body{{display:none;padding:0 20px 20px;border-top:1px solid var(--border)}}
.legend-body.open{{display:block}}

.color-guide{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 20px}}
.cg-item{{display:flex;align-items:center;gap:6px;font-size:0.78rem}}

.fw-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:4px}}
.fw-card{{
  background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px 16px
}}
.fw-card h5{{font-size:0.8rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.6px;color:var(--accent);margin-bottom:6px}}
.fw-card p{{font-size:0.79rem;color:var(--navy3);line-height:1.6;margin-bottom:6px}}
.fw-card .reading{{font-size:0.75rem;color:var(--slate);border-top:1px solid var(--border);
  padding-top:6px;margin-top:6px}}

.disclaimer{{
  margin-top:16px;padding:10px 14px;border-radius:6px;
  background:#fef9c3;border:1px solid #fde047;
  font-size:0.76rem;color:#713f12;line-height:1.6
}}
.disclaimer strong{{display:block;margin-bottom:2px}}

/* ── Summary table ────────────────────────────────────────── */
.tscroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px;
  border:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,.06)}}
table{{border-collapse:collapse;width:100%;min-width:800px}}
thead th{{
  background:var(--navy2);color:#f1f5f9;padding:11px 14px;text-align:left;
  font-size:0.7rem;text-transform:uppercase;letter-spacing:.7px;
  position:sticky;top:0;white-space:nowrap
}}
thead th:first-child{{min-width:120px}}
tbody tr{{background:var(--white);transition:background .12s}}
tbody tr:nth-child(even){{background:#fafbfc}}
tbody tr:hover{{background:#eff6ff}}
td{{padding:9px 14px;border-bottom:1px solid var(--border);vertical-align:middle}}
td.tk{{font-weight:700;font-size:0.88rem;color:var(--navy);white-space:nowrap}}
.period-lbl{{font-size:0.68rem;font-weight:400;color:var(--muted)}}

/* ── Detail cards ─────────────────────────────────────────── */
#detail-area{{margin-top:20px}}
.detail-card{{
  background:var(--white);border:1px solid var(--border);border-radius:12px;
  margin-bottom:16px;overflow:hidden;
  box-shadow:0 4px 12px rgba(0,0,0,.08)
}}
.card-header{{
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 20px;background:var(--navy2);
}}
.card-ticker{{font-weight:800;font-size:1.05rem;color:#f8fafc;letter-spacing:-.3px}}
.card-company{{font-size:0.82rem;font-weight:400;color:var(--muted)}}
.card-close{{
  border:none;background:transparent;color:var(--muted);font-size:1rem;
  cursor:pointer;padding:2px 6px;border-radius:4px;transition:color .15s
}}
.card-close:hover{{color:#f87171}}
.card-body{{padding:20px}}

/* ── Framework blocks inside cards ────────────────────────── */
.fw-block{{margin-bottom:24px}}
.fw-block:last-child{{margin-bottom:0}}
.fw-title{{
  font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;
  color:var(--accent);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)
}}
.fw-table{{min-width:480px;font-size:0.8rem}}
.fw-table thead th{{background:var(--navy3);font-size:0.68rem;padding:7px 10px}}
.fw-table td{{padding:6px 10px;border-bottom:1px solid var(--border)}}
.fw-table td:first-child{{color:var(--navy3);min-width:200px}}
.fw-table td.indent{{padding-left:22px;color:var(--slate);font-size:0.75rem}}
.fw-table tbody tr:hover td{{background:#f0f9ff}}

/* ── Footer ───────────────────────────────────────────────── */
footer{{
  text-align:center;padding:28px;color:var(--muted);font-size:0.72rem;
  border-top:1px solid var(--border);margin-top:40px
}}
footer a{{color:var(--accent);text-decoration:none}}
</style>
</head>
<body>

<header>
  <div class="logo">
    <h1>Oslo <span>Quant</span></h1>
    <span class="tagline">Pre-computation financial analysis · Oslo Børs</span>
  </div>
  <div class="meta-pill">
    <strong>{n_ok} of {len(COMPANIES)} companies</strong><br>
    Updated {now}
  </div>
</header>

<main>

<!-- ── Legend ─────────────────────────────────────────────── -->
<p class="section-title">Framework Guide &amp; Legends</p>
<div class="legend-panel">
  <button class="legend-toggle" aria-expanded="false" onclick="toggleLegend(this)">
    What do these frameworks measure? Click to expand
    <span class="arrow">▼</span>
  </button>
  <div class="legend-body">

    <div class="color-guide">
      <strong style="font-size:.78rem;color:var(--navy3);align-self:center">Colour coding:</strong>
      <span class="cg-item">{_badge("Green · Favourable","green")} Healthy / strong result</span>
      <span class="cg-item">{_badge("Amber · Moderate","yellow")} Neutral or watch zone</span>
      <span class="cg-item">{_badge("Red · Concern","red")} Weak or elevated risk</span>
    </div>

    <div class="fw-grid">
      <div class="fw-card">
        <h5>DuPont Decomposition</h5>
        <p>Breaks Return on Equity (ROE) into three drivers: profit margin, asset efficiency, and financial leverage. A 5-factor version further splits profitability into tax and interest burden components.</p>
        <div class="reading">
          <strong>How to read:</strong> ROE &gt; 15% is generally strong. An equity multiplier above 3 signals significant use of debt. A high ROE driven by leverage alone is less sustainable than one driven by margins.
        </div>
      </div>
      <div class="fw-card">
        <h5>Piotroski F-Score</h5>
        <p>A checklist of 9 binary signals (each scores 0 or 1) across three dimensions: profitability, capital structure, and operating efficiency. Higher scores indicate improving financial health.</p>
        <div class="reading">
          <strong>How to read:</strong> 8–9 = Strong. 5–7 = Moderate. 0–4 = Weak. A rising F-Score over time is more meaningful than a single year's reading.
        </div>
      </div>
      <div class="fw-card">
        <h5>Sloan Accruals</h5>
        <p>Measures earnings quality. Companies where cash flow from operations consistently exceeds reported net income tend to have higher-quality earnings that are more likely to persist.</p>
        <div class="reading">
          <strong>How to read:</strong> A negative accrual ratio (High quality) means cash earnings exceed accounting profits — a good sign. A positive ratio (Low quality) suggests profits are largely non-cash accruals that may not repeat.
        </div>
      </div>
      <div class="fw-card">
        <h5>Ohlson O-Score</h5>
        <p>A logistic regression model (Ohlson, 1980) that estimates the statistical probability of bankruptcy within one year. It uses nine financial ratios covering size, leverage, liquidity, and profitability.</p>
        <div class="reading">
          <strong>How to read:</strong> &lt;10% = Low risk. 10–30% = Moderate. &gt;30% = Elevated. The model was calibrated on US firms in the 1970s — treat probabilities as directional, not precise.
        </div>
      </div>
      <div class="fw-card">
        <h5>Altman Z-Score</h5>
        <p>A weighted combination of five balance-sheet ratios used to classify a company as financially safe, in a grey zone, or in distress. X4 uses book equity throughout to avoid currency-mismatch errors on dual-listed companies.</p>
        <div class="reading">
          <strong>How to read:</strong> Z &gt; 2.99 = Safe. Z 1.81–2.99 = Grey zone. Z &lt; 1.81 = Distress. Note: the model was designed for US manufacturing firms and is known to be less reliable for shipping, offshore, and capital-intensive sectors.
        </div>
      </div>
    </div>

    <div class="disclaimer">
      <strong>⚠ Data quality &amp; model limitations</strong>
      Financial data is sourced from Yahoo Finance via yfinance. Some companies in this portfolio (e.g. Frontline, Borr Drilling, Hafnia) report financial statements in USD while their Oslo Børs shares are priced in NOK. Previous versions of this dashboard used market capitalisation (NOK) for the Altman X4 ratio, producing inflated Z-Scores due to the currency mismatch. This has been corrected — book equity (in the reporting currency) is now used throughout. All models were originally calibrated on US companies and should be treated as relative indicators, not precise predictions. Always verify key figures against official annual reports before making decisions.
    </div>

  </div>
</div>

<!-- ── Currency Verification ──────────────────────────────── -->
<p class="section-title">Currency Verification</p>
<p style="font-size:0.76rem;color:var(--slate);margin-bottom:10px">
  Stock prices are always quoted in <strong>NOK</strong> on Oslo Børs.
  Financial statements may be reported in USD, EUR, or NOK.
  All framework ratios divide statement values in the same currency, so they are currency-neutral.
  The table below confirms the detected reporting currency per company.
</p>
{currency_html}

<!-- ── Summary ─────────────────────────────────────────────── -->
<p class="section-title">Summary — Most Recent Annual Period</p>
<p style="font-size:0.76rem;color:var(--slate);margin-bottom:10px">
  Click any row to open full historical details below.
</p>
<div class="tscroll">
<table>
  <thead>
    <tr>
      <th>Company</th>
      <th>Stmts&nbsp;Ccy</th>
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

<!-- ── Detail cards ─────────────────────────────────────────── -->
<div id="detail-area">
{detail_cards}
</div>

</main>

<footer>
  Oslo Quant · Data from <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a> via yfinance ·
  Frameworks: DuPont, Piotroski (1980), Sloan (1996), Ohlson (1980), Altman (1968) ·
  Results are for informational purposes only and do not constitute investment advice.
</footer>

<script>
function toggleLegend(btn) {{
  const body = btn.nextElementSibling;
  const open = body.classList.toggle('open');
  btn.setAttribute('aria-expanded', open);
}}

function toggleCard(ticker) {{
  const card = document.getElementById('card-' + ticker);
  if (!card) return;
  const visible = card.style.display !== 'none';
  card.style.display = visible ? 'none' : 'block';
  if (!visible) {{
    card.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}
}}
</script>

</body>
</html>"""
