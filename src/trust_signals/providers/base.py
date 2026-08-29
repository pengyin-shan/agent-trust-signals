"""Provider-adapter interface (Stage 1, work-order item 3).

One interface: send a conversation; receive text, token usage split into
uncached / cache-write / cache-read input plus output, and the raw usage
payload for release. Model identity is configuration data only: adapters
receive the model string from the frozen ``models`` /
``frontier_supplement.models`` entries via :func:`build_adapter` and never
hard-code it. Adding or swapping a model is a config edit (plus, post-freeze,
a deviations entry if it touches a registered arm).

Transport failures raise :class:`ProviderTransportError` so the runner can
apply the registered exclusion rule (re-run once, then mark the cell
infrastructure-incomplete). Malformed-but-delivered assistant output is NOT
an error here; it is returned as text and coded under the rubric.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Configuration or contract error in an adapter (not retryable)."""


class ProviderTransportError(RuntimeError):
    """Network/API transport failure (retry once per the exclusion rule)."""


@dataclass
class AdapterResponse:
    """Uniform response contract for every provider adapter."""

    text: str
    input_tokens_uncached: int
    input_tokens_cache_write: int
    input_tokens_cache_read: int
    output_tokens: int
    raw_usage: dict[str, Any]
    model_string_reported: str
    api_calls: int = 1
    raw_response: dict[str, Any] = field(default_factory=dict, repr=False)


class ProviderAdapter:
    """Base adapter. Subclasses implement :meth:`send` and usage parsing.

    Parameters come from configuration, never from code:

    - ``model_string``: the frozen model identifier for the arm.
    - ``base_url``: provider endpoint base (runtime config).
    - ``api_key_env``: name of the environment variable holding the key.
    - ``timeout_s`` / ``max_retries``: transport settings (runtime config).
    """

    provider_name = "abstract"
    requires_api_key = True

    def __init__(
        self,
        model_string: str,
        base_url: str,
        api_key_env: str | None = None,
        timeout_s: float = 300.0,
        max_retries: int = 2,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not model_string:
            raise ProviderError(f"{self.provider_name}: model_string must come from config")
        self.model_string = model_string
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.extra = extra or {}

    # -- key handling -----------------------------------------------------
    def _api_key(self) -> str:
        if not self.requires_api_key:
            return ""
        if not self.api_key_env:
            raise ProviderError(f"{self.provider_name}: api_key_env not configured")
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise ProviderError(
                f"{self.provider_name}: environment variable {self.api_key_env} is empty; "
                "populate .env before hosted calls"
            )
        return key

    # -- transport --------------------------------------------------------
    def _post_json(self, url: str, payload: dict, headers: dict) -> dict:
        """POST JSON with bounded retries on transport-level failures.

        Uses the standard library so the study environment adds no mandatory
        third-party HTTP dependency; retry with exponential backoff applies
        to connection errors, timeouts, and 5xx/429 responses.
        """
        body = json.dumps(payload).encode("utf-8")
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=body, method="POST")
            for k, v in {"Content-Type": "application/json", **headers}.items():
                req.add_header(k, v)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:  # delivered HTTP error
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    last_exc = exc
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise ProviderTransportError(
                    f"{self.provider_name}: HTTP {exc.code} from {url}: {detail}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                if attempt < self.max_retries:
                    last_exc = exc
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise ProviderTransportError(
                    f"{self.provider_name}: transport failure for {url}: {exc}"
                ) from exc
        raise ProviderTransportError(
            f"{self.provider_name}: retries exhausted for {url}: {last_exc}"
        )

    # -- contract ---------------------------------------------------------
    def send(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> AdapterResponse:
        raise NotImplementedError

    @classmethod
    def parse_usage(cls, response: dict) -> dict[str, int]:
        """Map a raw provider response to the four token fields (pure, offline-testable)."""
        raise NotImplementedError


def build_adapter(model_entry: dict, runtime_cfg: dict) -> ProviderAdapter:
    """Construct the right adapter from a frozen model entry + runtime settings.

    ``model_entry`` is an element of the frozen config's ``models`` or
    ``frontier_supplement.models`` lists (identity data). ``runtime_cfg`` is
    the non-frozen ``config/runtime.yaml`` (endpoints, key env names,
    timeouts). Nothing about model identity may originate here.
    """
    from . import anthropic_api, google_api, ollama_local, openai_api, openai_compatible

    runtime = model_entry.get("runtime")
    registry = {
        "anthropic_api": anthropic_api.AnthropicAdapter,
        "openai_api": openai_api.OpenAIAdapter,
        "google_api": google_api.GoogleAdapter,
        "openai_compatible": openai_compatible.OpenAICompatibleAdapter,
        "ollama": ollama_local.OllamaAdapter,
    }
    if runtime not in registry:
        raise ProviderError(f"unknown runtime {runtime!r} in model entry {model_entry!r}")
    providers_cfg = runtime_cfg.get("providers", {})
    pcfg = providers_cfg.get(runtime)
    if pcfg is None:
        raise ProviderError(f"runtime config has no providers.{runtime} section")
    cls = registry[runtime]
    return cls(
        model_string=model_entry["model_string"],
        base_url=pcfg["base_url"],
        api_key_env=pcfg.get("api_key_env"),
        timeout_s=float(pcfg.get("timeout_s", runtime_cfg.get("timeout_s", 300.0))),
        max_retries=int(pcfg.get("max_retries", runtime_cfg.get("max_retries", 2))),
        extra=pcfg.get("extra", {}),
    )
