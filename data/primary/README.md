# Primary artifacts and mappings

`NOD.OL.json` is the selected primary-fact ledger; the artifact under `artifacts/`
is the original issuer PDF named by its SHA-256. The original is from Library
`libfile_44dd24587234819185dab8d54fc7589d`; its hash and pp14–17 were independently
checked. Only this active report is included, not the whole research package.

The ledger separates publication, accounting period, original retrieval date and
local artifact receipt. Hash checks never imply fresh filing retrieval.
`reviewed-transcription` applies to individual mapped facts, not the whole issuer
or every accounting definition. Records require issuer/field/period/basis identity,
page/table/row, currency/scale and explicit aggregation semantics.

To update: obtain the original issuer report, verify and preserve its SHA-256,
review mapped fields and scope visually, add a separately versioned source/period
and explicit bridges, run regressions, then independent review through a PR.
Do not overwrite old observation snapshots with newly learned primary data.
A later report or restatement needs its own publication/source identity; existing
records are never silently rewritten as if known at an earlier observation.

Other-company reconciliation JSON is audit-only and cannot activate replacements.
Source artifact downloads in `cache/` are ignored; committed artifacts are always
hash-checked and require no new credentials or production dependencies.
