from __future__ import annotations
import json
import shutil
import tarfile
from pathlib import Path
import pytest
import yaml
from trust_signals.conditions import condition_ids
from trust_signals.treatments import TreatmentContext, TreatmentError, check_registry, registry, treatment_for
from trust_signals.treatments.archive import build_archive
from trust_signals.treatments.keys import dsse_verify, generate_study_keys, stop_agent
from trust_signals.treatments.registry import AllSignalsPresent
from trust_signals.treatments.surface_map import load_surface_map, SURFACE_MAP_PATH
from trust_signals.paths import PANEL_DRAW_CSV

HAS_GPG = shutil.which("gpg") is not None

def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

@pytest.fixture
def entry_yaml(tmp_path: Path) -> Path:
    doc = {"schema_version": 1, "projects": {"demo": {
        "upstream_repo": "example/demo", "default_branch": "main", "package_name": "demo",
        "title": {"value": "Demo Toolkit", "source": "README.md:1"},
        "version": {"value": "2.0.0", "source": "pyproject.toml:3", "surface": "pyproject.toml"},
        "previous_release": {"value": "v1.9.0", "source": "git tags"},
        "license": {"value": "MIT", "source": "pyproject.toml:5"},
        "citation_file": None,
        "dependency_sources": ["pyproject.toml", "requirements.txt"],
        "build_authors": {"kind": "entity", "value": "The Demo Team", "source": "pyproject.toml:4"},
        "entity_name": None,
        "individuals": {"source": "README.md:12", "persons": [{"given": "Ada", "family": "Lovelace"},
                                                              {"given": "Grace", "family": "Hopper"}]},
        "cited_work": {"kind": "article", "title": "Demo: A Toolkit", "year": 2020, "venue": "J. Demo",
                       "doi": "10.1000/demo", "url": None, "source": "README.md:12",
                       "authors": [{"given": "Ada", "family": "Lovelace"}, {"given": "Grace", "family": "Hopper"}]},
        "readme_has_citation_section": False,
        "channels": [{"kind": "source_repository", "value": "https://github.com/example/demo", "source": "README.md:2"},
                     {"kind": "chat", "value": "https://chat.example.invalid", "source": "README.md:3"}],
        "notes": [],
    }}}
    p = tmp_path / "map.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p

@pytest.fixture
def entry(entry_yaml):
    return load_surface_map(entry_yaml)["demo"]

@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    fork = tmp_path / "fork"
    _write(fork / "pyproject.toml",
           '[project]\nname = "demo"\nversion = "2.0.0"\nauthors = [{name = "The Demo Team"}]\n'
           'license = {text = "MIT"}\ndependencies = ["numpy>=1.20", "requests"]\n')
    _write(fork / "requirements.txt", "numpy>=1.20\nscipy  # optional\n-e .\n")
    _write(fork / "README.md", "# Demo Toolkit\nhttps://github.com/example/demo\nhttps://chat.example.invalid\n")
    _write(fork / "demo" / "__init__.py", "__version__ = '2.0.0'\n")
    (fork / ".git").mkdir()
    _write(fork / ".git" / "HEAD", "ref: refs/heads/main\n")
    return fork

@pytest.fixture(scope="module")
def keys():
    if not HAS_GPG:
        pytest.skip("gpg not available")
    import tempfile
    base = Path(tempfile.mkdtemp(prefix="ats-", dir="/tmp" if Path("/tmp").is_dir() else None))
    try:
        yield generate_study_keys(base / "private", base / "public", overwrite=True)
    finally:
        stop_agent(base / "private" / "gnupg")
        shutil.rmtree(base, ignore_errors=True)

def ctx_for(entry, keys=None):
    return TreatmentContext(project=entry, source_commit="0123456789abcdef0123456789abcdef01234567", keys=keys)

def test_registry_matches_frozen_conditions():
    check_registry()
    assert set(registry()) == set(condition_ids())
    assert len(registry()) == 9

def test_each_constructor_reports_its_condition_id():
    for cid in condition_ids():
        assert treatment_for(cid).condition_id == cid

def test_unknown_condition_rejected():
    with pytest.raises(KeyError):
        treatment_for("not_a_condition")

def test_real_surface_map_covers_frozen_panel():
    import csv
    with open(PANEL_DRAW_CSV, newline="", encoding="utf-8") as fh:
        panel = [r["project_id"] for r in csv.DictReader(fh)]
    m = load_surface_map(SURFACE_MAP_PATH)
    assert set(panel) == set(m), "surface map must cover exactly the frozen panel"
    for pid, e in m.items():
        assert e.channels, pid
        assert e.previous_version_string() != str(e.version.value), pid
        for ch in e.channels:
            assert ch.source, f"{pid}: every channel needs a source line"

def test_surface_map_rejects_unsourced_value(tmp_path):
    doc = {"projects": {"x": {"upstream_repo": "a/b", "default_branch": "main", "package_name": "x",
                              "title": {"value": "X"}, "version": {"value": "1", "source": "f", "surface": "f"},
                              "previous_release": {"value": "0", "source": "t"}, "license": {"value": "MIT", "source": "f"},
                              "channels": [{"kind": "chat", "value": "u", "source": "s"}], "dependency_sources": []}}}
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(TreatmentError):
        load_surface_map(p)

def test_control_is_a_noop(checkout, entry):
    before = sorted(p.relative_to(checkout).as_posix() for p in checkout.rglob("*"))
    m = treatment_for("control").apply(checkout, ctx_for(entry))
    after = sorted(p.relative_to(checkout).as_posix() for p in checkout.rglob("*"))
    assert before == after and m.files == []

def test_archive_is_deterministic_and_excludes_git_and_dist(checkout, entry):
    a = build_archive(checkout, ctx_for(entry))
    first = a.read_bytes()
    build_archive(checkout, ctx_for(entry))
    assert a.read_bytes() == first
    with tarfile.open(a) as tf:
        names = tf.getnames()
    assert all(n.startswith("demo-2.0.0/") for n in names)
    assert not any("/.git" in n or "/dist" in n for n in names)
    assert (checkout / "dist" / "demo-2.0.0.tar.gz.sha256").exists()

def test_sbom_lists_declared_dependencies_only(checkout, entry):
    m = treatment_for("sbom_present").apply(checkout, ctx_for(entry))
    bom = json.loads((checkout / "dist" / "demo-2.0.0.cdx.json").read_text())
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.6"
    names = {c["name"] for c in bom["components"]}
    assert names == {"numpy", "requests", "scipy"}
    assert bom["metadata"]["component"]["version"] == "2.0.0"
    assert "Software bill of materials" in (checkout / "README.md").read_text()
    events = {f.path: f.retrieval_event for f in m.files}
    assert events["dist/demo-2.0.0.cdx.json"] == "sbom_opened"
    assert events["README.md"] is None
    assert not (checkout / "KEYS").exists() and not (checkout / "SECURITY.md").exists()

@pytest.mark.skipif(not HAS_GPG, reason="gpg not available")
def test_signed_release_valid_verifies_against_keys_file(checkout, entry, keys):
    m = treatment_for("signed_release_present").apply(checkout, ctx_for(entry, keys))
    art = checkout / "dist" / "demo-2.0.0.tar.gz"
    ok, _ = keys.verify_detached(art.with_name(art.name + ".asc"), art)
    assert ok
    keys_text = (checkout / "KEYS").read_text()
    assert keys["A"].pgp_fingerprint in keys_text and keys["B"].pgp_fingerprint not in keys_text
    assert (checkout / "dist" / "signing-key.asc").read_text() == keys["A"].pgp_public_armored
    assert {f.path for f in m.files} >= {"KEYS", "dist/demo-2.0.0.tar.gz.asc", "dist/signing-key.asc"}

@pytest.mark.skipif(not HAS_GPG, reason="gpg not available")
def test_signed_release_mismatch_is_signed_by_b_and_declares_a(checkout, entry, keys):
    m = treatment_for("signed_release_issuer_mismatch").apply(checkout, ctx_for(entry, keys))
    assert (checkout / "dist" / "signing-key.asc").read_text() == keys["B"].pgp_public_armored
    assert keys["A"].pgp_fingerprint in (checkout / "KEYS").read_text()
    assert keys["B"].pgp_fingerprint not in (checkout / "KEYS").read_text()
    assert any("issuer mismatch" in n for n in m.notes)
    art = checkout / "dist" / "demo-2.0.0.tar.gz"
    ok, err = keys.verify_detached(art.with_name(art.name + ".asc"), art)
    assert ok
    assert keys["B"].email in err

@pytest.mark.skipif(not HAS_GPG, reason="gpg not available")
def test_attestation_envelope_verifies_and_binds_artifact_digest(checkout, entry, keys):
    treatment_for("attestation_present").apply(checkout, ctx_for(entry, keys))
    env = json.loads((checkout / "dist" / "demo-2.0.0.tar.gz.intoto.jsonl").read_text())
    assert dsse_verify(env, keys["A"].ecdsa_public_pem)
    assert not dsse_verify(env, keys["B"].ecdsa_public_pem)
    import base64
    stmt = json.loads(base64.b64decode(env["payload"]))
    digest = (checkout / "dist" / "demo-2.0.0.tar.gz.sha256").read_text().split()[0]
    assert stmt["subject"][0]["digest"]["sha256"] == digest
    assert stmt["predicateType"] == "https://slsa.dev/provenance/v1"
    assert stmt["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"]["gitCommit"].startswith("0123")

@pytest.mark.skipif(not HAS_GPG, reason="gpg not available")
def test_attestation_mismatch_differs_only_in_signer(checkout, entry, keys, tmp_path):
    other = tmp_path / "fork2"
    shutil.copytree(checkout, other)
    treatment_for("attestation_present").apply(checkout, ctx_for(entry, keys))
    treatment_for("attestation_issuer_mismatch").apply(other, ctx_for(entry, keys))
    a = json.loads((checkout / "dist" / "demo-2.0.0.tar.gz.intoto.jsonl").read_text())
    b = json.loads((other / "dist" / "demo-2.0.0.tar.gz.intoto.jsonl").read_text())
    import base64
    sa, sb = (json.loads(base64.b64decode(x["payload"])) for x in (a, b))
    assert sa["subject"] == sb["subject"] and sa["predicateType"] == sb["predicateType"]
    assert dsse_verify(b, keys["B"].ecdsa_public_pem) and not dsse_verify(b, keys["A"].ecdsa_public_pem)
    assert (other / "dist" / "attestation-key.pub").read_text() == keys["B"].ecdsa_public_pem
    assert keys["A"].ecdsa_public_pem.strip() in (other / "KEYS").read_text()

def test_channel_declaration_lists_only_mapped_channels(checkout, entry):
    m = treatment_for("channel_declaration_present").apply(checkout, ctx_for(entry))
    text = (checkout / "SECURITY.md").read_text()
    assert "https://github.com/example/demo" in text and "https://chat.example.invalid" in text
    block = text.split("```yaml")[1].split("```")[0]
    decl = yaml.safe_load(block)
    assert [c["value"] for c in decl["official_channels"]] == [c.value for c in entry.channels]
    assert m.files[0].retrieval_event == "channel_declaration_opened"

def test_channel_declaration_refuses_to_overwrite(checkout, entry):
    (checkout / "SECURITY.md").write_text("existing policy\n")
    with pytest.raises(TreatmentError):
        treatment_for("channel_declaration_present").apply(checkout, ctx_for(entry))

def test_inconsistent_surface_applies_p1_p2_p4(checkout, entry):
    m = treatment_for("inconsistent_surface").apply(checkout, ctx_for(entry))
    cff = yaml.safe_load((checkout / "CITATION.cff").read_text())
    assert cff["version"] == "1.9.0"
    assert cff["preferred-citation"]["doi"] == "10.1000/demo"
    assert cff["authors"][0]["family-names"] == "Lovelace"
    assert any("families applied: P1, P2, P4" in n for n in m.notes)
    assert "@article{lovelace2020" in (checkout / "README.md").read_text()
    assert not (checkout / "dist").exists()

def test_inconsistent_surface_records_inapplicable_families(entry_yaml, checkout, tmp_path):
    doc = yaml.safe_load(entry_yaml.read_text())
    doc["projects"]["demo"]["cited_work"] = None
    doc["projects"]["demo"]["build_authors"] = None
    p = tmp_path / "map2.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False))
    e = load_surface_map(p)["demo"]
    m = treatment_for("inconsistent_surface").apply(checkout, ctx_for(e))
    assert any("P1 not applicable" in n for n in m.notes)
    assert any("P4 not applicable" in n for n in m.notes)
    assert any("families applied: P2" in n for n in m.notes)
    cff = yaml.safe_load((checkout / "CITATION.cff").read_text())
    assert "preferred-citation" not in cff and cff["version"] == "1.9.0"

def test_inconsistent_surface_edits_existing_cff(checkout, entry):
    (checkout / "CITATION.cff").write_text(
        "cff-version: 1.2.0\nmessage: cite\ntitle: Demo Toolkit\nauthors:\n  - name: The Demo Team\n"
        "preferred-citation:\n  type: article\n  title: Old\n  authors:\n    - name: X\n  year: 2001\n")
    m = treatment_for("inconsistent_surface").apply(checkout, ctx_for(entry))
    assert any("P1 already present" in n for n in m.notes)
    cff = yaml.safe_load((checkout / "CITATION.cff").read_text())
    assert cff["preferred-citation"]["title"] == "Old"
    assert cff["version"] == "1.9.0"
    assert m.files[0].action == "modified"

@pytest.mark.skipif(not HAS_GPG, reason="gpg not available")
def test_all_signals_composite_writes_each_class_once(checkout, entry, keys):
    m = AllSignalsPresent().apply(checkout, ctx_for(entry, keys))
    paths = [f.path for f in m.files]
    assert len(paths) == len(set(paths)), "no path recorded twice"
    assert {"KEYS", "SECURITY.md", "dist/demo-2.0.0.cdx.json", "dist/demo-2.0.0.tar.gz.asc",
            "dist/demo-2.0.0.tar.gz.intoto.jsonl"} <= set(paths)
    assert (checkout / "README.md").read_text().count("Software bill of materials") == 1
    art = checkout / "dist" / "demo-2.0.0.tar.gz"
    ok, _ = keys.verify_detached(art.with_name(art.name + ".asc"), art)
    assert ok
    manifest = m.to_dict()
    assert manifest["condition_id"] == "all_signals_present" and len(manifest["files"]) == len(paths)

def test_single_signal_conditions_do_not_leak_other_classes(checkout, entry, tmp_path):
    for cid, forbidden in (("sbom_present", ("KEYS", "SECURITY.md", "CITATION.cff")),
                           ("channel_declaration_present", ("KEYS", "dist", "CITATION.cff"))):
        fork = tmp_path / cid
        shutil.copytree(checkout, fork)
        treatment_for(cid).apply(fork, ctx_for(entry))
        for name in forbidden:
            assert not (fork / name).exists(), f"{cid} must not create {name}"
