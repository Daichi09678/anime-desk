import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from ai_providers import discover_codex, run_agy, run_codex
from cli_process import ProcessResult


class ProtocolRunner:
    def __init__(self, events):
        self.events = events
        self.sent = []

    def send(self, value):
        self.sent.append(value)

    def run(self, command, **kwargs):
        kwargs["on_start"](self)
        done = False
        for event in self.events:
            if kwargs["on_stdout"](json.dumps(event)):
                done = True
                break
        return ProcessResult(0, "", "", done)


class ProviderProtocolTests(unittest.TestCase):
    def test_codex_model_pagination_and_deduplication(self):
        runner = ProtocolRunner([
            {"id": 0, "result": {}},
            {"id": 1, "result": {"account": {"type": "chatgpt"}}},
            {"id": 2, "result": {"data": [{"model": "first", "displayName": "First"}], "nextCursor": "page2"}},
            {"id": 2, "result": {"data": [{"model": "first"}, {"model": "second"}], "nextCursor": None}},
        ])
        with patch("ai_providers.ProcessRunner", return_value=runner):
            state = discover_codex("codex", Path.cwd())
        self.assertTrue(state.connected)
        self.assertEqual([m["id"] for m in state.models], ["first", "second"])
        self.assertTrue(any(s.get("params", {}).get("cursor") == "page2" for s in runner.sent))

    def test_codex_failed_turn_is_not_reported_as_completed(self):
        runner = ProtocolRunner([
            {"id": 0, "result": {}}, {"id": 1, "result": {"thread": {"id": "thread"}}},
            {"method": "item/agentMessage/delta", "params": {"itemId": "m", "delta": "Partial"}},
            {"method": "turn/completed", "params": {"turn": {"status": "failed", "error": {"message": "quota reached"}}}},
        ])
        with patch("ai_providers.ProcessRunner", return_value=runner), self.assertRaisesRegex(RuntimeError, "quota"):
            run_codex("codex", "model", "low", "prompt", [], Path.cwd(), False, 10,
                      threading.Event(), lambda text: None, lambda text: None)

    def test_agy_explicitly_sets_requested_model_and_readonly_mode_before_prompt(self):
        runner = ProtocolRunner([
            {"id": 0, "result": {"agentCapabilities": {"promptCapabilities": {"image": True}}}},
            {"id": 1, "result": {"sessionId": "session", "models": {"currentModelId": "other", "availableModels": [{"modelId": "chosen"}]}}},
            {"id": 3, "result": {}}, {"id": 4, "result": {}},
            {"method": "session/update", "params": {"update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hello"}}}},
            {"id": 2, "result": {"stopReason": "end_turn"}},
        ])
        with patch("ai_providers.ProcessRunner", return_value=runner):
            reply = run_agy("agy", "chosen", "low", "prompt", [], Path.cwd(), False, 10,
                            threading.Event(), lambda text: None, lambda text: None)
        self.assertEqual(reply.text, "Hello")
        methods = [s["method"] for s in runner.sent]
        self.assertLess(methods.index("session/set_model"), methods.index("session/prompt"))
        self.assertLess(methods.index("session/set_mode"), methods.index("session/prompt"))
        self.assertEqual(next(s["params"]["modelId"] for s in runner.sent if s["method"] == "session/set_model"), "chosen")

    def test_agy_without_image_capability_fails_instead_of_sending_only_a_path(self):
        runner = ProtocolRunner([{ "id": 0, "result": {"agentCapabilities": {"promptCapabilities": {}}}}])
        with patch("ai_providers.ProcessRunner", return_value=runner), self.assertRaisesRegex(RuntimeError, "dukungan gambar"):
            run_agy("agy", "chosen", "low", "prompt", ["image.png"], Path.cwd(), False, 10,
                    threading.Event(), lambda text: None, lambda text: None)


if __name__ == "__main__":
    unittest.main()
