"""OpenAI Chat Completions adapter (frontier_openai arm).

Chat Completions is used rather than the Responses API so the same request
shape serves both this adapter and the OpenAI-compatible adapter (DeepInfra).
Cache writes are not reported by this API and are recorded as zero; cached
input is billed at the frozen cache_read rate.
"""
from __future__ import annotations

from .base import AdapterResponse, ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    provider_name = "openai"

    @classmethod
    def parse_usage(cls, response: dict) -> dict[str, int]:
        u = response.get("usage", {}) or {}
        prompt = int(u.get("prompt_tokens", 0))
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        return {
            "input_tokens_uncached": max(prompt - cached, 0),
            "input_tokens_cache_write": 0,  # not reported by the API
            "input_tokens_cache_read": cached,
            "output_tokens": int(u.get("completion_tokens", 0)),
        }

    @staticmethod
    def _extract_text(response: dict) -> str:
        choices = response.get("choices", []) or []
        if not choices:
            return ""
        msg = choices[0].get("message", {}) or {}
        return msg.get("content") or ""

    def send(self, messages, system=None, max_tokens=4096, temperature=None) -> AdapterResponse:
        msgs = list(messages)
        if system is not None:
            msgs = [{"role": "system", "content": system}] + msgs
        payload = {
            "model": self.model_string,
            "messages": msgs,
            "max_completion_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        resp = self._post_json(f"{self.base_url}/v1/chat/completions", payload, headers)
        usage = self.parse_usage(resp)
        return AdapterResponse(
            text=self._extract_text(resp),
            raw_usage=resp.get("usage", {}) or {},
            model_string_reported=resp.get("model", ""),
            raw_response=resp,
            **usage,
        )
