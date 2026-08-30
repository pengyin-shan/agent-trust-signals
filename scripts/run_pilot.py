#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trust_signals.harness import LoopSettings
from trust_signals.runner import RUNS_ROOT, enumerate_trials, run_trials
from trust_signals.runner import trials as trials_mod
from _runner_common import load_all, make_docker_executor

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="local_openweight")
    ap.add_argument("--project", action="append")
    ap.add_argument("--condition", action="append")
    ap.add_argument("--harness", action="append")
    ap.add_argument("--n", type=int, default=1, help="trials per cell (capped at the registered count)")
    ap.add_argument("--scratch", action="store_true", help="write under runs/_pilot/ (not counted)")
    ap.add_argument("--max-steps", type=int, default=30)
    a = ap.parse_args()

    cfg, runtime_cfg, ledger, image_info, docker_info = load_all()
    if a.scratch:
        trials_mod.RUNS_ROOT = RUNS_ROOT / "_pilot"
        from trust_signals.runner import CostLedger
        ledger = CostLedger(cfg, trials_mod.RUNS_ROOT / "cost_ledger.csv")
    projects = a.project or ["qrisp", "faasm"]
    conditions = a.condition or ["control", "all_signals_present"]
    harnesses = a.harness or ["autonomous"]
    specs = enumerate_trials(cfg, [a.model], projects, conditions, harnesses, max_per_cell=a.n)
    print(f"{len(specs)} pilot trial(s) on {a.model}; artifacts under {trials_mod.RUNS_ROOT}")
    counts = run_trials(cfg, runtime_cfg, specs, ledger, make_docker_executor,
                        LoopSettings(max_steps=a.max_steps), image_info=image_info, docker_info=docker_info)
    print(counts)
    return 0 if counts["infrastructure_incomplete"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
