from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.evidence_tools import EvidenceTools
from backend.app.investigation import InvestigationManager, encode_sse
from backend.app.providers import MockLLM


ROOT = Path(__file__).resolve().parents[2]


class InvestigationLoopTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        provider = MockLLM(ROOT / "fixtures/investigations/mock_v1.json")
        tools = EvidenceTools(ROOT / "artifacts/catalog.sqlite", ROOT / "artifacts/numeric")
        self.manager = InvestigationManager(provider, tools)

    async def test_fixture_drives_complete_tool_loop(self) -> None:
        session = await self.manager.create("Loschbour")
        events = [event async for event in session.stream()]
        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "investigation.started")
        self.assertEqual(event_types[-1], "investigation.completed")
        self.assertEqual(event_types.count("tool.called"), 3)
        self.assertEqual(event_types.count("tool.result"), 3)
        self.assertIn("evidence.added", event_types)
        self.assertNotIn("investigation.failed", event_types)

    async def test_default_fixture_preserves_gap(self) -> None:
        session = await self.manager.create("一个未分类的输入")
        events = [event async for event in session.stream()]
        gaps = [
            event
            for event in events
            if event["type"] == "evidence.added"
            and event["data"]["evidence"]["record_type"] == "evidence_gap"
        ]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(events[-1]["type"], "investigation.completed")

    def test_sse_encoding(self) -> None:
        event = {"sequence": 7, "type": "narration", "data": {"text": "证据"}}
        encoded = encode_sse(event)
        self.assertIn("id: 7\n", encoded)
        self.assertIn("event: narration\n", encoded)
        self.assertTrue(encoded.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()

