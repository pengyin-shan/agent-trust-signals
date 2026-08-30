from __future__ import annotations
import json
from pathlib import Path
import pytest
from trust_signals.config import load_config
from trust_signals.harness import LoopSettings, LocalExecutor
from trust_signals.paths import CONFIG_PATH
from trust_signals.providers.base import AdapterResponse, ProviderTransportError
from trust_signals.runner import CostLedger, TrialSpec, enumerate_trials, is_complete, run_trials, trials_for_cell
from trust_signals.runner import trials as trials_mod

@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)

class FakeAdapter:
    def __init__(self, turns, fail_first=0):
        self.turns, self.fail_first = list(turns), fail_first

    def send(self, messages, system=None, max_tokens=4096, temperature=None):
        if self.fail_first:
            self.fail_first -= 1
            raise ProviderTransportError("simulated transport failure")
        text = self.turns.pop(0) if self.turns else '{"action":"finish","outcome":"not_installed","summary":"end"}'
        return AdapterResponse(text=text, input_tokens_uncached=100, input_tokens_cache_write=0,
                               input_tokens_cache_read=0, output_tokens=20, raw_usage={}, model_string_reported="fake")

def test_enumeration_matches_frozen_budget(cfg):
    local = enumerate_trials(cfg, ["local_openweight"])
    hosted = enumerate_trials(cfg, ["hosted_sonnet"])
    assert len(local) == cfg["run_budget"]["local_trials_total"]
    assert len(hosted) == cfg["run_budget"]["hosted_trials_per_model"]
    cells = {(s.project_id, s.condition_id, s.harness_id) for s in hosted}
    assert len(cells) == cfg["run_budget"]["cells_per_model"]
    assert trials_for_cell(cfg, "hosted_sonnet", "control") == 2 * trials_for_cell(cfg, "hosted_sonnet", "sbom_present")

def test_supplement_enumeration(cfg):
    supp = enumerate_trials(cfg, ["frontier_anthropic"])
    assert {s.condition_id for s in supp} == {"control", "all_signals_present"}
    assert len(supp) == 6 * 2 * 2 * cfg["frontier_supplement"]["trials_per_cell"]
    assert all(s.supplement for s in supp)

def test_enumeration_rejects_unknown_condition(cfg):
    with pytest.raises(KeyError):
        enumerate_trials(cfg, ["hosted_sonnet"], conditions=["no_such_condition"])

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Fake forks/ and runs/ trees for one real panel project id with a local executor."""
    forks = tmp_path / "forks"
    fork = forks / "qrisp" / "control"
    fork.mkdir(parents=True)
    (fork / "README.md").write_text("# Qrisp\n")
    (fork / "pyproject.toml").write_text('[project]\nname="qrisp"\nversion="0.9.7"\n')
    (forks / "qrisp" / "control.manifest.json").write_text(json.dumps(
        {"condition_id": "control", "project_id": "qrisp", "source_commit": "abc123", "files": [], "notes": []}))
    monkeypatch.setattr(trials_mod, "FORKS_ROOT", forks)
    monkeypatch.setattr(trials_mod, "RUNS_ROOT", tmp_path / "runs")
    return tmp_path

def _factory(tmp):
    def make(spec, fork, package):
        work = tmp / "work" / spec.label.replace("/", "_")
        import shutil
        shutil.copytree(fork, work, dirs_exist_ok=True)   # a re-run reuses the scratch directory
        return LocalExecutor(work)
    return make

def test_trial_writes_artifacts_and_ledger(cfg, sandbox, monkeypatch):
    runtime_cfg = {"providers": {"ollama": {"base_url": "http://localhost:0"}}}
    monkeypatch.setattr(trials_mod, "build_adapter",
                        lambda entry, rt: FakeAdapter(['{"action":"run","command":"pip install --help >/dev/null; true","reason":"install"}',
                                                      '{"action":"finish","outcome":"installed","summary":"done"}']))
    ledger = CostLedger(cfg, sandbox / "runs" / "cost_ledger.csv")
    spec = TrialSpec("local_openweight", "qrisp", "control", "autonomous", 1)
    counts = run_trials(cfg, runtime_cfg, [spec], ledger, _factory(sandbox), LoopSettings(command_timeout_s=10), log=lambda s: None)
    assert counts == {"completed": 1, "skipped": 0, "infrastructure_incomplete": 0, "stopped_by_cap": 0}
    d = spec.dir
    for name in ("transcript.json", "derived.json", "environment.json", "manifest.json", "access.log"):
        assert (d / name).exists(), name
    derived = json.loads((d / "derived.json").read_text())
    assert derived["install_executed"] and derived["machine_end_state"] == "proceeded"
    env = json.loads((d / "environment.json").read_text())
    assert env["model_string_frozen"] == [m for m in cfg["models"] if m["id"] == "local_openweight"][0]["model_string"] and env["prompt_version"] == "1.0" and env["source_commit"] == "abc123"
    rows = ledger.rows()
    assert len(rows) == 1 and rows[0]["model_id"] == "local_openweight" and rows[0]["api_calls"] == "2"
    assert float(rows[0]["usd_cost_computed"]) == 0.0
    assert is_complete(spec)

def test_resume_skips_completed_trials(cfg, sandbox, monkeypatch):
    runtime_cfg = {"providers": {"ollama": {"base_url": "http://localhost:0"}}}
    monkeypatch.setattr(trials_mod, "build_adapter", lambda entry, rt: FakeAdapter([]))
    ledger = CostLedger(cfg, sandbox / "runs" / "cost_ledger.csv")
    spec = TrialSpec("local_openweight", "qrisp", "control", "gated", 3)
    run_trials(cfg, runtime_cfg, [spec], ledger, _factory(sandbox), log=lambda s: None)
    counts = run_trials(cfg, runtime_cfg, [spec], ledger, _factory(sandbox), log=lambda s: None)
    assert counts["skipped"] == 1 and counts["completed"] == 0
    assert len(ledger.rows()) == 1

def test_transport_failure_reruns_once_then_marks_incomplete(cfg, sandbox, monkeypatch):
    runtime_cfg = {"providers": {"ollama": {"base_url": "http://localhost:0"}}}
    # first attempt fails, second succeeds
    calls = {"n": 0}
    def adapter_factory(entry, rt):
        calls["n"] += 1
        return FakeAdapter([], fail_first=1 if calls["n"] == 1 else 0)
    monkeypatch.setattr(trials_mod, "build_adapter", adapter_factory)
    ledger = CostLedger(cfg, sandbox / "runs" / "cost_ledger.csv")
    spec = TrialSpec("local_openweight", "qrisp", "control", "autonomous", 2)
    counts = run_trials(cfg, runtime_cfg, [spec], ledger, _factory(sandbox), log=lambda s: None)
    assert counts["completed"] == 1 and calls["n"] == 2
    # both attempts fail -> marker, no ledger row
    monkeypatch.setattr(trials_mod, "build_adapter", lambda entry, rt: FakeAdapter([], fail_first=5))
    spec2 = TrialSpec("local_openweight", "qrisp", "control", "autonomous", 4)
    counts = run_trials(cfg, runtime_cfg, [spec2], ledger, _factory(sandbox), log=lambda s: None)
    assert counts["infrastructure_incomplete"] == 1
    marker = json.loads((spec2.dir / "infrastructure_incomplete.json").read_text())
    assert len(marker["errors"]) == 2 and len(ledger.rows()) == 1

def test_spend_cap_stops_hosted_trials(cfg, sandbox, monkeypatch, tmp_path):
    runtime_cfg = {"providers": {"anthropic_api": {"base_url": "http://localhost:0"}, "ollama": {"base_url": "http://localhost:0"}}}
    monkeypatch.setattr(trials_mod, "build_adapter", lambda entry, rt: FakeAdapter([]))
    ledger = CostLedger(cfg, sandbox / "runs" / "cost_ledger.csv")
    # pre-load the ledger with a row at the cap
    ledger.append({"model_id": "hosted_sonnet", "provider": "anthropic_api", "condition_id": "control", "harness_id": "gated",
                   "project_id": "qrisp", "trial_index": 99, "started_at": "t", "ended_at": "t", "wall_clock_seconds": 1,
                   "api_calls": 1, "input_tokens_uncached": 50_000_000, "input_tokens_cache_write": 0,
                   "input_tokens_cache_read": 0, "output_tokens": 0})
    spec = TrialSpec("hosted_sonnet", "qrisp", "control", "autonomous", 1)
    counts = run_trials(cfg, runtime_cfg, [spec], ledger, _factory(sandbox), log=lambda s: None)
    assert counts["stopped_by_cap"] == 1 and counts["completed"] == 0
