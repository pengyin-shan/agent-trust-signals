from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from trust_signals.config import load_config
from trust_signals.paths import CONFIG_PATH
from analysis.coding import build_coding_sheet, write_sheet, read_sheet, validate_codes, draw_recode_sample, draw_audit_sample, kappa_report
from analysis.load import load_trials

STUDY_SEED = 202608211535

def main() -> int:
    ap = argparse.ArgumentParser(description="Rubric coding support: build the sheet, validate codes, draw the blind re-code sample, report kappa.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--runs", default=str(ROOT / "runs"))
    b.add_argument("--out", default=str(ROOT / "analysis" / "coding" / "coding_sheet.csv"))
    v = sub.add_parser("validate")
    v.add_argument("sheet")
    s = sub.add_parser("sample")
    s.add_argument("sheet")
    s.add_argument("--fraction", type=float, default=0.15)
    s.add_argument("--out", default=str(ROOT / "analysis" / "coding" / "recode_sample_blind.csv"))
    a = sub.add_parser("audit")
    a.add_argument("sheet")
    a.add_argument("--fraction", type=float, default=0.10)
    a.add_argument("--out", default=str(ROOT / "analysis" / "coding" / "audit_sample.csv"))
    k = sub.add_parser("kappa")
    k.add_argument("sheet")
    k.add_argument("recode")
    k.add_argument("--out", default=str(ROOT / "analysis" / "coding" / "kappa.csv"))
    args = ap.parse_args()

    if args.cmd == "build":
        import trust_signals.runner.trials as trials
        trials.RUNS_ROOT = Path(args.runs)
        cfg = load_config(CONFIG_PATH)
        rows = load_trials(cfg, Path(args.runs) / "cost_ledger.csv")
        sheet = build_coding_sheet(rows, Path(args.runs))
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        write_sheet(Path(args.out), sheet)
        print(f"{len(sheet)} rows written to {args.out}")
    elif args.cmd == "validate":
        problems = validate_codes(read_sheet(Path(args.sheet)))
        print("\n".join(problems) if problems else "no problems")
        return 1 if problems else 0
    elif args.cmd == "sample":
        rows = read_sheet(Path(args.sheet))
        problems = validate_codes(rows)
        if problems:
            print("\n".join(problems))
            return 1
        blind = draw_recode_sample(rows, args.fraction, STUDY_SEED)
        write_sheet(Path(args.out), blind)
        print(f"{len(blind)} blind rows written to {args.out}")
    elif args.cmd == "audit":
        sample = draw_audit_sample(read_sheet(Path(args.sheet)), args.fraction, STUDY_SEED)
        write_sheet(Path(args.out), sample)
        print(f"{len(sample)} unflagged proceeded rows written to {args.out} for full-read audit")
    elif args.cmd == "kappa":
        rep = kappa_report(read_sheet(Path(args.sheet)), read_sheet(Path(args.recode)))
        write_sheet(Path(args.out), rep)
        for r in rep:
            print(f"{r['label']}: n={r['n_pairs']} agreement={r['agreement']:.3f} kappa={r['kappa']:.3f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
