#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals import conditions, config, paths  # noqa: E402

FAILURES: list[str] = []

def fail(msg: str) -> None:
    FAILURES.append(msg)

def main() -> int:
    cfg = config.load_config(paths.CONFIG_PATH)

    pending = config.freeze_pending_strings(cfg)
    if pending:
        fail(f"FREEZE-PENDING values remain in configuration: {pending}")

    try:
        config.verify_corpus_hash(cfg, paths.CORPUS_PATH)
    except config.ConfigError as exc:
        fail(str(exc))

    outputs = [paths.PREREGISTRATION_JSON, paths.PANEL_DRAW_CSV,
               paths.CANDIDATE_RANKING_CSV, paths.SCREENING_LOG_CSV]
    missing = [p for p in outputs if not p.exists()]
    if missing:
        fail(f"missing out/ artifacts: {[str(p) for p in missing]}")
        return report()

    with open(paths.PANEL_DRAW_CSV, newline="", encoding="utf-8") as fh:
        panel = list(csv.DictReader(fh))
    if len(panel) != cfg["draw"]["panel_size"]:
        fail(f"panel has {len(panel)} rows, configuration says {cfg['draw']['panel_size']}")
    for sub, quota in cfg["draw"]["per_stratum"].items():
        n = sum(1 for r in panel if r["domain"] == sub)
        if n != quota:
            fail(f"stratum {sub}: {n} accepted, configuration says {quota}")

    with open(paths.SCREENING_LOG_CSV, newline="", encoding="utf-8") as fh:
        log = list(csv.DictReader(fh))
    accepted_ids = {r["project_id"] for r in panel}
    seen_rules: dict[str, set[str]] = {pid: set() for pid in accepted_ids}
    for entry in log:
        pid = entry["project_id"]
        if pid in accepted_ids:
            if entry["passed"] != "True":
                fail(f"accepted project {pid} has a non-passing screening entry: "
                     f"{entry['rule_id']} ({entry['reason']})")
            seen_rules[pid].add(entry["rule_id"])
    for pid, rules in seen_rules.items():
        if rules != {"S1", "S2", "S3", "S4", "S5"}:
            fail(f"accepted project {pid} missing screening entries for "
                 f"{sorted({'S1','S2','S3','S4','S5'} - rules)}")

    n_code = conditions.condition_count()
    n_cfg = len(cfg["conditions"])
    if n_code != n_cfg:
        fail(f"condition count: conditions.py says {n_code}, configuration says {n_cfg}")
    if not paths.PROTOCOL_DOC.exists():
        fail(f"missing protocol document: {paths.PROTOCOL_DOC}")
        return report()
    doc_text = paths.PROTOCOL_DOC.read_text(encoding="utf-8")
    m = re.search(r"^Condition count:\s*(\d+)", doc_text, re.MULTILINE)
    if not m:
        fail("PROTOCOL.md lacks the required 'Condition count: N' line")
    elif int(m.group(1)) != n_code:
        fail(f"PROTOCOL.md states condition count {m.group(1)}, conditions.py says {n_code}")

    with open(paths.PREREGISTRATION_JSON, encoding="utf-8") as fh:
        prereg = json.load(fh)
    if prereg.get("seed") != cfg["draw"]["seed"]:
        fail(f"preregistration seed {prereg.get('seed')} != configuration seed "
             f"{cfg['draw']['seed']}; the deposited record must match the executed draw")

    frozen_at = cfg["frozen_at"]
    if isinstance(frozen_at, str) and config.FREEZE_PENDING not in frozen_at:
        try:
            frozen_dt = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
            if frozen_dt.tzinfo is None:
                frozen_dt = frozen_dt.replace(tzinfo=timezone.utc)
            for p in outputs:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                if mtime > frozen_dt:
                    fail(f"{p.name} modified at {mtime.isoformat()}, after frozen_at "
                         f"{frozen_dt.isoformat()}; set frozen_at AFTER the final draw run")
        except ValueError:
            fail(f"frozen_at is not parseable ISO 8601: {frozen_at!r}")

    for doc in (paths.PROTOCOL_DOC, paths.CODING_RUBRIC):
        if not doc.exists():
            fail(f"missing protocol document: {doc}")
        elif config.FREEZE_PENDING in doc.read_text(encoding="utf-8"):
            fail(f"{doc.name} still contains a FREEZE-PENDING marker")

    return report()

def report() -> int:
    if FAILURES:
        print("FREEZE VERIFICATION FAILED:")
        for msg in FAILURES:
            print(f"  - {msg}")
        return 1
    print("Freeze verification passed: configuration, corpus, panel, screening log, "
          "condition counts, seed, timestamps, and protocol documents are consistent.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
