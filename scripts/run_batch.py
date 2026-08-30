#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trust_signals.runner import enumerate_trials, is_complete, is_infra_incomplete, run_trials
from _runner_common import load_all, make_docker_executor

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    cfg, runtime_cfg, ledger, image_info, docker_info = load_all()
    specs = enumerate_trials(cfg, a.model)
    done = sum(1 for s in specs if is_complete(s))
    infra = sum(1 for s in specs if is_infra_incomplete(s))
    local_ids = {m["id"] for m in cfg["models"] if m["arm"] == "local"}
    print(f"registered trials: {len(specs)}; complete: {done}; infrastructure-incomplete: {infra}; "
          f"remaining: {len(specs) - done - infra}; hosted spend so far: {ledger.total_hosted_usd(local_ids):.2f} USD")
    if a.status:
        return 0
    try:
        counts = run_trials(cfg, runtime_cfg, specs, ledger, make_docker_executor,
                            image_info=image_info, docker_info=docker_info)
    except KeyboardInterrupt:
        print("\ninterrupted; rerun the same command to resume")
        return 130
    print(counts)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
