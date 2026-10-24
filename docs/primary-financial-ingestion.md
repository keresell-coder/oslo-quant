# Selected primary financial ingestion — review batch 2

Starts at generated main ee2a65013f0acdfe073af4dfeb7112fed0e8c8fd.
No scoring formulas or universe changes; no production output is regenerated here.

The common primary schema and immutable source are in `data/primary/`. Nordic's
64 selected record/period mappings come from the actual Q3 2026 unaudited report,
printed pp14–17, publication22October, accounting end30September. Field-specific
records keep table/row/page, issuer URL and original SHA-256, currency/scale,
quarter/YTD/annual/stock scope, group basis, and transcription-review state.
The original network retrieval date is known only to the date; the precise
`retrieved_at`/`artifact_received_at` identifies local receipt of the supplied
Library artifact, not an invented original HTTP observation. Runtime source hash
checks are separate and do not imply a fresh filing retrieval.

One original Nordic PDF is committed under its SHA-256 for reproducibility. The
direct issuer URL returned403; the supplied Library original was materialized,
hash-verified and visually checked on pp14–17. No credentials, security bypass or
whole research-package upload is required. A changed/missing artifact blocks
configured primary inputs. Other research is retained only as minimal audit notes.

## Selection and remaining gates

`primary_adapter.py` adds one explicit primary virtual current period, LTM2026-09,
using compatible FY2025 + 9M2026 - 9M2025 flow bridges and the same-date primary
balance sheet. It copies frames, preserves provider annual columns, and retains
the previous provider virtual-current values in selection audit metadata. It
rejects incompatible currency, incomplete required tables, conflicting selections
and primary overrides older than provider observations. Existing annual ledger
behavior is unchanged, including MOWI's selected controls/proxy limitations.

Primary TTM USD: revenue815.987m, reported EBITDA108.503m, NI58.174m, CFO39.938m.
EPS and weighted shares are not bridged. Reported operating income is its own row,
not silently labelled standardized EBIT. Generic FCF is not manufactured: capex
including software and capitalized development are separate cash-flow lines.
Retained earnings335.403m is from p16, not Other equity395.126m. Original rounding
residuals stay visible; there are no balancing plugs.

Source metadata retains provider per-table dates and actual retrievals separately
from selected primary coverage. A known-release gap can qualify on selected primary
inputs only after the source/hash/scope/complete-core-table contract succeeds.
This is selected-field qualification, not whole-company verification. Existing
framework missing-input rules still apply; signals depending on undefined EBIT,
long-term debt, shares or FX can remain unassessable. No score is forced to appear.
Primary metadata participates in source snapshot identity across all frameworks.

DOFG issuer/provider/management EBITDA definitions and EV components remain separate
in `data/reconciliation/`; these are audit-only, not applied to financial frames.
The347m reconstruction is numerically consistent, not confirmation of provider
methodology. Provider TTM923m and the EV bridge remain unresolved;874m is not
silently substituted. PUBLI restatement replacement is deferred, not spot-converted.

## Verification

131 Python tests pass (56 pre-existing datetime deprecation warnings), plus diff
whitespace checks. Tests cover schema/source failures, cumulative-quarter errors,
non-additive bridges, primary selection/old-provider preservation, MOWI no-op,
missing core tables, wrong currency and stale overrides. The original safeguards
remain in the full suite. Actual source pages were visually checked.

`python -m oslo_quant.preview_primary` regenerates the offline review evidence in
`docs/review-evidence/primary-ingestion/nod-selection.json`. It uses real primary
records and an explicitly labelled issuer annual control comparator; it is NOT
claimed as a frozen provider snapshot or a production recalculation. Full provider
collection and gated publication occur only after independent implementation review,
using the existing staged publication workflow on main and live snapshot acceptance.
