#!/usr/bin/env python3
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals.runner import FORKS_ROOT
from trust_signals.treatments.surface_map import load_surface_map

def live_version(src: Path, surface: str) -> str | None:
    p = src / surface
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    if p.name == "VERSION":
        return text.strip().splitlines()[0].strip()
    m = re.search(r'^\s*(?:__version__|version)\s*[:=]\s*["\']?([^"\'\s]+)', text, re.M)
    return m.group(1) if m else None

def main() -> int:
    bad = 0
    for pid, e in load_surface_map().items():
        src = FORKS_ROOT / "_source" / pid
        if not src.is_dir():
            print(f"{pid}: no pinned clone at {src}")
            bad += 1
            continue
        lv = live_version(src, e.version_surface)
        ok = lv == str(e.version.value)
        print(f"{pid}: map version {e.version.value} | live {e.version_surface} -> {lv} | {'ok' if ok else 'MISMATCH'}")
        bad += 0 if ok else 1
        for ds in e.dependency_sources:
            if not (src / ds.path).exists():
                print(f"  dependency source missing: {ds.path}")
                bad += 1
        if e.citation_file and not (src / e.citation_file).exists():
            print(f"  citation file missing: {e.citation_file}")
            bad += 1
    print("surface map consistent with pinned clones" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0

if __name__ == "__main__":
    raise SystemExit(main())
