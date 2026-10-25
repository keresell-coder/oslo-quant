# Offline methodology review evidence

Run `python scripts/methodology_review.py` from this repository after installing dev dependencies. No network requests or production file writes occur.

* `control-before-after.json`: independently specified synthetic statement control; baseline versus revised framework outputs. Timestamp removed for reproducibility.
* `saved-results-before.html` / `saved-results-after.html`: exact old/new report renderer over the same saved production results, with no framework recomputation. New renderer marks legacy Piotroski calculations, removes Ohlson probability interpretation and withholds the old hybrid Altman reference. Existing legacy Sloan BS output is not relabelled original.
* `synthetic-divergence.html`: deliberately divergent diagnostic to inspect summary, detail and warning presentation; NOT Nordic output.

Actual production recalculation and financial gates must be checked after approved deployment. No primary data or historical output has been modified by these artifacts.
