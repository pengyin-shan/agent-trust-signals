import json
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.mixed import primary_contrast, plain_logistic, marginal_loglik, stratified_exact_permutation
from analysis.descriptive import wilson, holm
from analysis.execution import incidents_from_log, _classify

def _simulate(seed, b0=-1.5, b1=0.8, sigma=0.6, per_project=320, control_share=0.125):
    rng = np.random.default_rng(seed)
    n_control = int(per_project * control_share)
    project = np.repeat(np.arange(6), per_project)
    present = np.tile(np.array([0] * n_control + [1] * (per_project - n_control)), 6)
    u = rng.normal(0, sigma, 6)[project]
    y = (rng.random(len(project)) < 1 / (1 + np.exp(-(b0 + b1 * present + u)))).astype(float)
    return project, present, y

def test_mixed_recovers_effect_and_ci_covers_truth():
    ests, covered = [], 0
    for seed in range(6):
        project, present, y = _simulate(seed)
        r = primary_contrast(project, present, y, permutations=0)
        assert r.method == "mixed_logistic_lrt" and r.converged
        ests.append(r.log_odds_ratio)
        covered += r.ci95_low <= 0.8 <= r.ci95_high
    assert abs(np.mean(ests) - 0.8) < 0.25
    assert covered >= 4

def test_mixed_reduces_to_plain_logistic_when_variance_floors():
    project, present, y = _simulate(3, sigma=0.0)
    X = np.column_stack([np.ones(len(y)), present])
    b, ll = plain_logistic(X, y)
    ll_mixed = marginal_loglik(np.array([b[0], b[1], np.log(1e-4)]), [(X, y)])
    assert abs(ll - ll_mixed) < 1e-3

def test_null_p_values_are_not_anticonservative():
    ps = [primary_contrast(*_simulate(seed, b1=0.0), permutations=0).p_value for seed in range(12)]
    assert np.mean(np.array(ps) < 0.05) <= 0.2

def test_fallback_permutation_runs_and_detects_effect():
    project, present, y = _simulate(5, b1=1.5)
    fb = stratified_exact_permutation(project, present, y, permutations=200, seed=1)
    assert fb["p_value"] < 0.05 and len(fb["per_project"]) == 6

def test_wilson_interval_bounds():
    p, lo, hi = wilson(0, 10)
    assert p == 0.0 and lo == 0.0 and 0.0 < hi < 0.35
    p, lo, hi = wilson(10, 10)
    assert p == 1.0 and hi == pytest.approx(1.0) and 0.65 < lo < 1.0
    assert all(np.isnan(v) for v in wilson(0, 0))

def test_holm_adjustment():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)

def test_incident_classification_and_log_parsing(tmp_path):
    assert _classify('HTTP 400 from x: {"message": "prompt was flagged as potentially violating our usage policy"}') == "http_400_policy_filter"
    assert _classify("HTTP 529 from x: overloaded") == "http_529"
    assert _classify("ProviderTransportError: [Errno 8] nodename nor servname provided") == "dns_resolution"
    log = tmp_path / "hosted_batch.log"
    log.write_text("\n".join([
        "a/p/c/h/trial_01: infrastructure failure on attempt 1: ProviderTransportError: HTTP 529 from x",
        "a/p/c/h/trial_01: proceeded (events before decision: []; termination finish)",
        "a/p/c/h/trial_02: infrastructure failure on attempt 1: ProviderTransportError: HTTP 529 from x",
        "a/p/c/h/trial_02: infrastructure failure on attempt 2: ProviderTransportError: HTTP 529 from x",
        "spend cap reached (100.59 >= 100.00 USD); stopping before a/p/c/h/trial_03",
    ]))
    inc = incidents_from_log(log)
    assert inc["trials_recovered_on_second_attempt_by_arm"] == {"a": 1}
    assert inc["trials_failed_both_attempts_by_arm"] == {"a": 1}
    assert inc["cap_stop_events"][0]["spent_usd"] == 100.59

def test_mixed_converges_with_rare_events_and_large_variance():
    project, present, y = _simulate(11, b0=-7.0, b1=1.0, sigma=2.5)
    y[(project == 2) & (present == 1)][:5] = 1.0
    r = primary_contrast(project, present, y, permutations=50, seed=1)
    assert r.fallback_reason is None or "separation" in r.fallback_reason
    assert np.isfinite(r.loglik_null) and r.loglik_null > -200

def test_separation_routes_to_registered_fallback():
    project, present, y = _simulate(2, b0=-5.0, b1=1.0, sigma=0.5)
    y[present == 0] = 0.0
    r = primary_contrast(project, present, y, permutations=50, seed=1)
    assert r.method == "stratified_fisher_permutation" and "separation" in r.fallback_reason