#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from trust_signals import __version__, conditions, config, draw, paths
from trust_signals.screen import load_s2_evidence, load_s5_judgments

OUTPUTS = [
    paths.PREREGISTRATION_JSON,
    paths.PANEL_DRAW_CSV,
    paths.CANDIDATE_RANKING_CSV,
    paths.SCREENING_LOG_CSV,
]

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(paths.CONFIG_PATH))
    ap.add_argument("--force", action="store_true", help="allow overwriting existing outputs")
    args = ap.parse_args()
    cfg = config.load_config(args.config)
    config.verify_corpus_hash(cfg, paths.CORPUS_PATH)
    seed = config.require_seed(cfg)
    cfg_ids = [c["id"] for c in cfg["conditions"]]
    if cfg_ids != conditions.condition_ids():
        print("ERROR: condition list in configuration disagrees with conditions.py:", file=sys.stderr)
        print(f"  config:        {cfg_ids}", file=sys.stderr)
        print(f"  conditions.py: {conditions.condition_ids()}", file=sys.stderr)
        return 1

    existing = [p for p in OUTPUTS if p.exists()]
    if existing and not args.force:
        print("ERROR: outputs already exist; a frozen draw is not re-run.", file=sys.stderr)
        for p in existing:
            print(f"  {p}", file=sys.stderr)
        print("Use --force only if you are deliberately re-drawing BEFORE the freeze.", file=sys.stderr)
        return 1

    corpus = draw.load_corpus(paths.CORPUS_PATH)
    evidence = load_s2_evidence(paths.S2_EVIDENCE_PATH)
    judgments = load_s5_judgments(paths.S5_JUDGMENTS_PATH)

    result = draw.run_draw(cfg, corpus, evidence, judgments, seed)

    if result.pending_s5:
        print("S5 judgments pending; nothing accepted beyond the first pending rank.")
        print("Record each judgment in data/s5_judgments.csv "
              "(columns: project_id,decision,note,recorded_at; decision pass|fail; "
              "recorded_at ISO 8601 UTC), then re-run this script.\n")
        with open(paths.PENDING_S5_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["project_id", "stratum", "rank"])
            w.writeheader()
            w.writerows(result.pending_s5)
        for p in result.pending_s5:
            print(f"  rank {p['rank']:>2}  [{p['stratum']}]  {p['project_id']}")
        print(f"\nPending list written to {paths.PENDING_S5_CSV}")
        return 2

    if result.exhausted:
        print(f"ERROR: acceptance window exhausted before quota in: {result.exhausted}",
              file=sys.stderr)
        print("This is a protocol event. Do not widen the window silently; record the",
              file=sys.stderr)
        print("event and the decision in PROTOCOL.md's deviations section.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    paths.OUT_DIR.mkdir(exist_ok=True)

    prereg = {
        "written_at": now,
        "package_version": __version__,
        "python_version": platform.python_version(),
        "seed": seed,
        "resolved_config": cfg,
        "condition_count": conditions.condition_count(),
        "eligible_frame": result.eligible_frame,
        "accepted_project_ids": [r["project_id"] for r in result.accepted],
    }
    with open(paths.PREREGISTRATION_JSON, "w", encoding="utf-8") as fh:
        json.dump(prereg, fh, indent=2, sort_keys=True)

    with open(paths.PANEL_DRAW_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result.accepted[0].keys()) + ["accepted_at"])
        w.writeheader()
        for row in result.accepted:
            w.writerow({**row, "accepted_at": now})

    with open(paths.CANDIDATE_RANKING_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stratum", "rank", "project_id", "in_window"])
        for sub, ranking in result.ranking.items():
            for rank, pid in enumerate(ranking, start=1):
                w.writerow([sub, rank, pid, rank <= cfg["draw"]["oversample"]])

    with open(paths.SCREENING_LOG_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["project_id", "stratum", "stage", "rank", "rule_id",
                        "passed", "pending", "reason"],
        )
        w.writeheader()
        for entry in result.screening_log:
            w.writerow(asdict(entry))

    print(f"Draw complete under seed {seed}.")
    for sub in cfg["draw"]["strata"]:
        members = [r["project_id"] for r in result.accepted if r["domain"] == sub]
        print(f"  {sub}: {', '.join(members)}")
    print(f"Eligible frame sizes: "
          + ", ".join(f"{k}={len(v)}" for k, v in result.eligible_frame.items()))
    print("Artifacts written:")
    for p in OUTPUTS:
        print(f"  {p}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
