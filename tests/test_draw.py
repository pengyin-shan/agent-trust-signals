import copy

from trust_signals import config, draw, paths

def synthetic_corpus(n_per_domain=12):
    rows = []
    for dom in ("hpc", "qc"):
        for i in range(n_per_domain):
            pid = f"{dom}proj{i:02d}"
            rows.append({"project_id": pid, "github_repo": f"org-{pid}/{pid}",
                         "domain": dom, "doi": "", "pypi_package": "",
                         "npm_package": "", "stratum": "sc26", "source": "test"})
    return rows

def synthetic_evidence(corpus, installable=True):
    return {r["project_id"]: {"project_id": r["project_id"], "branch": "main",
                              "pyproject_toml": str(installable), "setup_py": "False",
                              "probed_at": "2026-08-19T00:00:00Z", "note": ""}
            for r in corpus}

def synthetic_judgments(corpus, decision="pass"):
    return {r["project_id"]: {"project_id": r["project_id"], "decision": decision,
                              "note": "test", "recorded_at": "2026-08-20T00:00:00Z"}
            for r in corpus}

def base_cfg():
    cfg = copy.deepcopy(config.load_config(paths.CONFIG_PATH))
    cfg["screening"]["s4_excluded"] = []
    cfg["screening"]["extra_collisions"] = []
    return cfg

def test_same_seed_identical_output():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = synthetic_judgments(corpus)
    r1 = draw.run_draw(cfg, corpus, ev, jd, seed=424242)
    r2 = draw.run_draw(cfg, corpus, ev, jd, seed=424242)
    assert r1.ranking == r2.ranking
    assert [a["project_id"] for a in r1.accepted] == [a["project_id"] for a in r2.accepted]

def test_different_seed_different_ranking():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = synthetic_judgments(corpus)
    r1 = draw.run_draw(cfg, corpus, ev, jd, seed=1)
    r2 = draw.run_draw(cfg, corpus, ev, jd, seed=2)
    assert r1.ranking != r2.ranking

def test_ranking_independent_of_corpus_row_order():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = synthetic_judgments(corpus)
    r1 = draw.run_draw(cfg, corpus, ev, jd, seed=7)
    r2 = draw.run_draw(cfg, list(reversed(corpus)), ev, jd, seed=7)
    assert r1.ranking == r2.ranking

def test_quota_met_and_stratified():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    r = draw.run_draw(cfg, corpus, synthetic_evidence(corpus),
                      synthetic_judgments(corpus), seed=99)
    assert r.complete
    assert len(r.accepted) == cfg["draw"]["panel_size"]
    for dom, quota in cfg["draw"]["per_stratum"].items():
        assert sum(1 for a in r.accepted if a["domain"] == dom) == quota

def test_frame_rules_filter_before_ranking():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    ev["hpcproj00"]["pyproject_toml"] = "False"
    ev["hpcproj01"]["pyproject_toml"] = "False"
    r = draw.run_draw(cfg, corpus, ev, synthetic_judgments(corpus), seed=5)
    assert "hpcproj00" not in r.ranking["hpc"]
    assert "hpcproj01" not in r.ranking["hpc"]
    frame_fails = [e for e in r.screening_log
                   if e.project_id == "hpcproj00" and e.rule_id == "S2" and not e.passed]
    assert frame_fails, "S2 frame exclusion must be logged"

def test_missing_judgment_halts_acceptance_in_rank_order():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = {}  # no judgments recorded at all
    r = draw.run_draw(cfg, corpus, ev, jd, seed=11)
    assert not r.complete
    assert r.accepted == []
    assert r.pending_s5
    jd = synthetic_judgments(corpus)
    r2 = draw.run_draw(cfg, corpus, ev, jd, seed=11)
    assert r2.complete
    assert r.ranking == r2.ranking


def test_s5_fail_skips_and_takes_next_rank():
    cfg = base_cfg()
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = synthetic_judgments(corpus)
    probe = draw.run_draw(cfg, corpus, ev, jd, seed=13)
    first_hpc = probe.ranking["hpc"][0]
    jd[first_hpc] = {"project_id": first_hpc, "decision": "fail",
                     "note": "unreachable", "recorded_at": "2026-08-20T00:00:00Z"}
    r = draw.run_draw(cfg, corpus, ev, jd, seed=13)
    assert r.complete
    accepted_ids = [a["project_id"] for a in r.accepted]
    assert first_hpc not in accepted_ids
    skip = [e for e in r.screening_log
            if e.project_id == first_hpc and e.rule_id == "S5" and not e.passed]
    assert skip, "S5 skip must be logged with its rule identifier"

def test_exhaustion_reported_not_silently_widened():
    cfg = base_cfg()
    cfg["draw"]["oversample"] = 3
    corpus = synthetic_corpus()
    ev = synthetic_evidence(corpus)
    jd = synthetic_judgments(corpus)
    probe = draw.run_draw(cfg, corpus, ev, jd, seed=17)
    for pid in probe.ranking["hpc"][:2]:
        jd[pid] = {"project_id": pid, "decision": "fail", "note": "x",
                   "recorded_at": "2026-08-20T00:00:00Z"}
    r = draw.run_draw(cfg, corpus, ev, jd, seed=17)
    assert "hpc" in r.exhausted
    assert not r.complete