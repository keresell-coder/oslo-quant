"""HTML dashboard generator — reads data/results/ and writes index.html."""

from __future__ import annotations

import datetime
import json
import math
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

def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _pct(v: Any, decimals: int = 1) -> str:
    f = _safe_float(v)
    return "—" if f is None else f"{f * 100:.{decimals}f}%"


def _num(v: Any, decimals: int = 2) -> str:
    f = _safe_float(v)
    return "—" if f is None else f"{f:.{decimals}f}"


def _large(v: Any) -> str:
    f = _safe_float(v)
    if f is None:
        return "—"
    if abs(f) >= 1_000_000_000:
        return f"{f / 1_000_000_000:.1f}B"
    if abs(f) >= 1_000_000:
        return f"{f / 1_000_000:.1f}M"
    return f"{f:,.0f}"


def _large_ccy(ccy: str):
    def fmt(v: Any) -> str:
        s = _large(v)
        if s == "—" or not ccy:
            return s
        return f'{s}&thinsp;<span style="font-size:0.65rem;color:var(--slate)">{ccy}</span>'
    return fmt


def _badge(text: str, color: str) -> str:
    palette = {
        "green":  ("#ffffff", "#16a34a"),
        "yellow": ("#ffffff", "#d97706"),
        "red":    ("#ffffff", "#dc2626"),
        "blue":   ("#ffffff", "#2563eb"),
        "gray":   ("#374151", "#e5e7eb"),
        "indigo": ("#ffffff", "#4f46e5"),
    }
    fg, bg = palette.get(color, palette["gray"])
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:99px;'
        f'font-size:0.73rem;font-weight:700;color:{fg};background:{bg};'
        f'letter-spacing:0.01em;white-space:nowrap">{text}</span>'
    )


def _ccy_badge(ccy: str) -> str:
    color = {"NOK": "blue", "USD": "indigo", "EUR": "yellow"}.get(ccy, "gray")
    return _badge(ccy or "?", color)


def _latest(fw: dict) -> tuple[str, dict] | tuple[None, None]:
    periods = fw.get("periods", {})
    if not periods:
        return None, None
    key = sorted(periods.keys(), reverse=True)[0]
    return key, periods[key]


# ---------------------------------------------------------------------------
# Company one-line summaries
# ---------------------------------------------------------------------------

# Sectors where the original Altman Z-Score (manufacturing) is unreliable.
# For these companies the Z'' non-manufacturing variant is more appropriate.
_ALTMAN_CAUTION = {
    "DOFG.OL", "ODL.OL", "BORR.OL", "FRO.OL", "HAFNI.OL",  # shipping/offshore
    "MOWI.OL",                                                  # aquaculture
    "KOG.OL", "KMAR.OL",                                       # defence / maritime tech
    "PUBLI.OL",                                                 # real estate
}


def _company_summary(ticker: str, fws: dict) -> str:
    positives: list[str] = []
    concerns:  list[str] = []

    _, dp = _latest(fws.get("dupont", {}))
    if dp:
        roe = _safe_float(dp.get("roe_3factor"))
        em  = _safe_float(dp.get("equity_multiplier"))
        if roe is not None:
            if roe >= 0.15:
                driver = "leverage" if (em or 0) > 4 else "operations"
                positives.append(f"strong ROE of {_pct(roe)} driven by {driver}")
            elif roe < 0:
                concerns.append(f"negative equity returns ({_pct(roe)} ROE)")
        if em is not None and em > 5:
            concerns.append(f"highly leveraged ({_num(em)}× equity multiplier)")

    _, pio = _latest(fws.get("piotroski", {}))
    if pio:
        f = pio.get("f_score")
        if f is not None:
            if f >= 7:
                positives.append(f"solid fundamentals (F-Score {f}/9)")
            elif f <= 3:
                concerns.append(f"weak fundamental signals (F-Score {f}/9)")

    _, sl = _latest(fws.get("sloan", {}))
    if sl:
        q = sl.get("earnings_quality", "Unknown")
        if q == "High":
            positives.append("cash-backed earnings")
        elif q == "Low":
            concerns.append("accrual-heavy earnings (low cash conversion)")

    _, oh = _latest(fws.get("ohlson", {}))
    if oh:
        prob = _safe_float(oh.get("bankruptcy_probability"))
        if prob is not None:
            if prob < 0.05:
                positives.append("very low distress risk (Ohlson)")
            elif prob > 0.20:
                concerns.append(f"elevated distress signal ({_pct(prob)}, Ohlson)")

    _, al = _latest(fws.get("altman", {}))
    if al:
        # Use Z'' for all companies — none of the 14 qualify as US manufacturing
        if al.get("z_score_prime") is not None:
            zone  = al.get("zone_prime", "Unknown")
            z     = _safe_float(al.get("z_score_prime"))
            label = "Z''="
        else:
            zone  = al.get("zone", "Unknown")
            z     = _safe_float(al.get("z_score"))
            label = "Z="
        if zone == "Safe":
            positives.append(f"Altman {label}{_num(z)} in safe zone")
        elif zone == "Distress":
            concerns.append(f"Altman flags distress ({label}{_num(z)})")

    if not positives and not concerns:
        return ""
    if positives and concerns:
        return (
            f"Screens positively on {', '.join(positives[:2])}; "
            f"flagged for {', '.join(concerns[:2])}."
        )
    if positives:
        return f"Strong across frameworks: {', '.join(positives[:3])}."
    return f"Concerns flagged: {', '.join(concerns[:3])}."


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _summary_row(ticker: str, fws: dict) -> str:
    period_cell = "—"
    ccy_info    = fws.get("currency", {})
    company     = TICKER_MAP.get(ticker)
    fin_ccy     = ccy_info.get("financial_currency") or (company.reporting_currency if company else "?")
    full_name   = company.full_name if company else ""

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
            c = "green" if s >= 7 else ("yellow" if s >= 5 else "red")
            piotroski = _f_score_bar(s, c)

    sloan = "—"
    if "sloan" in fws:
        _, p = _latest(fws["sloan"])
        if p:
            q = p.get("earnings_quality", "Unknown")
            c = "green" if q == "High" else ("yellow" if q == "Moderate" else ("red" if q == "Low" else "gray"))
            sloan = _badge(f"{q} ({_pct(p.get('cfo_accrual_ratio'))})", c)

    ohlson = "—"
    if "ohlson" in fws:
        _, p = _latest(fws["ohlson"])
        if p:
            prob = _safe_float(p.get("bankruptcy_probability"))
            if prob is not None:
                c = "green" if prob < 0.05 else ("yellow" if prob < 0.20 else "red")
                label = p.get("interpretation", "").replace(" distress risk", "")
                ohlson = _badge(f"{_pct(prob)} {label}", c)

    altman = "—"
    if "altman" in fws:
        _, p = _latest(fws["altman"])
        if p:
            # Z'' (non-manufacturing) is appropriate for all 14 Norwegian companies;
            # none qualify as US manufacturing. Show Z'' as primary throughout.
            if p.get("z_score_prime") is not None:
                z    = _num(p.get("z_score_prime"))
                zone = p.get("zone_prime", "Unknown")
                label = "Z''="
                tip   = ' title="Z\'\' non-manufacturing model — preferred for all non-US companies"'
            else:
                z    = _num(p.get("z_score"))
                zone = p.get("zone", "Unknown")
                label, tip = "Z=", ""
            c = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else ("red" if zone == "Distress" else "gray"))
            altman = f'<span{tip}>{_badge(f"{label}{z} {zone}", c)}</span>'

    return (
        f'<tr onclick="toggleCard(\'{ticker}\')" style="cursor:pointer">'
        f'<td class="tk">'
        f'  <div>{ticker}</div>'
        f'  <div class="co-name">{full_name}</div>'
        f'  <div class="period-lbl">{period_cell}</div>'
        f'</td>'
        f'<td style="white-space:nowrap">{_ccy_badge(fin_ccy)}</td>'
        f'<td>{roe}</td><td>{npm}</td>'
        f'<td>{piotroski}</td>'
        f'<td>{sloan}</td>'
        f'<td>{ohlson}</td>'
        f'<td>{altman}</td>'
        f'</tr>'
    )


def _f_score_bar(score: int, color: str) -> str:
    """Visual progress bar for Piotroski F-Score (0–9)."""
    colors = {"green": "#16a34a", "yellow": "#d97706", "red": "#dc2626"}
    bar_color = colors.get(color, "#6b7280")
    pct = round(score / 9 * 100)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<div style="width:72px;height:7px;background:#e5e7eb;border-radius:4px;overflow:hidden;flex-shrink:0">'
        f'<div style="width:{pct}%;height:100%;background:{bar_color};border-radius:4px"></div>'
        f'</div>'
        f'<span style="font-weight:700;font-size:0.8rem;color:{bar_color}">{score}/9</span>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Detail cards
# ---------------------------------------------------------------------------

def _detail_card(ticker: str, fws: dict) -> str:
    company   = TICKER_MAP.get(ticker)
    ccy_info  = fws.get("currency", {})
    fin_ccy   = ccy_info.get("financial_currency") or (company.reporting_currency if company else "?")
    full_name = company.full_name if company else ""

    sections = "".join(
        _fw_section(name, fws[name], fin_ccy)
        for name in ["dupont", "piotroski", "sloan", "ohlson", "altman"]
        if name in fws and fws[name].get("periods")
    )
    if not sections:
        return ""

    summary_txt  = _company_summary(ticker, fws)
    notes_txt    = company.notes if company else ""
    sector_txt   = company.sector if company else ""

    info_parts = []
    if summary_txt:
        info_parts.append(summary_txt)
    if notes_txt:
        info_parts.append(f"<em>ℹ {notes_txt}</em>")
    info_html = (
        '<div class="card-summary">' + "<br>".join(info_parts) + "</div>"
        if info_parts else ""
    )

    sector_badge = (
        f'<span style="font-size:0.72rem;background:rgba(255,255,255,0.12);'
        f'color:#cbd5e1;padding:2px 8px;border-radius:6px">{sector_txt}</span>'
        if sector_txt else ""
    )

    return (
        f'<div id="card-{ticker}" class="detail-card" style="display:none">'
        f'<div class="card-header">'
        f'  <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
        f'    <span class="card-ticker">{ticker}</span>'
        f'    <span class="card-company">{full_name}</span>'
        f'    {sector_badge}'
        f'    {_ccy_badge(fin_ccy)}'
        f'  </div>'
        f'  <button class="card-close" onclick="toggleCard(\'{ticker}\')" aria-label="Close">✕</button>'
        f'</div>'
        f'{info_html}'
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
    cols    = sorted(periods.keys(), reverse=True)
    th      = "".join(f"<th>{c}</th>" for c in cols)

    builders = {
        "dupont":    lambda p, c: _dupont_rows(p, c),
        "piotroski": lambda p, c: _piotroski_rows(p, c),
        "sloan":     lambda p, c: _sloan_rows(p, c, ccy),
        "ohlson":    lambda p, c: _ohlson_rows(p, c),
        "altman":    lambda p, c: _altman_rows(p, c),
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
    cls   = ' class="indent"' if indent else ""
    return f"<tr><td{cls}>{label}</td>{cells}</tr>"


def _colored_row(
    label: str, cols: list[str], src: dict, key: str, fmt=_num,
    green_ge: float | None = None, red_le: float | None = None,
    green_le: float | None = None, red_ge: float | None = None,
    indent: bool = False,
) -> str:
    """Like _row but applies green/red coloring based on value thresholds."""
    cells = ""
    for c in cols:
        v  = src.get(c, {}).get(key)
        s  = fmt(v)
        f  = _safe_float(v)
        color = ""
        if f is not None:
            if green_ge is not None and f >= green_ge:
                color = "#15803d"
            elif red_le is not None and f <= red_le:
                color = "#dc2626"
            elif green_le is not None and f <= green_le:
                color = "#15803d"
            elif red_ge is not None and f >= red_ge:
                color = "#b91c1c"
        style = f' style="color:{color};font-weight:600"' if color else ""
        cells += f"<td{style}>{s}</td>"
    cls = ' class="indent"' if indent else ""
    return f"<tr><td{cls}>{label}</td>{cells}</tr>"


def _dupont_driver_row(periods: dict, cols: list[str]) -> str:
    """Identify and label the dominant ROE driver per period."""
    cells = ""
    for c in cols:
        p   = periods.get(c, {})
        npm = _safe_float(p.get("net_profit_margin"))
        at  = _safe_float(p.get("asset_turnover"))
        em  = _safe_float(p.get("equity_multiplier"))
        if npm is None or at is None or em is None:
            cells += "<td>—</td>"
            continue
        # Score relative to approximate neutral baselines
        npm_s = abs(npm - 0.08) / max(abs(npm), 0.01)
        at_s  = abs(at  - 0.60) / max(abs(at),  0.01)
        em_s  = abs(em  - 2.50) / max(abs(em),  0.01)
        drivers = [("Margins", npm_s), ("Turnover", at_s), ("Leverage", em_s)]
        name, _ = max(drivers, key=lambda x: x[1])
        color = "#b91c1c" if name == "Leverage" and em > 4 else "#2563eb"
        cells += f'<td style="color:{color};font-weight:600;font-size:0.75rem">{name}</td>'
    return (
        f'<tr style="background:#f8fafc">'
        f'<td style="font-size:0.73rem;color:var(--slate);font-style:italic">Primary ROE driver</td>'
        f'{cells}</tr>'
    )


def _dupont_rows(periods: dict, cols: list[str]) -> str:
    r  = _colored_row("ROE (3-factor)", cols, periods, "roe_3factor", _pct,
                       green_ge=0.15, red_le=0.0)
    r += _colored_row("Net Profit Margin", cols, periods, "net_profit_margin", _pct,
                       green_ge=0.12, red_le=0.03)
    r += _colored_row("Asset Turnover", cols, periods, "asset_turnover",
                       green_ge=0.8, red_le=0.2)
    r += _colored_row("Equity Multiplier", cols, periods, "equity_multiplier",
                       green_le=2.5, red_ge=5.0)
    r += _dupont_driver_row(periods, cols)
    r += _colored_row("EBIT Margin", cols, periods, "ebit_margin", _pct,
                       green_ge=0.10, red_le=0.03)
    r += _row("Tax Burden",     cols, periods, "tax_burden")
    r += _row("Interest Burden", cols, periods, "interest_burden")
    r += _colored_row("ROE (5-factor check)", cols, periods, "roe_5factor", _pct,
                       green_ge=0.15, red_le=0.0)
    return r


def _piotroski_rows(periods: dict, cols: list[str]) -> str:
    cells = ""
    for c in cols:
        s = periods.get(c, {}).get("f_score")
        if s is not None:
            color = "green" if s >= 7 else ("yellow" if s >= 5 else "red")
            cells += f"<td>{_f_score_bar(s, color)}</td>"
        else:
            cells += "<td>—</td>"
    r = f"<tr><td><strong>F-Score (0–9)</strong></td>{cells}</tr>"

    signals = [
        ("F1_positive_roa",             "F1 · Positive ROA"),
        ("F2_positive_cfo",             "F2 · Positive operating cash flow"),
        ("F3_roa_increasing",           "F3 · ROA improving YoY"),
        ("F4_accruals_quality",         "F4 · Cash flow exceeds net income"),
        ("F5_leverage_decreasing",      "F5 · Long-term debt ratio falling"),
        ("F6_liquidity_improving",      "F6 · Current ratio improving"),
        ("F7_no_dilution",              "F7 · No share issuance"),
        ("F8_gross_margin_improving",   "F8 · Gross margin improving"),
        ("F9_asset_turnover_improving", "F9 · Asset turnover improving"),
    ]
    for key, label in signals:
        cells = ""
        for c in cols:
            v = periods.get(c, {}).get("signals", {}).get(key)
            if v == 1:
                cells += '<td style="color:#16a34a;font-weight:700;font-size:1rem">✓</td>'
            elif v == 0:
                cells += '<td style="color:#9ca3af">✗</td>'
            else:
                cells += "<td>—</td>"
        r += f'<tr><td class="indent">{label}</td>{cells}</tr>'

    r += _colored_row("Current Ratio", cols, periods, "current_ratio",
                       green_ge=1.5, red_le=1.0)
    r += _colored_row("Gross Margin", cols, periods, "gross_margin", _pct,
                       green_ge=0.30, red_le=0.10)
    r += _row("Asset Turnover", cols, periods, "asset_turnover")
    return r


def _sloan_rows(periods: dict, cols: list[str], ccy: str = "") -> str:
    cells = ""
    for c in cols:
        q     = periods.get(c, {}).get("earnings_quality", "Unknown")
        color = "green" if q == "High" else ("yellow" if q == "Moderate" else ("red" if q == "Low" else "gray"))
        cells += f"<td>{_badge(q, color)}</td>"
    r  = f"<tr><td><strong>Earnings Quality</strong></td>{cells}</tr>"
    r += _colored_row("CFO Accrual Ratio", cols, periods, "cfo_accrual_ratio", _pct,
                       green_le=-0.05, red_ge=0.05)
    r += _row("BS Accrual Ratio", cols, periods, "bs_accrual_ratio", _pct)
    fmt_abs = _large_ccy(ccy) if ccy else _large
    r += _row("Operating Cash Flow", cols, periods, "operating_cash_flow", fmt_abs)
    r += _row("Net Income",          cols, periods, "net_income",          fmt_abs)
    return r


def _ohlson_rows(periods: dict, cols: list[str]) -> str:
    r     = _row("O-Score", cols, periods, "o_score")
    cells = ""
    for c in cols:
        prob = _safe_float(periods.get(c, {}).get("bankruptcy_probability"))
        if prob is not None:
            color = "green" if prob < 0.05 else ("yellow" if prob < 0.20 else "red")
            cells += f"<td>{_badge(_pct(prob), color)}</td>"
        else:
            cells += "<td>—</td>"
    r += f"<tr><td><strong>Bankruptcy Probability</strong></td>{cells}</tr>"
    inp  = {c: periods.get(c, {}).get("inputs", {}) for c in cols}
    r += _colored_row("Total Liabilities / Total Assets", cols, inp, "tl_ta",
                       green_le=0.50, red_ge=0.80)
    r += _row("Working Capital / Total Assets",   cols, inp, "wc_ta")
    r += _colored_row("Net Income / Total Assets (ROA)", cols, inp, "ni_ta", _pct,
                       green_ge=0.05, red_le=0.0)
    r += _row("CFO / Total Liabilities", cols, inp, "cfo_tl")
    return r


def _altman_rows(periods: dict, cols: list[str]) -> str:
    # Original Z-Score row
    cells = ""
    for c in cols:
        z    = _safe_float(periods.get(c, {}).get("z_score"))
        zone = periods.get(c, {}).get("zone", "Unknown")
        color = "green" if zone == "Safe" else ("yellow" if zone == "Grey" else ("red" if zone == "Distress" else "gray"))
        cells += f"<td>{_badge(f'Z={_num(z)} · {zone}', color)}</td>"
    r  = f"<tr><td><strong>Z-Score (manufacturing model)</strong></td>{cells}</tr>"

    # Z'' non-manufacturing row
    cells2 = ""
    for c in cols:
        zpp   = _safe_float(periods.get(c, {}).get("z_score_prime"))
        zonep = periods.get(c, {}).get("zone_prime", "Unknown")
        color = "green" if zonep == "Safe" else ("yellow" if zonep == "Grey" else ("red" if zonep == "Distress" else "gray"))
        zpp_label = f"Z''={_num(zpp)} · {zonep}"
        cells2 += f"<td>{_badge(zpp_label, color)}</td>"
    r += (
        f'<tr><td style="font-size:0.75rem;color:var(--slate)">'
        f'Z&#8243;-Score (non-manufacturing · <strong>primary model for all 14 companies</strong>)'
        f'</td>{cells2}</tr>'
    )

    r += _row("X1  Working Capital / Assets",    cols, periods, "x1_working_capital_to_assets")
    r += _row("X2  Retained Earnings / Assets",  cols, periods, "x2_retained_earnings_to_assets")
    r += _colored_row("X3  EBIT / Assets", cols, periods, "x3_ebit_to_assets", _pct,
                       green_ge=0.10, red_le=0.03)
    r += _row("X4  Book Equity / Liabilities",   cols, periods, "x4_book_equity_to_liabilities")
    r += _row("X5  Revenue / Assets (Z only)",   cols, periods, "x5_revenue_to_assets")
    return r


# ---------------------------------------------------------------------------
# Currency verification table
# ---------------------------------------------------------------------------

def _currency_table(data: dict) -> str:
    rows = ""
    for company in COMPANIES:
        ticker   = company.ticker
        ccy_info = data.get(ticker, {}).get("currency", {})

        fin_ccy    = ccy_info.get("financial_currency") or company.reporting_currency
        price_ccy  = ccy_info.get("price_currency", "NOK")
        config_ccy = ccy_info.get("config_currency") or company.reporting_currency
        yf_ccy     = ccy_info.get("yfinance_currency") or "—"
        status     = ccy_info.get("verification_status", "pending")

        status_badge = {
            "verified":   _badge("✓ Verified",   "green"),
            "mismatch":   _badge("⚠ Mismatch",   "red"),
            "unverified": _badge("? Unverified",  "yellow"),
            "pending":    _badge("— Pending",     "gray"),
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
    now  = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
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
  --bg:#f1f5f9; --white:#ffffff;
  --accent:#2563eb; --accent2:#4f46e5;
}}
html{{scroll-behavior:smooth}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  background:var(--bg);color:var(--navy2);font-size:14px;line-height:1.6}}

/* ── Header ───────────────────────────────────────────────── */
header{{
  background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);
  border-bottom:3px solid var(--accent);
  padding:20px 32px;
  display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px
}}
.logo{{display:flex;align-items:baseline;gap:12px}}
.logo h1{{font-size:1.6rem;font-weight:900;color:#f8fafc;letter-spacing:-0.5px}}
.logo h1 span{{color:#60a5fa}}
.logo .tagline{{font-size:0.78rem;color:var(--muted);font-style:italic}}
.meta-pill{{
  background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;
  padding:6px 16px;font-size:0.75rem;color:var(--muted);text-align:right;line-height:1.9
}}
.meta-pill strong{{color:#f8fafc;font-size:0.85rem}}

/* ── Layout ───────────────────────────────────────────────── */
main{{max-width:1480px;margin:0 auto;padding:28px 20px 60px}}

/* ── Section headings ─────────────────────────────────────── */
.section-title{{
  font-size:0.68rem;font-weight:800;letter-spacing:2px;text-transform:uppercase;
  color:var(--slate);margin:32px 0 12px;
  display:flex;align-items:center;gap:10px
}}
.section-title::after{{content:"";flex:1;height:1px;background:var(--border)}}

/* ── Collapsible panels (legend + currency) ───────────────── */
.panel{{
  background:var(--white);border:1px solid var(--border);border-radius:12px;
  margin-bottom:20px;overflow:hidden;
  box-shadow:0 1px 4px rgba(0,0,0,.05)
}}
.panel-toggle{{
  width:100%;border:none;background:none;cursor:pointer;
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 20px;font-weight:700;font-size:0.88rem;color:var(--navy2);
  text-align:left;transition:background .15s
}}
.panel-toggle:hover{{background:#f8fafc}}
.panel-toggle .arrow{{transition:transform .25s;font-size:0.75rem;color:var(--slate)}}
.panel-toggle[aria-expanded="true"] .arrow{{transform:rotate(180deg)}}
.panel-body{{display:none;padding:0 20px 20px;border-top:1px solid var(--border)}}
.panel-body.open{{display:block}}

.color-guide{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 20px;align-items:center}}
.cg-item{{display:flex;align-items:center;gap:6px;font-size:0.78rem}}

.fw-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:4px}}
.fw-card{{
  background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px 16px
}}
.fw-card h5{{font-size:0.78rem;font-weight:800;text-transform:uppercase;
  letter-spacing:.8px;color:var(--accent);margin-bottom:6px}}
.fw-card p{{font-size:0.79rem;color:var(--navy3);line-height:1.6;margin-bottom:6px}}
.fw-card .reading{{font-size:0.75rem;color:var(--slate);border-top:1px solid var(--border);
  padding-top:6px;margin-top:6px}}

.disclaimer{{
  margin-top:16px;padding:12px 16px;border-radius:8px;
  background:#fef3c7;border-left:4px solid #d97706;
  font-size:0.76rem;color:#78350f;line-height:1.7
}}
.disclaimer strong{{display:block;margin-bottom:4px;font-size:0.8rem}}

/* ── Summary table ────────────────────────────────────────── */
.tscroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px;
  border:1px solid var(--border);box-shadow:0 2px 6px rgba(0,0,0,.06)}}
table{{border-collapse:collapse;width:100%;min-width:820px}}
thead th{{
  background:var(--navy2);color:#e2e8f0;padding:11px 14px;text-align:left;
  font-size:0.67rem;text-transform:uppercase;letter-spacing:.9px;
  position:sticky;top:0;white-space:nowrap
}}
thead th:first-child{{min-width:140px}}
tbody tr{{background:var(--white);transition:background .12s}}
tbody tr:nth-child(even){{background:#f8fafc}}
tbody tr:hover{{background:#eff6ff;cursor:pointer}}
td{{padding:9px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
td.tk{{white-space:nowrap}}
td.tk > div:first-child{{font-weight:800;font-size:0.88rem;color:var(--navy)}}
.co-name{{font-size:0.7rem;font-weight:400;color:var(--slate);margin-top:1px}}
.period-lbl{{font-size:0.65rem;color:var(--muted)}}

/* ── Detail cards ─────────────────────────────────────────── */
#detail-area{{margin-top:20px}}
.detail-card{{
  background:var(--white);border:1px solid var(--border);border-radius:12px;
  margin-bottom:16px;overflow:hidden;
  box-shadow:0 4px 16px rgba(0,0,0,.08)
}}
.card-header{{
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 20px;background:linear-gradient(135deg,#1e293b 0%,#1e3a8a 100%);
}}
.card-ticker{{font-weight:900;font-size:1.1rem;color:#f8fafc;letter-spacing:-.3px}}
.card-company{{font-size:0.82rem;font-weight:400;color:#94a3b8}}
.card-close{{
  border:none;background:rgba(255,255,255,0.1);color:#94a3b8;font-size:1rem;
  cursor:pointer;padding:4px 10px;border-radius:6px;transition:all .15s
}}
.card-close:hover{{background:rgba(239,68,68,0.2);color:#fca5a5}}
.card-summary{{
  padding:12px 20px;background:#f0f9ff;border-bottom:1px solid #bae6fd;
  font-size:0.8rem;color:#075985;line-height:1.6
}}
.card-body{{padding:20px}}

/* ── Framework blocks inside cards ────────────────────────── */
.fw-block{{margin-bottom:24px}}
.fw-block:last-child{{margin-bottom:0}}
.fw-title{{
  font-size:0.7rem;font-weight:800;text-transform:uppercase;letter-spacing:1px;
  color:var(--accent);margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #dbeafe
}}
.fw-table{{min-width:480px;font-size:0.8rem}}
.fw-table thead th{{background:var(--navy3);font-size:0.67rem;padding:7px 10px}}
.fw-table td{{padding:6px 10px;border-bottom:1px solid #f1f5f9}}
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
    <strong>{n_ok} of {len(COMPANIES)} companies computed</strong><br>
    Updated {now}
  </div>
</header>

<main>

<!-- ── Legend ─────────────────────────────────────────────── -->
<p class="section-title">Framework Guide &amp; Legends</p>
<div class="panel">
  <button class="panel-toggle" aria-expanded="false" onclick="togglePanel(this)">
    What do these frameworks measure? &nbsp;<span style="font-weight:400;color:var(--slate)">Click to expand</span>
    <span class="arrow">▼</span>
  </button>
  <div class="panel-body">

    <div class="color-guide">
      <strong style="font-size:.78rem;color:var(--navy3)">Colour key:</strong>
      <span class="cg-item">{_badge("Green · Favourable","green")} Healthy / strong</span>
      <span class="cg-item">{_badge("Amber · Watch","yellow")} Neutral / watch zone</span>
      <span class="cg-item">{_badge("Red · Concern","red")} Weak or elevated risk</span>
    </div>

    <div class="fw-grid">
      <div class="fw-card">
        <h5>DuPont Decomposition</h5>
        <p>Breaks Return on Equity (ROE) into three drivers: profit margin, asset efficiency, and financial leverage. The 5-factor version further splits profitability into tax and interest burden components. Cells are colour-coded: <strong>green</strong> = strong, <strong>red</strong> = weak. The <em>Primary ROE driver</em> row identifies whether ROE is earned through margins, asset turnover, or leverage.</p>
        <div class="reading">
          <strong>How to read:</strong> ROE &gt;15% is strong. Equity multiplier above 5× signals very high debt usage. Leverage-driven ROE is less sustainable than margin-driven ROE.
        </div>
      </div>
      <div class="fw-card">
        <h5>Piotroski F-Score</h5>
        <p>A checklist of 9 binary signals across profitability, capital structure, and operating efficiency. Each signal scores 0 or 1. The progress bar shows the total out of 9.</p>
        <div class="reading">
          <strong>How to read:</strong> 7–9 = Strong. 5–6 = Moderate. 0–4 = Weak. A rising score over multiple years is more meaningful than any single reading.
        </div>
      </div>
      <div class="fw-card">
        <h5>Sloan Accruals</h5>
        <p>Measures earnings quality. A negative accrual ratio means cash flow exceeds reported income — a hallmark of durable, high-quality earnings. A positive ratio suggests profit is largely non-cash accruals that may not repeat.</p>
        <div class="reading">
          <strong>How to read:</strong> High = cash earnings exceed accounting profits (good). Low = accruals exceed cash (caution). Absolute cash flows are shown in the company's reporting currency.
        </div>
      </div>
      <div class="fw-card">
        <h5>Ohlson O-Score</h5>
        <p>A logistic regression model estimating the probability of bankruptcy within one year using nine financial ratios covering size, leverage, liquidity, and profitability. <strong>Key calibration limitations:</strong> (1) calibrated on US industrial firms in the 1970s with a ~7% annual bankruptcy rate — far above the &lt;1% rate for large listed Norwegian companies, so raw probabilities are structurally overstated; (2) the leverage term (+6.03 × TL/TA) systematically inflates risk for capital-intensive sectors (shipping, offshore, aquaculture, real estate) where high debt is backed by physical assets; (3) SIZE variable is expressed in millions, consistent with Begley et al. (1996) to avoid a common implementation error that inflates O-Scores by ~2.8 points. Use probabilities as <em>relative, directional signals</em> within a peer group — not as absolute bankruptcy forecasts.</p>
        <div class="reading">
          <strong>How to read:</strong> &lt;5% = Low risk. 5–20% = Moderate. &gt;20% = Elevated. Thresholds are set conservatively to account for the lower Norwegian base rate. Cross-check with Altman Z&#8243; and company fundamentals before drawing conclusions.
        </div>
      </div>
      <div class="fw-card">
        <h5>Altman Z-Score</h5>
        <p>Five balance-sheet ratios weighted to classify companies as safe, grey-zone, or distress. Two variants are shown: the original Z (1968, US manufacturing) and the Z&#8243; non-manufacturing model (1995). <strong>Z&#8243; is displayed as primary for all companies</strong> — none of the 14 covered firms qualify as US manufacturing, and Z&#8243; removes the asset-turnover term (X5) that artificially penalises capital-intensive businesses.</p>
        <div class="reading">
          <strong>How to read Z&#8243;:</strong> &gt;2.6 = Safe. 1.1–2.6 = Grey. &lt;1.1 = Distress. Thresholds: Safe &gt;2.6 | Grey 1.1–2.6 | Distress &lt;1.1. Original Z thresholds (Safe &gt;2.99, Grey 1.81–2.99, Distress &lt;1.81) are still shown for reference in the detail card.
        </div>
      </div>
    </div>

    <div class="disclaimer">
      <strong>⚠ Data quality &amp; model limitations</strong>
      Financial data is sourced from Yahoo Finance. Stock prices on Oslo Børs are always in NOK; companies that report in USD or EUR have their price data converted to the reporting currency before any price-based metric is computed. All five models were originally calibrated on US companies — treat scores as relative indicators and cross-check with official annual reports before drawing conclusions. Ohlson O-Score probabilities are structurally overstated for large listed Norwegian firms and capital-intensive sectors; use as a relative signal within a peer group. Altman Z&#8243; (non-manufacturing) is shown as primary — the original Z is retained for reference only.
    </div>

  </div>
</div>

<!-- ── Summary ─────────────────────────────────────────────── -->
<p class="section-title">Summary — Most Recent Annual Period</p>
<p style="font-size:0.76rem;color:var(--slate);margin-bottom:12px">
  Click any row to open the full historical detail card below.
</p>
<div class="tscroll">
<table>
  <thead>
    <tr>
      <th>Company</th>
      <th>Stmts&nbsp;Ccy</th>
      <th>ROE</th>
      <th>Net&nbsp;Margin</th>
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

<!-- ── Currency Verification ──────────────────────────────── -->
<p class="section-title" style="margin-top:48px">Currency Verification</p>
<div class="panel">
  <button class="panel-toggle" aria-expanded="false" onclick="togglePanel(this)">
    Currency detection results per company &nbsp;<span style="font-weight:400;color:var(--slate)">Click to expand</span>
    <span class="arrow">▼</span>
  </button>
  <div class="panel-body">
    <p style="font-size:0.76rem;color:var(--slate);padding:14px 0 12px">
      Oslo Børs prices are always quoted in <strong>NOK</strong>. For companies reporting in USD or EUR, prices are converted using a live FX rate before any price-based metric is computed. The table shows the detected reporting currency and its verification status.
    </p>
    {currency_html}
  </div>
</div>

</main>

<footer>
  Oslo Quant · Data from <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a> via yfinance ·
  Frameworks: DuPont · Piotroski (1980) · Sloan (1996) · Ohlson (1980) · Altman (1968) ·
  For informational purposes only — not investment advice.
</footer>

<script>
function togglePanel(btn) {{
  const body = btn.nextElementSibling;
  const open = body.classList.toggle('open');
  btn.setAttribute('aria-expanded', open);
}}

function toggleCard(ticker) {{
  const card = document.getElementById('card-' + ticker);
  if (!card) return;
  const visible = card.style.display !== 'none';
  card.style.display = visible ? 'none' : 'block';
  if (!visible) card.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
}}
</script>

</body>
</html>"""
