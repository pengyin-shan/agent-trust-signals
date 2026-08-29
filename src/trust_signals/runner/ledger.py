"""Per-trial cost ledger (Stage 1, work-order item 4).

The column schema is read from the frozen ``cost_recording.per_trial_fields``
list at construction time and is never retyped in code. ``usd_cost_computed``
is always computed here from the frozen rate card; callers may not supply it.
Appends are resume-safe: an existing ledger is validated against the frozen
schema and appended to, matching the runner's resume flag.

Cache-write pricing ruling (documented, Pengyin-approved required before any
hosted trial that writes cache): the cache-write rate for a model resolves,
in order, to ``provider_specific.cache_write``, then
``provider_specific.cache_write_5m`` (Anthropic prompt caching defaults to
the 5-minute TTL), else no rate. If cache-write tokens are nonzero and no
rate resolves, the append fails loudly rather than under-billing.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class LedgerError(ValueError):
    """Raised on schema violations or rate-card resolution failures."""


TOKEN_FIELDS = (
    "input_tokens_uncached",
    "input_tokens_cache_write",
    "input_tokens_cache_read",
    "output_tokens",
)


class CostLedger:
    def __init__(self, config: dict, ledger_path: str | Path) -> None:
        cost_cfg = config.get("cost_recording")
        if not cost_cfg:
            raise LedgerError("config has no cost_recording section")
        fields = cost_cfg.get("per_trial_fields")
        if not isinstance(fields, list) or not fields:
            raise LedgerError("cost_recording.per_trial_fields missing or empty")
        self.fields: list[str] = list(fields)
        if "usd_cost_computed" not in self.fields:
            raise LedgerError("per_trial_fields must include usd_cost_computed")
        for tf in TOKEN_FIELDS:
            if tf not in self.fields:
                raise LedgerError(f"per_trial_fields must include {tf}")

        entries = (cost_cfg.get("rate_card") or {}).get("entries") or []
        self._rates: dict[str, dict[str, Any]] = {}
        for e in entries:
            self._rates[e["model_id"]] = e
        if not self._rates:
            raise LedgerError("rate card has no entries")

        self.path = Path(ledger_path)
        if self.path.exists():
            self._validate_existing_header()

    # -- schema -----------------------------------------------------------
    def _validate_existing_header(self) -> None:
        with open(self.path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return  # empty file: header will be written on first append
        if header != self.fields:
            raise LedgerError(
                f"existing ledger header {header} does not match frozen schema {self.fields}; "
                "refusing to append"
            )

    # -- pricing ----------------------------------------------------------
    def _cache_write_rate(self, entry: dict) -> float | None:
        ps = entry.get("provider_specific") or {}
        for key in ("cache_write", "cache_write_5m"):
            if key in ps:
                return float(ps[key])
        return None

    def compute_usd(
        self,
        model_id: str,
        input_tokens_uncached: int,
        input_tokens_cache_write: int,
        input_tokens_cache_read: int,
        output_tokens: int,
    ) -> float:
        entry = self._rates.get(model_id)
        if entry is None:
            raise LedgerError(f"model_id {model_id!r} not in the frozen rate card")
        r = entry["usd_per_mtok"]
        usd = (
            input_tokens_uncached * float(r["input"])
            + input_tokens_cache_read * float(r["cache_read"])
            + output_tokens * float(r["output"])
        )
        if input_tokens_cache_write:
            cw = self._cache_write_rate(entry)
            if cw is None:
                raise LedgerError(
                    f"cache-write tokens recorded for {model_id!r} but the frozen rate card "
                    "resolves no cache-write rate; refusing to under-bill"
                )
            usd += input_tokens_cache_write * cw
        return round(usd / 1_000_000.0, 8)

    # -- writing ----------------------------------------------------------
    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Validate a trial record against the frozen schema, compute USD, append."""
        if "usd_cost_computed" in record and record["usd_cost_computed"] not in (None, ""):
            raise LedgerError(
                "usd_cost_computed is computed by the ledger from the frozen rate card; "
                "callers must not supply it"
            )
        row = dict(record)
        row["usd_cost_computed"] = self.compute_usd(
            row["model_id"], *(int(row[tf]) for tf in TOKEN_FIELDS)
        )
        missing = [f for f in self.fields if f not in row]
        if missing:
            raise LedgerError(f"record missing frozen fields: {missing}")
        extra = [k for k in row if k not in self.fields]
        if extra:
            raise LedgerError(f"record has fields outside the frozen schema: {extra}")

        write_header = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.fields)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        return row

    # -- reading ----------------------------------------------------------
    def rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with open(self.path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def total_hosted_usd(self, local_model_ids: set[str] | None = None) -> float:
        """Sum computed USD over non-local rows, for spend-cap enforcement."""
        local_ids = local_model_ids or {
            mid for mid, e in self._rates.items() if e.get("provider") == "local"
        }
        return round(
            sum(
                float(r["usd_cost_computed"])
                for r in self.rows()
                if r["model_id"] not in local_ids
            ),
            8,
        )
