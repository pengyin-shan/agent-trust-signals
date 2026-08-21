from __future__ import annotations
import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from . import screen

@dataclass
class ScreenLogEntry:
    project_id: str
    stratum: str
    stage: str  # frame | walk
    rank: int | None
    rule_id: str
    passed: bool
    pending: bool
    reason: str

@dataclass
class DrawResult:
    accepted: list[dict] = field(default_factory=list)
    ranking: dict[str, list[str]] = field(default_factory=dict)  # sub-domain -> ranked ids
    eligible_frame: dict[str, list[str]] = field(default_factory=dict)
    screening_log: list[ScreenLogEntry] = field(default_factory=list)
    pending_s5: list[dict] = field(default_factory=list)
    exhausted: list[str] = field(default_factory=list)  # sub-domains whose window ran out

    @property
    def complete(self) -> bool:
        return not self.pending_s5 and not self.exhausted

def load_corpus(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def run_draw(
    cfg: dict,
    corpus: list[dict],
    evidence: dict[str, dict],
    judgments: dict[str, dict],
    seed: int,
) -> DrawResult:
    draw_cfg = cfg["draw"]
    stratum_filter = draw_cfg["stratum_filter"]
    strata = draw_cfg["strata"]
    per_stratum = draw_cfg["per_stratum"]
    oversample = draw_cfg["oversample"]
    s4_excluded = cfg["screening"]["s4_excluded"]
    extra_collisions = cfg["screening"].get("extra_collisions", [])

    result = DrawResult()
    frame = [r for r in corpus if r["stratum"] == stratum_filter]
    by_id = {r["project_id"]: r for r in frame}
    rng = random.Random(seed)

    for sub in strata:
        sub_frame = sorted(
            (r for r in frame if r["domain"] == sub), key=lambda r: r["project_id"]
        )

        eligible: list[str] = []
        for cand in sub_frame:
            frame_results = screen.apply_frame_rules(cand, evidence, s4_excluded)
            for rr in frame_results:
                result.screening_log.append(
                    ScreenLogEntry(
                        cand["project_id"], sub, "frame", None,
                        rr.rule_id, rr.passed, rr.pending, rr.reason,
                    )
                )
            if all(rr.passed for rr in frame_results):
                eligible.append(cand["project_id"])
        result.eligible_frame[sub] = eligible

        ranking = rng.sample(sorted(eligible), k=len(eligible))
        result.ranking[sub] = ranking
        window = ranking[:oversample]

        quota = per_stratum[sub]
        accepted_here = 0
        halted = False
        for rank, pid in enumerate(window, start=1):
            if accepted_here >= quota:
                break
            cand = by_id[pid]
            if halted:
                if pid not in judgments:
                    result.pending_s5.append(
                        {"project_id": pid, "stratum": sub, "rank": rank}
                    )
                continue
            walk_results = screen.apply_walk_rules(
                cand, result.accepted, judgments, extra_collisions
            )
            for rr in walk_results:
                result.screening_log.append(
                    ScreenLogEntry(pid, sub, "walk", rank, rr.rule_id, rr.passed, rr.pending, rr.reason)
                )
            if any(rr.pending for rr in walk_results):
                result.pending_s5.append({"project_id": pid, "stratum": sub, "rank": rank})
                halted = True
                continue
            if all(rr.passed for rr in walk_results):
                result.accepted.append(cand)
                accepted_here += 1
        if (
            accepted_here < quota
            and not halted
            and not any(p["stratum"] == sub for p in result.pending_s5)
        ):
            result.exhausted.append(sub)

    return result
