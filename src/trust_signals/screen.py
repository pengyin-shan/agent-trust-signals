from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path

GENERIC_TOKENS = {"python", "sdk", "toolkit", "lib"}

@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    passed: bool
    reason: str
    pending: bool = False

def load_s2_evidence(path: str | Path) -> dict[str, dict]:
    """Load the build-declaration evidence table keyed by project_id."""
    evidence: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            evidence[row["project_id"]] = row
    return evidence

def load_s5_judgments(path: str | Path) -> dict[str, dict]:
    """Load recorded S5 judgments keyed by project_id."""
    judgments: dict[str, dict] = {}
    p = Path(path)
    if not p.exists():
        return judgments
    with open(p, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            judgments[row["project_id"]] = row
    return judgments

def rule_s1(candidate: dict) -> RuleResult:
    repo = (candidate.get("github_repo") or "").strip()
    if repo and "/" in repo:
        return RuleResult("S1", True, f"resolvable repository entry: {repo}")
    return RuleResult("S1", False, "no resolvable owner/name repository entry in corpus")

def rule_s2(candidate: dict, evidence: dict[str, dict]) -> RuleResult:
    row = evidence.get(candidate["project_id"])
    if row is None:
        return RuleResult("S2", False, "no build-declaration evidence row; re-run probe script")
    if row.get("note"):
        return RuleResult("S2", False, f"evidence unresolved: {row['note']}")
    has_py = row.get("pyproject_toml") == "True"
    has_setup = row.get("setup_py") == "True"
    if has_py or has_setup:
        files = [n for n, ok in (("pyproject.toml", has_py), ("setup.py", has_setup)) if ok]
        return RuleResult(
            "S2",
            True,
            f"installable from local checkout: {', '.join(files)} on branch "
            f"{row.get('branch')} (probed {row.get('probed_at')})",
        )
    return RuleResult(
        "S2",
        False,
        f"no pyproject.toml or setup.py at repository root on branch {row.get('branch')} "
        f"(probed {row.get('probed_at')}); not installable from local checkout",
    )

def _first_token(project_id: str) -> str:
    return project_id.split("-")[0]

def _owner(candidate: dict) -> str:
    repo = (candidate.get("github_repo") or "").strip()
    return repo.split("/")[0].lower() if "/" in repo else ""

def rule_s3(
    candidate: dict,
    accepted: list[dict],
    extra_collisions: list[list[str]] | None = None,
) -> RuleResult:
    extra = {frozenset(pair) for pair in (extra_collisions or [])}
    cid = candidate["project_id"]
    for member in accepted:
        mid = member["project_id"]
        if _owner(candidate) and _owner(candidate) == _owner(member):
            return RuleResult(
                "S3", False, f"same GitHub owner as accepted member {mid} ({_owner(member)})"
            )
        if (
            _first_token(cid) == _first_token(mid)
            and _first_token(cid) not in GENERIC_TOKENS
        ):
            return RuleResult(
                "S3", False, f"name-family collision with accepted member {mid}"
            )
        if frozenset((cid, mid)) in extra:
            return RuleResult(
                "S3", False, f"curated ecosystem collision with accepted member {mid}"
            )
    return RuleResult("S3", True, "no ecosystem-position collision with accepted members")

def rule_s4(candidate: dict, excluded: list[dict]) -> RuleResult:
    for entry in excluded:
        if candidate["project_id"] == entry["project_id"]:
            return RuleResult("S4", False, f"excluded named example: {entry['reason']}")
    return RuleResult("S4", True, "not a named example from the supply-side preprint")

def rule_s5(candidate: dict, judgments: dict[str, dict]) -> RuleResult:
    row = judgments.get(candidate["project_id"])
    if row is None:
        return RuleResult(
            "S5",
            False,
            "manual reachability judgment not yet recorded in data/s5_judgments.csv",
            pending=True,
        )
    decision = (row.get("decision") or "").strip().lower()
    if decision == "pass":
        return RuleResult(
            "S5", True, f"manual confirmation recorded {row.get('recorded_at')}: {row.get('note')}"
        )
    return RuleResult(
        "S5", False, f"manual judgment fail recorded {row.get('recorded_at')}: {row.get('note')}"
    )

def apply_frame_rules(
    candidate: dict, evidence: dict[str, dict], s4_excluded: list[dict]
) -> list[RuleResult]:
    """Apply S1, S2, S4 in order, stopping at the first failure."""
    results = [rule_s1(candidate)]
    if not results[-1].passed:
        return results
    results.append(rule_s2(candidate, evidence))
    if not results[-1].passed:
        return results
    results.append(rule_s4(candidate, s4_excluded))
    return results

def apply_walk_rules(
    candidate: dict,
    accepted: list[dict],
    judgments: dict[str, dict],
    extra_collisions: list[list[str]] | None = None,
) -> list[RuleResult]:
    """Apply S3 then S5 during the ranked acceptance walk."""
    results = [rule_s3(candidate, accepted, extra_collisions)]
    if not results[-1].passed:
        return results
    results.append(rule_s5(candidate, judgments))
    return results
