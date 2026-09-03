from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from trust_signals.config import load_config
from trust_signals.paths import CONFIG_PATH, FREEZE_MANIFEST_JSON
from analysis.report import run_all, PERMUTATIONS

def main() -> int:
    ap = argparse.ArgumentParser(description="Run the pre-registered analysis against runs/ and write analysis/out/.")
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--out", default=str(ROOT / "analysis" / "out"))
    ap.add_argument("--ledger", default=None, help="defaults to <runs>/cost_ledger.csv")
    ap.add_argument("--batch-log", default=None, help="defaults to <runs>/hosted_batch.log")
    ap.add_argument("--reconciliation-inputs", default=str(ROOT / "analysis" / "reconciliation_inputs.yaml"))
    ap.add_argument("--permutations", type=int, default=PERMUTATIONS)
    args = ap.parse_args()
    runs = Path(args.runs)
    import trust_signals.runner.trials as trials
    trials.RUNS_ROOT = runs
    ledger = Path(args.ledger) if args.ledger else runs / "cost_ledger.csv"
    log = Path(args.batch_log) if args.batch_log else runs / "hosted_batch.log"
    cfg = load_config(CONFIG_PATH)
    summary = run_all(cfg, ledger, Path(args.out), FREEZE_MANIFEST_JSON, log if log.exists() else None,
                      Path(args.reconciliation_inputs), args.permutations)
    c = summary["completion"]
    print(f"registered {c['registered_complete']}/{c['registered_total']}; supplement {c['supplement_complete']}/{c['supplement_total']}; "
          f"primary method {summary['primary_method']}; outputs in {args.out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())