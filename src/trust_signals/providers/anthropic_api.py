"""Anthropic Messages API adapter (hosted_sonnet, frontier_anthropic arms)."""
from __future__ import annotations

from .base import AdapterResponse, ProviderAdapter

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(ProviderAdapter):
    provider_name = "anthropic"

    @classmethod
    def parse_usage(cls, response: dict) -> dict[str, int]:
        u = response.get("usage", {}) or {}
        return {
            # Anthropic reports input_tokens as the uncached portion.
            "input_tokens_uncached": int(u.get("input_tokens", 0)),
            "input_tokens_cache_write": int(u.get("cache_creation_input_tokens", 0)),
            "input_tokens_cache_read": int(u.get("cache_read_input_tokens", 0)),
            "output_tokens": int(u.get("output_tokens", 0)),
        }

    @staticmethod
    def _extract_text(response: dict) -> str:
        parts = []
        for block in response.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)

    def send(self, messages, system=None, max_tokens=4096, temperature=None) -> AdapterResponse:
        payload = {
            "model": self.model_string,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {
            "x-api-key": self._api_key(),
            "anthropic-version": ANTHROPIC_VERSION,
        }
        resp = self._post_json(f"{self.base_url}/v1/messages", payload, headers)
        usage = self.parse_usage(resp)
        return AdapterResponse(
            text=self._extract_text(resp),
            raw_usage=resp.get("usage", {}) or {},
            model_string_reported=resp.get("model", ""),
            raw_response=resp,
            **usage,
        )
