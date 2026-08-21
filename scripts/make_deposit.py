#!/usr/bin/env python3
from __future__ import annotations
import json
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals import __version__, config, paths  # noqa: E402

BUNDLE_FILES = [
    paths.PROTOCOL_DOC,
    paths.CONFIG_PATH,
    paths.CODING_RUBRIC,
    paths.PREREGISTRATION_JSON,
    paths.PANEL_DRAW_CSV,
    paths.CANDIDATE_RANKING_CSV,
    paths.SCREENING_LOG_CSV,
    paths.CORPUS_PATH,
    paths.S2_EVIDENCE_PATH,
    paths.S5_JUDGMENTS_PATH,
]

def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "NOT-A-GIT-CHECKOUT"

def main() -> int:
    check = subprocess.run(
        [sys.executable, str(paths.ROOT / "scripts" / "verify_freeze.py")]
    )
    if check.returncode != 0:
        print("Refusing to bundle: verify_freeze.py failed.", file=sys.stderr)
        return 1

    missing = [p for p in BUNDLE_FILES if not p.exists()]
    if missing:
        print(f"Missing bundle files: {[str(p) for p in missing]}", file=sys.stderr)
        return 1

    manifest = {
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__,
        "repository_commit": git_commit(),
        "files": {
            str(p.relative_to(paths.ROOT)): config.sha256_of(p) for p in BUNDLE_FILES
        },
    }
    with open(paths.FREEZE_MANIFEST_JSON, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    with tarfile.open(paths.DEPOSIT_ARCHIVE, "w:gz") as tar:
        for p in BUNDLE_FILES + [paths.FREEZE_MANIFEST_JSON]:
            tar.add(p, arcname=f"deposit/{p.relative_to(paths.ROOT)}")

    print(f"Manifest: {paths.FREEZE_MANIFEST_JSON}")
    print(f"Bundle:   {paths.DEPOSIT_ARCHIVE}")
    print(f"Commit:   {manifest['repository_commit']}")
    if manifest["repository_commit"] == "NOT-A-GIT-CHECKOUT":
        print("WARNING: not a git checkout; commit not recorded. Initialize git, commit, "
              "and re-run so the manifest binds the deposit to a commit.")
    print("Next: create the Zenodo record (restricted access), attach the bundle, "
          "mint the DOI, then tag the repository at this commit.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
