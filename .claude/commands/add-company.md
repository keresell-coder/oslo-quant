---
description: Add a company to the Oslo Quant dashboard, with ticker and currency verification
---

Add a company to the dashboard. The user asked for: **$ARGUMENTS**

Work through this in order. Do not skip step 1 — a wrong ticker does not raise an
error, it fetches empty and silently overwrites good data.

## 1. Verify before writing anything

Confirm from a real source (web search, or the FMP MCP tools if available), not from
memory:

- **Exact yfinance ticker.** Usually `<SYMBOL>.OL` for Oslo Børs, but check — Norbit
  is `NORBT.OL`, not `NRBIT.OL`. If FMP uses a different symbol, record it as
  `alt_ticker`.
- **Reporting currency, from the annual report — not the trading currency.** Every
  Oslo Børs share trades in NOK; that says nothing about the accounts. Cadeler trades
  NOK and reports EUR. Mowi reports EUR. Getting this wrong distorts every
  price-based metric, because prices are converted into the reporting currency.
- **Full legal name** and what the company actually does.

If the ticker cannot be confirmed, stop and ask the user rather than guessing.

## 2. Choose the sector

Reuse an existing `sector` string verbatim to group the company with its peers —
match the exact text, since grouping is by string equality. Only invent a new sector
label if nothing fits.

## 3. Edit `oslo_quant/config.py`

Add a `CompanyConfig` to `_COMPANIES_RAW`. Position in that list does not matter;
`COMPANIES` is sorted by `(sector, ticker)`. Add a `notes=` string for anything that
would mislead a reader of the dashboard — accounting quirks, recent listing, limited
history, currency mismatch with a sector peer.

## 4. Update everything that counts companies

- `tests/test_config.py` — the count assertion **and** the expected ticker set.
  This is missed often; run the tests.
- `README.md` company table — regenerate from config, do not hand-edit.
- `CLAUDE.md` — the company table and every "N companies" reference.

## 5. Verify and commit

```bash
python3 -m pytest tests/ -q
ruff check oslo_quant/
python3 -c "import oslo_quant.report as r; r.generate()"
```

Confirm the new ticker appears in `index.html` and the sector ordering is right.
Commit and push to `main`.

## 6. Tell the user what to expect

The new company has no stored data until the next scheduled run fetches it, so the
dashboard header will read e.g. "16 of 17" until Friday evening. Say this explicitly
so it does not look like a failure.
