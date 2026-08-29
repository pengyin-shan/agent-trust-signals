"""OpenAI-compatible adapter for third-party endpoints (frontier_openweight arm).

Serves DeepInfra's OpenAI-compatible endpoint; the base URL comes from
runtime config (expected https://api.deepinfra.com/v1/openai) and is verified
against the live endpoint during the smoke test, since the frozen config's
note references an endpoint that is not itself recorded in the frozen files.
The request/response shape is inherited from the OpenAI adapter; only the
endpoint path differs (the base URL already ends in the provider prefix).
"""
from __future__ import annotations

from .base import AdapterResponse
from .openai_api import OpenAIAdapter


class OpenAICompatibleAdapter(OpenAIAdapter):
    provider_name = "openai_compatible"

    def send(self, messages, system=None, max_tokens=4096, temperature=None) -> AdapterResponse:
        msgs = list(messages)
        if system is not None:
            msgs = [{"role": "system", "content": system}] + msgs
        payload = {
            "model": self.model_string,
            "messages": msgs,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        resp = self._post_json(f"{self.base_url}/chat/completions", payload, headers)
        usage = self.parse_usage(resp)
        return AdapterResponse(
            text=self._extract_text(resp),
            raw_usage=resp.get("usage", {}) or {},
            model_string_reported=resp.get("model", ""),
            raw_response=resp,
            **usage,
        )
