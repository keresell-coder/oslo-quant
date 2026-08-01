# Post-Restatement Review — Oslo Quant

**Date:** 1 August 2026
**Scope:** Verification of the 2026-08-01 restatement (commit `c6c97a2`) against the independent audit of 30 July 2026, plus a fresh model / content / code critique.
**Test suite:** 68 tests passing (45 pre-existing + 23 new regression tests).
**Data:** All 17 companies recomputed from live yfinance data on 2026-08-01; healthcheck 17/17 PASS.

---

## 1. Audit findings — resolution status

| Audit finding (severity) | Status |
|---|---|
| Substring field resolution selects wrong rows (**Critical**) | **Fixed.** Exact-match first; substring only as a logged fallback. A full 17-ticker production run produced **zero** fallback warnings — every field resolved exactly. Regression fixture reproduces the real yfinance vocabulary/row order with decoy rows. |
| Empty periods scored as real results (**Critical**) | **Fixed.** All-NaN and stub columns (no Total Assets / Total Revenue anchor) are dropped. Zero `Z=0.00 Distress` rows and zero `21.08%` default Ohlson probabilities remain in the recomputed data. |
| Missing components neutralized to zero (**High**) | **Fixed.** No zero-substitution anywhere. Missing input ⇒ `None` / "Not assessable". Mowi's Altman zone is now honestly Not assessable (no retained-earnings row from the provider) instead of "Safe". |
| Net income = continuing operations (**High**) | **Fixed** under an explicit policy: total operations (yfinance exact `Net Income`). ELK 2025: NOK −668m / ROE −2.7% (was +301m / +1.2%). TEL 2025: NOK 7,034m / 9.6% (was 10,961m / 15.0%). Matches the audit's diagnostics. |
| Piotroski early years mechanically 0/1 (**High→was understated**) | **Fixed.** Unassessable signals are `None`; headline score withheld unless 9/9. The artifactual 0- and 1-score years are gone from every chart. |
| Sloan method divergence not escalated (**High**) | **Fixed** (mechanically): `methods_diverge_materially` flag at >10pp. Currently flags 23 of 68 company-periods. |
| 5-factor ROE check tautological (DuPont) | **Fixed.** Computed as the product of the five components; verified equal to NI/avg-equity across all companies. |
| Piotroski dated 1980; "US-calibrated" framing (**Medium**) | **Fixed** (dated 2000). Framework guide wording otherwise unchanged. |
| Ohlson currency/SIZE bias (**High**) | **Not fixed — documented.** See §3. |
| Sector-blind thresholds (**Medium**) | **Not fixed — inherent limitation, documented.** |
| No filing-level source ledger (**High**) | **Not fixed.** Still single-source yfinance. |

Verified classification impact of the fix (latest period, before → after):
BORR Grey→Distress · FRO Safe→Grey · KOG Safe→Grey · PUBLI Safe→Distress · TEL Safe→Grey · MOWI Safe→Not assessable. These are exactly the reclassifications the audit predicted. Note the direction: **every error the old code made flattered the portfolio.**

## 2. New findings from this review (not in the July audit)

1. **Three inconsistent F-score cutoffs.** `piotroski._interpret()` says Strong ≥ 8; the dashboard legend says "7–9 = Strong"; the summary-table colour turns green at ≥ 7. Piotroski (2000) uses 8–9 as the high-score portfolio, so the code is right and the legend/colour are wrong. One-line fixes; left unfixed pending a decision on which convention to standardise on.
2. **KIT.OL reporting currency is likely wrong in config.** yfinance reports EUR; config says NOK. Kitron changed presentation currency to EUR in 2024, so yfinance is probably correct. Verify against the annual report, then update `config.py` and the CLAUDE.md table.
3. **PUBLI.OL now reports SEK per yfinance** (config: NOK) — consistent with the Nasdaq Stockholm redomiciling. Same verification path.
4. **History depth shrank.** yfinance supplies 4 usable statement years; the oldest has no prior-year comparison, so most companies now show 3 scored Piotroski years (DOFG: none, missing gross profit). This is honest, but charts are visibly shorter than before — a restatement consequence users should expect.
5. **TEL 2022 ROE now 74.7%.** Not a bug: the total-operations policy includes the one-off CelcomDigi gain (total NI NOK 44.9bn). The perimeter policy trades silent exclusion for visible one-offs; users must read spikes against the annual report.

## 3. What remains open (ranked)

1. **Ohlson cross-currency SIZE bias** — assets are logged in reporting currency; USD reporters carry ~+0.96 and EUR ~+1.00 O-score penalty vs NOK reporters (≈2.5× in probability terms). The FX machinery already exists in the pipeline; convert total assets to a common currency before the SIZE term, or suppress cross-company Ohlson comparison until then.
2. **Source ledger** — no filing-level tie-out or committed raw snapshot per run; wrong provider data remains undetectable from the published package.
3. **Sector-aware interpretation** — PUBLI's 107.8% "EBIT margin" (fair-value gains on investment property) and the IAS 41 effects at MOWI/SALM are correct arithmetic on misleading-for-screening inputs.
4. **Original Z book-equity deviation** — documented and reference-only, but consider converting market cap to reporting currency (the FX path exists) instead of substituting book equity.
5. **Sloan ±5% thresholds** — dashboard convention, not from the paper; now at least accompanied by the divergence flag.

## 4. Verdict

The July audit's two Critical findings and the mechanical High findings are closed, with regression tests that reproduce the provider's real vocabulary so the bug class cannot silently return. The dashboard carries a visible restatement notice, and every published score is now either computed from exactly-resolved inputs or explicitly "Not assessable."

**Posture: usable as a screening tool with documented caveats** — upgraded from "not decision-ready" for screening purposes only. It remains, by design, not a substitute for filing review: Ohlson cross-currency ranking is still invalid, thresholds are still sector-blind, and yfinance is still the only source. Those are the next three items in priority order.
