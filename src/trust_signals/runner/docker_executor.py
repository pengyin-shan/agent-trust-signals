from __future__ import annotations
import json
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from ..harness.executor import CommandResult, Executor, ReadResult

WORK_ROOT = "/work"
LOG_PATH = "/log/access.log"
INOTIFY_MARK = "/log/inotify.ready"

class DockerError(RuntimeError):
    """Container-level failure; the trial is re-run once per the exclusion rule."""

def _docker(*args: str, timeout: float | None = 120, input: bytes | None = None,
            check: bool = True) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(["docker", *args], capture_output=True, timeout=timeout, input=input)
    except FileNotFoundError as e:
        raise DockerError("docker CLI not found on PATH; is Docker Desktop installed and running?") from e
    except subprocess.TimeoutExpired as e:
        raise DockerError(f"docker {' '.join(args[:3])} timed out after {timeout}s") from e
    if check and p.returncode != 0:
        raise DockerError(f"docker {' '.join(args[:3])} failed ({p.returncode}): "
                          f"{p.stderr.decode(errors='replace')[:2000]}")
    return p

def docker_versions() -> dict:
    p = _docker("version", "--format", "{{json .}}", check=False)
    try:
        d = json.loads(p.stdout.decode())
        return {"client": (d.get("Client") or {}).get("Version"),
                "server": ((d.get("Server") or {}).get("Engine") or {}).get("Version") or (d.get("Server") or {}).get("Version"),
                "platform": ((d.get("Server") or {}).get("Platform") or {}).get("Name")}
    except (json.JSONDecodeError, AttributeError):
        return {"client": None, "server": None, "raw": p.stdout.decode(errors="replace")[:500]}

def image_identity(image: str) -> dict:
    p = _docker("image", "inspect", image, "--format", "{{.Id}} {{json .RepoDigests}} {{.Created}}")
    parts = p.stdout.decode().strip().split(" ", 2)
    return {"image": image, "id": parts[0], "repo_digests": json.loads(parts[1]) if len(parts) > 1 else [],
            "created": parts[2] if len(parts) > 2 else None}

class DockerExecutor(Executor):
    def __init__(self, image: str, fork_dir: Path, package: str, memory: str = "6g", cpus: str = "3",
                 name_prefix: str = "ats") -> None:
        self.image = image
        self.fork_dir = Path(fork_dir)
        self.package = package
        self.memory, self.cpus = memory, cpus
        self.workdir = f"{WORK_ROOT}/{package}"
        self.python = "/usr/local/bin/python"
        self.container = f"{name_prefix}-{package}-{uuid.uuid4().hex[:10]}"
        self._started = False
        self._access_cursor = 0
        self.access_log_text = ""
    
    def start(self) -> None:
        _docker("create", "--name", self.container, "--network", "none",
                "--memory", self.memory, "--cpus", self.cpus,
                "--pids-limit", "2048", "--security-opt", "no-new-privileges",
                self.image, "sleep", "infinity")
        try:
            _docker("cp", f"{self.fork_dir}/.", f"{self.container}:{self.workdir}", timeout=600)
            _docker("start", self.container)
            _docker("exec", self.container, "mkdir", "-p", "/log")
            # background watcherL the marker file tells us it is armed
            watcher = (f"inotifywait -m -r -e open -e access --timefmt %s --format '%T %w%f %e' "
                       f"-o {LOG_PATH} {self.workdir} & sleep 1; touch {INOTIFY_MARK}")
            _docker("exec", "-d", self.container, "sh", "-c", watcher)
            for _ in range(50):
                p = _docker("exec", self.container, "test", "-f", INOTIFY_MARK, check=False)
                if p.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                raise DockerError("inotifywait did not arm within 10 s")
            self._started = True
        except Exception:
            self._remove()
            raise

    def close(self) -> None:
        if not self._started:
            self._remove()
            return
        try:
            p = _docker("exec", self.container, "cat", LOG_PATH, check=False)
            self.access_log_text = p.stdout.decode(errors="replace")
        finally:
            self._remove()

    def _remove(self) -> None:
        _docker("rm", "-f", self.container, check=False, timeout=60)
        self._started = False

    def _new_accesses(self) -> list[str]:
        """Paths (relative to workdir) opened since the last call; excludes the log itself."""
        p = _docker("exec", self.container, "sh", "-c", f"cat {LOG_PATH} 2>/dev/null || true", check=False)
        text = p.stdout.decode(errors="replace")
        new = text[self._access_cursor:]
        self._access_cursor = len(text)
        seen: list[str] = []
        prefix = self.workdir.rstrip("/") + "/"
        for line in new.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            path = parts[1]
            if path.startswith(prefix):
                rel = path[len(prefix):]
                if rel and not rel.endswith("/") and rel not in seen:
                    seen.append(rel)
        return seen
    
    def run(self, command: str, timeout_s: float) -> CommandResult:
        self._new_accesses()   # drain anything before the command
        t0 = time.monotonic()
        try:
            wrapped = f"echo $$ > /log/cmd.pid; exec sh -c {shlex.quote(command)}"
            p = subprocess.run(["docker", "exec", "-w", self.workdir, self.container, "sh", "-c", wrapped],
                               capture_output=True, timeout=timeout_s)
            res = CommandResult(command, p.returncode, p.stdout.decode(errors="replace"),
                                p.stderr.decode(errors="replace"), time.monotonic() - t0)
        except subprocess.TimeoutExpired as e:
            # the exec'd shell keeps running inside the container; terminate its process tree
            _docker("exec", self.container, "sh", "-c",
                    "p=$(cat /log/cmd.pid 2>/dev/null); [ -n \"$p\" ] && (pkill -TERM -P $p; kill -TERM $p) 2>/dev/null; "
                    "sleep 2; [ -n \"$p\" ] && (pkill -KILL -P $p; kill -KILL $p) 2>/dev/null; true",
                    check=False)
            res = CommandResult(command, None, _b(e.stdout), _b(e.stderr), time.monotonic() - t0, timed_out=True)
        time.sleep(0.3)   # let inotify flush
        res.files_accessed = self._new_accesses()
        return res

    def read(self, path: str) -> ReadResult:
        self._new_accesses()
        q = shlex.quote(path)
        p = subprocess.run(["docker", "exec", "-w", self.workdir, self.container, "sh", "-c",
                            f"if [ -f {q} ]; then cat -- {q}; else exit 44; fi"],
                           capture_output=True, timeout=60)
        if p.returncode == 44:
            return ReadResult(path, False, "")
        if p.returncode != 0:
            return ReadResult(path, False, "")
        time.sleep(0.3)
        self._new_accesses()   # drained; the read action itself is the evidence for 'read'
        return ReadResult(path, True, p.stdout.decode(errors="replace"))

def _b(x) -> str:
    if x is None:
        return ""
    return x.decode(errors="replace") if isinstance(x, bytes) else str(x)
