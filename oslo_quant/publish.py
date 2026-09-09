"""Stage, validate and publish; a failed attempt updates health only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from oslo_quant.config import ROOT
from oslo_quant.trust import stamp


def promote(candidate: Path, health: dict, root: Path) -> bool:
    public_health = root / "health.json"
    if health.get("status") not in {"current", "degraded"}:
        try:
            previous = json.loads(public_health.read_text())
        except (OSError, ValueError):
            previous = {}
        health["last_good_snapshot_id"] = previous.get("last_good_snapshot_id") or previous.get("snapshot_id")
        health["published_content_retained"] = True
        public_health.write_text(json.dumps(health, indent=2) + "\n")
        return False
    # Check every required publication component before touching the prior output.
    if not (candidate / "index.html").is_file() or not (candidate / "results" / "run.json").is_file():
        raise ValueError("Validated candidate is missing report or run manifest")
    shutil.copytree(candidate / "results", root / "data" / "results", dirs_exist_ok=True)
    shutil.copyfile(candidate / "index.html", root / "index.html")
    health["last_good_snapshot_id"] = health["snapshot_id"]
    health["published_content_retained"] = False
    public_health.write_text(json.dumps(health, indent=2) + "\n")
    return True


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    with tempfile.TemporaryDirectory(prefix="oslo-quant-publish-") as tmp:
        candidate = Path(tmp)
        staged_results = candidate / "results"
        shutil.copytree(ROOT / "data" / "results", staged_results, dirs_exist_ok=True)
        env = {**os.environ, "OSLO_QUANT_RESULTS_DIR": str(staged_results)}
        health = {"schema_version": 1, "status": "blocked", "generated_at": stamp(),
                  "snapshot_id": None, "withheld_reasons": []}
        try:
            # Force upstream reads in scheduled publication. Local analysis can reuse TTL caches.
            subprocess.run([sys.executable, "-m", "oslo_quant.cli", "--force-refresh", *argv], env=env, check=False)
            check = subprocess.run([sys.executable, "-m", "oslo_quant.healthcheck", "--json",
                                    str(staged_results / "health.json")], env=env, check=False)
            health = json.loads((staged_results / "health.json").read_text())
            if check.returncode == 0:
                subprocess.run([sys.executable, "-m", "oslo_quant.report", "--output",
                                str(candidate / "index.html")], env=env, check=True)
            return 0 if promote(candidate, health, ROOT) else 1
        except Exception as exc:
            health.update(status="blocked", generated_at=stamp(), withheld_reasons=[str(exc)])
            promote(candidate, health, ROOT)
            print(f"Publication retained after failed attempt: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
