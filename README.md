# oslo-quant

Oslo Børs quantitative pre-computation system — fetches financial data for 14 Oslo Stock Exchange companies and runs five analytical frameworks to produce structured JSON results.

## Companies

| Ticker | Alt ticker |
|--------|------------|
| DOFG.OL | |
| BRG.OL | |
| ODL.OL | |
| ELK.OL | |
| NOD.OL | |
| VEND.OL | |
| PUBLI.OL | |
| MOWI.OL | |
| TEL.OL | |
| KOG.OL | |
| KMAR.OL | |
| BORR.OL | BORR |
| FRO.OL | |
| HAFNI.OL | |

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
