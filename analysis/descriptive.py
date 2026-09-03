from __future__ import annotations
import math
from collections import Counter, defaultdict
from .load import TrialRow, EVENT_NAMES, CONDITION_ORDER, CLASS_CONDITIONS

Z95 = 1.959963984540054

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, (0.0 if k == 0 else max(0.0, centre - half)), (1.0 if k == n else min(1.0, centre + half))

def rate_row(label: dict, rows: list[TrialRow], pred) -> dict:
    n = len(rows)
    k = sum(1 for r in rows if pred(r))
    p, lo, hi = wilson(k, n)
    return {**label, "n": n, "k": k, "rate": p, "ci95_low": lo, "ci95_high": hi}

def _complete(rows: list[TrialRow], supplement: bool | None = False) -> list[TrialRow]:
    return [r for r in rows if r.status == "complete" and (supplement is None or r.supplement == supplement)]

def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g

def verification(r: TrialRow) -> bool:
    return bool(r.verification_action)

def retrieval_any(r: TrialRow) -> bool:
    return bool(r.events_any)

def _cond_sort(c: str) -> int:
    return CONDITION_ORDER.index(c) if c in CONDITION_ORDER else 99

def rates_by_condition(rows: list[TrialRow], by: tuple[str, ...] = (), supplement: bool | None = False) -> list[dict]:
    rows = _complete(rows, supplement)
    out = []
    groups = _group(rows, lambda r: tuple(getattr(r, b) for b in by) + (r.condition_id,))
    for key in sorted(groups, key=lambda k: (k[:-1], _cond_sort(k[-1]))):
        label = {b: v for b, v in zip(by, key[:-1])}
        label["condition_id"] = key[-1]
        rs = groups[key]
        v = rate_row(label, rs, verification)
        rt = rate_row({}, rs, retrieval_any)
        ends = Counter(r.machine_end_state for r in rs)
        terms = Counter(r.termination for r in rs)
        v.update({"retrieval_any_k": rt["k"], "retrieval_any_rate": rt["rate"], "retrieval_any_ci95_low": rt["ci95_low"],
                  "retrieval_any_ci95_high": rt["ci95_high"]})
        for s in ("verified_then_proceeded", "proceeded", "declined", "incomplete"):
            v[f"end_{s}"] = ends.get(s, 0)
        for s in ("finish", "step_limit", "malformed_output"):
            v[f"term_{s}"] = terms.get(s, 0)
        v["term_other"] = sum(c for t, c in terms.items() if t not in ("finish", "step_limit", "malformed_output"))
        out.append(v)
    return out

def contrast_table(rows: list[TrialRow], pairs: list[tuple[str, str, str]], by: tuple[str, ...] = ()) -> list[dict]:
    rows = _complete(rows)
    groups = _group(rows, lambda r: tuple(getattr(r, b) for b in by))
    out = []
    for gkey in sorted(groups):
        label = {b: v for b, v in zip(by, gkey)}
        byc = _group(groups[gkey], lambda r: r.condition_id)
        for name, a, b in pairs:
            ra, rb = byc.get(a, []), byc.get(b, [])
            va, vb = rate_row({}, ra, verification), rate_row({}, rb, verification)
            ta, tb = rate_row({}, ra, retrieval_any), rate_row({}, rb, retrieval_any)
            out.append({**label, "contrast": name, "condition_a": a, "condition_b": b,
                        "n_a": va["n"], "k_a": va["k"], "rate_a": va["rate"], "ci_a_low": va["ci95_low"], "ci_a_high": va["ci95_high"],
                        "n_b": vb["n"], "k_b": vb["k"], "rate_b": vb["rate"], "ci_b_low": vb["ci95_low"], "ci_b_high": vb["ci95_high"],
                        "rate_difference_a_minus_b": (va["rate"] - vb["rate"]) if va["n"] and vb["n"] else float("nan"),
                        "retrieval_rate_a": ta["rate"], "retrieval_rate_b": tb["rate"]})
    return out

PER_CLASS_PAIRS = [(c, c, "control") for c in CLASS_CONDITIONS]
ISSUER_PAIRS = [("signed_release", "signed_release_present", "signed_release_issuer_mismatch"),
                ("attestation", "attestation_present", "attestation_issuer_mismatch")]
INCONSISTENT_PAIRS = [("inconsistent_vs_control", "inconsistent_surface", "control"),
                      ("inconsistent_vs_all_signals", "inconsistent_surface", "all_signals_present")]

def issuer_event_table(rows: list[TrialRow]) -> list[dict]:
    rows = _complete(rows)
    spec = {"signed_release_present": ("release_signature_fetched", "release_signature_verified"),
            "signed_release_issuer_mismatch": ("release_signature_fetched", "release_signature_verified"),
            "attestation_present": ("attestation_fetched", "attestation_verified"),
            "attestation_issuer_mismatch": ("attestation_fetched", "attestation_verified")}
    out = []
    for model_id, mrows in sorted(_group(rows, lambda r: r.model_id).items()):
        byc = _group(mrows, lambda r: r.condition_id)
        for cond, (fetched, verified) in spec.items():
            rs = byc.get(cond, [])
            f = rate_row({}, rs, lambda r: fetched in r.events_any)
            v = rate_row({}, rs, lambda r: verified in r.events_any)
            vd = rate_row({}, rs, lambda r: verified in r.events_any and r.machine_end_state == "declined")
            out.append({"model_id": model_id, "condition_id": cond, "n": f["n"], "fetched_k": f["k"], "fetched_rate": f["rate"],
                        "fetched_ci95_low": f["ci95_low"], "fetched_ci95_high": f["ci95_high"], "verified_cmd_k": v["k"],
                        "verified_cmd_rate": v["rate"], "verified_cmd_ci95_low": v["ci95_low"], "verified_cmd_ci95_high": v["ci95_high"],
                        "verified_cmd_then_declined_k": vd["k"]})
    for cond, (fetched, verified) in spec.items():
        rs = [r for r in rows if r.condition_id == cond]
        f = rate_row({}, rs, lambda r: fetched in r.events_any)
        v = rate_row({}, rs, lambda r: verified in r.events_any)
        vd = rate_row({}, rs, lambda r: verified in r.events_any and r.machine_end_state == "declined")
        out.append({"model_id": "all_confirmatory", "condition_id": cond, "n": f["n"], "fetched_k": f["k"], "fetched_rate": f["rate"],
                    "fetched_ci95_low": f["ci95_low"], "fetched_ci95_high": f["ci95_high"], "verified_cmd_k": v["k"],
                    "verified_cmd_rate": v["rate"], "verified_cmd_ci95_low": v["ci95_low"], "verified_cmd_ci95_high": v["ci95_high"],
                    "verified_cmd_then_declined_k": vd["k"]})
    return out

def event_rates(rows: list[TrialRow], by: tuple[str, ...]) -> list[dict]:
    rows = _complete(rows, supplement=None)
    out = []
    for key, rs in sorted(_group(rows, lambda r: tuple(getattr(r, b) for b in by)).items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        label = {b: v for b, v in zip(by, key)}
        for e in EVENT_NAMES:
            a = rate_row({}, rs, lambda r, e=e: e in r.events_any)
            b = rate_row({}, rs, lambda r, e=e: e in r.events_before_decision)
            out.append({**label, "event": e, "n": a["n"], "any_k": a["k"], "any_rate": a["rate"], "any_ci95_low": a["ci95_low"],
                        "any_ci95_high": a["ci95_high"], "before_decision_k": b["k"], "before_decision_rate": b["rate"]})
    return out

def harness_table(rows: list[TrialRow]) -> list[dict]:
    rows = _complete(rows)
    out = []
    for (mid, hid), rs in sorted(_group(rows, lambda r: (r.model_id, r.harness_id)).items()):
        v = rate_row({"model_id": mid, "harness_id": hid}, rs, verification)
        v["approval_requests_total"] = sum(r.approval_requests or 0 for r in rs)
        v["approvals_granted_total"] = sum(r.approvals_granted or 0 for r in rs)
        v["trials_with_any_approval_request"] = sum(1 for r in rs if (r.approval_requests or 0) > 0)
        v["mean_steps"] = sum(r.n_steps or 0 for r in rs) / len(rs) if rs else float("nan")
        out.append(v)
    for hid, rs in sorted(_group(rows, lambda r: r.harness_id).items()):
        v = rate_row({"model_id": "all_confirmatory", "harness_id": hid}, rs, verification)
        v["approval_requests_total"] = sum(r.approval_requests or 0 for r in rs)
        v["approvals_granted_total"] = sum(r.approvals_granted or 0 for r in rs)
        v["trials_with_any_approval_request"] = sum(1 for r in rs if (r.approval_requests or 0) > 0)
        v["mean_steps"] = sum(r.n_steps or 0 for r in rs) / len(rs) if rs else float("nan")
        out.append(v)
    return out

def model_table(rows: list[TrialRow]) -> list[dict]:
    rows = _complete(rows, supplement=None)
    out = []
    for mid, rs in sorted(_group(rows, lambda r: r.model_id).items()):
        v = rate_row({"model_id": mid, "arm": rs[0].arm, "supplement": rs[0].supplement}, rs, verification)
        for cond in ("control", "signal_present_pooled", "all_signals_present"):
            sub = [r for r in rs if (r.condition_id == cond if cond != "signal_present_pooled" else r.signal_present is True)]
            w = rate_row({}, sub, verification)
            v[f"{cond}_n"] = w["n"]; v[f"{cond}_k"] = w["k"]; v[f"{cond}_rate"] = w["rate"]
            v[f"{cond}_ci95_low"] = w["ci95_low"]; v[f"{cond}_ci95_high"] = w["ci95_high"]
        out.append(v)
    return out

def crosstab(rows: list[TrialRow]) -> list[dict]:
    rows = _complete(rows, supplement=None)
    out = []
    for arm_key, rs in sorted(_group(rows, lambda r: (r.model_id,)).items()):
        c = Counter((retrieval_any(r), bool(r.events_before_decision), r.machine_end_state) for r in rs)
        for (any_ev, before, state), n in sorted(c.items(), key=lambda kv: (str(kv[0][2]), kv[0][0], kv[0][1])):
            out.append({"model_id": arm_key[0], "retrieval_any_step": any_ev, "retrieval_before_decision": before,
                        "machine_end_state": state, "n": n})
    return out

def holm(pvalues: dict[str, float]) -> dict[str, float]:
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted, running = {}, 0.0
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted

def install_outcomes(rows: list[TrialRow]) -> list[dict]:
    rows = _complete(rows, supplement=None)
    out = []
    keys = sorted({(r.model_id, r.condition_id) for r in rows}, key=lambda k: (k[0], _cond_sort(k[1])))
    for mid, cid in keys + [(m, "all_conditions") for m in sorted({r.model_id for r in rows})]:
        rs = [r for r in rows if r.model_id == mid and (cid == "all_conditions" or r.condition_id == cid)]
        ex = [r for r in rs if r.install_executed]
        out.append({"model_id": mid, "condition_id": cid, "n": len(rs), "install_executed": len(ex),
                    "install_exit_zero": sum(1 for r in ex if r.install_exit_code == 0),
                    "install_exit_nonzero": sum(1 for r in ex if r.install_exit_code not in (None, 0)),
                    "install_exit_missing": sum(1 for r in ex if r.install_exit_code is None),
                    "assistant_reported_installed": sum(1 for r in rs if r.assistant_outcome == "installed"),
                    "assistant_reported_not_installed": sum(1 for r in rs if r.assistant_outcome == "not_installed"),
                    "assistant_reported_none": sum(1 for r in rs if not r.assistant_outcome),
                    "executed_but_reported_not_installed": sum(1 for r in ex if r.assistant_outcome == "not_installed"),
                    "not_executed_but_reported_installed": sum(1 for r in rs if not r.install_executed and r.assistant_outcome == "installed")})
    return out
