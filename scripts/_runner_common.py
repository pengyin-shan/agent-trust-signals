from __future__ import annotations
import json
import os
from pathlib import Path
import yaml
from trust_signals.config import load_config
from trust_signals.paths import CONFIG_PATH, ROOT
from trust_signals.runner import CostLedger, DockerExecutor, RUNS_ROOT, docker_versions

IMAGE = "agent-trust-signals-sandbox:1.0"

def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def load_all() -> tuple[dict, dict, CostLedger, dict, dict]:
    load_dotenv()
    cfg = load_config(CONFIG_PATH)
    runtime_cfg = yaml.safe_load((ROOT / "config" / "runtime.yaml").read_text(encoding="utf-8"))
    ledger_path = ROOT / runtime_cfg.get("ledger", {}).get("path", "runs/cost_ledger.csv")
    if str(ledger_path).startswith(str(ROOT / "out")):
        raise SystemExit("config/runtime.yaml ledger.path points under out/ (frozen); set it to runs/cost_ledger.csv")
    ledger = CostLedger(cfg, ledger_path)
    image_json = RUNS_ROOT / "image.json"
    if not image_json.exists():
        raise SystemExit("runs/image.json missing; run scripts/build_image.py first")
    image_info = json.loads(image_json.read_text(encoding="utf-8"))
    return cfg, runtime_cfg, ledger, image_info, docker_versions()

def make_docker_executor(spec, fork: Path, package: str) -> DockerExecutor:
    return DockerExecutor(IMAGE, fork, package)
