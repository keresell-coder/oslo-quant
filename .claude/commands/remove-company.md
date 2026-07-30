---
description: Remove a company from the Oslo Quant dashboard and clean up its stored data
---

Remove a company from the dashboard. The user asked to remove: **$ARGUMENTS**

## 1. Identify it precisely

Resolve what the user named to an exact ticker in `oslo_quant/config.py`. If the name
is ambiguous, confirm with the user before deleting anything.

## 2. Remove it

- Delete the `CompanyConfig` entry from `_COMPANIES_RAW` in `oslo_quant/config.py`.
- `git rm -r data/results/<TICKER>` — remove the stored results too, otherwise a dead
  directory lingers.
- Grep the whole repo for the ticker: `grep -rn "<TICKER>" --include="*.py"
  --include="*.md" .` Stale references have hidden in unexpected places before,
  including a dead constant in `report.py`.

## 3. Update everything that counts companies

- `tests/test_config.py` — count assertion **and** expected ticker set.
- `README.md` company table — regenerate from config.
- `CLAUDE.md` — company table and every "N companies" reference.

Note the freshness floor in `healthcheck.py` is 80% of the configured total and
scales automatically; no change needed, but mention the new floor to the user.

## 4. Verify and commit

```bash
python3 -m pytest tests/ -q
ruff check oslo_quant/
python3 -c "import oslo_quant.report as r; r.generate()"
grep -rn "<TICKER>" --include="*.py" --include="*.md" . | grep -v "\.git/"
```

The last command should return nothing. Confirm the ticker is gone from `index.html`,
then commit and push to `main`.
