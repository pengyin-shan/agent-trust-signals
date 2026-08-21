import copy
import pytest
from trust_signals import config, paths

def good_cfg():
    return config.load_config(paths.CONFIG_PATH)

def test_shipped_config_loads():
    cfg = good_cfg()
    assert cfg["draw"]["panel_size"] == 6

def test_shipped_corpus_hash_matches():
    cfg = good_cfg()
    config.verify_corpus_hash(cfg, paths.CORPUS_PATH)

def test_missing_top_key_raises(tmp_path):
    cfg = good_cfg()
    del cfg["conditions"]
    with pytest.raises(config.ConfigError, match="conditions"):
        config._validate(cfg)

def test_per_stratum_sum_mismatch_raises():
    cfg = copy.deepcopy(good_cfg())
    cfg["draw"]["per_stratum"]["hpc"] = 5
    with pytest.raises(config.ConfigError, match="sum to panel_size"):
        config._validate(cfg)

def test_unknown_signal_class_raises():
    cfg = copy.deepcopy(good_cfg())
    cfg["conditions"][0]["class"] = "telepathy"
    with pytest.raises(config.ConfigError, match="unknown signal class"):
        config._validate(cfg)

def test_unknown_arm_raises():
    cfg = copy.deepcopy(good_cfg())
    cfg["models"][0]["arm"] = "orbital"
    with pytest.raises(config.ConfigError, match="unknown arm"):
        config._validate(cfg)

def test_run_budget_drift_raises():
    cfg = copy.deepcopy(good_cfg())
    cfg["run_budget"]["hosted_trials_total"] = 999
    with pytest.raises(config.ConfigError, match="run_budget.hosted_trials_total"):
        config._validate(cfg)

def test_null_seed_refused_by_require_seed():
    cfg = copy.deepcopy(good_cfg())
    cfg["draw"]["seed"] = None
    with pytest.raises(config.ConfigError, match="seed is null"):
        config.require_seed(cfg)

def test_corpus_hash_mismatch_raises(tmp_path):
    cfg = copy.deepcopy(good_cfg())
    bad = tmp_path / "corpus.csv"
    bad.write_text("project_id\nmallory\n")
    with pytest.raises(config.ConfigError, match="SHA256 mismatch"):
        config.verify_corpus_hash(cfg, bad)

def test_freeze_pending_detector_finds_placeholders():
    cfg = copy.deepcopy(good_cfg())
    found = config.freeze_pending_strings(cfg)
    assert "frozen_at" in found
    assert "draw.seed" in found