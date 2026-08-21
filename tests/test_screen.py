from trust_signals import screen

def cand(pid="proj-a", repo="org-a/proj-a"):
    return {"project_id": pid, "github_repo": repo, "domain": "hpc"}

EVIDENCE = {
    "proj-a": {"project_id": "proj-a", "branch": "main", "pyproject_toml": "True",
               "setup_py": "False", "probed_at": "2026-08-19T00:00:00Z", "note": ""},
    "proj-b": {"project_id": "proj-b", "branch": "main", "pyproject_toml": "False",
               "setup_py": "False", "probed_at": "2026-08-19T00:00:00Z", "note": ""},
    "proj-c": {"project_id": "proj-c", "branch": "", "pyproject_toml": "",
               "setup_py": "", "probed_at": "2026-08-19T00:00:00Z",
               "note": "branch unresolved; manual check required"},
}

S4 = [{"project_id": "famous-example", "reason": "named example"}]

def test_s1_pass_and_fail():
    assert screen.rule_s1(cand()).passed
    assert not screen.rule_s1(cand(repo="")).passed
    assert not screen.rule_s1(cand(repo="no-slash")).passed

def test_s2_checkout_installable_passes():
    r = screen.rule_s2(cand("proj-a"), EVIDENCE)
    assert r.passed
    assert "pyproject.toml" in r.reason

def test_s2_no_build_declaration_fails():
    assert not screen.rule_s2(cand("proj-b"), EVIDENCE).passed

def test_s2_unresolved_and_missing_evidence_fail():
    assert not screen.rule_s2(cand("proj-c"), EVIDENCE).passed
    assert not screen.rule_s2(cand("proj-zzz"), EVIDENCE).passed

def test_s3_owner_collision():
    accepted = [cand("other", "org-a/other")]
    assert not screen.rule_s3(cand("proj-a", "org-a/proj-a"), accepted).passed
    assert screen.rule_s3(cand("proj-a", "org-b/proj-a"), accepted).passed

def test_s3_name_family_collision():
    accepted = [{"project_id": "qthing", "github_repo": "o1/qthing", "domain": "qc"}]
    newc = {"project_id": "qthing-extras", "github_repo": "o2/qthing-extras", "domain": "qc"}
    assert not screen.rule_s3(newc, accepted).passed

def test_s3_curated_pair_collision():
    accepted = [{"project_id": "alpha", "github_repo": "o1/alpha", "domain": "qc"}]
    newc = {"project_id": "bridge-alpha", "github_repo": "o2/bridge-alpha", "domain": "qc"}
    assert screen.rule_s3(newc, accepted).passed  # heuristic alone does not see it
    assert not screen.rule_s3(newc, accepted, [["bridge-alpha", "alpha"]]).passed

def test_s4_exclusion():
    assert not screen.rule_s4(cand("famous-example"), S4).passed
    assert screen.rule_s4(cand("proj-a"), S4).passed

def test_s5_pending_pass_fail():
    pending = screen.rule_s5(cand("proj-a"), {})
    assert not pending.passed and pending.pending
    ok = screen.rule_s5(cand("proj-a"), {"proj-a": {"decision": "pass", "note": "installs",
                                                    "recorded_at": "2026-08-20T00:00:00Z"}})
    assert ok.passed and not ok.pending
    no = screen.rule_s5(cand("proj-a"), {"proj-a": {"decision": "fail", "note": "dead host",
                                                    "recorded_at": "2026-08-20T00:00:00Z"}})
    assert not no.passed and not no.pending