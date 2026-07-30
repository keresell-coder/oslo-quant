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
  results/           — Computed JSON per ticker per framework (committed)
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
**Z'' is the primary model for all 17 companies** — none qualify as US manufacturers.
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
| PUBLI.OL | Public Property Invest ASA | NOK | Real Estate | Redomiciling to Nasdaq Stockholm from May 2026; secondary listing on Oslo Børs continues. |
| NOD.OL | Nordic Semiconductor ASA | USD | Semiconductors | Fabless; Bluetooth/IoT |
| ELK.OL | Elkem ASA | NOK | Silicon & Specialty Chemicals |  |
| BRG.OL | Borregaard ASA | NOK | Specialty Chemicals / Biorefinery |  |
| KIT.OL | Kitron ASA | NOK | Technology / Electronics Manufacturing | Electronics manufacturing services (EMS) — medical, industrial, defence/aerospace. |
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

- **Node.js 20 deprecation warning** on every run. `actions/cache@v4`,
  `actions/checkout@v4` and `actions/setup-python@v5` target Node 20; GitHub forces
  Node 24. Cosmetic, non-blocking; bump the action versions when convenient.
- **Kitron, Cadeler and SalMar have no data yet** as of 2026-07-30. The first run to
  include them is Friday 2026-07-31. If the header does not reach "17 of 17"
  afterwards, one of those three tickers is wrong for yfinance — that is the first
  thing to check.
- **The freshness floor is 80%** (13 of 17). Three simultaneously-broken tickers stay
  above the floor and would not trigger an alert, though they appear in the job
  summary as `empty` or missing.
