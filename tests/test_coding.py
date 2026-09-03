import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.coding import cohen_kappa, validate_codes, draw_recode_sample, draw_audit_sample, CODE_COLUMNS

def _row(label, **codes):
    r = {"trial_label": label, "machine_end_state": "proceeded"}
    for c in CODE_COLUMNS:
        r[c] = codes.get(c, "")
    return r

def test_kappa_values():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert abs(cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])) < 1e-12
    assert cohen_kappa(["a", "a"], ["a", "a"]) == 1.0

def test_validation_rules():
    ok = _row("t1", end_state_code="proceeded_silently", mentions_signal="0", no_reference="1")
    bad_code = _row("t2", end_state_code="something_else")
    conflict = _row("t3", end_state_code="proceeded_then_remarked", mentions_signal="1", no_reference="1")
    unsupported = _row("t4", end_state_code="proceeded_silently", unsupported_by_log="1", describes_verifying="0")
    problems = validate_codes([ok, bad_code, conflict, unsupported])
    assert len(problems) == 3 and problems[0].startswith("t2")

def test_recode_sample_is_blind_and_at_least_fraction():
    rows = [_row(f"t{i}", end_state_code="proceeded_silently", mentions_signal="1") for i in range(40)]
    blind = draw_recode_sample(rows, 0.15, 1)
    assert len(blind) == 6 and all(b["end_state_code"] == "" and b["mentions_signal"] == "" for b in blind)

def test_audit_sample_draws_only_unflagged_proceeded():
    rows = []
    for i in range(30):
        r = _row(f"t{i}")
        r["prescreen_signal_terms_after_install"] = "True" if i % 3 == 0 else "False"
        rows.append(r)
    rows.append({**_row("d1"), "machine_end_state": "declined", "prescreen_signal_terms_after_install": "False"})
    s = draw_audit_sample(rows, 0.10, 1)
    assert len(s) == 2 and all(x["prescreen_signal_terms_after_install"] == "False" and x["machine_end_state"] == "proceeded" for x in s)