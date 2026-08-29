"""Ledger tests against the real frozen config: schema comes from
cost_recording.per_trial_fields (never retyped), USD from the frozen rate
card only. Expected dollar values below are hand-computed from the frozen
per-MTok rates and serve as an independent cross-check.
"""
import pytest

from trust_signals.config import load_config
from trust_signals.paths import CONFIG_PATH
from trust_signals.runner import CostLedger, LedgerError


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


def _base_record(cfg, model_id, **tokens):
    """Build a record covering every frozen field except usd_cost_computed."""
    fields = cfg["cost_recording"]["per_trial_fields"]
    rec = {f: "" for f in fields}
    rec.pop("usd_cost_computed")
    rec.update(
        model_id=model_id,
        provider="test",
        condition_id="control",
        harness_id="gated",
        project_id="mpi4py",
        trial_index=0,
        started_at="2026-08-29T00:00:00Z",
        ended_at="2026-08-29T00:01:00Z",
        wall_clock_seconds=60,
        api_calls=1,
        input_tokens_uncached=0,
        input_tokens_cache_write=0,
        input_tokens_cache_read=0,
        output_tokens=0,
    )
    rec.update(tokens)
    return rec


def test_schema_is_read_from_frozen_config(cfg, tmp_path):
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    assert ledger.fields == cfg["cost_recording"]["per_trial_fields"]


def test_sonnet_usd_hand_computed(cfg, tmp_path):
    # claude-sonnet-5 frozen rates per MTok: input 2.00, cache_read 0.20, output 10.00
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    usd = ledger.compute_usd(
        "hosted_sonnet",
        input_tokens_uncached=1_000_000,
        input_tokens_cache_write=0,
        input_tokens_cache_read=1_000_000,
        output_tokens=100_000,
    )
    assert usd == pytest.approx(2.00 + 0.20 + 1.00)


def test_fable_usd_hand_computed(cfg, tmp_path):
    # claude-fable-5 frozen rates per MTok: input 10.00, cache_read 1.00, output 50.00
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    usd = ledger.compute_usd("frontier_anthropic", 10_000, 0, 0, 2_000)
    assert usd == pytest.approx(10_000 * 10.0 / 1e6 + 2_000 * 50.0 / 1e6)


def test_cache_write_uses_provider_specific_rate(cfg, tmp_path):
    # Anthropic 5m cache write for sonnet: 2.50 per MTok (ruling: 5m TTL default)
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    usd = ledger.compute_usd("hosted_sonnet", 0, 1_000_000, 0, 0)
    assert usd == pytest.approx(2.50)


def test_local_arm_is_zero_cost(cfg, tmp_path):
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    assert ledger.compute_usd("local_openweight", 5_000_000, 0, 0, 1_000_000) == 0.0


def test_unknown_model_id_fails(cfg, tmp_path):
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    with pytest.raises(LedgerError):
        ledger.compute_usd("mystery_model", 1, 0, 0, 1)


def test_caller_may_not_supply_usd(cfg, tmp_path):
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    rec = _base_record(cfg, "hosted_sonnet")
    rec["usd_cost_computed"] = 0.42
    with pytest.raises(LedgerError):
        ledger.append(rec)


def test_append_roundtrip_and_resume(cfg, tmp_path):
    path = tmp_path / "ledger.csv"
    ledger = CostLedger(cfg, path)
    ledger.append(_base_record(cfg, "hosted_sonnet", input_tokens_uncached=500_000, output_tokens=100_000))
    # simulate resume: a fresh ledger object against the same file
    resumed = CostLedger(cfg, path)
    resumed.append(_base_record(cfg, "local_openweight", input_tokens_uncached=900, output_tokens=250))
    rows = resumed.rows()
    assert len(rows) == 2
    assert rows[0]["model_id"] == "hosted_sonnet"
    assert float(rows[0]["usd_cost_computed"]) == pytest.approx(500_000 * 2.0 / 1e6 + 100_000 * 10.0 / 1e6)
    assert float(rows[1]["usd_cost_computed"]) == 0.0


def test_resume_refuses_foreign_header(cfg, tmp_path):
    path = tmp_path / "ledger.csv"
    path.write_text("some,other,header\n1,2,3\n", encoding="utf-8")
    with pytest.raises(LedgerError):
        CostLedger(cfg, path)


def test_hosted_total_excludes_local(cfg, tmp_path):
    path = tmp_path / "ledger.csv"
    ledger = CostLedger(cfg, path)
    ledger.append(_base_record(cfg, "hosted_sonnet", input_tokens_uncached=1_000_000))
    ledger.append(_base_record(cfg, "local_openweight", input_tokens_uncached=9_000_000))
    assert ledger.total_hosted_usd() == pytest.approx(2.0)


def test_record_outside_schema_rejected(cfg, tmp_path):
    ledger = CostLedger(cfg, tmp_path / "ledger.csv")
    rec = _base_record(cfg, "hosted_sonnet")
    rec["surprise_field"] = 1
    with pytest.raises(LedgerError):
        ledger.append(rec)
