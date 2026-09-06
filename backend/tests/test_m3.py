from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.evidence_tools import EvidenceTools
from backend.app.investigation import ClaimStore, InvestigationManager, encode_sse
from backend.app.providers import MockLLM
from backend.app.reports import build_investigation_report


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

    async def test_sessions_and_events_survive_manager_restart(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = ClaimStore(Path(temporary_directory) / "investigations.sqlite")
            first = InvestigationManager(self.manager.provider, self.manager.evidence_tools, claim_store=store)
            for question in ("苏轼迁徙", "客家人迁徙"):
                session = await first.create(question)
                _ = [event async for event in session.stream()]

            restored = InvestigationManager(
                self.manager.provider,
                self.manager.evidence_tools,
                claim_store=ClaimStore(store.path),
            )
            summaries = restored.list_sessions()
            self.assertEqual([item.question for item in summaries], ["客家人迁徙", "苏轼迁徙"])
            first_session = next(
                session for session in restored.sessions.values() if session.question == "苏轼迁徙"
            )
            events = [event async for event in first_session.stream()]
            self.assertEqual(events[0]["type"], "investigation.started")
            self.assertEqual(events[-1]["type"], "investigation.completed")

    async def test_deleted_session_is_removed_from_memory_and_sqlite(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = ClaimStore(Path(temporary_directory) / "investigations.sqlite")
            manager = InvestigationManager(
                self.manager.provider,
                self.manager.evidence_tools,
                claim_store=store,
            )
            session = await manager.create("苏轼迁徙")
            _ = [event async for event in session.stream()]

            self.assertTrue(await manager.delete(session.id))
            self.assertIsNone(manager.get(session.id))

            restored = InvestigationManager(
                self.manager.provider,
                self.manager.evidence_tools,
                claim_store=ClaimStore(store.path),
            )
            self.assertEqual(restored.list_sessions(), [])

    async def test_builds_professional_and_public_reports_from_dynamic_state(self) -> None:
        session = await self.manager.create("Loschbour")
        _ = [event async for event in session.stream()]

        professional = build_investigation_report(session, "professional")
        public = build_investigation_report(session, "public")

        self.assertEqual(professional["subtitle"], "专业历史文博版")
        self.assertEqual(public["subtitle"], "博物馆公众版")
        self.assertTrue(professional["sections"])
        self.assertTrue(public["sections"])
        self.assertGreaterEqual(professional["stats"]["evidence"], len(professional["sources"]))


if __name__ == "__main__":
    unittest.main()
