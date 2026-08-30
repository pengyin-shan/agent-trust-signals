from __future__ import annotations
import csv
import json
import shutil
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable
from ..harness import LoopSettings, Transcript, derive, prompts, run_loop
from ..harness.executor import Executor
from ..paths import PANEL_DRAW_CSV, ROOT
from ..providers import ProviderTransportError, build_adapter
from ..treatments.base import utc_now
from ..treatments.surface_map import load_surface_map
from .environment import host_descriptor, image_tools, ollama_descriptor
from .ledger import CostLedger

RUNS_ROOT = ROOT / "runs"
FORKS_ROOT = ROOT / "forks"

class InfrastructureError(RuntimeError):
    pass

@dataclass(frozen=True)
class TrialSpec:
    model_id: str
    project_id: str
    condition_id: str
    harness_id: str
    trial_index: int
    supplement: bool = False

    @property
    def dir(self) -> Path:
        return RUNS_ROOT / self.model_id / self.project_id / self.condition_id / self.harness_id / f"trial_{self.trial_index:02d}"

    @property
    def label(self) -> str:
        return f"{self.model_id}/{self.project_id}/{self.condition_id}/{self.harness_id}/trial_{self.trial_index:02d}"


def panel_ids() -> list[str]:
    with open(PANEL_DRAW_CSV, newline="", encoding="utf-8") as fh:
        return [r["project_id"] for r in csv.DictReader(fh)]


def model_entry(cfg: dict, model_id: str) -> dict:
    for m in list(cfg["models"]) + list(cfg["frontier_supplement"]["models"]):
        if m["id"] == model_id:
            return m
    raise KeyError(f"model id {model_id!r} is not in the frozen configuration")


def is_supplement_model(cfg: dict, model_id: str) -> bool:
    return any(m["id"] == model_id for m in cfg["frontier_supplement"]["models"])


def trials_for_cell(cfg: dict, model_id: str, condition_id: str) -> int:
    if is_supplement_model(cfg, model_id):
        return int(cfg["frontier_supplement"]["trials_per_cell"])
    entry = model_entry(cfg, model_id)
    base = int(cfg["trials"]["hosted" if entry["arm"] == "hosted" else "local"])
    return base * int(cfg["trials"]["control_multiplier"]) if condition_id == "control" else base


def enumerate_trials(cfg: dict, model_ids: Iterable[str], projects: Iterable[str] | None = None,
                     conditions: Iterable[str] | None = None, harnesses: Iterable[str] | None = None,
                     max_per_cell: int | None = None) -> list[TrialSpec]:
    projects = list(projects) if projects else panel_ids()
    all_conditions = [c["id"] for c in cfg["conditions"]]
    all_harnesses = [h["id"] for h in cfg["harnesses"]]
    out: list[TrialSpec] = []
    for mid in model_ids:
        supp = is_supplement_model(cfg, mid)
        conds = list(conditions) if conditions else (list(cfg["frontier_supplement"]["conditions"]) if supp else all_conditions)
        for pid in projects:
            for cid in conds:
                if cid not in all_conditions:
                    raise KeyError(f"unknown condition {cid!r}")
                n = trials_for_cell(cfg, mid, cid)
                if max_per_cell is not None:
                    n = min(n, max_per_cell)
                for hid in (list(harnesses) if harnesses else all_harnesses):
                    for i in range(1, n + 1):
                        out.append(TrialSpec(mid, pid, cid, hid, i, supp))
    return out

def is_complete(spec: TrialSpec) -> bool:
    p = spec.dir / "transcript.json"
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("termination"))
    except (json.JSONDecodeError, OSError):
        return False

def is_infra_incomplete(spec: TrialSpec) -> bool:
    return (spec.dir / "infrastructure_incomplete.json").exists()

def fork_and_manifest(spec: TrialSpec) -> tuple[Path, dict]:
    fork = FORKS_ROOT / spec.project_id / spec.condition_id
    mpath = FORKS_ROOT / spec.project_id / f"{spec.condition_id}.manifest.json"
    if not fork.is_dir() or not mpath.exists():
        raise InfrastructureError(f"treated fork or manifest missing for {spec.project_id}/{spec.condition_id}; "
                                  "run scripts/build_treated_forks.py --all --out forks")
    return fork, json.loads(mpath.read_text(encoding="utf-8"))

def execute_trial(cfg: dict, runtime_cfg: dict, spec: TrialSpec, ledger: CostLedger,
                  make_executor: Callable[[TrialSpec, Path, str], Executor],
                  settings: LoopSettings = LoopSettings(), image_info: dict | None = None,
                  docker_info: dict | None = None) -> dict:
    entry = model_entry(cfg, spec.model_id)
    fork, manifest = fork_and_manifest(spec)
    package = load_surface_map()[spec.project_id].package_name
    spec.dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FORKS_ROOT / spec.project_id / f"{spec.condition_id}.manifest.json", spec.dir / "manifest.json")

    adapter = build_adapter(entry, runtime_cfg)
    executor = make_executor(spec, fork, package)
    started = utc_now()
    tools = {}
    try:
        if hasattr(executor, "start"):
            executor.start()
            if hasattr(executor, "container"):
                tools = image_tools(executor.container)
        tr: Transcript = run_loop(spec.harness_id, adapter, executor, package, settings)
    finally:
        executor.close()
    ended = utc_now()

    derived = derive(tr, manifest)
    (spec.dir / "transcript.json").write_text(json.dumps(tr.to_dict(), indent=1), encoding="utf-8")
    (spec.dir / "derived.json").write_text(json.dumps(derived.to_dict(), indent=1), encoding="utf-8")
    (spec.dir / "access.log").write_text(getattr(executor, "access_log_text", ""), encoding="utf-8")
    env = {
        "trial": asdict(spec), "started_at": started, "ended_at": ended,
        "model_id": spec.model_id, "model_string_frozen": entry["model_string"],
        "model_strings_reported": tr.model_strings_reported, "runtime": entry["runtime"],
        "prompt_version": prompts.PROMPT_VERSION, "source_commit": manifest.get("source_commit"),
        "host": host_descriptor(), "docker": docker_info or {}, "image": image_info or {},
        "image_tools": tools, "executor": type(executor).__name__,
        "ollama": ollama_descriptor(runtime_cfg["providers"]["ollama"]["base_url"]) if entry["runtime"] == "ollama" else None,
        "loop_settings": asdict(settings),
    }
    (spec.dir / "environment.json").write_text(json.dumps(env, indent=1), encoding="utf-8")

    ledger.append({
        "model_id": spec.model_id, "provider": entry.get("provider") or entry["runtime"],
        "condition_id": spec.condition_id, "harness_id": spec.harness_id, "project_id": spec.project_id,
        "trial_index": spec.trial_index, "started_at": started, "ended_at": ended,
        "wall_clock_seconds": tr.wall_clock_seconds, "api_calls": tr.api_calls,
        "input_tokens_uncached": tr.input_tokens_uncached, "input_tokens_cache_write": tr.input_tokens_cache_write,
        "input_tokens_cache_read": tr.input_tokens_cache_read, "output_tokens": tr.output_tokens,
    })
    return derived.to_dict()

def run_trials(cfg: dict, runtime_cfg: dict, specs: list[TrialSpec], ledger: CostLedger,
               make_executor: Callable[[TrialSpec, Path, str], Executor],
               settings: LoopSettings = LoopSettings(), resume: bool = True,
               log: Callable[[str], None] = print, image_info: dict | None = None,
               docker_info: dict | None = None) -> dict:
    cap = float(cfg["run_budget"]["hosted_spend_cap_usd"])
    local_ids = {m["id"] for m in cfg["models"] if m["arm"] == "local"}
    counts = {"completed": 0, "skipped": 0, "infrastructure_incomplete": 0, "stopped_by_cap": 0}
    for spec in specs:
        if resume and (is_complete(spec) or is_infra_incomplete(spec)):
            counts["skipped"] += 1
            continue
        hosted = spec.model_id not in local_ids
        if hosted:
            spent = ledger.total_hosted_usd(local_ids)
            if spent >= cap:
                log(f"spend cap reached ({spent:.2f} >= {cap:.2f} USD); stopping before {spec.label}")
                counts["stopped_by_cap"] += 1
                break
        errors: list[str] = []
        for attempt in (1, 2):
            try:
                d = execute_trial(cfg, runtime_cfg, spec, ledger, make_executor, settings, image_info, docker_info)
                log(f"{spec.label}: {d['machine_end_state']} (events before decision: {d['events_before_decision']}; "
                    f"termination {d['termination']})")
                counts["completed"] += 1
                break
            except (ProviderTransportError, InfrastructureError, Exception) as e:  # noqa: BLE001
                msg = f"attempt {attempt}: {type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
                errors.append(msg)
                log(f"{spec.label}: infrastructure failure on attempt {attempt}: {type(e).__name__}: {str(e)[:200]}")
                if isinstance(e, KeyboardInterrupt):
                    raise
        else:
            spec.dir.mkdir(parents=True, exist_ok=True)
            (spec.dir / "infrastructure_incomplete.json").write_text(
                json.dumps({"trial": asdict(spec), "recorded_at": utc_now(), "errors": errors}, indent=1),
                encoding="utf-8")
            counts["infrastructure_incomplete"] += 1
    return counts
