#!/usr/bin/env python3
from __future__ import annotations
import csv
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals import config, paths  # noqa: E402

BRANCHES = ("main", "master", "develop", "dev")
MARKER_FILES = ("README.md", "README.rst", "CMakeLists.txt", "pyproject.toml",
                "setup.py", "Makefile", "Cargo.toml")

def exists(repo: str, branch: str, fname: str) -> bool:
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{fname}"
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "panel-screen-probe"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False

def main() -> int:
    cfg = config.load_config(paths.CONFIG_PATH)
    config.verify_corpus_hash(cfg, paths.CORPUS_PATH)
    stratum = cfg["draw"]["stratum_filter"]
    with open(paths.CORPUS_PATH, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["stratum"] == stratum]
    probed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = []
    for r in rows:
        repo = r["github_repo"]
        branch_used = None
        for branch in BRANCHES:
            if any(exists(repo, branch, f) for f in MARKER_FILES):
                branch_used = branch
                break
        if branch_used is None:
            evidence.append({"project_id": r["project_id"], "github_repo": repo,
                             "domain": r["domain"], "branch": "", "pyproject_toml": "",
                             "setup_py": "", "probed_at": probed_at,
                             "note": "branch unresolved; manual check required"})
            print(f"  {r['project_id']}: UNRESOLVED")
            continue
        py = exists(repo, branch_used, "pyproject.toml")
        sp = exists(repo, branch_used, "setup.py")
        evidence.append({"project_id": r["project_id"], "github_repo": repo,
                         "domain": r["domain"], "branch": branch_used,
                         "pyproject_toml": str(py), "setup_py": str(sp),
                         "probed_at": probed_at, "note": ""})
        time.sleep(0.1)

    with open(paths.S2_EVIDENCE_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["project_id", "github_repo", "domain",
                                           "branch", "pyproject_toml", "setup_py",
                                           "probed_at", "note"])
        w.writeheader()
        w.writerows(evidence)

    n_pass = sum(1 for e in evidence
                 if e["pyproject_toml"] == "True" or e["setup_py"] == "True")
    print(f"Probed {len(evidence)} projects at {probed_at}; "
          f"{n_pass} pass S2 (checkout-installable). "
          f"Evidence written to {paths.S2_EVIDENCE_PATH}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
