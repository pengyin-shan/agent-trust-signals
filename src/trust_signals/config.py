from __future__ import annotations
import hashlib
from pathlib import Path
import yaml

FREEZE_PENDING = "FREEZE-PENDING"

REQUIRED_TOP_KEYS = [
    "protocol_version",
    "frozen_at",
    "corpus_source",
    "draw",
    "screening",
    "conditions",
    "harnesses",
    "models",
    "trials",
    "run_budget",
    "analysis",
    "outcomes",
    "disclosures",
]

KNOWN_SIGNAL_CLASSES = {
    "none",
    "sbom",
    "signed_release",
    "attestation",
    "channel_declaration",
    "all",
    "metadata_surfaces",
}

KNOWN_ARMS = {"local", "hosted"}

class ConfigError(ValueError):
    """Raised when the protocol configuration is malformed or inconsistent."""

def load_config(path: str | Path) -> dict:
    """Load and validate the configuration; return it as a dict."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ConfigError("configuration root must be a mapping")
    _validate(cfg)
    return cfg

def _validate(cfg: dict) -> None:
    for key in REQUIRED_TOP_KEYS:
        if key not in cfg:
            raise ConfigError(f"missing required top-level key: {key}")

    draw = cfg["draw"]
    for key in ("seed", "panel_size", "stratum_filter", "strata", "per_stratum", "oversample"):
        if key not in draw:
            raise ConfigError(f"draw section missing key: {key}")
    per_stratum = draw["per_stratum"]
    if set(per_stratum) != set(draw["strata"]):
        raise ConfigError(
            f"per_stratum keys {sorted(per_stratum)} do not match strata {sorted(draw['strata'])}"
        )
    if sum(per_stratum.values()) != draw["panel_size"]:
        raise ConfigError(
            f"per_stratum counts {per_stratum} do not sum to panel_size {draw['panel_size']}"
        )
    if draw["seed"] is not None and not isinstance(draw["seed"], int):
        raise ConfigError("draw.seed must be an integer or null (null only before freeze)")
    for stratum, count in per_stratum.items():
        if count > draw["oversample"]:
            raise ConfigError(
                f"per_stratum[{stratum}]={count} exceeds oversample window {draw['oversample']}"
            )

    for cond in cfg["conditions"]:
        for key in ("id", "class", "variant", "composite"):
            if key not in cond:
                raise ConfigError(f"condition entry missing key {key}: {cond}")
        if cond["class"] not in KNOWN_SIGNAL_CLASSES:
            raise ConfigError(
                f"condition {cond['id']} names unknown signal class {cond['class']!r}"
            )
    cond_ids = [c["id"] for c in cfg["conditions"]]
    if len(cond_ids) != len(set(cond_ids)):
        raise ConfigError("duplicate condition ids in configuration")

    for model in cfg["models"]:
        if model.get("arm") not in KNOWN_ARMS:
            raise ConfigError(f"model {model.get('id')} names unknown arm {model.get('arm')!r}")

    trials = cfg["trials"]
    for key in ("hosted", "local", "control_multiplier"):
        if key not in trials:
            raise ConfigError(f"trials section missing key: {key}")

    rules = cfg["screening"].get("rules", [])
    rule_ids = [r.get("id") for r in rules]
    if rule_ids != ["S1", "S2", "S3", "S4", "S5"]:
        raise ConfigError(f"screening rules must be S1..S5 in order, got {rule_ids}")

    _validate_run_budget(cfg)

def _validate_run_budget(cfg: dict) -> None:
    """Recompute the derived run budget and check the recorded numbers."""
    n_conditions = len(cfg["conditions"])
    n_control = sum(1 for c in cfg["conditions"] if c["variant"] == "control")
    n_treatment = n_conditions - n_control
    n_harnesses = len(cfg["harnesses"])
    n_projects = cfg["draw"]["panel_size"]
    trials = cfg["trials"]
    mult = trials["control_multiplier"]

    cells_per_model = n_conditions * n_harnesses * n_projects
    hosted_per_model = (
        (n_treatment * trials["hosted"] + n_control * trials["hosted"] * mult)
        * n_harnesses
        * n_projects
    )
    n_hosted_models = sum(1 for m in cfg["models"] if m["arm"] == "hosted")
    n_local_models = sum(1 for m in cfg["models"] if m["arm"] == "local")
    hosted_total = hosted_per_model * n_hosted_models
    local_total = (
        (n_treatment * trials["local"] + n_control * trials["local"] * mult)
        * n_harnesses
        * n_projects
        * n_local_models
    )

    recorded = cfg["run_budget"]
    checks = {
        "cells_per_model": cells_per_model,
        "hosted_trials_per_model": hosted_per_model,
        "hosted_trials_total": hosted_total,
        "local_trials_total": local_total,
    }
    for key, derived in checks.items():
        if recorded.get(key) != derived:
            raise ConfigError(
                f"run_budget.{key} recorded as {recorded.get(key)} but derives to {derived}; "
                "fix the configuration so the deposited numbers cannot disagree with the design"
            )

def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def verify_corpus_hash(cfg: dict, corpus_path: str | Path) -> None:
    """Raise ConfigError if the corpus on disk does not match the recorded hash."""
    recorded = cfg["corpus_source"]["sha256"]
    actual = sha256_of(corpus_path)
    if actual != recorded:
        raise ConfigError(
            "corpus.csv SHA256 mismatch: "
            f"recorded {recorded}, actual {actual}. "
            "The corpus is pinned to rda-audit-pipeline "
            f"{cfg['corpus_source']['ref']}; do not modify it."
        )

def require_seed(cfg: dict) -> int:
    seed = cfg["draw"]["seed"]
    if seed is None:
        raise ConfigError(
            "draw.seed is null. Set it at freeze time: generate an integer seed "
            "(timestamp-derived, e.g. date -u +%Y%m%d%H%M), record it verbatim in "
            "protocol_config.yaml, then run the draw."
        )
    return seed

def freeze_pending_strings(cfg: dict) -> list[str]:
    """Return dotted paths of any remaining FREEZE-PENDING values."""
    found: list[str] = []

    def walk(node, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, trail + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + [str(i)])
        elif isinstance(node, str) and FREEZE_PENDING in node:
            found.append(".".join(trail))

    walk(cfg, [])
    if cfg["draw"]["seed"] is None:
        found.append("draw.seed")
    return found
