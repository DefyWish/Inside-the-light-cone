from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.app.providers import (
    AgentAction,
    FailoverLLMProvider,
    InvestigationState,
    LLMProvider,
    MockLLM,
    OpenAICompatibleConfig,
    OpenAICompatibleLLM,
    provider_from_environment,
)
from backend.app.research_agent import KimiWebSearchResearchProvider


ROOT = Path(__file__).resolve().parents[2]


class ChatHandler(BaseHTTPRequestHandler):
    response_payload: dict = {}
    last_path = ""
    last_authorization = ""
    last_request: dict = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).last_path = self.path
        type(self).last_authorization = self.headers.get("Authorization", "")
        type(self).last_request = json.loads(self.rfile.read(length))
        body = json.dumps(type(self).response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


class FormulaHandler(BaseHTTPRequestHandler):
    chat_calls = 0

    def _reply(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._reply(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "description": "search",
                            "parameters": {"type": "object"},
                        },
                    }
                ]
            }
        )

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.path.endswith("/fibers"):
            self._reply({"context": {"encrypted_output": "encrypted-search-result"}})
            return
        type(self).chat_calls += 1
        if type(self).chat_calls == 1:
            self._reply(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "web_search:0",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": "{\"query\":\"曹操墓\"}",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
            return
        self._reply(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "title": "曹操墓考古资料",
                                            "source_url": "https://example.org/cao-cao",
                                            "quote": "原文引文",
                                            "summary": "考古摘要",
                                            "source_id": "example:cao-cao",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ]
            }
        )

    def log_message(self, _format: str, *_args) -> None:
        return


class FailingProvider(LLMProvider):
    name = "primary"

    async def next_action(self, state: InvestigationState) -> AgentAction:
        raise RuntimeError("primary unavailable")


class WorkingProvider(LLMProvider):
    name = "backup"

    async def next_action(self, state: InvestigationState) -> AgentAction:
        return AgentAction(type="finish", text="backup ok")


class ProviderAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_openai_compatible_json_action_over_local_http(self) -> None:
        ChatHandler.response_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "type": "tool_call",
                                "motivation": "先查样本",
                                "tool": "search_ancient_samples",
                                "arguments": {"individual": "Tianyuan"},
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OpenAICompatibleLLM(
                OpenAICompatibleConfig(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    api_key="test-key",
                    model="test-model",
                    provider_name="local-test",
                ),
                [{"name": "search_ancient_samples"}],
            )
            state = InvestigationState(question="查 Tianyuan")
            action = await provider.next_action(state)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(action.tool, "search_ancient_samples")
        self.assertEqual(action.arguments["individual"], "Tianyuan")
        self.assertEqual(ChatHandler.last_path, "/v1/chat/completions")
        self.assertEqual(ChatHandler.last_authorization, "Bearer test-key")
        self.assertEqual(ChatHandler.last_request["model"], "test-model")

    async def test_native_tool_call_is_translated_to_canonical_action(self) -> None:
        action = OpenAICompatibleLLM._translate_message(
            {
                "content": None,
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_literature",
                            "arguments": "{\"query\":\"Tianyuan\"}",
                        }
                    }
                ],
            }
        )
        self.assertEqual(action.type, "tool_call")
        self.assertEqual(action.tool, "search_literature")
        self.assertEqual(action.arguments, {"query": "Tianyuan"})

    async def test_native_control_calls_translate_to_narration_and_finish(self) -> None:
        narration = OpenAICompatibleLLM._translate_message(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "narrate_investigation",
                            "arguments": '{"text":"阶段叙述"}',
                        }
                    }
                ]
            }
        )
        finished = OpenAICompatibleLLM._translate_message(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "finish_investigation",
                            "arguments": '{"text":"专业综合论述","public_text":"展厅故事"}',
                        }
                    }
                ]
            }
        )

        self.assertEqual(narration, AgentAction(type="narration", text="阶段叙述"))
        self.assertEqual(
            finished,
            AgentAction(type="finish", text="专业综合论述", public_text="展厅故事"),
        )

    async def test_kimi_k3_uses_high_reasoning_and_longer_timeout(self) -> None:
        ChatHandler.response_payload = {
            "choices": [{"message": {"content": '{"type":"finish","text":"ok"}'}}]
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OpenAICompatibleLLM(
                OpenAICompatibleConfig(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    api_key="test-key",
                    model="kimi-k3",
                    provider_name="kimi-test",
                ),
                [],
            )
            await provider.next_action(InvestigationState(question="曹操"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(ChatHandler.last_request["reasoning_effort"], "high")
        self.assertTrue(ChatHandler.last_request["tools"])
        tool_names = {
            item["function"]["name"] for item in ChatHandler.last_request["tools"]
        }
        self.assertIn("finish_investigation", tool_names)
        self.assertEqual(provider.config.timeout_seconds, 90.0)

    async def test_failover_switches_to_backup(self) -> None:
        provider = FailoverLLMProvider([FailingProvider(), WorkingProvider()])
        action = await provider.next_action(InvestigationState(question="test"))
        self.assertEqual(action.text, "backup ok")
        self.assertEqual(provider.active_index, 1)

    async def test_missing_keys_select_mock_without_stopping(self) -> None:
        environment = {
            "JIALUO_PROVIDER_MODE": "auto",
            "JIALUO_PRIMARY_BASE_URL": "",
            "JIALUO_PRIMARY_API_KEY": "",
            "JIALUO_BACKUP_BASE_URL": "",
            "JIALUO_BACKUP_API_KEY": "",
        }
        with patch.dict("os.environ", environment, clear=True):
            provider = provider_from_environment(
                ROOT / "fixtures/investigations/mock_v1.json",
                [],
            )
        self.assertIsInstance(provider, MockLLM)


    async def test_lightcone_environment_configures_official_primary_model(self) -> None:
        environment = {
            "LIGHTCONE_PROVIDER_MODE": "auto",
            "LIGHTCONE_PRIMARY_BASE_URL": "https://api.openai.com/v1",
            "LIGHTCONE_PRIMARY_API_KEY": "test-key",
            "LIGHTCONE_PRIMARY_MODEL": "gpt-5.6-sol",
        }
        with patch.dict("os.environ", environment, clear=True):
            provider = provider_from_environment(
                ROOT / "fixtures/investigations/mock_v1.json",
                [],
            )
        self.assertIsInstance(provider, OpenAICompatibleLLM)
        self.assertEqual(provider.config.model, "gpt-5.6-sol")

    async def test_kimi_formula_web_search_flow(self) -> None:
        FormulaHandler.chat_calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), FormulaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = KimiWebSearchResearchProvider(
                base_url=f"http://127.0.0.1:{server.server_port}",
                api_key="test-key",
                model="kimi-k3",
            )
            items = await provider.investigate("查找曹操墓的权威考古资料")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "曹操墓考古资料")
        self.assertEqual(FormulaHandler.chat_calls, 2)


if __name__ == "__main__":
    unittest.main()
