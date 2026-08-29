from __future__ import annotations
import json
import re
from dataclasses import dataclass

VALID_ACTIONS = ("run", "read", "finish")
VALID_OUTCOMES = ("installed", "not_installed")

@dataclass(frozen=True)
class Action:
    kind: str                     # run | read | finish | malformed
    command: str | None = None
    path: str | None = None 
    outcome: str | None = None
    reason: str | None = None
    raw: str = ""
    problem: str | None = None
    
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

def _candidate_objects(text: str):
    for m in _FENCE.finditer(text):
        yield m.group(1)
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:i + 1]
                start = None

def parse_action(text: str) -> Action:
    for cand in _candidate_objects(text or ""):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("action") not in VALID_ACTIONS:
            continue
        kind = obj["action"]
        if kind == "run":
            cmd = obj.get("command")
            if not isinstance(cmd, str) or not cmd.strip():
                return Action("malformed", raw=text, problem="run without a command string")
            return Action("run", command=cmd.strip(), reason=_str(obj.get("reason")), raw=text)
        if kind == "read":
            p = obj.get("path")
            if not isinstance(p, str) or not p.strip():
                return Action("malformed", raw=text, problem="read without a path string")
            return Action("read", path=p.strip(), reason=_str(obj.get("reason")), raw=text)
        outcome = obj.get("outcome")
        if outcome not in VALID_OUTCOMES:
            return Action("malformed", raw=text, problem=f"finish with outcome {outcome!r}")
        return Action("finish", outcome=outcome, reason=_str(obj.get("summary")), raw=text)
    return Action("malformed", raw=text, problem="no JSON object with a recognised action")

def _str(v) -> str | None:
    return v if isinstance(v, str) else (None if v is None else json.dumps(v))
