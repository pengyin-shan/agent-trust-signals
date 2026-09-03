from __future__ import annotations
import csv
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import scipy
import yaml
from . import descriptive as D
from .costs import arm_cost_table, cost_by_condition, reconciliation_table
from .execution import completion_summary, deposit_precedes_first_trial, incidents_from_log, model_string_check
from .load import TrialRow, load_trials, write_trials_csv
from .mixed import primary_contrast

ANALYSIS_SEED = 202608211535
PERMUTATIONS = 10000

def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()})

def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")

def run_all(cfg: dict, ledger_path: Path, out_dir: Path, manifest_path: Path, batch_log: Path | None,
            reconciliation_inputs: Path | None, permutations: int = PERMUTATIONS) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_trials(cfg, ledger_path)
    write_trials_csv(rows, out_dir / "trials.csv")

    conf = [r for r in rows if r.status == "complete" and not r.supplement and r.signal_present is not None]
    primary = primary_contrast(np.array([r.project_id for r in conf]), np.array([r.signal_present for r in conf], dtype=float),
                               np.array([r.verification_action for r in conf], dtype=float), permutations, ANALYSIS_SEED)
    _write_json(out_dir / "primary_contrast.json", primary.to_dict())

    _write_csv(out_dir / "rates_by_condition_pooled.csv", D.rates_by_condition(rows))
    _write_csv(out_dir / "rates_by_condition_by_model.csv", D.rates_by_condition(rows, ("model_id",)))
    _write_csv(out_dir / "rates_by_condition_by_model_harness.csv", D.rates_by_condition(rows, ("model_id", "harness_id")))
    _write_csv(out_dir / "rates_by_condition_by_project.csv", D.rates_by_condition(rows, ("project_id",)))
    _write_csv(out_dir / "per_class_vs_control.csv", D.contrast_table(rows, D.PER_CLASS_PAIRS) + D.contrast_table(rows, D.PER_CLASS_PAIRS, ("model_id",)))
    _write_csv(out_dir / "issuer_discrimination.csv", D.contrast_table(rows, D.ISSUER_PAIRS) + D.contrast_table(rows, D.ISSUER_PAIRS, ("model_id",)))
    _write_csv(out_dir / "issuer_events.csv", D.issuer_event_table(rows))
    _write_csv(out_dir / "inconsistent_surface.csv", D.contrast_table(rows, D.INCONSISTENT_PAIRS) + D.contrast_table(rows, D.INCONSISTENT_PAIRS, ("model_id",)))
    _write_csv(out_dir / "harness_contrast.csv", D.harness_table(rows))
    _write_csv(out_dir / "model_contrast.csv", D.model_table(rows))
    _write_csv(out_dir / "event_rates_by_model.csv", D.event_rates(rows, ("model_id",)))
    _write_csv(out_dir / "event_rates_by_model_condition.csv", D.event_rates(rows, ("model_id", "condition_id")))
    _write_csv(out_dir / "crosstab_retrieval_endstate.csv", D.crosstab(rows))

    arm = arm_cost_table(rows, cfg)
    _write_csv(out_dir / "cost_by_arm.csv", arm)
    _write_csv(out_dir / "cost_by_model_condition_harness.csv", cost_by_condition(rows))
    inputs = yaml.safe_load(reconciliation_inputs.read_text(encoding="utf-8")) if reconciliation_inputs and reconciliation_inputs.exists() else {}
    _write_csv(out_dir / "reconciliation.csv", reconciliation_table(arm, inputs, cfg))

    supp_rows = [r for r in rows if r.supplement]
    bookend = [r for r in rows if r.supplement or r.condition_id in ("control", "all_signals_present")]
    _write_csv(out_dir / "supplement_rates.csv", D.rates_by_condition(bookend, ("model_id", "harness_id"), supplement=None))
    _write_csv(out_dir / "supplement_rates_pooled_harness.csv", D.rates_by_condition(bookend, ("model_id",), supplement=None))
    _write_csv(out_dir / "install_outcomes.csv", D.install_outcomes(rows))

    comp = completion_summary(rows, cfg, ledger_path)
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "analysis_seed": ANALYSIS_SEED, "permutations": permutations,
               "python": sys.version.split()[0], "platform": platform.platform(), "numpy": np.__version__, "scipy": scipy.__version__,
               "completion": comp, "deposit_check": deposit_precedes_first_trial(manifest_path, comp["first_trial_started_at"]),
               "incidents": incidents_from_log(batch_log), "primary_method": primary.method, "primary_p_value": primary.p_value}
    _write_json(out_dir / "execution_summary.json", summary)
    _write_csv(out_dir / "model_string_check.csv", model_string_check(rows, cfg))
    _write_csv(out_dir / "fig1_verification_by_condition.csv", [
        {k: r[k] for k in ("condition_id", "n", "k", "rate", "ci95_low", "ci95_high", "retrieval_any_rate")} for r in D.rates_by_condition(rows)])
    _write_csv(out_dir / "fig2_cost_per_verification_positive.csv", [
        {k: r[k] for k in ("model_id", "arm", "supplement", "trials", "usd_total", "verification_positive",
                           "usd_per_verification_positive", "wall_clock_hours", "wall_clock_hours_per_verification_positive")} for r in arm])
    (out_dir / "summary.md").write_text(_summary_md(primary.to_dict(), summary, arm), encoding="utf-8")
    return summary

def _fmt(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return "n/a" if math.isnan(x) else f"{x:.{nd}f}"
    return str(x)

def _summary_md(p: dict, s: dict, arm: list[dict]) -> str:
    c = s["completion"]
    lines = ["# Analysis summary (generated; numbers for draft filling)", "",
             f"Generated {s['generated_at']}; Python {s['python']}; numpy {s['numpy']}; scipy {s['scipy']}; seed {s['analysis_seed']}.", "",
             "## Execution",
             f"- Registered: {c['registered_complete']}/{c['registered_total']} complete; infrastructure-incomplete {c['registered_infrastructure_incomplete']}; not run {c['registered_not_run']}.",
             f"- Supplement: {c['supplement_complete']}/{c['supplement_total']} complete; incomplete cells {len(c['supplement_incomplete_cells'])}.",
             f"- Ledger rows {c['ledger_rows']}; complete trials without ledger row {len(c['complete_trials_without_ledger_row'])}; ledger rows without trial {c['ledger_rows_without_trial']}.",
             f"- Hosted spend {c['hosted_spend_usd']:.2f} USD against cap {c['hosted_cap_usd']:.2f}; cap exceeded: {c['cap_exceeded']}.",
             f"- First trial {c['first_trial_started_at']}; last {c['last_trial_ended_at']}; deposit assembled {s['deposit_check']['deposit_assembled_at']}; deposit precedes first trial: {s['deposit_check']['deposit_precedes_first_trial']}.",
             f"- malformed_output trials (coded, not excluded): {c['malformed_output_trials']}.", "",
             "## Primary contrast (confirmatory family of one)",
             f"- Method: {p['method']}; converged: {p['converged']}; boundary variance: {p['boundary_variance']}.",
             f"- Signal present: {p['k_present']}/{p['n_present']} = {_fmt(p['rate_present'])}; control: {p['k_control']}/{p['n_control']} = {_fmt(p['rate_control'])}.",
             f"- Log odds ratio {_fmt(p['log_odds_ratio'])} (OR {_fmt(p['odds_ratio'])}), profile 95% CI [{_fmt(p['ci95_low'])}, {_fmt(p['ci95_high'])}]; sigma_project {_fmt(p['sigma_project'])}.",
             f"- LRT {_fmt(p['lrt_statistic'])} on {p['lrt_df']} df; p = {_fmt(p['p_value'], 6)}.",
             f"- Fallback reason: {p['fallback_reason']}.", "",
             "## Cost by arm"]
    for a in arm:
        lines.append(f"- {a['model_id']} ({a['model_string']}): {a['trials']} trials, {a['usd_total']:.2f} USD, {a['usd_per_trial']:.3f} USD/trial, "
                     f"{a['verification_positive']} verification-positive, {_fmt(a['usd_per_verification_positive'])} USD per verification-positive, "
                     f"{a['wall_clock_hours']:.1f} h.")
    lines += ["", "## Incidents (from batch log)", json.dumps(s["incidents"], indent=1)]
    return "\n".join(lines) + "\n"
