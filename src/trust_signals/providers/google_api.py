"""Google Gemini generateContent adapter (hosted_flashlite arm).

Output tokens are candidate tokens plus thinking tokens, matching the frozen
rate-card note that the output price includes thinking tokens. Explicit
context caching is not enabled by the runner; cachedContentTokenCount is
still parsed so implicit caching, if reported, lands in cache_read.
"""
from __future__ import annotations

from .base import AdapterResponse, ProviderAdapter


class GoogleAdapter(ProviderAdapter):
    provider_name = "google"

    @classmethod
    def parse_usage(cls, response: dict) -> dict[str, int]:
        u = response.get("usageMetadata", {}) or {}
        prompt = int(u.get("promptTokenCount", 0))
        cached = int(u.get("cachedContentTokenCount", 0))
        candidates = int(u.get("candidatesTokenCount", 0))
        thoughts = int(u.get("thoughtsTokenCount", 0))
        return {
            "input_tokens_uncached": max(prompt - cached, 0),
            "input_tokens_cache_write": 0,  # explicit caching unused by the runner
            "input_tokens_cache_read": cached,
            "output_tokens": candidates + thoughts,
        }

    @staticmethod
    def _extract_text(response: dict) -> str:
        candidates = response.get("candidates", []) or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content", {}) or {}).get("parts", []) or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    def send(self, messages, system=None, max_tokens=4096, temperature=None) -> AdapterResponse:
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system is not None:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if temperature is not None:
            payload["generationConfig"]["temperature"] = temperature
        url = f"{self.base_url}/v1beta/models/{self.model_string}:generateContent"
        headers = {"x-goog-api-key": self._api_key()}
        resp = self._post_json(url, payload, headers)
        usage = self.parse_usage(resp)
        return AdapterResponse(
            text=self._extract_text(resp),
            raw_usage=resp.get("usageMetadata", {}) or {},
            model_string_reported=resp.get("modelVersion", self.model_string),
            raw_response=resp,
            **usage,
        )
