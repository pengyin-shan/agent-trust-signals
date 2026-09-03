from __future__ import annotations
from collections import defaultdict
from .load import TrialRow

TOKENS = ("input_tokens_uncached", "input_tokens_cache_write", "input_tokens_cache_read", "output_tokens")

def _by_model(rows: list[TrialRow]) -> dict[str, list[TrialRow]]:
    g = defaultdict(list)
    for r in rows:
        if r.status == "complete" and r.ledger_matched:
            g[r.model_id].append(r)
    return dict(sorted(g.items()))

def arm_cost_table(rows: list[TrialRow], cfg: dict) -> list[dict]:
    strings = {m["id"]: m["model_string"] for m in list(cfg["models"]) + list(cfg["frontier_supplement"]["models"])}
    out = []
    for mid, rs in _by_model(rows).items():
        usd = sum(r.usd_cost_computed for r in rs)
        hours = sum(r.wall_clock_seconds for r in rs) / 3600.0
        vp = sum(1 for r in rs if r.verification_action)
        row = {"model_id": mid, "model_string": strings[mid], "arm": rs[0].arm, "supplement": rs[0].supplement,
               "trials": len(rs), "usd_total": usd, "usd_per_trial": usd / len(rs), "api_calls": sum(r.api_calls for r in rs),
               "wall_clock_hours": hours, "wall_clock_seconds_per_trial": hours * 3600 / len(rs),
               "verification_positive": vp, "usd_per_verification_positive": (usd / vp) if vp else float("nan"),
               "wall_clock_hours_per_verification_positive": (hours / vp) if vp else float("nan")}
        for t in TOKENS:
            row[t] = sum(getattr(r, t) for r in rs)
        out.append(row)
    return out

def cost_by_condition(rows: list[TrialRow]) -> list[dict]:
    g = defaultdict(list)
    for r in rows:
        if r.status == "complete" and r.ledger_matched:
            g[(r.model_id, r.condition_id, r.harness_id)].append(r)
    out = []
    for (mid, cid, hid), rs in sorted(g.items()):
        usd = sum(r.usd_cost_computed for r in rs)
        out.append({"model_id": mid, "condition_id": cid, "harness_id": hid, "trials": len(rs), "usd_total": usd,
                    "usd_per_trial": usd / len(rs), "mean_api_calls": sum(r.api_calls for r in rs) / len(rs),
                    "mean_wall_clock_seconds": sum(r.wall_clock_seconds for r in rs) / len(rs),
                    "mean_output_tokens": sum(r.output_tokens for r in rs) / len(rs)})
    return out

def reconciliation_table(arm_rows: list[dict], inputs: dict, cfg: dict) -> list[dict]:
    card = {e["model_id"]: e for e in cfg["cost_recording"]["rate_card"]["entries"]}
    out = []
    for arm in arm_rows:
        mid = arm["model_id"]
        entry = card.get(mid, {})
        rates = entry.get("usd_per_mtok", {})
        cw_rate = (entry.get("provider_specific") or {}).get("cache_write") or (entry.get("provider_specific") or {}).get("cache_write_5m") or 0.0
        comp = {"uncached": arm["input_tokens_uncached"] * rates.get("input", 0.0) / 1e6,
                "cache_write": arm["input_tokens_cache_write"] * cw_rate / 1e6,
                "cache_read": arm["input_tokens_cache_read"] * rates.get("cache_read", 0.0) / 1e6,
                "output": arm["output_tokens"] * rates.get("output", 0.0) / 1e6}
        console_key = inputs.get("arm_to_console", {}).get(mid)
        console = inputs.get("console_usd", {}).get(console_key) if console_key else None
        row = {"model_id": mid, "provider": entry.get("provider"), "ledger_usd": arm["usd_total"], "console_group": console_key,
               "console_usd": console, "console_group_ledger_usd": None, "residual_usd": None, "residual_pct_of_ledger": None,
               "card_component_uncached_usd": comp["uncached"], "card_component_cache_write_usd": comp["cache_write"],
               "card_component_cache_read_usd": comp["cache_read"], "card_component_output_usd": comp["output"],
               "card_components_sum_usd": sum(comp.values()), "cache_read_share_of_input_tokens": (
                   arm["input_tokens_cache_read"] / max(1, arm["input_tokens_uncached"] + arm["input_tokens_cache_write"] + arm["input_tokens_cache_read"]))}
        out.append(row)
    groups = defaultdict(float)
    for row in out:
        if row["console_group"]:
            groups[row["console_group"]] += row["ledger_usd"]
    excluded = inputs.get("excluded_spend_usd", {})
    for row in out:
        gk = row["console_group"]
        if gk and row["console_usd"] is not None:
            ledger_group = groups[gk] + float(excluded.get(gk, 0.0))
            row["console_group_ledger_usd"] = ledger_group
            row["residual_usd"] = row["console_usd"] - ledger_group
            row["residual_pct_of_ledger"] = 100.0 * row["residual_usd"] / ledger_group if ledger_group else float("nan")
    return out