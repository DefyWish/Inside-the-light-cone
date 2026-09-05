from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.evidence_tools import EvidenceTools
from backend.app.investigation import InvestigationManager
from backend.app.providers import AgentAction, InvestigationState, LLMProvider, MockLLM
from backend.app.research_agent import MockResearchLLM, ResearchAgent, ResearchStagingStore


ROOT = Path(__file__).resolve().parents[2]


class SlowProvider(LLMProvider):
    name = "slow"

    async def next_action(self, state: InvestigationState) -> AgentAction:
        await asyncio.sleep(30)
        return AgentAction(type="finish", text="late")


class StaticResearchProvider:
    name = "static-research"

    def __init__(self, items: list[dict]) -> None:
        self.items = items

    async def investigate(self, _query: str) -> list[dict]:
        return self.items


class ResearchAndRedirectTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        staging_path = Path(self.temporary.name) / "research.sqlite"
        self.research_agent = ResearchAgent(
            MockResearchLLM(
                ROOT / "fixtures/research/mock_corpus_v1.json",
                delay_seconds=0,
            ),
            ResearchStagingStore(staging_path),
        )
        self.staging_path = staging_path
        provider = MockLLM(ROOT / "fixtures/investigations/mock_v1.json")
        tools = EvidenceTools(ROOT / "artifacts/catalog.sqlite", ROOT / "artifacts/numeric")
        self.manager = InvestigationManager(provider, tools, self.research_agent)

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    async def test_quote_gate_accepts_and_stages_published_corpus(self) -> None:
        outcome = await self.research_agent.investigate("查找 Loschbour 的论文背景")
        self.assertEqual(outcome.status, "ok")
        self.assertTrue(outcome.items[0].quote)
        self.assertEqual(outcome.items[0].review_status, "temporary")
        with sqlite3.connect(self.staging_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM research_findings").fetchone()[0]
        self.assertEqual(count, 1)

    async def test_quote_gate_rejects_unquoted_result(self) -> None:
        outcome = await self.research_agent.investigate("无引文测试")
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.items, [])

    async def test_research_gate_rejects_news_and_keeps_scholarly_source(self) -> None:
        agent = ResearchAgent(
            StaticResearchProvider(
                [
                    {
                        "title": "新闻转载",
                        "source_url": "https://www.news.cn/example",
                        "quote": "转载内容",
                        "summary": "新闻摘要",
                        "source_kind": "peer_reviewed_article",
                    },
                    {
                        "title": "Ancient DNA study",
                        "source_url": "https://doi.org/10.1000/example",
                        "quote": "Primary-source quotation.",
                        "summary": "原始论文摘要",
                        "claim": "一项古 DNA 分析形成了可检验的历史判断。",
                        "relation_to_question": "它提供遗传证据环节。",
                        "source_kind": "peer_reviewed_article",
                        "doi": "10.1000/example",
                        "event_year_start": 220,
                        "narrative_role": "evidence",
                    },
                ]
            ),
            ResearchStagingStore(Path(self.temporary.name) / "source-gate.sqlite"),
        )
        outcome = await agent.investigate("曹操古 DNA 文献")

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(len(outcome.items), 1)
        self.assertEqual(outcome.items[0].source_url, "https://doi.org/10.1000/example")
        self.assertEqual(outcome.items[0].event_year_start, 220)
        self.assertEqual(
            outcome.items[0].provenance["admission_gate"],
            "scholarly_source_and_verbatim_quote",
        )

    async def test_gap_dispatches_research_agent(self) -> None:
        session = await self.manager.create("Loschbour")
        events = [event async for event in session.stream()]
        event_types = [event["type"] for event in events]
        self.assertIn("research.dispatched", event_types)
        self.assertIn("research.returned", event_types)
        dispatched = next(event for event in events if event["type"] == "research.dispatched")
        self.assertIn("本轮检索参数", dispatched["data"]["query"])
        self.assertIn("Loschbour", dispatched["data"]["query"])
        research_leaves = [
            event
            for event in events
            if event["type"] == "evidence.added"
            and event["data"]["evidence"]["record_type"] == "research_finding"
        ]
        self.assertEqual(len(research_leaves), 1)
        self.assertTrue(
            any(observation.get("tool") == "research_agent" for observation in session.state.observations)
        )

    async def test_completed_investigation_can_continue_in_new_direction(self) -> None:
        session = await self.manager.create("Loschbour")
        first_events = [event async for event in session.stream()]
        cursor = first_events[-1]["sequence"]

        accepted = await self.manager.redirect(session.id, "一个未分类的输入")
        self.assertEqual(accepted.mode, "continued")
        continued = [event async for event in session.stream(after=cursor)]

        self.assertEqual(continued[0]["type"], "investigation.redirected")
        self.assertEqual(continued[0]["data"]["direction"], "一个未分类的输入")
        self.assertEqual(continued[-1]["type"], "investigation.completed")
        self.assertTrue(
            any(
                event["type"] == "evidence.added"
                and event["data"]["evidence"]["record_type"] == "evidence_gap"
                for event in continued
            )
        )

    async def test_stop_is_a_control_event_and_session_history_is_listable(self) -> None:
        manager = InvestigationManager(
            SlowProvider(),
            EvidenceTools(ROOT / "artifacts/catalog.sqlite", ROOT / "artifacts/numeric"),
        )
        session = await manager.create("曹操")
        await asyncio.sleep(0)
        stopped = await manager.stop(session.id)
        events = [event async for event in session.stream()]

        self.assertEqual(stopped.mode, "stopped")
        self.assertEqual(events[-1]["type"], "investigation.stopped")
        self.assertNotIn("investigation.completed", [event["type"] for event in events])
        await session.publish("research.returned", {"message": "late result"})
        summary = manager.list_sessions()[0]
        self.assertEqual(summary.question, "曹操")
        self.assertEqual(summary.status, "stopped")


if __name__ == "__main__":
    unittest.main()
