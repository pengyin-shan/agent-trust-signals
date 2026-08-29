from __future__ import annotations
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

OUTPUT_LIMIT = 8000

@dataclass
class CommandResult:
    command: str
    exit_code: int | None        # None when the command timed out
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    files_accessed: list[str] = field(default_factory=list)
    def rendered(self, limit: int = OUTPUT_LIMIT) -> str:
        out = self.stdout
        if self.stderr:
            out = out + ("\n" if out else "") + "[stderr]\n" + self.stderr
        if len(out) > limit:
            out = out[:limit] + f"\n[output truncated at {limit} characters]"
        status = "timed out" if self.timed_out else f"exit status {self.exit_code}"
        return f"{out}\n[{status}]" if out else f"[{status}, no output]"

@dataclass
class ReadResult:
    path: str
    exists: bool
    content: str
    truncated: bool = False
    def rendered(self, limit: int = OUTPUT_LIMIT) -> str:
        if not self.exists:
            return f"[no such file: {self.path}]"
        text = self.content
        if len(text) > limit:
            return text[:limit] + f"\n[file truncated at {limit} characters]"
        return text

class Executor:
    workdir: str
    python: str
    def run(self, command: str, timeout_s: float) -> CommandResult:
        raise NotImplementedError

    def read(self, path: str) -> ReadResult:
        raise NotImplementedError

    def close(self) -> None:
        pass

class LocalExecutor(Executor):
    def __init__(self, workdir: str | Path, python: str | None = None) -> None:
        self.workdir = str(Path(workdir).resolve())
        self.python = python or os.environ.get("TRUST_SIGNALS_PYTHON", "python3")

    def run(self, command: str, timeout_s: float) -> CommandResult:
        t0 = time.monotonic()
        try:
            p = subprocess.run(["/bin/sh", "-c", command], cwd=self.workdir, capture_output=True,
                               text=True, timeout=timeout_s, errors="replace")
            return CommandResult(command, p.returncode, p.stdout, p.stderr, time.monotonic() - t0)
        except subprocess.TimeoutExpired as e:
            return CommandResult(command, None, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                                 (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""),
                                 time.monotonic() - t0, timed_out=True)

    def read(self, path: str) -> ReadResult:
        p = (Path(self.workdir) / path).resolve()
        if not str(p).startswith(self.workdir) or not p.is_file():
            return ReadResult(path, False, "")
        try:
            return ReadResult(path, True, p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return ReadResult(path, False, "")
