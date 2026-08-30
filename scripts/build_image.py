#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals.paths import ROOT
from trust_signals.runner import RUNS_ROOT, docker_versions, image_identity

IMAGE = "agent-trust-signals-sandbox:1.0"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--platform", default="linux/arm64")
    a = ap.parse_args()
    cmd = ["docker", "build", "--platform", a.platform, "-t", IMAGE, "-f", str(ROOT / "docker" / "Dockerfile"),
           str(ROOT / "docker")]
    if a.no_cache:
        cmd.insert(2, "--no-cache")
    print(" ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        print("image build failed", file=sys.stderr)
        return 1
    info = image_identity(IMAGE)
    tools = subprocess.run(["docker", "run", "--rm", "--network", "none", IMAGE, "cat", "/etc/study-image-tools.json"],
                           capture_output=True, text=True)
    info["tools"] = json.loads(tools.stdout) if tools.returncode == 0 else {"error": tools.stderr[-500:]}
    info["docker"] = docker_versions()
    RUNS_ROOT.mkdir(exist_ok=True)
    (RUNS_ROOT / "image.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
