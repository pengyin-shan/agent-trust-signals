from __future__ import annotations
import json
from trust_signals.providers.anthropic_api import AnthropicAdapter

def make_adapter(captured):
    a = AnthropicAdapter.__new__(AnthropicAdapter)
    a.model_string = "claude-sonnet-5"
    a.base_url = "https://api.example.invalid"
    a._api_key = lambda: "k"
    def fake_post(url, payload, headers):
        captured.append(payload)
        return {"content": [{"type": "text", "text": "ok"}], "model": "claude-sonnet-5",
                "usage": {"input_tokens": 3, "cache_creation_input_tokens": 10,
                          "cache_read_input_tokens": 20, "output_tokens": 2}}
    a._post_json = fake_post
    return a

def test_breakpoints_on_system_and_last_user_turn():
    captured = []
    a = make_adapter(captured)
    msgs = [{"role": "user", "content": "task"},
            {"role": "assistant", "content": "act"},
            {"role": "user", "content": "output"}]
    r = a.send(msgs, system="sys", max_tokens=64)
    p = captured[0]
    assert p["system"] == [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    assert p["messages"][0] == msgs[0] and p["messages"][1] == msgs[1]
    last = p["messages"][2]
    assert last["content"][0]["text"] == "output" and last["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert r.input_tokens_cache_write == 10 and r.input_tokens_cache_read == 20 and r.text == "ok"
    assert json.dumps(p)

def test_single_turn_gets_breakpoint():
    captured = []
    a = make_adapter(captured)
    a.send([{"role": "user", "content": "only"}], system="s")
    assert captured[0]["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
