# Financial input contracts — first bounded repair

Known issuer release availability is separate from provider retrieval, statement
period ends, calculation time and market prices. Nordic's issuer quarterly archive
(https://www.nordicsemi.com/Investor-Relations/Reports/Quarterly) shows Q3 2026
published on 22 October. The registry in `oslo_quant/financial_contracts.py` records
period/release/source/observation separately; it contains no replacement figures.
Unknown issuer dates remain unverified. This is a bounded registry, not an automated
filing calendar or verification of accounting definitions.

Publication re-evaluates each quarterly table against the known release, even when
retrieval just succeeded. A lagging or missing required table withholds the company
through the existing summary/detail publication gate. Currency agreement between
provider and configured reporting currency is only a screening contract; mismatch
or missing currency blocks qualification. Quote currency is no longer substituted
for missing financial currency. Missing/nonpositive/nonfinite FX removes prices
from price-dependent calculation inputs, rather than leaving NOK labelled USD.
Conversion rate/source/retrieval context is persisted. Formulas are unchanged.

Offline evidence in `docs/review-evidence/` uses original 9ba10d270cc38ef1948c5d5a5b6fc84d02a714e0
results (calculation parent b880276eb462f3a5ca47430ef4b379ed5ebd3aae).
It is not a fresh download: it shows June coverage withheld, and retained legacy
currency metadata unqualified. Tests independently simulate a fresh successful
retrieval with June periods so download recency cannot bypass the filing guard.

Verified locally: 105 Python tests pass (56 existing datetime deprecation warnings)
and git diff whitespace check. No primary financial refresh was performed.
After independent review: merge, dispatch `run_oslo_quant.yml` on main, inspect
staged health/qualification and generated commit, then verify Pages snapshot,
NOD health and both summary/detail withholding on the actual deployed revision.
The existing 14/17 floor remains unchanged. A blocked attempt retains the old
report and updates health only; distinguish guard deployment from refreshed or
fully reconciled financial inputs. Unknown EBITDA definitions are not reconciled.
