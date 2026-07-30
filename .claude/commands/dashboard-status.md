---
description: Check whether the live Oslo Quant dashboard is current and the last run succeeded
---

Report whether the dashboard is up to date. Answer in plain language — the repository
owner is not a software engineer.

## What to check

1. **Latest run.** Use the GitHub MCP Actions tools to list recent runs of
   `run_oslo_quant.yml`. Report the date, the conclusion, and — importantly — whether
   the `Verify results are fresh` step passed. A run can be green overall only if that
   step passed, since it is the last step and has no `continue-on-error`.

2. **Latest commit on `main`.** Find the newest `Update results and report [date]`
   commit. That is when data last changed.

3. **What the published page says.** Read the committed `index.html` on `main`:

   ```bash
   git fetch -q origin main
   git show origin/main:index.html | grep -oE "Updated [0-9-]+ [0-9:]+ [A-Z]+" | head -1
   git show origin/main:index.html | grep -oE "[0-9]+ of [0-9]+ companies computed" | head -1
   ```

   Note this is what *should* be served, not proof of what the live site shows.
   Outbound access to `github.io` is usually blocked from this environment, so if
   `WebFetch` fails, say so plainly and ask the user to look at the page — do not
   claim the live site is fine when you could not reach it.

4. **Company coverage.** If the header is not "N of N", identify which companies are
   missing. Recently added companies legitimately have no data until the next run.

## How to report

Lead with the answer: is it current, yes or no. Then the evidence. If something is
wrong, give the likely cause in order of probability:

1. Browser cache — reload in a new tab.
2. Pages source branch changed (Settings → Pages must be `main` / root).
3. The run failed — link the Actions run.
4. The run succeeded but fetched nothing — check the job summary for companies listed
   as `empty`.

Expect scheduled runs to start hours late; GitHub deprioritises them. A run that has
not started yet on Friday evening is normal, not a failure.
