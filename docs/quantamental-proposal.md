# Quantamental Expansion — Feasibility Study & Implementation Proposal

**Status:** Proposal for discussion. No pipeline or dashboard code has been changed.
**Date:** 2026-07-30
**Scope:** Adding Value, Growth, Moat (ROIC vs WACC) and Fama–French CMA (asset growth)
to the existing five Quality/Risk frameworks.

---

## 0. Executive summary (plain language)

**The short version:** yes, all four factor families are feasible from the data source we
already use. No second data provider is needed for any of them. But there is a prerequisite
that must be dealt with first, and it is not optional.

**What I found in the existing code.** While tracing where valuation inputs would come from,
I found that the helper every framework uses to pull a line item out of Yahoo's financial
statements — `BaseFramework._get()` — matches row names by *substring*, and takes the first
row that matches in Yahoo's own row order. That is silently picking the wrong line item in at
least four places:

| We ask for | We actually get | Affected |
|---|---|---|
| `EBIT` | **Normalized EBITDA** | Altman X3, DuPont EBIT margin & interest burden |
| `Current Assets` | **Total Non Current Assets** | Altman X1, Ohlson WC/TA, Piotroski F6 |
| `Current Liabilities` | **Total Non Current Liabilities** | same as above |
| `Retained Earnings` | **Gains Losses Not Affecting Retained Earnings** | Altman X2, Ohlson |

This is verified, not suspected — Section 2.1 shows the reproduction and the corroborating
evidence in our own committed results (Telenor's "working capital / assets" is +0.41; a
telco's real working capital is negative).

Every new metric in this proposal — ROIC, EV/EBITDA, NOPAT — reads the same statements
through the same helper. Building on top of it would multiply the problem rather than
contain it. So **Phase 0 is a canonical field-mapping layer**, and everything else sits on
top of it.

**What the expansion looks like once that is done.** Three new frameworks
(`valuation`, `growth`, `moat`), one new market-data layer, one small config file of market
assumptions (risk-free rates, equity risk premium), and a summary table that switches between
three lenses — Quality & Risk (what we have today), Value, and Growth & Moat — instead of
growing to 20 columns.

**The one genuine data limitation:** Yahoo gives us **four** annual periods, not six. So a
3-year CAGR is available today; a 5-year CAGR is not, for anyone. The fix is to start
archiving each year's statements into the repository from now on, which makes 5-year growth
available from 2028 onward without any new provider.

---

## 1. Part 1 — Factor expansion & methodology

Notation: `t` = fiscal period (annual), `RC` = the company's reporting currency,
all balance-sheet items at period end, all income/cash-flow items for the period.

### 1.1 Value

Everything in this block requires one thing the pipeline does not currently compute:
**market capitalisation in the reporting currency, per period**.

```
Shares_t   = OrdinarySharesNumber_t            (fallback: ShareIssued_t,
                                                then DilutedAverageShares_t)
Price_t    = last unadjusted close on or before fiscal period end, in NOK
FX_t       = NOK→RC rate on that same date
MarketCap_t = Price_t × Shares_t × FX_t                                  [RC]
```

Two traps here, both real (Section 2.3): the price series we cache today is
**dividend-adjusted**, which understates historical prices and therefore makes every
historical multiple look cheaper than it was; and the FX conversion currently applies
**one spot rate to the whole 5-year price history**.

#### P/E

```
P/E_t = MarketCap_t / NetIncomeCommonStockholders_t
```

Use net income **attributable to common shareholders** (excludes minority interest), so that
numerator and denominator refer to the same claim. Report `n/m` when earnings ≤ 0 — never a
negative P/E, which sorts nonsensically.

Cross-check (should agree within ~2%): `Price_t / DilutedEPS_t`. Divergence beyond that is a
share-count data-quality flag worth surfacing.

#### P/B

```
P/B_t = MarketCap_t / CommonStockEquity_t
```

`CommonStockEquity` is equity attributable to the parent, which matches market cap's claim.
Do **not** use `TotalEquityGrossMinorityInterest` here. `n/m` when equity ≤ 0.

#### EV/EBITDA

```
EV_t = MarketCap_t
     + TotalDebt_t                                  (includes IFRS 16 lease obligations)
     + MinorityInterest_t
     + PreferredStockEquity_t
     − CashCashEquivalentsAndShortTermInvestments_t

EBITDA_t          = EBIT_t + DepreciationAmortizationDepletion_t   (from cash flow stmt)
EBITDA_norm_t     = EBITDA_t − TotalUnusualItemsExcludingGoodwill_t

EV/EBITDA_t       = EV_t / EBITDA_t
EV/EBITDA_norm_t  = EV_t / EBITDA_norm_t
EV/EBIT_t         = EV_t / EBIT_t
```

**Compute EBITDA ourselves rather than reading Yahoo's `EBITDA` row.** Yahoo's row is
opaque about what it normalises, and for Mowi and SalMar the IAS 41 biological-asset
fair-value movement runs through EBIT — the same distortion CLAUDE.md already documents for
Altman/Ohlson. Publishing both the reported and the normalised multiple side by side is the
honest treatment: the gap between them *is* the information.

IFRS 16 consistency note: because `TotalDebt` includes lease liabilities and EBITDA is
post-IFRS 16 (lease cost sits in D&A and interest, not opex), EV/EBITDA is internally
consistent. This matters for Cadeler, DOF, Borr and Odfjell, where leases are large.

#### FCF yield (recommended addition, near-zero marginal cost)

```
FCF yield_t = FreeCashFlow_t / MarketCap_t
```

Yahoo publishes `FreeCashFlow` directly. For the capital-intensive half of this universe
(offshore, drilling, shipping, aquaculture) FCF yield is a far better cheapness signal than
P/E, because P/E at a cyclical peak is the classic value trap.

---

### 1.2 Moat / profitability — ROIC vs WACC

This is the most demanding block, and the one where being explicit about definitions matters
most. Morningstar's economic moat rating is *forward-looking* — narrow = excess returns
expected to persist ≥ 10 years, wide = ≥ 20 years ([Morningstar equity research
methodology](https://www.morningstar.com/content/dam/marketing/shared/research/methodology/705988Morningstar_Equity_Research_Methodology.pdf)).
We cannot forecast, so what we build is a **backward-looking quantitative proxy**: the size
and the *persistence* of the realised ROIC−WACC spread. It must be labelled as such on the
dashboard; calling it a "moat rating" without that caveat would overclaim.

#### NOPAT

```
τ_t   = clamp(TaxRateForCalcs_t, 0.00, 0.50)
        fallback: clamp(TaxProvision_t / PretaxIncome_t, 0.00, 0.50)
        fallback: 0.22  (Norwegian statutory rate)

NOPAT_t = EBIT_t × (1 − τ_t)
```

Yahoo publishes `TaxRateForCalcs` as a line item, which is convenient and — importantly for
this universe — *company-specific*. Three Norwegian tax regimes make a single statutory rate
wrong:

- **Tonnage tax** (FRO, HAFNI, and parts of DOFG/ODL): shipping income is permanently
  tax-exempt, so the effective rate is near zero and, correctly, there is **no interest tax
  shield** either. Using 22% would flatter both NOPAT and the after-tax cost of debt.
  ([Norwegian Maritime Authority](https://www.sdir.no/en/the-norwegian-ship-registers/norwegian-tonnage-tax-regime/))
- **Aquaculture resource rent tax** (MOWI, SALM): 25% effective on the Norwegian sea-phase,
  implying a ~47% marginal rate on that income since 2023.
  ([regjeringen.no](https://www.regjeringen.no/en/aktuelt/resource-rent-tax-on-aquaculture/id2929113/))
- Everyone else: 22% flat.
  ([PwC Tax Summaries](https://taxsummaries.pwc.com/norway/corporate/taxes-on-corporate-income))

Reading the reported effective rate handles all three without a sector lookup table, which is
why it is preferred over the statutory rate.

#### Invested capital

I recommend the **financing-side (net) definition**, because it is directly derivable from
rows Yahoo actually populates for all 17 companies:

```
IC_t = TotalDebt_t + CommonStockEquity_t + MinorityInterest_t
     − CashCashEquivalentsAndShortTermInvestments_t
```

which is equivalently `NetDebt_t + TotalEquityGrossMinorityInterest_t`.

This is the standard McKinsey/Koller "invested capital = operating assets funded by investors"
identity, approached from the financing side. Damodaran's operating-side alternative
(`Total assets − non-debt current liabilities`, optionally less non-operating cash) reaches
the same place but depends on `CurrentLiabilities` and `CurrentDebt`, which is precisely the
pair of rows Yahoo populates least consistently — and the pair our current code mis-resolves.
([Damodaran, *Return on Capital, Return on Invested Capital*](https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf))

Also compute the operating-side variant as a **cross-check only** and flag when the two
differ by more than 15%; Yahoo additionally publishes its own `InvestedCapital` row, which
gives a third reference point. Disagreement between three definitions is a data-quality
signal, not something to hide.

On excess cash: I recommend **not** carving out an operating-cash allowance (the
"cash minus 2% of revenue" convention). It adds a judgement parameter for a small effect on
most of this universe, and it interacts badly with shipping companies that hold large cash
balances as working capital against charter cycles. Subtract all cash, and say so.

```
ROIC_t = NOPAT_t / average(IC_t, IC_{t−1})
```

Averaging matches what DuPont and Piotroski already do here for assets and equity.

#### WACC

```
E_t    = MarketCap_t                                (market value of equity, RC)
D_t    = TotalDebt_t                                (book value as proxy for market value)
w_e    = E_t / (D_t + E_t)          w_d = 1 − w_e

WACC_t = w_e × Ke_t + w_d × Kd_t × (1 − τ_t)
```

**Cost of equity** — CAPM with a Blume-adjusted, locally-estimated beta:

```
β_raw  = cov(r_stock , r_index) / var(r_index)
         5 years of *weekly* returns, stock in NOK vs OSEBX in NOK, min 104 observations
β_adj  = 0.67 × β_raw + 0.33 × 1.00                 (Blume adjustment)

Ke_t   = Rf(RC) + β_adj × MRP + SP
```

- **Estimate beta ourselves; do not use Yahoo's `info["beta"]`.** Yahoo's beta for Oslo tickers
  is computed against a US benchmark on monthly data. We already fetch 5 years of daily prices
  for every company; one extra fetch of the OSEBX index gives us a locally-consistent,
  reproducible, testable beta.
- **Estimate beta on NOK prices, before the FX conversion.** The pipeline currently converts
  prices into the reporting currency; beta must be measured in the same currency as the index,
  i.e. on the raw NOK series. This is a concrete ordering constraint on the new market-data
  layer.
- **MRP = 5.0%.** The PwC / Norwegian Society of Financial Analysts (FFN) survey has put the
  Norwegian market risk premium at 5.0% for over a decade, unchanged in the 2025 edition.
  ([PwC Norge](https://www.pwc.no/no/innsikt/risikopremien-i-det-norske-markedet.html),
  [FFN 2025](https://finansfag.no/uploads/Risikopremien/MRP2025.pdf))
- **Rf by reporting currency**, so that a USD reporter's WACC is a USD discount rate:
  NOK ≈ 4.3% (Norwegian 10-year government bond, mid-2026), USD ≈ 4.2%, EUR ≈ 2.6%.
  The same PwC survey reports that 55% of Norwegian practitioners use the 10-year government
  bond as the risk-free rate, which is the convention adopted here.
- **SP — small-company premium.** 67% of respondents in that survey apply one. Proposed
  tiers: 0 bp above NOK 20bn market cap, +100 bp for 5–20bn, +200 bp below 5bn. This is the
  single most arbitrary knob in the whole proposal and should be a config constant that can
  be set to zero.

**Cost of debt:**

```
Kd_t = clamp( InterestExpense_t / average(TotalDebt_t, TotalDebt_{t−1}),
              Rf + 0.5pp,  Rf + 8.0pp )
       fallback when debt ≈ 0 or interest missing:  Rf + 2.5pp
```

The clamp is protection against Yahoo's interest-expense row occasionally being net rather
than gross, which produces absurd implied rates.

#### Moat classification

```
spread_t     = ROIC_t − WACC_t
persistence  = count of years in the available window (max 4 today) with spread_t > 0
```

| Label | Rule | Colour |
|---|---|---|
| **Strong franchise** | latest spread ≥ +5pp **and** positive in ≥ 4 of last 4–5 yrs | green |
| **Narrow** | latest spread ≥ +1pp **and** positive in ≥ 3 | green |
| **None** | latest spread < +1pp, or positive in < 3 years | amber |
| **Eroding** | positive in ≥ 3 prior years **but** latest spread < 0 | red |
| **Insufficient history** | fewer than 3 usable periods (VEND, CADLR today) | gray |

Persistence is doing real work here: a single year of ROIC > WACC in a tanker company at the
top of a rate cycle is not a moat, and this rule will not call it one.

---

### 1.3 Growth

```
CAGR_n(X) = (X_t / X_{t−n})^(1/n) − 1
```

defined **only** when both endpoints are strictly positive; otherwise report `n/m` plus the
absolute change, never a fabricated percentage. Metrics:

- Revenue CAGR (3y)
- Diluted EPS CAGR (3y) — use `DilutedEPS`, which is share-count aware, rather than net
  income; a company that grew earnings 40% while issuing 50% more shares has not grown
- EBITDA CAGR (3y)
- **Growth quality flag:** `EPS CAGR ≥ Revenue CAGR` → growth is accompanied by margin
  expansion or share-count discipline, rather than pure top-line inflation

**n = 3, not 5.** Yahoo's annual statements give four fiscal years (see Section 2.2), so three
compounding intervals is the ceiling. 5-year CAGR becomes available in 2028 if we start
archiving statements now (Phase 6) — from our own repository, no new provider.

---

### 1.4 Fama–French CMA — asset growth

The CMA (Conservative Minus Aggressive) factor in Fama–French (2015) sorts on the asset-growth
measure of Cooper, Gulen & Schill (2008): firms that expand the balance sheet aggressively
subsequently underperform on a risk-adjusted basis.

```
AssetGrowth_t   = (TotalAssets_t − TotalAssets_{t−1}) / TotalAssets_{t−1}
AssetGrowth_3y  = mean of the last three annual observations
```

([Cooper, Gulen & Ion](https://www.smu.edu/-/media/Site/Cox/Departments/Finance/FINASeminarSeries/cooper_gulen_ion_2017.ashx),
[Quantpedia summary](https://quantpedia.com/strategies/asset-growth-effect))

The same caveat that applies to Sloan accruals applies here, and harder: half this universe
*is* capital deployment. Cadeler building installation vessels, DOF and Odfjell renewing
fleets, PUBLI acquiring property — high asset growth is the business model, not a red flag.

**Therefore do not display asset growth as a standalone traffic light.** Display it against
the ROIC spread as a 2×2, which is the actual quantamental question:

| | Spread > 0 | Spread ≤ 0 |
|---|---|---|
| **Asset growth ≤ 10%** | Disciplined compounder (green) | Stagnant (amber) |
| **Asset growth > 25%** | Value-creating expansion (green, watch funding) | **Empire building (red)** — the CMA short |

The bottom-right cell is the entire point of the factor. Presenting it this way turns a
blunt penalty into a genuine screening signal.

---

### 1.5 Proposed thresholds (Nordic / European context)

These are **starting values**, and I want to be explicit that they are informed judgement,
not fitted parameters. Oslo Børs trades at an average P/E around 20.5, versus a trailing
19.4 for the STOXX Europe 600 as of January 2026, so this is not a structurally cheap market
and thresholds imported from US large-cap screens would mark almost everything "expensive".
([Siblis Research — Europe](https://siblisresearch.com/data/europe-pe-ratio/),
[Chartmill — Euronext Oslo](https://www.chartmill.com/stock/markets/europe/exchange/139-euronext-oslo))

| Metric | Green | Amber | Red | Notes |
|---|---|---|---|---|
| P/E | < 12 | 12 – 20 | > 20 | `n/m` if E ≤ 0. Low P/E at a cyclical peak is a trap — always read with FCF yield |
| P/B | < 1.0 | 1.0 – 3.0 | > 3.0 | Meaningless for asset-light (VEND, NORBT, KIT); primary for PUBLI, FRO, HAFNI |
| EV/EBITDA | < 6.0 | 6.0 – 10.0 | > 10.0 | Nordic mid-cap industrials typically clear 7–9 |
| EV/EBIT | < 10 | 10 – 16 | > 16 | Better than EV/EBITDA where D&A is economically real (offshore, shipping) |
| FCF yield | > 8% | 3 – 8% | < 3% | |
| ROIC | > 12% | 6 – 12% | < 6% | |
| **ROIC − WACC** | > +3pp | −1 to +3pp | < −1pp | The headline moat number |
| Revenue CAGR 3y | > 10% | 3 – 10% | < 3% | |
| EPS CAGR 3y | > 10% | 0 – 10% | < 0% | `n/m` if either endpoint ≤ 0 |
| Asset growth | ≤ 10% | 10 – 25% | > 25% | **Only meaningful crossed with ROIC spread** — see 1.4 |

**Recalibration plan.** Once Phase 2–4 have run once, we will have the actual cross-sectional
distribution for these 17 companies. The right final step is to re-anchor each threshold on
the universe's own quartiles (green = top quartile, red = bottom quartile) and keep the
absolute thresholds above only as a sanity floor. That is Phase 5, and it is the difference
between a screen that says something and a screen that colours everything amber.

**Sector exceptions that must be surfaced in the legend:**

| Sector | Companies | Caveat |
|---|---|---|
| Aquaculture | MOWI, SALM | IAS 41 fair value inflates EBIT/EBITDA → read the *normalised* multiple |
| Shipping (tonnage tax) | FRO, HAFNI | Near-zero tax → NOPAT ≈ EBIT, no debt tax shield. NAV/P/B is the market's primary lens, not P/E |
| Offshore & drilling | DOFG, BORR, ODL, CADLR | Large IFRS 16 leases; high asset growth is capex, not empire building |
| Real estate | PUBLI | EV/EBITDA weak; P/B and net yield are the sector convention. EPRA NRV is not available from Yahoo |
| Asset-light tech | VEND, NORBT, KIT, NOD | P/B uninformative; use EV/EBIT + growth + ROIC |

---

## 2. Part 2 — Data feasibility & pipeline integration

### 2.1 Prerequisite: the field-resolution defect

`BaseFramework._get()` (`oslo_quant/frameworks/base.py:29`) does:

```python
matches = [idx for idx in df.index if name.lower() in str(idx).lower()]
if matches:
    val = df.loc[matches[0], target_col]
```

Substring match, first hit in DataFrame row order wins. yfinance orders statement rows to a
fixed list (`yfinance/scrapers/fundamentals.py:178` → `df.reindex([k for k in keys if k in df.index])`)
and renders them in title case, so the row order is deterministic and known. Replaying our
own lookups against that vocabulary:

```
INC ('EBIT', 'Operating Income')          -> 'Normalized EBITDA'                          (3 matches)
INC ('Net Income',)                       -> 'Net Income From Continuing Operation
                                              Net Minority Interest'                      (9 matches)
BS  ('Current Assets', ...)               -> 'Total Non Current Assets'                   (4 matches)
BS  ('Current Liabilities', ...)          -> 'Total Non Current Liabilities Net
                                              Minority Interest'                          (4 matches)
BS  ('Retained Earnings', ...)            -> 'Gains Losses Not Affecting Retained
                                              Earnings'                                   (2 matches)
BS  ('Long Term Debt', ...)               -> 'Long Term Debt And Capital Lease Obligation' (2 matches)
```

Corroborated by our own committed results:

- `TEL.OL` 2025 `ebit_margin` = **49.3%**. Telenor's EBIT margin is ~17%; its EBITDA margin
  is ~49%. The figure labelled EBIT margin on the live dashboard is the EBITDA margin.
- `TEL.OL` 2025 `x1_working_capital_to_assets` = **+0.41**. A telco's working capital is
  structurally negative. `(non-current assets − non-current liabilities) / assets` ≈ +0.4.

Consequence: Altman X1/X2/X3, DuPont's EBIT margin and interest burden, Piotroski's F6, and
Ohlson's WC/TA are all computed from the wrong rows today. The `Long Term Debt` case is
arguably acceptable (leases are debt post-IFRS 16) but should be an explicit choice.

**Separately:** every ticker with five period columns has an entirely empty oldest column
(all 14 companies show a null-valued `2021`), which Altman turns into `z_score: 0.0`,
`zone: "Distress"` because `_v(nan) → 0`. That is a false red badge in the historical detail
cards. The fix is a guard that drops periods where the core inputs are all missing.

**Proposed fix — a canonical field map** (`oslo_quant/frameworks/fields.py`):

```python
FIELDS = {
    "ebit":            ["EBIT", "Operating Income", "Total Operating Income As Reported"],
    "current_assets":  ["Current Assets"],
    "current_liabs":   ["Current Liabilities"],
    "retained":        ["Retained Earnings"],
    "net_income":      ["Net Income Common Stockholders", "Net Income"],
    ...
}

def get(df, field, col=None, *, strict=True): ...
```

Resolution rule: **exact match on the full row label first**, in the order listed; substring
matching only as an explicit opt-in (`strict=False`) for genuinely variable labels. Add a
regression test that builds a fixture index from `yfinance.const.fundamentals_keys` in
Yahoo's real order and asserts each canonical field resolves to the intended row — this is
the test that would have caught all six cases above, and the current fixtures do not, because
they use idealised row names.

**This will change published numbers.** Altman Z''/X1/X2/X3 and DuPont EBIT margin will move
for most companies once corrected. That needs a visible note on the dashboard for one or two
weeks, not a silent restatement.

### 2.2 What Yahoo actually gives us

Verified against the installed `yfinance` 1.5.2 field catalogue
(`yfinance/const.py: fundamentals_keys`), not assumed:

| Need | Available? | Source |
|---|---|---|
| Current market cap | ✅ | `Ticker.info["marketCap"]` (NOK) |
| Current shares outstanding | ✅ | `info["sharesOutstanding"]`, `impliedSharesOutstanding` |
| **Historical** shares outstanding | ✅ | balance sheet `OrdinarySharesNumber` / `ShareIssued`; income stmt `DilutedAverageShares` |
| Historical EPS | ✅ | income stmt `DilutedEPS`, `BasicEPS`, `NormalizedDilutedEPS` |
| Prices (unadjusted) | ✅ | `history(auto_adjust=False)` → raw `Close` **and** `Adj Close` |
| EBIT, EBITDA, D&A | ✅ | `EBIT`, `EBITDA`, `NormalizedEBITDA`; `DepreciationAmortizationDepletion` (CF) |
| Effective tax rate | ✅ | `TaxRateForCalcs`, plus `TaxProvision` / `PretaxIncome` |
| Total debt, net debt, cash | ✅ | `TotalDebt`, `NetDebt`, `CashCashEquivalentsAndShortTermInvestments` |
| Minority interest, preferred | ✅ | `MinorityInterest`, `PreferredStockEquity` |
| Free cash flow | ✅ | `FreeCashFlow` (CF) |
| Yahoo's own invested capital | ✅ | `InvestedCapital` (useful as a cross-check) |
| FX time series | ✅ | `Ticker("NOKUSD=X").history(period="10y")` |
| OSEBX index for beta | ✅ | `OSEBX.OL` (fallback `^OSEAX`) |
| TTM statements | ✅ | `ttm_income_stmt`, `ttm_cash_flow` (yfinance ≥ 0.2.5x) |
| **6+ years of annual history** | ❌ | Yahoo returns 4 annual periods |
| Sovereign bond yields (NOK/EUR) | ❌ | `^TNX` covers US only; no reliable Yahoo ticker for NST/Bund |
| Forward estimates / consensus | ❌ | Not needed for anything proposed here |

**Verdict on a secondary source: not required.** Everything in Sections 1.1–1.4 comes from
Yahoo. Specifically on FMP:

- Its free tier is 250 requests/day and its deep-history annual statements are US-focused;
  .OL fundamentals coverage is not dependable enough to be a *primary* source for anything.
- More importantly, the current FMP integration has a latent defect worth fixing regardless.
  `_merge_statements()` (`pipeline.py:190`) concatenates FMP columns for periods Yahoo lacks —
  but FMP's row labels (`netIncome`, `totalAssets`) share no vocabulary with Yahoo's
  (`Net Income`, `Total Assets`). A pandas outer join on mismatched indexes yields a period
  column that is all-NaN for every row the frameworks look up. That produces exactly the
  phantom empty period described in 2.1. Either normalise FMP row names into the canonical
  vocabulary from Phase 0, or restrict FMP to filling *cells* rather than adding *columns*.

The two genuine gaps (deep history, sovereign yields) are better solved by a repository
archive and a small config constant respectively than by adding a provider.

### 2.3 Currency handling — the proposal

Today: `_convert_prices()` (`pipeline.py:209`) fetches **one** spot FX rate and multiplies the
entire 5-year price history by it. For the current-period metrics on the live dashboard that
is fine. For historical P/E rows it is not: NOK/USD moved materially over 2021–2026, so a
single rate misprices every historical multiple.

**Proposed logic, in the order the pipeline must execute it:**

1. Fetch prices **unadjusted** (`auto_adjust=False`), keeping raw `Close` (for market cap) and
   `Adj Close` (for return-based work such as beta). Adjusted prices are dividend-back-adjusted
   and must never be used to reconstruct historical market cap.
2. Estimate **beta on the NOK series** against OSEBX in NOK, before any conversion.
3. Fetch the **FX series** `NOK{RC}=X` for the same window, once per currency pair, cached
   across tickers (the existing `_fx_cache` pattern extends naturally).
4. For each fiscal period end, take the last available price and the FX rate **on that same
   date** (forward-fill up to 5 calendar days for holidays); compute
   `MarketCap_t = Price_t × Shares_t × FX_t`.
5. For the current snapshot, use spot price and spot FX. Record both the rate and its date in
   the result JSON so a reader can reproduce the number.
6. If the FX series is unavailable, mark the affected value-metric periods `null` with a
   reason code. **Do not fall back to an unconverted number** — the current fallback leaves
   prices in NOK while the denominator is in USD, which silently inflates P/B by roughly 10×.
   A missing value is safe; a wrong value is not.

Failure of any FX fetch should be visible in the existing Currency Verification panel.

### 2.4 Point-in-time integrity

A P/E computed as "FY2023 earnings ÷ price on 2023-12-31" is a valuation snapshot dated to the
balance-sheet date, but FY2023 earnings were not public until Feb/Mar 2024. This is
**look-ahead bias**, and it means the historical multiple rows are legitimate context but are
*not* a backtestable signal.

Recommendation: keep period-end pricing (simple, reproducible, standard for a valuation
history), and state the limitation in the legend. If backtesting ever becomes a goal, the
change is to lag the price by one quarter — a one-line change if the market-data layer is
built with a `price_asof(date)` helper from the start, which is why the layer should be
designed that way now.

---

## 3. Part 3 — Architecture

### 3.1 Module layout

```
oslo_quant/
  config.py              (+ ALL_FRAMEWORKS gains "valuation", "growth", "moat")
  market_params.py       NEW — risk-free rates, MRP, size premium, index ticker, AS_OF date
  fetchers/
    base.py              Statements gains: prices_raw, fx, shares, market (snapshot dict)
    yfinance_fetcher.py  + unadjusted prices, FX series, index series, info snapshot
  marketdata.py          NEW — MarketData: price_asof(), fx_asof(), market_cap(), beta()
  frameworks/
    fields.py            NEW — canonical field map + strict resolver   ← Phase 0
    base.py              _get() delegates to fields.get(); + _cagr(), _drop_empty_periods()
    valuation.py         NEW — P/E, P/B, EV/EBITDA (reported + normalised), EV/EBIT, FCF yield
    growth.py            NEW — revenue/EPS/EBITDA CAGR, asset growth (CMA), growth quality
    moat.py              NEW — NOPAT, invested capital, ROIC, WACC, spread, persistence
  report.py              + three lenses, three card sections, new legends
  healthcheck.py         (no change needed — it iterates ALL_FRAMEWORKS)
```

`Statements` grows from four keys to seven. Because it is a `TypedDict` consumed positionally
by name, existing frameworks are unaffected.

### 3.2 Result JSON — shape and payload

**Keep one file per framework per ticker, with the existing envelope.** `report._load_results()`
globs `*.json` and keys on the file stem, so new frameworks require no loader change at all.

```jsonc
// data/results/TEL.OL/valuation.json
{
  "ticker": "TEL.OL",
  "framework": "valuation",
  "computed_at": "2026-07-31T17:40:11Z",
  "financial_currency": "NOK",
  "price_currency": "NOK",
  "snapshot": {                       // current, spot-priced — drives the summary table
    "price_nok": 148.20,
    "fx_rate": 1.0,
    "fx_date": "2026-07-31",
    "shares": 1399000000,
    "market_cap": 207328800000,
    "pe": 18.9, "pb": 3.2, "ev_ebitda": 6.4, "ev_ebitda_norm": 6.6,
    "ev_ebit": 11.8, "fcf_yield": 0.071
  },
  "periods": {                        // historical, period-end priced — drives the card
    "2025": { "market_cap": 198400000000, "pe": 18.1, "pb": 3.0,
              "ev_ebitda": 6.2, "ev_ebit": 11.5, "fcf_yield": 0.068,
              "price": 141.80, "fx_rate": 1.0 },
    "2024": { ... }
  }
}
```

The `snapshot` block is new but additive; the `periods` block matches every existing
framework file, which keeps `healthcheck.py`'s period-count guard working unchanged.

**Payload arithmetic** (the bloat question, answered concretely):

| | Today | After |
|---|---|---|
| `data/results/` | 84 files, 396 KB | ~135 files, ~600 KB |
| `index.html` | 270 KB | ~420 KB (≈ 60 KB over the wire; GitHub Pages gzips) |
| Weekly commit diff | ~15 KB | ~25 KB |

This is not a bloat problem. Three cheap disciplines keep it that way: round ratios to 4
decimals (already the convention via `_fmt`), drop all-null periods rather than serialising
them, and store raw absolute inputs (market cap, invested capital, NOPAT) **only** in the
`moat`/`valuation` files rather than repeating them in each framework.

The real constraint is not bytes, it is **visual density** — which is Part 4.

### 3.3 Things that must be updated in lockstep

1. `config.ALL_FRAMEWORKS` — adding the three keys makes `healthcheck` and the CLI's
   `--frameworks` flag pick them up automatically.
2. `tests/test_config.py::test_all_frameworks_list` — asserts the exact list; will fail.
3. `tests/fixtures.py` — currently uses idealised row names. Phase 0 replaces these with
   fixtures built from the real Yahoo vocabulary and ordering.
4. `.github/workflows/run_oslo_quant.yml` — the `workflow_dispatch` input description still
   says "all 14"; the framework list in the description needs the three new names.
5. `pyproject.toml` — `yfinance>=0.2.40` is unpinned against a library that has since gone to
   1.5.x. A weekly unattended job installing an unpinned major version is a standing risk.
   Recommend `yfinance>=1.5,<2`.
6. `README.md` and `CLAUDE.md` framework sections.

---

## 4. Part 4 — UI / UX

The summary table has 8 columns today. Adding value, growth and moat naively takes it to ~18,
which on a laptop means horizontal scrolling and, in practice, nobody reading columns 9+.

### 4.1 Summary table: three lenses, one table

A segmented control above the table switches which metric block is rendered. The company
identity column (ticker, name, period, currency) is sticky across all lenses.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [ Quality & Risk ]  [ Value ]  [ Growth & Moat ]  [ All ]                  │
├──────────────┬─────────────────────────────────────────────────────────────┤
│ Company      │  … lens columns …                          │  Quantamental  │
└──────────────┴─────────────────────────────────────────────────────────────┘
```

| Lens | Columns |
|---|---|
| **Quality & Risk** (default, = today) | ROE · Net margin · Piotroski · Sloan · Ohlson · Altman Z'' |
| **Value** | P/E · P/B · EV/EBITDA (reported + normalised) · FCF yield |
| **Growth & Moat** | Rev CAGR 3y · EPS CAGR 3y · ROIC · ROIC−WACC · Asset growth (2×2 badge) |
| **All** | everything, horizontally scrollable — the power-user escape hatch |

Implementation: render all four `<tbody>` variants into the page and toggle `display` in the
existing vanilla-JS style (`togglePanel`/`toggleCard` already establish the pattern — no
framework, no build step, still a single self-contained file). Remember the chosen lens in
`localStorage` so a reload doesn't reset it.

### 4.2 The composite column — "Quantamental score"

One column visible in every lens, so switching lenses never loses the overall picture:

```
Score = 0.30 × Quality + 0.25 × Risk + 0.25 × Value + 0.20 × Growth&Moat
```

Each pillar is a **percentile rank within our own 17-company universe** (not an absolute
score), which sidesteps the entire threshold-calibration problem for the headline number and
is standard practice for a small, sector-diverse screen. Companies missing a pillar get that
pillar's weight redistributed, and the cell shows how many pillars were available (`4/4`,
`3/4`). Hovering shows the pillar breakdown.

This is Phase 5 — deliberately *after* the metrics exist and their distributions are visible.
Weighting factors before seeing the data would be guesswork.

### 4.3 Detail cards

Cards keep their current structure and gain three sections built with the existing
`_fw_section` builder, so the code shape is unchanged:

1. **New: "At a glance" strip** at the top of each card — four pillar chips (Quality, Risk,
   Value, Growth/Moat) with score and colour, then the existing narrative sentence.
2. **Valuation** section — one row per multiple, one column per year, exactly like DuPont's
   table today. Historical multiples in a card are far more informative than a single current
   number: seeing Frontline at 3× EV/EBITDA in 2022 and 11× in 2025 tells the cyclical story
   at a glance.
3. **Growth** section — CAGRs, yearly revenue/EPS/EBITDA growth, asset growth row.
4. **Moat** section — ROIC, WACC, spread by year, with the spread row colour-scaled, plus the
   WACC input breakdown (beta, Ke, Kd, weights, tax rate) as an indented sub-block, so every
   number is auditable rather than a black box.

### 4.4 Optional: the Value–Quality scatter

The single most useful quantamental visual is a scatter of **EV/EBITDA (x) against ROIC−WACC
(y)**, bubble size = market cap, quadrant-shaded. "Cheap and value-creating" is the
bottom-right — the actual screen output. It can be hand-rolled as inline SVG (17 points, no
library, no CDN, consistent with the single-file constraint). Proposed as Phase 5, optional.

### 4.5 Legend additions

The existing legend panel gets: one card per new framework in the same tone as the current
five; a **WACC assumptions panel** stating Rf per currency, MRP, size-premium tiers, beta
method and the `AS_OF` date of those constants; and an explicit paragraph on the two
limitations that matter — the moat label is backward-looking, and the historical multiples
carry look-ahead bias.

---

## 5. Part 5 — Roadmap

Each phase is independently shippable and independently revertible
(`git checkout -- data/results/` restores committed results; `index.html` regenerates from
JSON with `oslo-quant-report`).

### Phase 0 — Canonical field mapping *(prerequisite, blocks everything else)*
- `frameworks/fields.py` with exact-match-first resolution; `_get()` delegates to it.
- Fix the six mis-resolutions; make the `Long Term Debt` lease treatment an explicit choice.
- Drop periods where all core inputs are missing (kills the false 2021 "Distress" badge).
- Rebuild `tests/fixtures.py` from the real Yahoo row vocabulary and ordering; add a
  resolution test asserting every canonical field maps to the intended row.
- **Acceptance:** tests pass; a re-run changes Altman X1/X2/X3 and DuPont EBIT margin in the
  expected direction (Telenor EBIT margin ≈ 17%, working capital negative).
- **Communication:** a dated note on the dashboard explaining that historical figures were
  restated and why.

### Phase 1 — Market-data layer
- Unadjusted prices + adjusted prices; FX series per currency pair; OSEBX series; `info`
  snapshot; all cached in `data/raw/` as today.
- `marketdata.py` with `price_asof()`, `fx_asof()`, `market_cap(period)`, `beta()`.
- New `market.json` per ticker (spot price, shares, market cap, FX rate + date, beta).
- **Acceptance:** computed market caps for TEL, MOWI, KOG match Yahoo's reported `marketCap`
  within 2%; FX conversion reproduces a manual check for one EUR and one USD reporter.

### Phase 2 — Valuation framework + Value lens
- `valuation.py`; summary-table lens switcher; card section; legend card.
- **Acceptance:** all 17 companies produce a P/E or an explicit `n/m`; no negative P/E is
  ever rendered; historical multiples move sensibly with the price series.

### Phase 3 — Growth + CMA
- `growth.py`; Growth & Moat lens (growth half); asset-growth 2×2 badge.
- **Acceptance:** CAGR is `n/m` wherever an endpoint is non-positive; VEND and CADLR are
  correctly reported as insufficient-history rather than showing a spurious number.

### Phase 4 — Moat (ROIC vs WACC)
- `market_params.py`; `moat.py`; WACC input sub-block in the card; assumptions panel.
- **Acceptance:** WACC lands in a defensible 6–12% band for every company; tonnage-tax
  shippers show a near-zero tax rate and no debt tax shield; a spot check against a published
  broker WACC for Telenor or Kongsberg is within ~2pp.

### Phase 5 — Calibration + composite + scatter
- Re-anchor thresholds on the universe's own quartiles; add the composite score column; add
  the optional Value–Quality scatter.
- **Acceptance:** no threshold leaves more than ~60% of the universe in a single colour band.

### Phase 6 — History archive (unlocks 5-year CAGR)
- Append each run's annual statement rows to a committed `data/history/<TICKER>/annuals.json`,
  deduplicated by fiscal period. Costs a few KB per company per year.
- 5-year CAGR becomes available in 2028 with no new data provider.

**Suggested sequencing:** Phase 0 alone, verified over one weekly run, before starting
Phase 1. Phases 1+2 together, then 3, then 4. Phase 5 only after all metrics have run at
least twice.

---

## 6. Risks and open decisions

**Risks**

| Risk | Mitigation |
|---|---|
| Phase 0 changes published historical numbers | Dated restatement note on the dashboard; land Phase 0 on its own so the cause is unambiguous |
| Yahoo drops or renames a field | Canonical map fails loudly to `null` with a reason code rather than silently resolving to a neighbouring row |
| `yfinance` unpinned major version in weekly CI | Pin `>=1.5,<2` |
| Missing shares data for recent listings (VEND, CADLR) | Fall back to `DilutedAverageShares`; if absent, `n/m` — never estimate |
| Cyclical value traps (FRO, HAFNI, BORR at peak earnings) | Pair P/E with FCF yield and EV/EBITDA; sector caveats in the legend |
| WACC constants going stale | `AS_OF` date rendered on the dashboard; refresh is a one-line config edit, documented in CLAUDE.md |
| More metrics → more amber noise | Phase 5 quartile recalibration; lenses instead of 18 columns |

**Decisions — agreed 2026-07-30**

1. **Phase 0 ships alone, first.** The field-map fix lands on its own and is published by one
   weekly run with a dated restatement note on the dashboard, before any new factor is built.
   Rationale: it moves numbers that are live today, and isolating it keeps the cause of every
   changed figure unambiguous.
2. **Invested capital subtracts all cash.**
   `IC = TotalDebt + CommonStockEquity + MinorityInterest − Cash & short-term investments`
   (equivalently `NetDebt + Equity incl. minority interest`). No operating-cash allowance, no
   tunable carve-out. Known consequence: ROIC is slightly overstated for shippers holding
   large cash balances as cycle working capital — to be noted in the Moat legend card.
3. **WACC includes a tiered small-company premium**: 0bp above NOK 20bn market cap,
   +100bp for 5–20bn, +200bp below 5bn. Held as a single config constant in
   `market_params.py` so it can be set to zero without touching framework code. Raises the
   hurdle rate for NORBT, KIT and CADLR.
4. **First release after Phase 0 is Value, end-to-end**: market-data layer + `valuation.py` +
   the Value lens + the card section + legend card, shipped complete and visible on the live
   dashboard. Growth and Moat follow the same pattern once the shape has been reviewed in
   production.

---

## Sources

- [Damodaran — *Return on Capital (ROC), Return on Invested Capital (ROIC) and Return on Equity*](https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf)
- [Morgan Stanley Counterpoint Global — *Return on Invested Capital*](https://www.morganstanley.com/im/publication/insights/articles/article_returnoninvestedcapital.pdf)
- [Morningstar — Equity Research Methodology (economic moat)](https://www.morningstar.com/content/dam/marketing/shared/research/methodology/705988Morningstar_Equity_Research_Methodology.pdf)
- [PwC Norge / FFN — *Risikopremien i det norske markedet*](https://www.pwc.no/no/innsikt/risikopremien-i-det-norske-markedet.html) · [2025 edition (PDF)](https://finansfag.no/uploads/Risikopremien/MRP2025.pdf)
- [Cooper, Gulen & Ion — *The Use of Asset Growth in Empirical Asset Pricing Models*](https://www.smu.edu/-/media/Site/Cox/Departments/Finance/FINASeminarSeries/cooper_gulen_ion_2017.ashx)
- [Quantpedia — Asset Growth Effect](https://quantpedia.com/strategies/asset-growth-effect)
- [PwC Tax Summaries — Norway, corporate income taxes](https://taxsummaries.pwc.com/norway/corporate/taxes-on-corporate-income)
- [Norwegian Government — Resource rent tax on aquaculture](https://www.regjeringen.no/en/aktuelt/resource-rent-tax-on-aquaculture/id2929113/)
- [Norwegian Maritime Authority — Tonnage tax regime](https://www.sdir.no/en/the-norwegian-ship-registers/norwegian-tonnage-tax-regime/)
- [Siblis Research — Europe P/E ratios](https://siblisresearch.com/data/europe-pe-ratio/)
- [ChartMill — Euronext Oslo listed companies](https://www.chartmill.com/stock/markets/europe/exchange/139-euronext-oslo)
- [Trading Economics — Norway government bond yield](https://tradingeconomics.com/norway/government-bond-yield)
