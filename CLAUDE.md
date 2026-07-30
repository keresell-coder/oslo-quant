# Oslo Quant — Developer Reference

A weekly quantitative dashboard for 15 Oslo Børs companies. A GitHub Actions workflow
fetches financial data every Friday after market close, runs five valuation/distress
frameworks, and commits an updated `index.html` back to the repository (served via
GitHub Pages).

---

## Repository layout

```
oslo_quant/
  config.py          — Company list (COMPANIES, TICKER_MAP) and path constants
  cli.py             — Entry point: oslo-quant CLI (fetch + compute)
  pipeline.py        — Orchestrates fetchers → frameworks → writes JSON to data/results/
  report.py          — Reads JSON results, generates index.html
  fetchers/
    base.py          — Statements TypedDict; shared logic
    yfinance_fetcher.py  — Primary data source (Yahoo Finance)
    fmp_fetcher.py       — Secondary / verification (Financial Modelling Prep)
  frameworks/
    base.py          — BaseFramework: _get(), _safe_div(), _fmt(), _periods()
    dupont.py        — DuPont 3-factor and 5-factor ROE decomposition
    piotroski.py     — Piotroski F-Score (9 binary signals)
    sloan.py         — Sloan Accruals (earnings quality)
    ohlson.py        — Ohlson O-Score (bankruptcy probability)
    altman.py        — Altman Z-Score (Z, Z', Z'')
.github/workflows/
  run_oslo_quant.yml — Weekly Friday 17:00 UTC (after close); also manual dispatch
data/
  raw/               — Parquet cache (gitignored); recreated each workflow run
  results/           — Computed JSON per ticker per framework (committed)
index.html           — Generated dashboard (committed, served via GitHub Pages)
pyproject.toml
```

---

## Running locally

```bash
pip install -e .                        # install with dev extras: pip install -e ".[dev]"

oslo-quant                              # fetch + compute all 15 tickers, all 5 frameworks
oslo-quant --tickers TEL.OL MOWI.OL    # subset of tickers
oslo-quant --frameworks dupont piotroski  # subset of frameworks
oslo-quant --force-refresh              # ignore cached parquet, re-fetch from Yahoo

oslo-quant-report                       # regenerate index.html from data/results/
```

Results land in `data/results/<TICKER>/<framework>.json`.
The HTML is always regenerated from those JSON files — re-run `oslo-quant-report`
after any change to `report.py` or `config.py` without needing to re-fetch data.

---

## Adding or changing a company

Edit `oslo_quant/config.py`. Each entry is a `CompanyConfig`:

```python
CompanyConfig(
    ticker="EXAMPLE.OL",
    alt_ticker=None,              # FMP ticker if different (e.g. "BORR" for BORR.OL)
    reporting_currency="NOK",     # currency used in financial statements
    full_name="Example ASA",
    sector="Your Sector",
    notes="Optional caveat shown on the dashboard card.",
)
```

`ALL_FRAMEWORKS` in config.py lists the five framework keys.
Price currency for all .OL tickers is always NOK (Oslo Børs).

---

## Framework design notes

### DuPont (`dupont.py`)
Standard 3-factor (NPM × Asset Turnover × Equity Multiplier = ROE) and
5-factor decomposition. No known issues.

### Piotroski F-Score (`piotroski.py`)
Nine binary signals (0/1). Score ≥ 8 = Strong, 5–7 = Moderate, ≤ 4 = Weak.
Uses average assets rather than beginning-of-year assets for ROA (minor deviation
from the original paper; immaterial in practice).

### Sloan Accruals (`sloan.py`)
Two methods: CFO-based (primary) and balance-sheet method (approximate).
CFI is intentionally excluded from the accrual calculation to avoid false
low-quality signals for capital-intensive sectors (offshore, shipping, aquaculture)
where large investing cash flows are normal, not a sign of earnings manipulation.

### Ohlson O-Score (`ohlson.py`)
**Critical implementation detail**: SIZE = log(total_assets / 1_000_000).
Assets are expressed in millions (`_GNP_DIVISOR = 1_000_000`), consistent with
Begley et al. (1996). Omitting this divisor inflates the O-Score by ~2.8 points,
which is a common error in implementations found online.
Raw probabilities are structurally high for large listed Norwegian companies
(model calibrated on 1970s US firms with ~7% annual bankruptcy rate). Use as a
relative/directional signal within a peer group, not as an absolute forecast.

### Altman Z-Score (`altman.py`)
Three variants computed: original Z (manufacturing), Z' (private firms), Z'' (non-manufacturing).
**Z'' is the primary model for all 15 companies** — none qualify as US manufacturers.
Z thresholds: Safe > 2.6, Grey zone 1.1–2.6, Distress ≤ 1.1.
Original Z is retained in the dashboard as a reference row shown in gray.
X4 uses book equity (not market cap) for all companies to ensure consistency
across periods and avoid price-driven distortion.

---

## Dashboard (report.py)

`report.py` reads every `data/results/<TICKER>/<framework>.json` and produces a
single-file `index.html` with:
- Summary table (one row per company: latest period, key metrics, traffic-light badges)
- Expandable detail cards per company (one section per framework)
- Framework legends explaining methodology and caveats

**Badge colour palette**:
- `green` = positive/good, `yellow` = moderate/caution, `red` = negative/bad/distress
- `gray` = informational / reference-only (e.g. original Z row)
- Currency badges: NOK = teal (#0891b2), USD = orange (#c2410c), EUR = purple (#7c3aed)

**Timestamp**: displayed in CET/CEST (Europe/Oslo timezone) using `zoneinfo`.

---

## GitHub Actions workflow

File: `.github/workflows/run_oslo_quant.yml`  
Schedule: every Friday at 17:00 UTC — 19:00 CEST (summer) / 18:00 CET (winter).
GitHub cron is fixed UTC and does not follow DST, hence the one-hour seasonal drift.
Oslo Børs continuous trading ends 16:20 local and the closing auction ~16:25, so the
day's closing prices are always settled before the run.  
Manual dispatch: Actions tab → "Run Oslo Quant" → optional ticker/framework subset.

Key design choices:
- `continue-on-error: true` on the `oslo-quant` step — partial results are committed
  even if some tickers fail (e.g. yfinance outage or delisted ticker).
- `data/raw/` is gitignored; each run fetches fresh data from Yahoo Finance.
  The `data/results/` JSON files are committed, so the dashboard always reflects
  the last successful run even if the current run is incomplete.
- Pip packages are cached keyed on `pyproject.toml` hash.
- Push target: `HEAD:${{ github.ref_name }}` (not hardcoded `main`).

**FMP_API_KEY**: stored as a GitHub Actions secret. Used only in `fmp_fetcher.py`
for supplementary data; the main pipeline uses yfinance and runs without it.

---

## The 15 companies

| Ticker    | Full name                  | Ccy | Sector                        | Notes |
|-----------|----------------------------|-----|-------------------------------|-------|
| DOFG.OL   | DOF Group ASA              | USD | Offshore / Marine Services    | |
| BRG.OL    | Borregaard ASA             | NOK | Specialty Chemicals / Biorefinery | |
| ODL.OL    | Odfjell Drilling Ltd       | USD | Offshore Drilling             | Harsh-environment semis & drillships (North Sea). Not jack-ups (BORR.OL is jack-ups). |
| ELK.OL    | Elkem ASA                  | NOK | Silicon & Specialty Chemicals | |
| NOD.OL    | Nordic Semiconductor ASA   | USD | Semiconductors                | Fabless; Bluetooth/IoT |
| VEND.OL   | Vend Marketplaces ASA      | NOK | Media / Online Classifieds    | Schibsted carve-out, listed May 2025. Limited history. |
| PUBLI.OL  | Public Property Invest ASA | NOK | Real Estate                   | Redomiciling to Nasdaq Stockholm from May 2026; secondary listing on Oslo Børs continues. |
| MOWI.OL   | Mowi ASA                   | EUR | Aquaculture / Salmon Farming  | IAS 41 fair-value movements inflate EBIT; creates non-cash distress signals. |
| TEL.OL    | Telenor ASA                | NOK | Telecommunications            | |
| KOG.OL    | Kongsberg Gruppen ASA      | NOK | Defence / Technology          | |
| KMAR.OL   | Kongsberg Maritime ASA     | NOK | Maritime Technology           | KOG.OL carve-out, listed April 2026. Very limited standalone history. |
| BORR.OL   | Borr Drilling Ltd          | USD | Offshore Drilling             | Jack-up rigs, shallow water. alt_ticker="BORR" for FMP. |
| FRO.OL    | Frontline plc              | USD | Crude Oil Tankers             | Cyprus-registered (redomiciled from Bermuda 2022). |
| HAFNI.OL  | Hafnia Ltd                 | USD | Product Tankers               | |
| NORBT.OL  | Norbit ASA                 | NOK | Technology / Sensing & Connectivity | Multibeam sonar, underwater sensors, telematics/IoT. alt_ticker="NORBT" for FMP. Listed June 2019. |

---

## Branches and GitHub Pages deployment

Active branch: `claude/build-oslo-quant-system-lzUvb` — this is where the workflow
commits, because it pushes to `HEAD:${{ github.ref_name }}` and the schedule runs on
this branch.

**GitHub Pages must be pointed at that same branch** (Settings → Pages → Source →
Deploy from a branch → `claude/build-oslo-quant-system-lzUvb` / root).

This coupling has bitten once already: between 2026-05-19 and 2026-07-27 the workflow
ran green every week and committed fresh results, but Pages was still serving `main`,
which had been frozen at the last PR merge. The dashboard showed 10-week-old data
while every Actions run reported success — nothing failed, the page was simply built
from a branch nothing was writing to.

If the live page's "Updated …" timestamp ever lags the newest `Update results and
report [date]` commit, check the Pages source branch first; the pipeline is rarely the
problem.

`main` is kept as a mirror of the active branch. It is not what Pages serves, so it
can be re-synced by fast-forward merge at any time without a PR.
