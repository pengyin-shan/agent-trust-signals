#!/usr/bin/env python3
"""Pre-execution checklist item: smoke test each provider adapter.

For every model entry in the frozen config (registered arms plus frontier
supplement), send one trivial call and check that:
  1. the adapter returns text and a usage split,
  2. the model string reported by the API matches the frozen string,
  3. the ledger computes a cost for the trial from the frozen rate card.

Nothing is written to the real ledger; costs are printed only. Run after
.env is populated. Cost of a full run is a few cents.

Usage:
    python scripts/smoke_adapters.py                # all six arms
    python scripts/smoke_adapters.py --only ollama  # by runtime
    python scripts/smoke_adapters.py --only hosted_sonnet  # by model_id
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from trust_signals.config import load_config  # noqa: E402
from trust_signals.paths import CONFIG_PATH, ROOT  # noqa: E402
from trust_signals.providers import ProviderTransportError, build_adapter  # noqa: E402
from trust_signals.runner import CostLedger  # noqa: E402

PROMPT = "Reply with the single word: ready"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None, help="model_id or runtime to test")
    args = parser.parse_args()

    cfg = load_config(CONFIG_PATH)
    with open(ROOT / "config" / "runtime.yaml", encoding="utf-8") as fh:
        runtime_cfg = yaml.safe_load(fh)
    ledger = CostLedger(cfg, ROOT / "out" / "_smoke_ledger_unused.csv")

    entries = list(cfg["models"]) + list(cfg["frontier_supplement"]["models"])
    if args.only:
        entries = [e for e in entries if args.only in (e["id"], e["runtime"])]
        if not entries:
            print(f"no model entry matches --only {args.only}")
            return 2

    failures = 0
    for entry in entries:
        mid, frozen = entry["id"], entry["model_string"]
        print(f"\n== {mid} ({entry['runtime']}) -> {frozen}")
        try:
            adapter = build_adapter(entry, runtime_cfg)
            resp = adapter.send([{"role": "user", "content": PROMPT}], max_tokens=32)
        except ProviderTransportError as exc:
            print(f"  TRANSPORT FAILURE: {exc}")
            failures += 1
            continue
        except Exception as exc:  # config/contract errors surface plainly
            print(f"  FAILURE: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        ok_string = frozen in (resp.model_string_reported or frozen) or (
            resp.model_string_reported or ""
        ).startswith(frozen)
        usd = ledger.compute_usd(
            mid,
            resp.input_tokens_uncached,
            resp.input_tokens_cache_write,
            resp.input_tokens_cache_read,
            resp.output_tokens,
        )
        print(f"  text: {resp.text[:60]!r}")
        print(f"  reported model string: {resp.model_string_reported!r} "
              f"{'MATCHES frozen' if ok_string else '*** DOES NOT MATCH frozen ***'}")
        print(f"  usage: uncached={resp.input_tokens_uncached} cache_write={resp.input_tokens_cache_write} "
              f"cache_read={resp.input_tokens_cache_read} output={resp.output_tokens}")
        print(f"  computed cost from frozen rate card: ${usd}")
        if not ok_string:
            failures += 1

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
