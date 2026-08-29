"""Ollama local adapter (local_openweight arm, zero marginal cost).

keep_alive is passed on every request so the model stays loaded across a
batch (work-order item 4); the value comes from runtime config.
"""
from __future__ import annotations

from .base import AdapterResponse, ProviderAdapter


class OllamaAdapter(ProviderAdapter):
    provider_name = "ollama"
    requires_api_key = False

    @classmethod
    def parse_usage(cls, response: dict) -> dict[str, int]:
        return {
            "input_tokens_uncached": int(response.get("prompt_eval_count", 0)),
            "input_tokens_cache_write": 0,
            "input_tokens_cache_read": 0,
            "output_tokens": int(response.get("eval_count", 0)),
        }

    def send(self, messages, system=None, max_tokens=4096, temperature=None) -> AdapterResponse:
        msgs = list(messages)
        if system is not None:
            msgs = [{"role": "system", "content": system}] + msgs
        options = {"num_predict": max_tokens}
        if temperature is not None:
            options["temperature"] = temperature
        payload = {
            "model": self.model_string,
            "messages": msgs,
            "stream": False,
            "options": options,
            "keep_alive": self.extra.get("keep_alive", "30m"),
        }
        resp = self._post_json(f"{self.base_url}/api/chat", payload, {})
        usage = self.parse_usage(resp)
        return AdapterResponse(
            text=(resp.get("message", {}) or {}).get("content", ""),
            raw_usage={
                k: resp.get(k)
                for k in ("prompt_eval_count", "eval_count", "total_duration", "load_duration")
                if k in resp
            },
            model_string_reported=resp.get("model", ""),
            raw_response=resp,
            **usage,
        )
