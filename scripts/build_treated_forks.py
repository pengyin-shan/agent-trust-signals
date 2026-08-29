#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals.conditions import condition_ids  # noqa: E402
from trust_signals.paths import PANEL_DRAW_CSV  # noqa: E402
from trust_signals.treatments import TreatmentContext, TreatmentError, check_registry, treatment_for  # noqa: E402
from trust_signals.treatments.keys import load_study_keys  # noqa: E402
from trust_signals.treatments.surface_map import load_surface_map  # noqa: E402

NEEDS_KEYS = {"signed_release_present", "signed_release_issuer_mismatch", "attestation_present",
              "attestation_issuer_mismatch", "all_signals_present"}

def panel() -> list[dict]:
    with open(PANEL_DRAW_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise TreatmentError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()

def ensure_source(row: dict, entry, source_root: Path, pin: str | None) -> tuple[Path, str]:
    src = source_root / row["project_id"]
    if not src.exists():
        source_root.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{row['github_repo']}.git"
        print(f"cloning {url} -> {src}")
        git("clone", "--quiet", "--branch", entry.default_branch, url, str(src))
    if pin:
        git("fetch", "--quiet", "origin", pin, cwd=src)
        git("checkout", "--quiet", pin, cwd=src)
    return src, git("rev-parse", "HEAD", cwd=src)

def build_one(src: Path, commit: str, entry, condition: str, out_root: Path, keys) -> Path:
    dest = out_root / entry.project_id / condition
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)
    ctx = TreatmentContext(project=entry, source_commit=commit, keys=keys)
    manifest = treatment_for(condition).apply(dest, ctx)
    manifest.write(out_root / entry.project_id / f"{condition}.manifest.json")
    return dest

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", action="append", help="project_id from out/panel_draw.csv (repeatable)")
    ap.add_argument("--condition", action="append", help="frozen condition id (repeatable)")
    ap.add_argument("--all", action="store_true", help="every panel project and every condition")
    ap.add_argument("--out", required=True, type=Path, help="output root")
    ap.add_argument("--source-dir", type=Path, help="directory holding existing clones named by project_id")
    ap.add_argument("--pin", action="append", default=[], help="project_id=<commit> to check out")
    a = ap.parse_args()

    check_registry()
    rows = panel()
    by_id = {r["project_id"]: r for r in rows}
    projects = list(by_id) if a.all or not a.project else a.project
    conditions = condition_ids() if a.all or not a.condition else a.condition
    unknown = [c for c in conditions if c not in condition_ids()]
    if unknown:
        print(f"unknown condition(s): {unknown}; frozen ids: {condition_ids()}", file=sys.stderr)
        return 2
    pins = dict(p.split("=", 1) for p in a.pin)
    surface = load_surface_map()
    keys = load_study_keys() if any(c in NEEDS_KEYS for c in conditions) else None
    source_root = a.source_dir or (a.out / "_source")

    for pid in projects:
        if pid not in by_id:
            print(f"{pid} is not in the frozen panel", file=sys.stderr)
            return 2
        if pid not in surface:
            print(f"{pid} has no surface map entry; refusing", file=sys.stderr)
            return 2
        entry = surface[pid]
        src, commit = ensure_source(by_id[pid], entry, source_root, pins.get(pid))
        for cond in conditions:
            try:
                dest = build_one(src, commit, entry, cond, a.out, keys)
            except TreatmentError as e:
                print(f"{pid}/{cond}: FAILED: {e}", file=sys.stderr)
                return 1
            print(f"{pid}/{cond}: built at {dest} (source {commit[:12]})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
