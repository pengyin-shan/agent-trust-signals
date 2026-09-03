from __future__ import annotations
import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from trust_signals.runner.trials import TrialSpec, enumerate_trials, is_complete, is_infra_incomplete, RUNS_ROOT, model_entry, is_supplement_model

EVENT_NAMES = ("sbom_opened", "release_signature_fetched", "release_signature_verified", "attestation_fetched",
               "attestation_verified", "channel_declaration_opened", "metadata_surface_opened")
PRESENT_CONDITIONS = ("sbom_present", "signed_release_present", "signed_release_issuer_mismatch", "attestation_present",
                      "attestation_issuer_mismatch", "channel_declaration_present", "all_signals_present")
CLASS_CONDITIONS = ("sbom_present", "signed_release_present", "attestation_present", "channel_declaration_present",
                    "all_signals_present")
CONDITION_ORDER = ("control",) + CLASS_CONDITIONS[:4] + ("signed_release_issuer_mismatch", "attestation_issuer_mismatch",
                                                          "all_signals_present", "inconsistent_surface")

@dataclass
class TrialRow:
    model_id: str
    arm: str
    supplement: bool
    project_id: str
    condition_id: str
    harness_id: str
    trial_index: int
    status: str
    signal_present: bool | None
    verification_action: bool | None
    machine_end_state: str | None
    termination: str | None
    install_executed: bool | None
    install_exit_code: int | None
    assistant_outcome: str | None = None
    events_before_decision: list[str] = field(default_factory=list)
    events_any: list[str] = field(default_factory=list)
    n_steps: int | None = None
    approval_requests: int | None = None
    approvals_granted: int | None = None
    model_strings_reported: list[str] = field(default_factory=list)
    api_calls: int | None = None
    input_tokens_uncached: int | None = None
    input_tokens_cache_write: int | None = None
    input_tokens_cache_read: int | None = None
    output_tokens: int | None = None
    wall_clock_seconds: float | None = None
    usd_cost_computed: float | None = None
    ledger_matched: bool = False

    @property
    def cell(self) -> str:
        return f"{self.model_id}/{self.project_id}/{self.condition_id}/{self.harness_id}"

    @property
    def label(self) -> str:
        return f"{self.cell}/trial_{self.trial_index:02d}"

    def to_flat(self) -> dict:
        d = asdict(self)
        d["events_before_decision"] = ";".join(self.events_before_decision)
        d["events_any"] = ";".join(self.events_any)
        d["model_strings_reported"] = ";".join(sorted(set(self.model_strings_reported)))
        for e in EVENT_NAMES:
            d[f"ev_before_{e}"] = e in self.events_before_decision
            d[f"ev_any_{e}"] = e in self.events_any
        d["retrieval_any"] = bool(self.events_any)
        return d

def arm_of(cfg: dict, model_id: str) -> str:
    if is_supplement_model(cfg, model_id):
        return "frontier"
    return model_entry(cfg, model_id)["arm"]

def signal_present(condition_id: str) -> bool | None:
    if condition_id == "control":
        return False
    if condition_id in PRESENT_CONDITIONS:
        return True
    return None

def read_ledger(path: Path) -> dict[tuple, dict]:
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["model_id"], r["project_id"], r["condition_id"], r["harness_id"], int(r["trial_index"]))
            if key in out:
                raise ValueError(f"duplicate ledger row for {key}")
            out[key] = r
    return out

def _read_trial(spec: TrialSpec, cfg: dict) -> TrialRow:
    row = TrialRow(spec.model_id, arm_of(cfg, spec.model_id), spec.supplement, spec.project_id, spec.condition_id,
                   spec.harness_id, spec.trial_index, "not_run", signal_present(spec.condition_id), None, None, None,
                   None, None)
    if is_infra_incomplete(spec):
        row.status = "infrastructure_incomplete"
        return row
    if not is_complete(spec):
        return row
    d = json.loads((spec.dir / "derived.json").read_text(encoding="utf-8"))
    t = json.loads((spec.dir / "transcript.json").read_text(encoding="utf-8"))
    row.status = "complete"
    row.verification_action = bool(d["verification_action"])
    row.machine_end_state = d["machine_end_state"]
    row.termination = d["termination"]
    row.install_executed = bool(d["install_executed"])
    row.install_exit_code = d["install_exit_code"]
    row.assistant_outcome = d.get("assistant_outcome")
    row.events_before_decision = sorted(set(d["events_before_decision"]))
    row.events_any = sorted({e["event"] for e in d["events"]})
    steps = t.get("steps", [])
    row.n_steps = len(steps)
    row.approval_requests = sum(1 for s in steps if s.get("approval_requested"))
    row.approvals_granted = sum(1 for s in steps if s.get("approval_granted"))
    row.model_strings_reported = list(t.get("model_strings_reported", []))
    row.api_calls = t.get("api_calls")
    row.wall_clock_seconds = t.get("wall_clock_seconds")
    return row

def load_trials(cfg: dict, ledger_path: Path) -> list[TrialRow]:
    ledger = read_ledger(ledger_path)
    model_ids = [m["id"] for m in cfg["models"]] + [m["id"] for m in cfg["frontier_supplement"]["models"]]
    rows = []
    for spec in enumerate_trials(cfg, model_ids):
        row = _read_trial(spec, cfg)
        l = ledger.get((row.model_id, row.project_id, row.condition_id, row.harness_id, row.trial_index))
        if l is not None:
            row.ledger_matched = True
            row.api_calls = int(l["api_calls"])
            row.wall_clock_seconds = float(l["wall_clock_seconds"])
            row.usd_cost_computed = float(l["usd_cost_computed"])
            for k in ("input_tokens_uncached", "input_tokens_cache_write", "input_tokens_cache_read", "output_tokens"):
                setattr(row, k, int(l[k]))
        rows.append(row)
    return rows

def write_trials_csv(rows: list[TrialRow], path: Path) -> None:
    flat = [r.to_flat() for r in rows]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flat[0].keys()))
        w.writeheader()
        w.writerows(flat)

def runs_root() -> Path:
    return RUNS_ROOT
