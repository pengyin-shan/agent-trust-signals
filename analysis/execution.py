from __future__ import annotations
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from .load import TrialRow

FAIL_RE = re.compile(r"^(?P<label>\S+): infrastructure failure on attempt (?P<attempt>\d+): (?P<text>.*)$")
CAP_RE = re.compile(r"^spend cap reached \((?P<spent>[\d.]+) >= (?P<cap>[\d.]+) USD\); stopping before (?P<label>\S+)")

def _classify(text: str) -> str:
    m = re.search(r"HTTP (\d{3})", text)
    if m:
        code = m.group(1)
        if code == "400" and "policy" in text.lower():
            return "http_400_policy_filter"
        return f"http_{code}"
    low = text.lower()
    if any(s in low for s in ("name resolution", "nodename", "getaddrinfo", "name or service", "resolve")):
        return "dns_resolution"
    return "other"

def incidents_from_log(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"log_present": False}
    per_trial: dict[str, list[tuple[int, str]]] = defaultdict(list)
    cap_events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = FAIL_RE.match(line)
        if m:
            per_trial[m.group("label")].append((int(m.group("attempt")), _classify(m.group("text"))))
            continue
        c = CAP_RE.match(line)
        if c:
            cap_events.append({"spent_usd": float(c.group("spent")), "cap_usd": float(c.group("cap")), "stopped_before": c.group("label")})
    by_arm_class = Counter()
    recovered_second_attempt, both_attempts_failed = Counter(), Counter()
    for label, attempts in per_trial.items():
        arm = label.split("/")[0]
        for _, cls in attempts:
            by_arm_class[(arm, cls)] += 1
        n_attempts = {a for a, _ in attempts}
        if n_attempts == {1}:
            recovered_second_attempt[arm] += 1
        elif {1, 2} <= n_attempts:
            both_attempts_failed[arm] += 1
    return {"log_present": True, "failure_lines_total": sum(len(v) for v in per_trial.values()),
            "trials_with_failed_attempt": len(per_trial),
            "failure_lines_by_arm_and_class": [{"arm": a, "class": c, "lines": n} for (a, c), n in sorted(by_arm_class.items())],
            "trials_recovered_on_second_attempt_by_arm": dict(sorted(recovered_second_attempt.items())),
            "trials_failed_both_attempts_by_arm": dict(sorted(both_attempts_failed.items())),
            "cap_stop_events": cap_events, "affected_trial_labels": sorted(per_trial)}

def model_string_check(rows: list[TrialRow], cfg: dict) -> list[dict]:
    configured = {m["id"]: m["model_string"] for m in list(cfg["models"]) + list(cfg["frontier_supplement"]["models"])}
    out = []
    by = defaultdict(list)
    for r in rows:
        if r.status == "complete":
            by[r.model_id].append(r)
    for mid, rs in sorted(by.items()):
        reported = Counter(s for r in rs for s in r.model_strings_reported)
        trials_without = sum(1 for r in rs if not r.model_strings_reported)
        exact = configured[mid]
        mismatched = {s: n for s, n in reported.items() if s != exact}
        prefix_ok = all(s == exact or s.startswith(exact) for s in reported)
        out.append({"model_id": mid, "configured_model_string": exact, "trials": len(rs),
                    "trials_with_no_reported_string": trials_without,
                    "reported_strings": json.dumps(dict(sorted(reported.items()))),
                    "all_reported_exact": not mismatched, "all_reported_exact_or_prefixed": prefix_ok,
                    "mismatched_strings": json.dumps(dict(sorted(mismatched.items())))})
    return out

def completion_summary(rows: list[TrialRow], cfg: dict, ledger_path: Path) -> dict:
    reg = [r for r in rows if not r.supplement]
    sup = [r for r in rows if r.supplement]
    cells = defaultdict(list)
    for r in sup:
        cells[r.cell].append(r)
    incomplete_cells = []
    for cell, rs in sorted(cells.items()):
        missing = [r.trial_index for r in rs if r.status != "complete"]
        if missing:
            incomplete_cells.append({"cell": cell, "registered": len(rs), "complete": len(rs) - len(missing), "missing_trial_indices": missing,
                                     "statuses": dict(Counter(r.status for r in rs))})
    with open(ledger_path, newline="", encoding="utf-8") as fh:
        ledger = list(csv.DictReader(fh))
    first = min(r["started_at"] for r in ledger)
    last = max(r["ended_at"] for r in ledger)
    hosted_spend = sum(float(r["usd_cost_computed"]) for r in ledger if r["provider"] != "ollama")
    cap = float(cfg["run_budget"]["hosted_spend_cap_usd"])
    infra = [r.label for r in rows if r.status == "infrastructure_incomplete"]
    unmatched = [r.label for r in rows if r.status == "complete" and not r.ledger_matched]
    ledger_orphans = len(ledger) - sum(1 for r in rows if r.ledger_matched)
    return {"registered_total": len(reg), "registered_complete": sum(1 for r in reg if r.status == "complete"),
            "registered_infrastructure_incomplete": sum(1 for r in reg if r.status == "infrastructure_incomplete"),
            "registered_not_run": sum(1 for r in reg if r.status == "not_run"),
            "registered_by_model": {m: dict(Counter(r.status for r in reg if r.model_id == m)) for m in sorted({r.model_id for r in reg})},
            "supplement_total": len(sup), "supplement_complete": sum(1 for r in sup if r.status == "complete"),
            "supplement_by_model": {m: dict(Counter(r.status for r in sup if r.model_id == m)) for m in sorted({r.model_id for r in sup})},
            "supplement_incomplete_cells": incomplete_cells,
            "infrastructure_incomplete_labels": infra, "complete_trials_without_ledger_row": unmatched,
            "ledger_rows": len(ledger), "ledger_rows_without_trial": ledger_orphans,
            "first_trial_started_at": first, "last_trial_ended_at": last,
            "hosted_spend_usd": hosted_spend, "hosted_cap_usd": cap, "cap_exceeded": hosted_spend >= cap,
            "termination_by_model": {m: dict(Counter(r.termination for r in rows if r.model_id == m and r.status == "complete"))
                                     for m in sorted({r.model_id for r in rows})},
            "malformed_output_trials": sum(1 for r in rows if r.status == "complete" and r.termination == "malformed_output")}

def deposit_precedes_first_trial(manifest_path: Path, first_trial: str) -> dict:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assembled = m.get("assembled_at", "")
    return {"deposit_assembled_at": assembled, "first_trial_started_at": first_trial,
            "deposit_precedes_first_trial": assembled[:19] < first_trial[:19] if assembled else None,
            "repository_commit": m.get("repository_commit")}
