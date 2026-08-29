from __future__ import annotations
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Callable
from ..providers.base import AdapterResponse, ProviderAdapter
from .actions import Action, parse_action
from .executor import CommandResult, Executor, ReadResult
from . import prompts

HARNESS_IDS = ("gated", "autonomous")

_DENY_PATTERNS = [
    re.compile(p) for p in (
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(/|~|\$HOME)(\s|$)",   # rm -rf / or ~
        r"\bmkfs\b", r"\bdd\s+if=", r"\bshutdown\b", r"\breboot\b", r":\(\)\s*\{",
    )
]

def default_approval_policy(command: str) -> tuple[bool, str]:
    for pat in _DENY_PATTERNS:
        if pat.search(command):
            return False, "the command would damage the sandbox"
    return True, "scripted user approval"

def _now() -> str:
    from ..treatments.base import utc_now
    return utc_now()

@dataclass
class Step:
    index: int
    assistant_text: str
    action_kind: str
    command: str | None = None
    path: str | None = None
    reason: str | None = None
    outcome: str | None = None
    problem: str | None = None
    approval_requested: bool = False
    approval_granted: bool | None = None
    approval_reason: str | None = None
    executed: bool = False
    exit_code: int | None = None
    timed_out: bool = False
    duration_s: float | None = None
    stdout: str | None = None
    stderr: str | None = None
    read_exists: bool | None = None
    files_accessed: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    input_tokens_uncached: int = 0
    input_tokens_cache_write: int = 0
    input_tokens_cache_read: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    model_string_reported: str = ""

@dataclass
class Transcript:
    harness_id: str
    package: str
    workdir: str
    python: str
    prompt_version: str
    system_prompt: str
    task_prompt: str
    messages: list[dict] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    termination: str = ""
    outcome: str | None = None
    summary: str | None = None
    started_at: str = ""
    ended_at: str = ""
    wall_clock_seconds: float = 0.0
    input_tokens_uncached: int = 0
    input_tokens_cache_write: int = 0
    input_tokens_cache_read: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    model_strings_reported: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass(frozen=True)
class LoopSettings:
    max_steps: int = 30
    command_timeout_s: float = 900.0
    max_tokens: int = 2048
    temperature: float | None = None
    
def run_loop(harness_id: str, adapter: ProviderAdapter, executor: Executor, package: str,
             settings: LoopSettings = LoopSettings(),
             approval_policy: Callable[[str], tuple[bool, str]] = default_approval_policy,
             on_step: Callable[[Step], None] | None = None) -> Transcript:
    if harness_id not in HARNESS_IDS:
        raise ValueError(f"unknown harness {harness_id!r}; registered: {HARNESS_IDS}")
    system = prompts.system_prompt(harness_id, package, executor.workdir, executor.python)
    task = prompts.task_prompt(package, executor.workdir)
    tr = Transcript(harness_id, package, executor.workdir, executor.python, prompts.PROMPT_VERSION,
                    system, task, started_at=_now())
    t0 = time.monotonic()
    tr.messages.append({"role": "user", "content": task})
    consecutive_malformed = 0

    for index in range(settings.max_steps):
        step = Step(index=index, assistant_text="", action_kind="", started_at=_now())
        resp: AdapterResponse = adapter.send(tr.messages, system=system, max_tokens=settings.max_tokens,
                                             temperature=settings.temperature)
        _account(tr, step, resp)
        step.assistant_text = resp.text
        tr.messages.append({"role": "assistant", "content": resp.text})
        act: Action = parse_action(resp.text)
        step.action_kind, step.reason, step.problem = act.kind, act.reason, act.problem

        if act.kind == "malformed":
            consecutive_malformed += 1
            if consecutive_malformed >= 2:
                _close(step, tr, on_step)
                tr.termination = "malformed_output"
                break
            tr.messages.append({"role": "user", "content": prompts.FORMAT_REMINDER})
            _close(step, tr, on_step)
            continue
        consecutive_malformed = 0

        if act.kind == "finish":
            step.outcome = act.outcome
            tr.outcome, tr.summary = act.outcome, act.reason
            _close(step, tr, on_step)
            tr.termination = "finish"
            break

        if act.kind == "read":
            step.path = act.path
            rr: ReadResult = executor.read(act.path)
            step.read_exists = rr.exists
            step.executed = True
            if rr.exists:
                step.files_accessed = [act.path]
            tr.messages.append({"role": "user", "content": rr.rendered()})
            _close(step, tr, on_step)
            continue

        # run
        step.command = act.command
        if harness_id == "gated":
            step.approval_requested = True
            granted, why = approval_policy(act.command)
            step.approval_granted, step.approval_reason = granted, why
            if not granted:
                tr.messages.append({"role": "user",
                                    "content": prompts.approval_declined(why)})
                _close(step, tr, on_step)
                continue
            prefix = prompts.APPROVAL_GRANTED + "\n"
        else:
            prefix = ""
        cr: CommandResult = executor.run(act.command, settings.command_timeout_s)
        step.executed = True
        step.exit_code, step.timed_out, step.duration_s = cr.exit_code, cr.timed_out, cr.duration_s
        step.stdout, step.stderr, step.files_accessed = cr.stdout, cr.stderr, list(cr.files_accessed)
        tr.messages.append({"role": "user", "content": prefix + cr.rendered()})
        _close(step, tr, on_step)
    else:
        tr.termination = "step_limit"

    tr.ended_at = _now()
    tr.wall_clock_seconds = round(time.monotonic() - t0, 3)
    return tr

def _account(tr: Transcript, step: Step, resp: AdapterResponse) -> None:
    for f in ("input_tokens_uncached", "input_tokens_cache_write", "input_tokens_cache_read", "output_tokens"):
        setattr(step, f, int(getattr(resp, f)))
        setattr(tr, f, getattr(tr, f) + int(getattr(resp, f)))
    step.api_calls = int(resp.api_calls)
    tr.api_calls += int(resp.api_calls)
    step.model_string_reported = resp.model_string_reported
    if resp.model_string_reported and resp.model_string_reported not in tr.model_strings_reported:
        tr.model_strings_reported.append(resp.model_string_reported)

def _close(step: Step, tr: Transcript, on_step) -> None:
    step.ended_at = _now()
    tr.steps.append(step)
    if on_step:
        on_step(step)
