"""Offline adapter tests: usage parsing per provider payload shape and the
config-only model-identity contract. No network access is used or mocked at
the transport layer; parsing is pure. Live smoke tests are a separate script
run during the pre-execution checklist.
"""
import pytest

from trust_signals.config import load_config
from trust_signals.paths import CONFIG_PATH
from trust_signals.providers import ProviderError, build_adapter
from trust_signals.providers.anthropic_api import AnthropicAdapter
from trust_signals.providers.google_api import GoogleAdapter
from trust_signals.providers.ollama_local import OllamaAdapter
from trust_signals.providers.openai_api import OpenAIAdapter
from trust_signals.providers.openai_compatible import OpenAICompatibleAdapter

RUNTIME_CFG = {
    "providers": {
        "anthropic_api": {"base_url": "https://api.anthropic.com", "api_key_env": "K"},
        "openai_api": {"base_url": "https://api.openai.com", "api_key_env": "K"},
        "google_api": {"base_url": "https://generativelanguage.googleapis.com", "api_key_env": "K"},
        "openai_compatible": {"base_url": "https://api.deepinfra.com/v1/openai", "api_key_env": "K"},
        "ollama": {"base_url": "http://localhost:11434"},
    }
}


def test_anthropic_usage_split():
    resp = {
        "usage": {
            "input_tokens": 100,
            "cache_creation_input_tokens": 40,
            "cache_read_input_tokens": 500,
            "output_tokens": 77,
        }
    }
    u = AnthropicAdapter.parse_usage(resp)
    assert u == {
        "input_tokens_uncached": 100,
        "input_tokens_cache_write": 40,
        "input_tokens_cache_read": 500,
        "output_tokens": 77,
    }


def test_openai_usage_split_subtracts_cached():
    resp = {
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 700},
        }
    }
    u = OpenAIAdapter.parse_usage(resp)
    assert u["input_tokens_uncached"] == 300
    assert u["input_tokens_cache_read"] == 700
    assert u["input_tokens_cache_write"] == 0
    assert u["output_tokens"] == 50


def test_openai_compatible_inherits_parsing():
    resp = {"usage": {"prompt_tokens": 10, "completion_tokens": 3}}
    u = OpenAICompatibleAdapter.parse_usage(resp)
    assert u["input_tokens_uncached"] == 10
    assert u["output_tokens"] == 3


def test_google_output_includes_thinking_tokens():
    resp = {
        "usageMetadata": {
            "promptTokenCount": 200,
            "cachedContentTokenCount": 50,
            "candidatesTokenCount": 30,
            "thoughtsTokenCount": 120,
        }
    }
    u = GoogleAdapter.parse_usage(resp)
    assert u["input_tokens_uncached"] == 150
    assert u["input_tokens_cache_read"] == 50
    assert u["output_tokens"] == 150  # candidates + thinking, per frozen rate-card note


def test_ollama_usage():
    resp = {"prompt_eval_count": 900, "eval_count": 250}
    u = OllamaAdapter.parse_usage(resp)
    assert u["input_tokens_uncached"] == 900
    assert u["output_tokens"] == 250
    assert u["input_tokens_cache_read"] == 0


def test_text_extraction_shapes():
    assert AnthropicAdapter._extract_text(
        {"content": [{"type": "text", "text": "a"}, {"type": "tool_use"}, {"type": "text", "text": "b"}]}
    ) == "ab"
    assert OpenAIAdapter._extract_text({"choices": [{"message": {"content": "hi"}}]}) == "hi"
    assert GoogleAdapter._extract_text(
        {"candidates": [{"content": {"parts": [{"text": "x"}, {"text": "y"}]}}]}
    ) == "xy"


def test_factory_builds_every_frozen_arm_from_config():
    cfg = load_config(CONFIG_PATH)
    entries = list(cfg["models"]) + list(cfg["frontier_supplement"]["models"])
    assert len(entries) == 6
    for entry in entries:
        adapter = build_adapter(entry, RUNTIME_CFG)
        # model identity flows from the frozen entry, untouched
        assert adapter.model_string == entry["model_string"]


def test_factory_rejects_unknown_runtime():
    with pytest.raises(ProviderError):
        build_adapter({"runtime": "mystery", "model_string": "x"}, RUNTIME_CFG)


def test_adapter_requires_model_string_from_config():
    with pytest.raises(ProviderError):
        AnthropicAdapter(model_string="", base_url="https://api.anthropic.com", api_key_env="K")


def test_no_hardcoded_model_strings_in_provider_modules():
    """Guard the identity-as-config rule: frozen model strings must not
    appear in provider source code."""
    from pathlib import Path

    cfg = load_config(CONFIG_PATH)
    strings = [m["model_string"] for m in cfg["models"]] + [
        m["model_string"] for m in cfg["frontier_supplement"]["models"]
    ]
    src = Path(__file__).resolve().parents[1] / "src" / "trust_signals" / "providers"
    blob = "".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    for s in strings:
        assert s not in blob, f"frozen model string {s!r} hard-coded in providers/"
