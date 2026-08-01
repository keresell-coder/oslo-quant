# Oslo Quant — Developer Reference

A weekly quantitative dashboard for 17 Oslo Børs companies. A GitHub Actions workflow
fetches financial data every Friday after market close, runs five valuation/distress
frameworks, and commits an updated `index.html` back to the repository (served via
GitHub Pages).

## At a glance

| | |
|---|---|
| **Live dashboard** | https://keresell-coder.github.io/oslo-quant/ |
| **Repository** | https://github.com/keresell-coder/oslo-quant |
| **Actions runs** | https://github.com/keresell-coder/oslo-quant/actions |
| **Branch** | `main` — the only branch. Default branch, workflow push target, and Pages source all point at it. |
| **Schedule** | Fridays, 17:17 UTC (19:17 CEST / 18:17 CET). Often runs hours late; see below. |
| **Alerting** | A failed Actions run emails the repo owner. That is the *only* alert channel. |

The repository owner is not a software engineer. Prefer plain language in
explanations, spell out GitHub UI steps click by click, and never assume familiarity
with git, branches, or YAML.

---

## Repository layout

```
oslo_quant/
  config.py          — Company list (COMPANIES, TICKER_MAP) and path constants
  cli.py             — Entry point: oslo-quant CLI (fetch + compute)
  pipeline.py        — Orchestrates fetchers → frameworks → writes JSON to data/results/
  report.py          — Reads JSON results, generates index.html
  healthcheck.py     — Post-run freshness assertion (see "Failure visibility")
  fetchers/
    base.py          — Statements TypedDict; shared logic
    yfinance_fetcher.py  — Primary data source (Yahoo Finance)
    fmp_fetcher.py       — Secondary / verification (Financial Modelling Prep)
  ltm.py             — LTM "virtual current year" built from quarterly statements
  verified.py        — report-verified fundamentals ledger (verify + gap-fill)
  frameworks/
    base.py          — BaseFramework: _get(), _safe_div(), _fmt(), _periods()
    dupont.py        — DuPont 3-factor and 5-factor ROE decomposition
    piotroski.py     — Piotroski F-Score (9 binary signals)
    sloan.py         — Sloan Accruals (earnings quality)
    ohlson.py        — Ohlson O-Score (bankruptcy probability)
    altman.py        — Altman Z-Score (Z, Z', Z'')
.claude/
  commands/          — Slash commands: /add-company, /remove-company, /dashboard-status
.github/workflows/
  run_oslo_quant.yml — Weekly Friday 17:17 UTC (after close); also manual dispatch
data/
  raw/               — Parquet cache (gitignored); recreated each workflow run
  results/           — Computed JSON per ticker per framework (committed);
                       plus per-ticker verification.json (ledger tie-out) and
                       ltm.json (LTM build status/reason)
  verified/          — Report-verified fundamentals ledger (committed, static):
                       one JSON per company, per-FY values with page-level
                       source citations. Verified against yfinance each run;
                       fills provider gaps (e.g. MOWI retained earnings).
index.html           — Generated dashboard (committed, served via GitHub Pages)
pyproject.toml
```

---

## Running locally

```bash
pip install -e .                        # install with dev extras: pip install -e ".[dev]"

oslo-quant                              # fetch + compute all 17 tickers, all 5 frameworks
oslo-quant --tickers TEL.OL MOWI.OL    # subset of tickers
oslo-quant --frameworks dupont piotroski  # subset of frameworks
oslo-quant --force-refresh              # ignore cached parquet, re-fetch from Yahoo

oslo-quant-report                       # regenerate index.html from data/results/
oslo-quant-check                        # assert the last run actually refreshed data
```

`oslo-quant-check` exits 1 unless at least 80% of configured companies (13 of 17)
were recomputed within the last 6 hours. Tune with `--min-fresh` / `--within-hours`.
Run locally straight after `oslo-quant` and it passes; run it on a stale checkout
and it fails — that is the intended behaviour, not a bug.

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

Add the entry to `_COMPANIES_RAW`. Placement in that list does not matter — the
exported `COMPANIES` is `sorted(_COMPANIES_RAW, key=(sector, ticker))`, and that
order is what the dashboard renders, so sector grouping cannot drift. Reuse an
existing `sector` string verbatim to group a company with its peers; a new string
creates a new group.

**Verify the ticker before adding it.** yfinance and FMP do not always agree, and a
wrong symbol fails silently as an empty fetch. Norbit is `NORBT.OL` (not `NRBIT.OL`);
Cadeler is `CADLR.OL` on Oslo and `CDLR` on NYSE. Check `reporting_currency` against
the annual report, not the trading currency — Cadeler trades in NOK but reports in
EUR, and prices are converted into the reporting currency before any price-based
metric is computed.

`ALL_FRAMEWORKS` in config.py lists the five framework keys.
Price currency for all .OL tickers is always NOK (Oslo Børs).

---

## Framework design notes

### The 2026-08-01 restatement — read this first

An independent audit (July 2026) found that `BaseFramework._get()` matched
statement rows by **substring, first match wins**, against yfinance's row order.
In production this resolved `EBIT` → *Normalized EBITDA*, `Current Assets` →
*Total Non Current Assets*, `Current Liabilities` → *Total Non Current
Liabilities Net Minority Interest*, `Net Income` → *continuing-operations
income*, and sometimes `Retained Earnings` → *Gains Losses Not Affecting
Retained Earnings*. Every populated company was affected; 5 of 14 Altman Z″
zones and most Piotroski scores were wrong. Three things changed:

1. **Field resolution is exact-match first** (case-insensitive), across all
   candidate names in order. Substring matching survives only as a logged
   fallback. Regression fixtures in `tests/fixtures.py`
   (`make_yfinance_like_statements`) reproduce the provider's real vocabulary
   and row order with decoy rows — keep them in sync if yfinance's labels change.
2. **Missing inputs are never scored.** No zero-substitution anywhere. A
   framework with a material missing input reports `None` /
   `"Not assessable"`. Empty or stub statement columns (no `Total Assets` /
   `Total Revenue` anchor) are dropped before computation.
3. **Net income means total operations** (yfinance's exact `Net Income` row,
   i.e. including discontinued operations, attributable basis as provided).
   This is a deliberate perimeter policy: one-off gains (e.g. Telenor's 2022
   CelcomDigi gain, NOK 44.9bn total NI) now show up in ROE/accruals rather
   than being silently excluded. Sector/perimeter judgment still applies.

All `data/results/` histories were recomputed on 2026-08-01 and the dashboard
carries a visible restatement notice. Do not compare current scores against
pre-restatement snapshots without accounting for this.

### LTM — the virtual current year (`ltm.py`, added 2026-08-01)

When quarterly data allows, an **"LTM YYYY-MM"** column is appended after the
latest FY. Flows are the sum of the last 4 quarters (or 2 half-years); the
balance sheet is the latest quarter as-is. Because "LTM …" sorts above year
labels, every framework's YoY signal automatically compares **LTM vs the
latest full FY** — overlapping windows, accepted by design as a development
tracker (user decision 2026-08-01). Hard rules: the window must be contiguous
and complete (a missing OR empty quarter refuses the LTM — see KIT/NOD cases
in `tests/test_ltm_and_ledger.py`); no LTM is built when the latest interim
does not extend beyond the FY end (the FY report is then the newest
information); Sloan's balance-sheet method is suppressed for LTM (window
mismatch). Build status and refusal reasons persist per ticker in
`data/results/<TICKER>/ltm.json`.

### Verified ledger (`verified.py` + `data/verified/`, added 2026-08-01)

Per-company JSON of line items transcribed from annual reports with page-level
citations. Applied after fetch: items present in both sources are compared
(>2% deviation → logged MISMATCH, yfinance value kept — never silently
patched); items missing from yfinance are **filled** from the report.
Historical FY data is static — once etched, never edit, only append new years.
Results land in `data/results/<TICKER>/verification.json`. MOWI's ledger fills
retained earnings ("Other equity" in Mowi's statement of changes in equity),
which is what makes its Altman score assessable at all.

### DuPont (`dupont.py`)
Standard 3-factor (NPM × Asset Turnover × Equity Multiplier = ROE) and
5-factor decomposition. The 5-factor ROE is computed as the actual product of
its five components, so it functions as a genuine internal-consistency check
against the 3-factor ROE (they should agree to rounding; disagreement means a
data problem).

### Piotroski F-Score (`piotroski.py`)
Nine binary signals (0/1). Score ≥ 8 = Strong, 5–7 = Moderate, ≤ 4 = Weak.
Uses average assets rather than beginning-of-year assets for ROA (minor deviation
from the original paper; immaterial in practice).
A signal whose inputs are unavailable is `None`, not 0, and the headline
F-score is only published when all nine signals are assessable — otherwise the
period shows "Not assessable (n of 9 signals)" with a partial sum in the JSON.
The oldest fetched year therefore never gets a score (no prior-year
comparison), and DOFG has no scores at all while yfinance lacks its gross
profit. Published as Piotroski (2000) — the paper is from 2000, not 1980.

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
The probability is only computed when every model input is present (incl. the
prior-year income needed for CHIN); otherwise the period reports
"Not assessable". The SIZE term is expressed in **millions of USD** — total
assets are converted from the reporting currency at the current spot rate
(supplied by the pipeline via ``stmts["meta"]["fx_to_usd"]``) so NOK/SEK/EUR/
USD reporters are comparable; without an FX rate the score is Not assessable.
Applying today's rate to historical years is a disclosed approximation (SIZE
is log-scale and insensitive to it). Fixed 2026-08-01 — before that, native-
currency assets understated NOK reporters' risk ~2.5× vs USD reporters.

### Altman Z-Score (`altman.py`)
Three variants computed: original Z (manufacturing), Z' (private firms), Z'' (non-manufacturing).
**Z'' is the primary model for all 17 companies** — none qualify as US manufacturers.
Z thresholds: Safe > 2.6, Grey zone 1.1–2.6, Distress ≤ 1.1.
Original Z is retained in the dashboard as a reference row shown in gray.
X4 uses book equity (not market cap) for all companies to ensure consistency
across periods and avoid price-driven distortion.
A Z-score is only computed when every component of that variant is present —
a missing component makes the zone "Not assessable" rather than entering the
sum as zero. Mowi is the standing example: yfinance provides no Retained
Earnings row for it, so its Altman zones are Not assessable (previously it
showed "Safe" with X2 silently zeroed).

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
Schedule: every Friday at 17:17 UTC — 19:17 CEST (summer) / 18:17 CET (winter).
GitHub cron is fixed UTC and does not follow DST, hence the one-hour seasonal drift.
Oslo Børs continuous trading ends 16:20 local and the closing auction ~16:25, so the
day's closing prices are always settled before the run.  
Manual dispatch: Actions tab → "Run Oslo Quant" → optional ticker/framework subset.

**Expect the run to start late.** GitHub deprioritises scheduled jobs under load; the
previous 06:00 cron consistently fired 3–6 hours behind schedule. The cron is set to
`:17` rather than `:00` to avoid the most contended slot, but never assume a scheduled
run starts on time. Friday evening is chosen partly because hours of slip are harmless
there — a Monday-morning slot was drifting into the trading day.

Steps run in this order, and the order matters:
`fetch/compute → generate report → commit & push → verify freshness`.

Key design choices:
- `continue-on-error: true` on the `oslo-quant` step — partial results are committed
  even if some tickers fail (e.g. yfinance outage or delisted ticker).
- `data/raw/` is gitignored; each run fetches fresh data from Yahoo Finance.
  The `data/results/` JSON files are committed, so the dashboard always reflects
  the last successful run even if the current run is incomplete.
- Pip packages are cached keyed on `pyproject.toml` hash.
- Push target: `HEAD:${{ github.ref_name }}` (not hardcoded `main`).

### Failure visibility

`continue-on-error: true` is correct for partial failures but it has a sharp edge: a
run in which *every* ticker fails still reports success and still commits. Combined
with committed `data/results/`, that produces the worst failure mode this project has
— a green checkmark over a dashboard that silently stops moving.

The `Verify results are fresh` step closes that gap. It runs `oslo-quant-check`, which
counts companies whose `computed_at` stamp is recent rather than counting files (the
files are always there), and fails the job below the floor. It runs *after* the push
on purpose: whatever data was obtained still gets published, and the failure is a
notification rather than a blocker.

**Recency alone is not sufficient**, because of a sharp edge in the pipeline: if a
fetch returns empty statements, the frameworks still compute "successfully" with zero
periods, and `_persist()` writes that result — overwriting good committed data with an
empty file carrying a brand-new `computed_at`. A timestamp-only check would wave this
through. `oslo-quant-check` therefore requires both a recent stamp **and** at least one
framework with ≥1 period, and reports zero-period companies separately as `empty`.

Practical consequence when working locally: **do not run `oslo-quant` without working
network access.** A blocked or offline fetch will silently replace good `data/results/`
with empty files. If it happens, `git checkout -- data/results/` restores them.

**A failed job is the only alerting channel.** GitHub emails the repository owner on
scheduled-workflow failure by default; nothing else here will ever tell you something
broke. Do not add `continue-on-error` to this step.

**FMP_API_KEY**: stored as a GitHub Actions secret. Used only in `fmp_fetcher.py`
for supplementary data; the main pipeline uses yfinance and runs without it.

---

## The 17 companies

Listed in dashboard order — `COMPANIES` is sorted by (sector, ticker).

| Ticker    | Full name                  | Ccy | Sector                        | Notes |
|-----------|----------------------------|-----|-------------------------------|-------|
| MOWI.OL | Mowi ASA | EUR | Aquaculture / Salmon Farming | IAS 41 fair-value movements inflate EBIT; creates non-cash distress signals. |
| SALM.OL | SalMar ASA | NOK | Aquaculture / Salmon Farming | Reports NOK (Mowi reports EUR) — not directly comparable in absolute terms. Same IAS 41 caveat. |
| FRO.OL | Frontline plc | USD | Crude Oil Tankers | Cyprus-registered (redomiciled from Bermuda 2022). |
| KOG.OL | Kongsberg Gruppen ASA | NOK | Defence / Technology |  |
| VEND.OL | Vend Marketplaces ASA | NOK | Media / Online Classifieds | Schibsted carve-out, listed May 2025. Limited history. |
| DOFG.OL | DOF Group ASA | USD | Offshore / Marine Services |  |
| BORR.OL | Borr Drilling Ltd | USD | Offshore Drilling | Jack-up rigs, shallow water. alt_ticker="BORR" for FMP. |
| ODL.OL | Odfjell Drilling Ltd | USD | Offshore Drilling | Harsh-environment semis & drillships (North Sea). Not jack-ups (BORR.OL is jack-ups). |
| CADLR.OL | Cadeler A/S | EUR | Offshore Wind / Installation | Danish-domiciled; wind turbine installation vessels. Reports EUR, trades NOK. NYSE: CDLR. |
| HAFNI.OL | Hafnia Ltd | USD | Product Tankers |  |
| PUBLI.OL | Public Property Invest ASA | SEK | Real Estate | Redomiciled to Nasdaq Stockholm May 2026; Oslo secondary listing continues. Reporting currency NOK→SEK with the redomicile (NOK/SEK ≈ 1.00). |
| NOD.OL | Nordic Semiconductor ASA | USD | Semiconductors | Fabless; Bluetooth/IoT |
| ELK.OL | Elkem ASA | NOK | Silicon & Specialty Chemicals |  |
| BRG.OL | Borregaard ASA | NOK | Specialty Chemicals / Biorefinery |  |
| KIT.OL | Kitron ASA | EUR | Technology / Electronics Manufacturing | Electronics manufacturing services (EMS) — medical, industrial, defence/aerospace. Presentation currency NOK→EUR in 2024; yfinance restates all history in EUR. |
| NORBT.OL | Norbit ASA | NOK | Technology / Sensing & Connectivity | Multibeam sonar, underwater sensors, telematics/IoT. alt_ticker="NORBT" for FMP. Listed June 2019. |
| TEL.OL | Telenor ASA | NOK | Telecommunications |  |

---

## Branches and GitHub Pages deployment

**Target: one branch, `main`, for everything.** Four separate things must agree, and
the only reliable way to keep them agreeing is to have nothing to choose between:

| Thing | Must be | Where it is set |
|---|---|---|
| Repository default branch | `main` | Settings → General → Default branch |
| Scheduled-run branch | `main` | *Not configurable* — GitHub only fires `schedule` on the default branch |
| Workflow push target | `main` | Follows automatically via `HEAD:${{ github.ref_name }}` |
| GitHub Pages source | `main` / root | Settings → Pages → Deploy from a branch |

The third and fourth rows are the trap. The push target is derived from whichever
branch the run started on, so it silently follows the default branch — but the Pages
source does **not**. Change the default branch without changing Pages and the workflow
happily commits to a branch nobody is serving.

### Why this matters — the 2026 incident

Between 2026-05-19 and 2026-07-27 the workflow ran green every single week and
committed fresh results. Pages was still serving `main`, frozen at the last PR merge.
The dashboard showed 10-week-old data while every Actions run reported success.
Nothing failed; the page was simply built from a branch nothing was writing to.

Diagnostic: **if the live page's "Updated …" timestamp lags the newest `Update results
and report [date]` commit, check the Pages source branch first.** The pipeline is
rarely the problem.

### Current state — migration complete (2026-07-30)

The repository previously ran with `claude/build-oslo-quant-system-lzUvb` as both
default branch and Pages source, with `main` as a stale side branch. That is finished:
the default branch is `main`, the old `claude/*` branches are deleted, and `main` is
the only branch in the repository.

**Do not reintroduce a second long-lived branch.** Commit directly to `main`. Feature
branches for a single PR are fine; leaving one alive for weeks is what caused the
incident above.

---

## Runbook — common requests

Slash commands live in `.claude/commands/`: `/add-company`, `/remove-company`,
`/dashboard-status`. They encode the checklists below.

### "Add company X" / "Remove company X"

Use `/add-company` or `/remove-company`. The steps that are easy to forget:

1. **Verify the ticker against a real source before writing it.** yfinance and FMP
   disagree more often than expected, and a wrong symbol does not error — it fetches
   empty and silently overwrites good data. Past corrections: Norbit is `NORBT.OL`
   not `NRBIT.OL`; SalMar is `SALM.OL`; Solstad Maritime is `SOMA.OL` not `SLAM.OL`.
2. **Check the reporting currency against the annual report, not the ticker.**
   Cadeler trades in NOK but reports in EUR; Mowi reports in EUR; SalMar in NOK.
   Prices are converted into the reporting currency before any price-based metric.
3. Add to `_COMPANIES_RAW` (position irrelevant — the list is sorted).
4. Update `tests/test_config.py` (count + expected ticker set) — it *will* fail
   otherwise, and it has been missed before.
5. Regenerate `README.md` and the CLAUDE.md table from config, don't hand-edit.
6. On removal, `git rm -r data/results/<TICKER>` as well.
7. `oslo-quant-report` to regenerate `index.html`, then commit.

New companies show as missing until the next run fetches them — the header will read
e.g. "14 of 17". That is expected, not a bug.

### "Is the dashboard up to date?" / "Did this week's run work?"

Use `/dashboard-status`. Manually: compare the live page's "Updated …" stamp against
the newest `Update results and report [date]` commit on `main`. If the page lags the
commit, suspect Pages configuration, not the pipeline.

### "The page hasn't changed"

In likelihood order:
1. Browser cache — reload, or open the URL in a new tab.
2. Pages source branch no longer `main` (Settings → Pages).
3. The run failed — check Actions. Since the freshness check was added, a run that
   fails to fetch real data goes red rather than green.
4. The run succeeded but fetched nothing. The job summary shows
   `Refreshed N of M companies`; companies listed as `empty` had a fetch return no
   statements.

### "Change the schedule"

`.github/workflows/run_oslo_quant.yml`, the `cron:` line. It is UTC and ignores DST,
so a fixed cron drifts an hour between summer and winter. Keep it off the top of the
hour. Update the CLAUDE.md workflow section to match.

### Working locally

**Never run `oslo-quant` without working network access.** A blocked fetch writes
empty results over good committed data. If it happens:
`git checkout -- data/results/`. This has already happened once in a sandbox.

---

## Known open items

- **Currency changes verified and config updated (2026-08-01):** KIT.OL now
  EUR (presentation-currency change 2024; magnitude check confirms yfinance
  serves the whole history in EUR, so the series is internally consistent) and
  PUBLI.OL now SEK (redomicile; NOK/SEK ≈ 1.00). Remaining to-do: tie one
  historical year each against the company's own restated comparatives in the
  first EUR/SEK annual report.
- **DOFG has no Piotroski scores** — yfinance carries no Gross Profit row for
  it, and DOF's own income statement has no cost-of-sales split either, so F8
  is permanently unassessable and the headline score is withheld by policy.
- **Verified-ledger population is incremental.** MOWI is populated (FY2023–25
  from the FY2025 annual report; FY2022 retained earnings needs the FY2023
  report). KOG, KIT, PUBLI and DOFG are scaffolds with per-company transcription
  priorities in their notes — populate them next.
- **yfinance quarterly coverage is patchy.** Many tickers are missing Q3 2025
  (TEL, KOG, BRG, KIT as a date gap; NOD as an empty column), and ELK/VEND lack
  quarterly cash flow — those companies get no LTM until the provider data
  completes or the ledger fills the gap. This is by design: no LTM is ever
  built over a broken window.

- **Node.js 20 deprecation warning** on every run. `actions/cache@v4`,
  `actions/checkout@v4` and `actions/setup-python@v5` target Node 20; GitHub forces
  Node 24. Cosmetic, non-blocking; bump the action versions when convenient.
- **Kitron, Cadeler and SalMar populated on 2026-08-01** (as part of the
  restatement recompute) — all 17 companies now carry data.
- **The freshness floor is 80%** (13 of 17). Three simultaneously-broken tickers stay
  above the floor and would not trigger an alert, though they appear in the job
  summary as `empty` or missing.
