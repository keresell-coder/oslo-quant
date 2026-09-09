# oslo-quant

**Live dashboard: https://keresell-coder.github.io/oslo-quant/**

Updated automatically every Friday evening after Oslo Børs closes.

## Source trust and publication

Publication now stages a real upstream refresh and validates all five framework
files against one run and source snapshot before replacing the report. At least
14 of 17 companies must pass; failed companies have their summary and detail
scores withheld. Failed publication updates only [health.json](https://keresell-coder.github.io/oslo-quant/health.json),
retains the prior report/results, and fails the workflow. The HTML reads this
health record at view time and checks its snapshot against the displayed report.

Local raw caches expire after 24 hours and require an original, timezone-aware
retrieval time plus matching file hashes. Legacy, future-dated, or damaged caches
refresh. `computed_at` is calculation time; `source_metadata.groups.*.source_fetched_at`
is actual provider retrieval time. Cache reuse cannot count as a new retrieval.
Public health distinguishes source retrieval, statement period ends, missing
tables, and selected primary-ledger line-item coverage. Filing publication dates
remain **unverified**; fresh Yahoo retrieval is not proof of the latest filing.
A latest statement older than 180 days raises a disclosed age warning.

Use `python -m oslo_quant.publish` for gated publication and
`python -m pytest -q` for the regression suite (also run on PRs and main).
Piotroski display bands match calculation: 8–9 strong, 5–7 moderate.

Oslo Børs quantitative pre-computation system — fetches financial data for 17 Oslo Stock Exchange companies and runs five analytical frameworks to produce structured JSON results.

## Companies

Listed in dashboard order (sorted by sector).

| Ticker | Company | Sector | Ccy | Alt ticker |
|--------|---------|--------|-----|------------|
| MOWI.OL | Mowi ASA | Aquaculture / Salmon Farming | EUR |  |
| SALM.OL | SalMar ASA | Aquaculture / Salmon Farming | NOK |  |
| FRO.OL | Frontline plc | Crude Oil Tankers | USD |  |
| KOG.OL | Kongsberg Gruppen ASA | Defence / Technology | NOK |  |
| VEND.OL | Vend Marketplaces ASA | Media / Online Classifieds | NOK |  |
| DOFG.OL | DOF Group ASA | Offshore / Marine Services | USD |  |
| BORR.OL | Borr Drilling Ltd | Offshore Drilling | USD | BORR |
| ODL.OL | Odfjell Drilling Ltd | Offshore Drilling | USD |  |
| CADLR.OL | Cadeler A/S | Offshore Wind / Installation | EUR | CDLR |
| HAFNI.OL | Hafnia Ltd | Product Tankers | USD |  |
| PUBLI.OL | Public Property Invest ASA | Real Estate | NOK |  |
| NOD.OL | Nordic Semiconductor ASA | Semiconductors | USD |  |
| ELK.OL | Elkem ASA | Silicon & Specialty Chemicals | NOK |  |
| BRG.OL | Borregaard ASA | Specialty Chemicals / Biorefinery | NOK |  |
| KIT.OL | Kitron ASA | Technology / Electronics Manufacturing | NOK |  |
| NORBT.OL | Norbit ASA | Technology / Sensing & Connectivity | NOK | NORBT |
| TEL.OL | Telenor ASA | Telecommunications | NOK |  |

## Frameworks

| Name | Description |
|------|-------------|
| `dupont` | 3-factor and 5-factor DuPont decomposition of ROE |
| `piotroski` | Piotroski F-Score (9 binary signals, 0–9) |
| `sloan` | Sloan accruals — earnings quality via balance-sheet and CFO-based accrual ratios |
| `ohlson` | Ohlson O-Score — logistic bankruptcy probability model (1980) |
| `altman` | Altman Z-Score — financial distress classification (1968) |

## Data sources

- **Primary**: [yfinance](https://github.com/ranaroussi/yfinance) — balance sheet, income statement, cash flow, 5-year price history
- **Optional**: [Financial Modeling Prep](https://financialmodelingprep.com/) API — supplemental historical statements

## Installation

```bash
pip install -e .
```

Copy `.env.example` to `.env` and optionally add your FMP API key:

```bash
cp .env.example .env
# edit .env — FMP_API_KEY is optional
```

## Usage

```bash
# Run all 14 companies, all 5 frameworks
oslo-quant

# Specific tickers and frameworks
oslo-quant --tickers TEL.OL MOWI.OL --frameworks dupont piotroski

# Force re-fetch (ignore cached parquet files)
oslo-quant --force-refresh

# Show full JSON output on stdout
oslo-quant --tickers BORR.OL --output full

# Quiet mode
oslo-quant --output none
```

## Output

Raw data is cached in `data/raw/{TICKER}/*.parquet`. Framework results are written to `data/results/{TICKER}/{framework}.json`.

Example result structure (`data/results/TEL.OL/dupont.json`):

```json
{
  "ticker": "TEL.OL",
  "framework": "dupont",
  "computed_at": "2024-01-15T10:00:00Z",
  "periods": {
    "2023": {
      "net_profit_margin": 0.0842,
      "asset_turnover": 0.312,
      "equity_multiplier": 3.14,
      "roe_3factor": 0.0823,
      ...
    }
  }
}
```

## Tests

```bash
pytest
```

## Project structure

```
oslo_quant/
├── config.py          # tickers, paths, env vars
├── cli.py             # argparse entry point
├── pipeline.py        # fetch → compute → persist orchestration
├── fetchers/
│   ├── base.py        # Statements TypedDict + BaseFetcher ABC
│   ├── yfinance_fetcher.py
│   └── fmp_fetcher.py
└── frameworks/
    ├── base.py        # BaseFramework ABC + shared helpers
    ├── dupont.py
    ├── piotroski.py
    ├── sloan.py
    ├── ohlson.py
    └── altman.py
```
