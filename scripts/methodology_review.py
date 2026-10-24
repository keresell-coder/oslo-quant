"""Reproduce offline review artifacts; does not fetch data or change saved results."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oslo_quant import report
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.frameworks.altman import AltmanFramework

BASE = "c9b4eaa2041f8bff4923e5821b96cda0edce037e"
OUT = ROOT / "review-evidence"
OUT.mkdir(exist_ok=True)


def old_module(path):
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True
    )
    namespace = {
        "__name__": "methodology_review_baseline",
        "__file__": str(ROOT / path),
    }
    exec(compile(source, str(ROOT / path), "exec"), namespace)
    return namespace


def stable(result):
    result.pop("computed_at", None)
    return result


fixture = runpy.run_path(str(ROOT / "tests/test_methodology_contracts.py"))[
    "statements"
]()
classes = [PiotroskiFramework, SloanFramework, OhlsonFramework, AltmanFramework]
before = {}
after = {}
for cls in classes:
    name = cls.name
    old = old_module(f"oslo_quant/frameworks/{name}.py")[cls.__name__]
    before[name] = stable(old().compute(fixture, "CONTROL"))
    after[name] = stable(cls().compute(fixture, "CONTROL"))
(OUT / "control-before-after.json").write_text(
    json.dumps(
        {
            "baseline_revision": BASE,
            "fixture": "Synthetic independent arithmetic control from tests/test_methodology_contracts.py; not an issuer valuation",
            "before": before,
            "after": after,
        },
        indent=2,
        allow_nan=False,
    )
    + "\n"
)
data = report._load_results()
old_report = old_module("oslo_quant/report.py")
(OUT / "saved-results-before.html").write_text(old_report["_build_html"](data))
(OUT / "saved-results-after.html").write_text(report._build_html(data))
# Full report renderer with a deliberately divergent synthetic control, clearly named.
control = {"NOD.OL": after}
control["NOD.OL"]["sloan"]["periods"]["2024"].update(
    cfo_accrual_ratio=-0.02,
    bs_accrual_ratio=0.15,
    methods_divergence=0.17,
    methods_diverge_materially=True,
)
(OUT / "synthetic-divergence.html").write_text(
    report._build_html(control).replace(
        "<body>",
        "<body><p>SYNTHETIC CONTROL ONLY — not Nordic financial results or a valuation.</p>",
    )
)
(OUT / "README.md").write_text("""# Offline methodology review evidence

Run `python scripts/methodology_review.py` from this repository after installing dev dependencies. No network requests or production file writes occur.

* `control-before-after.json`: independently specified synthetic statement control; baseline versus revised framework outputs. Timestamp removed for reproducibility.
* `saved-results-before.html` / `saved-results-after.html`: exact old/new report renderer over the same saved production results, with no framework recomputation. New renderer marks legacy Piotroski calculations, removes Ohlson probability interpretation and withholds the old hybrid Altman reference. Existing legacy Sloan BS output is not relabelled original.
* `synthetic-divergence.html`: deliberately divergent diagnostic to inspect summary, detail and warning presentation; NOT Nordic output.

Actual production recalculation and financial gates must be checked after approved deployment. No primary data or historical output has been modified by these artifacts.
""")
print("Wrote offline review evidence")

# Normalize template whitespace only in the offline evidence artifacts.
for page in OUT.glob("*.html"):
    page.write_text("\n".join(line.rstrip() for line in page.read_text().splitlines()) + "\n")
