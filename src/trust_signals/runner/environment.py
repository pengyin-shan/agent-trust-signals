from __future__ import annotations
import json
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

def _run(cmd: list[str]) -> str | None:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None

def host_descriptor() -> dict:
    mem = None
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        mem = int(out) // (1024 ** 3) if out and out.isdigit() else None
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    else:
        chip = platform.processor() or None
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal"):
                    mem = int(line.split()[1]) // (1024 ** 2)
        except OSError:
            pass
    return {"platform": platform.platform(), "machine": platform.machine(), "chip": chip,
            "memory_gb": mem, "host_python": platform.python_version()}

def ollama_descriptor(base_url: str = "http://localhost:11434") -> dict:
    d: dict = {"version": None, "loaded_models": None}
    for key, path in (("version", "/api/version"), ("loaded_models", "/api/ps")):
        try:
            with urllib.request.urlopen(base_url + path, timeout=5) as r:
                doc = json.loads(r.read().decode())
            d[key] = doc.get("version") if key == "version" else [m.get("name") for m in doc.get("models", [])]
        except Exception:  # noqa: BLE001
            pass
    return d

def image_tools(container: str) -> dict:
    """Read /etc/study-image-tools.json from a running study container."""
    out = _run(["docker", "exec", container, "cat", "/etc/study-image-tools.json"])
    try:
        return json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {}
