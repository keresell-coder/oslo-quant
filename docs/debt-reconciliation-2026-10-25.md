# Debt source reconciliation — bounded review batch, 25 October 2026

Base: Quant `a31b7cf36c25fa6fc753bc36f190a73c2a6024b5`; Workspace `d7b0a34c8e475c31712c59ac609d95c3aa1c223c`. Isolated branches. No merge, publication workflow or production data regeneration is authorized in this batch. Energy and daily screeners are unchanged.

## Diagnostic

All76 saved F5 signals were unknown because neither accepted exact current-maturities label resolved. Long Term Debt resolved75 times. Raw Yahoo/yfinance capture (25October, version0.2.66) has CurrentDebt and debt/lease aggregate rows; these are not universal current-LTD aliases. Other gaps remain (F7 unknown30 periods, older opening balances and gross profit).

The frozen raw provider frames, currencies and observation timestamps are in Quant `tests/fixtures/debt_provider_20261025/`. Original names/currency units are retained. No missing value becomes zero because of a provider omission or an isolated dash.

## Effective scope in Quant

Only NOD and MOWI FY2025/FY2024 non-lease current/noncurrent debt pairs are source-selected for F5. The bank/bond carrying-amount scope excludes leases and accrued interest and is mutually exclusive. Source pages, field labels, original PDF SHA256, publication/availability and differences against original provider rows are preserved. Frames remain immutable; the selection is consumed only by F5. Average-assets formula and named annual conventions are unchanged.

Three original annual PDFs are pinned once per hash in `data/debt/artifacts/` for offline reproducibility. These are the necessary NOD2025/NOD2024/MOWI2025 sources, not the full research package. This adds about42MB; hashes remain checked at runtime. Adding Mowi's issuer host is a bounded source-origin mapping, with no credential/auth changes.

NOD: noncurrent USD98.377m/87.336m and current principal explicitly0/0. Sole bond and undrawn RCF context plus maturity tables establish nil; current interest663k/626k and leases remain separate. NOD2024 publication date is unauthenticated. It remains null; first documented availability is25October2026. It cannot qualify an earlier evaluation. No historical publication date is invented.

MOWI: EUR2790.1m+149.9m /1957.3m+200m, group carrying amounts. The149.9m Schuldschein carrying amount is not replaced by150m face principal. Parent note identifies instruments only; parent noncurrent totals are not substituted for group totals.

Provider Total Assets must match same-currency/group primary controls within the source's stated rounding increment. Opening controls are required for each leverage ratio; adjacent debt periods are required for F5. No current annual observation is carried into an interim period. The source panel discloses original provider/selected values, availability, classification and source links. Qualification is field-specific, not whole-company verification.

Offline actual-provider preview: NOD FY2025 F5 becomes0 (0.1099143 vs0.1046598), yielding full annual score6. MOWI FY2025 F5 becomes0 (0.3130457 vs0.2569178), but F7 remains unknown and full score stays withheld. FY2024 F5 lacks FY2023 debt mapping and stays unknown. Nordic current LTM2026-09 still lacks compatible interim debt/F7 and stays withheld. This does not unlock current headline scores or all76 periods.

## DOFG and PUBLI — audit only, both tools

DOF explicit note22 current principal160/142m, noncurrent1423/1463m, leases separate. Do not derive143 by rounded145−2. Note22/APM/balance interest/rounding discrepancies stay disclosed. FY2023 primary asset control is absent in this package, so no effective F5 overlay is selected. IFRS TTM EBITDA874m versus a consistent gross-finance-cost numerical reconstruction936m still differs from provider923m by13m. This is not confirmed provider methodology, and provider missing Q32025 is not filled with an implied189m. EV remains unresolved/withheld; no replacement valuation.

PUBLI selected official SEK debt25727+206 /5588+205m remains separate from the provider uniform-translation series. No matching2023 opening assets or full IFRS replacement is established. Original annual contractual bank maturities Year1 NOK4/1m conflict in scope with current-bank balance/rollforward nil; preserve that disclosure difference without claiming all near-term principal is bonds or reclassifying debt. An isolated current-lease dash is not promoted to verified zero.

The provider FY2025 NI/CFO/assets numerically reconstruct from original NOK via approximately0.915048512. Provider revenue reconstructs rental1089+reimbursed fee15=1104mNOK, whereas issuer operating income is rental1089+other5=1094mNOK. Official IAS21 historical translation uses distinct flow/stock/acquisition rates. This is a numerical hypothesis, not provider-confirmed policy or a license to apply corrective FX. Actual raw provider assets are now observed and recorded; methodology/restatement differences remain open.

These additions to `data/reconciliation/*_definition_component_mapping.json` are audit-only. Workspace changes only these disclosures; existing values, EPS/EV gates, peer/history policy and generated snapshots remain unchanged.

## Evidence / verification

Primary research package: Library `libfile_5735c693e6388191bf3805caf0ca5a72`, ZIP SHA256 `6e93534125f322eb8e1365158f8ce9da9b39586a39fb0dca5c1761beee7032f0`. Independent review accepted only the bounded fields and caveats above. The actual relevant source pages were also visually checked locally.

Quant: `python -m pytest -q`; offline reproduction `python scripts/preview_debt_reconciliation.py`, outputs `docs/review-evidence/debt-reconciliation/before-after.json` and `source-preview.html`. Controls cover missing/explicit nil, leases/interest, doublecount/duplicates, currency/period/basis conflict, as-of availability, source rounding boundaries, asset compatibility, real provider annual controls and no annual-to-interim backfill.

Workspace: existing Python/Node/syntax CI remains required. Production/live acceptance is NOT run for this draft batch. No deployment claim is made. Historical saved outputs stay unchanged; future approved recalculation must carry this debt contract version and exact source availability, with versioned old/new evidence.

Final local validation: Quant167 tests passed (36 pre-existing datetime deprecation warnings); Workspace90 Python tests and9 Node tests passed, Python compilation and both JS syntax checks passed. Source-preview HTML visually inspected. Exact-head CI is checked on the draft PR; no publication run is triggered.
