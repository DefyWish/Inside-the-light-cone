from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from pydantic import BaseModel

from .evidence_tools import EvidenceTools, ToolResult
from .providers import InvestigationState, LLMProvider
from .research_agent import ResearchAgent


class InvestigationRequest(BaseModel):
    question: str


class InvestigationCreated(BaseModel):
    investigation_id: str
    provider: str


class RedirectRequest(BaseModel):
    direction: str


class RedirectAccepted(BaseModel):
    investigation_id: str
    direction: str
    mode: str


class StopAccepted(BaseModel):
    investigation_id: str
    mode: str


class InvestigationSummary(BaseModel):
    investigation_id: str
    question: str
    provider: str
    status: str
    event_count: int
    created_at: str


class ClaimStore:
    """运行时 claim/relation 持久化；与只读的 catalog 构建制品分离。"""
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT NOT NULL,
                    investigation_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    event_year_start INTEGER,
                    event_year_end INTEGER,
                    motivation TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (investigation_id, claim_id)
                )"""
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(claims)")
            }
            if "status" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN status TEXT NOT NULL DEFAULT 'open'"
                )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT NOT NULL,
                    investigation_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (investigation_id, relation_id)
                )"""
            )

    def save_claim(self, investigation_id: str, claim: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO claims (
                    claim_id, investigation_id, text, evidence_level,
                    event_year_start, event_year_end, motivation, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim["claim_id"], investigation_id, claim["text"],
                    claim["evidence_level"], claim.get("event_year_start"),
                    claim.get("event_year_end"), claim.get("motivation"),
                    datetime.now(timezone.utc).isoformat(),
                    claim.get("status", "open"),
                ),
            )

    def save_relation(self, investigation_id: str, relation: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO relations (
                    relation_id, investigation_id, subject_id, predicate,
                    object_id, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    relation["relation_id"], investigation_id, relation["subject_id"],
                    relation["predicate"], relation["object_id"], relation.get("note"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


@dataclass
class InvestigationSession:
    id: str
    question: str
    provider: str
    state: InvestigationState
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    redirects: asyncio.Queue[str] = field(default_factory=asyncio.Queue)

    @property
    def status(self) -> str:
        if not self.events:
            return "connecting"
        for event in reversed(self.events):
            terminal = event["type"]
            if terminal == "investigation.completed":
                return "completed"
            if terminal == "investigation.failed":
                return "failed"
            if terminal == "investigation.stopped":
                return "stopped"
        return "running"

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        async with self.condition:
            event = {
                "sequence": len(self.events) + 1,
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
            self.events.append(event)
            self.condition.notify_all()

    async def finish(self) -> None:
        async with self.condition:
            self.done = True
            self.condition.notify_all()

    async def reopen(self) -> None:
        async with self.condition:
            self.done = False
            self.condition.notify_all()

    async def stream(self, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        cursor = max(after, 0)
        while True:
            async with self.condition:
                await self.condition.wait_for(lambda: cursor < len(self.events) or self.done)
                pending = self.events[cursor:]
                finished = self.done
            for event in pending:
                cursor += 1
                yield event
            if finished and cursor >= len(self.events):
                return


class InvestigationManager:
    STOP_COMMANDS = {
        "停止",
        "停止调查",
        "终止",
        "终止调查",
        "停下",
        "stop",
        "stop investigation",
    }

    def __init__(
        self,
        provider: LLMProvider,
        evidence_tools: EvidenceTools,
        research_agent: ResearchAgent | None = None,
        maximum_steps: int = 28,
        claim_store: ClaimStore | None = None,
    ) -> None:
        self.provider = provider
        self.evidence_tools = evidence_tools
        self.research_agent = research_agent
        self.maximum_steps = maximum_steps
        self.claim_store = claim_store
        self.sessions: dict[str, InvestigationSession] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def create(self, question: str) -> InvestigationSession:
        investigation_id = str(uuid.uuid4())
        session = InvestigationSession(
            id=investigation_id,
            question=question,
            provider=self.provider.name,
            state=InvestigationState(question=question),
        )
        self.sessions[investigation_id] = session
        self._start_task(session, resumed=False)
        return session

    def _start_task(self, session: InvestigationSession, resumed: bool) -> None:
        task = asyncio.create_task(self._run(session, resumed=resumed))
        self.tasks[session.id] = task
        task.add_done_callback(lambda _: self.tasks.pop(session.id, None))

    def get(self, investigation_id: str) -> InvestigationSession | None:
        return self.sessions.get(investigation_id)

    @classmethod
    def is_stop_command(cls, text: str) -> bool:
        return text.strip().casefold() in cls.STOP_COMMANDS

    def list_sessions(self) -> list[InvestigationSummary]:
        sessions = sorted(self.sessions.values(), key=lambda item: item.created_at, reverse=True)
        return [
            InvestigationSummary(
                investigation_id=session.id,
                question=session.question,
                provider=session.provider,
                status=session.status,
                event_count=len(session.events),
                created_at=session.created_at,
            )
            for session in sessions
        ]

    async def stop(self, investigation_id: str) -> StopAccepted | None:
        session = self.get(investigation_id)
        if session is None:
            return None
        if session.done:
            return StopAccepted(investigation_id=investigation_id, mode="already_done")
        await self._publish_agent_status(session, "stopped", "调查已停止。")
        await session.publish("investigation.stopped", {"message": "调查已停止。"})
        task = self.tasks.get(investigation_id)
        if task is not None:
            task.cancel()
        await session.finish()
        return StopAccepted(investigation_id=investigation_id, mode="stopped")

    async def redirect(self, investigation_id: str, direction: str) -> RedirectAccepted | None:
        session = self.get(investigation_id)
        if session is None:
            return None
        cleaned = direction.strip()
        if not cleaned:
            return RedirectAccepted(
                investigation_id=investigation_id,
                direction=cleaned,
                mode="ignored",
            )
        if self.is_stop_command(cleaned):
            stopped = await self.stop(investigation_id)
            return RedirectAccepted(
                investigation_id=investigation_id,
                direction=cleaned,
                mode=stopped.mode if stopped else "ignored",
            )
        if session.done:
            await session.reopen()
            self._reset_direction(session, cleaned)
            await session.publish(
                "investigation.redirected",
                {"direction": cleaned, "mode": "continued"},
            )
            self._start_task(session, resumed=True)
            mode = "continued"
        else:
            await session.redirects.put(cleaned)
            mode = "queued"
        return RedirectAccepted(
            investigation_id=investigation_id,
            direction=cleaned,
            mode=mode,
        )

    @staticmethod
    def _reset_direction(session: InvestigationSession, direction: str) -> None:
        session.state.question = direction
        session.state.provider_cursor = 0
        session.state.provider_scenario = None

    async def _apply_redirect(self, session: InvestigationSession) -> bool:
        latest: str | None = None
        while True:
            try:
                latest = session.redirects.get_nowait()
            except asyncio.QueueEmpty:
                break
        if latest is None:
            return False
        self._reset_direction(session, latest)
        await session.publish(
            "investigation.redirected",
            {"direction": latest, "mode": "interrupted"},
        )
        return True

    @staticmethod
    def _is_gap(tool_name: str, result: ToolResult) -> bool:
        if tool_name == "mark_evidence_gap":
            return False
        if result.alias_only:
            return True
        return result.status != "ok" or any(
            item.get("record_type") == "evidence_gap" for item in result.items
        )

    @staticmethod
    def _has_marked_gap(state: InvestigationState) -> bool:
        return any(
            item.get("record_type") == "evidence_gap"
            for observation in state.observations
            for item in observation.get("items", [])
        )

    @staticmethod
    def _ensure_evidence_id(item: dict[str, Any]) -> str:
        existing = item.get("evidence_id")
        if existing:
            return str(existing)
        identity = {
            key: item.get(key)
            for key in (
                "source_id", "source_url", "title", "claim", "individual_id",
                "genetic_id", "site", "event_year_start", "event_year_end",
            )
            if item.get(key) is not None
        }
        evidence_id = "ev:" + uuid.uuid5(
            uuid.NAMESPACE_URL,
            json.dumps(identity or item, ensure_ascii=False, sort_keys=True, default=str),
        ).hex
        item["evidence_id"] = evidence_id
        return evidence_id

    async def _publish_agent_status(
        self,
        session: InvestigationSession,
        status: str,
        message: str,
        activity: str | None = None,
        pending_research: int = 0,
    ) -> None:
        state = session.state
        active_line = next(
            (line["line"] for line in state.lines if line["status"] == "open"),
            None,
        )
        gaps = [
            item.get("topic") or item.get("title")
            for observation in state.observations
            for item in observation.get("items", [])
            if item.get("record_type") == "evidence_gap"
        ]
        await session.publish(
            "agent.status",
            {
                "state": status,
                "objective": state.question,
                "message": message,
                "activity": activity,
                "active_line": active_line,
                "next_intention": active_line,
                "pending_research": pending_research,
                "hypotheses": [
                    {"id": claim["claim_id"], "text": claim["text"], "status": claim["status"]}
                    for claim in state.claims[-4:]
                ],
                "gaps": [gap for gap in gaps[-4:] if gap],
            },
        )

    @staticmethod
    def _evidence_label_index(state: InvestigationState) -> dict[str, str]:
        """把已收集证据的 URL/DOI/标题等标识映射到展示名，供关系目标归一化。"""
        index: dict[str, str] = {}
        for observation in state.observations:
            for item in observation.get("items", []):
                label = (
                    item.get("claim") or item.get("title") or item.get("individual_id")
                    or item.get("genetic_id") or item.get("site") or item.get("topic")
                )
                if not label:
                    continue
                label = str(label).strip()
                for key in (
                    item.get("source_url"), item.get("doi"), item.get("title"),
                    item.get("claim"), item.get("individual_id"), item.get("genetic_id"),
                    item.get("site"), label,
                ):
                    if key:
                        index[str(key).strip()] = label
        return index

    def _resolve_link_target(
        self, state: InvestigationState, target: str, exclude: str | None = None
    ) -> str:
        cleaned = target.strip()
        for claim in state.claims:
            if claim["claim_id"] == cleaned:
                return cleaned
        lowered = cleaned.casefold()
        for claim in state.claims:
            if claim["claim_id"] == exclude:
                continue
            if lowered and (lowered in claim["text"].casefold() or claim["text"].casefold() in lowered):
                return claim["claim_id"]
        # URL/DOI/PMID/标题 → 证据展示名归一化，保证前端可按标签挂接
        index = self._evidence_label_index(state)
        if cleaned in index:
            return index[cleaned]
        best: str | None = None
        for key, label in index.items():
            if len(cleaned) >= 8 and (cleaned in key or key in cleaned):
                best = label
                break
        return best or cleaned

    async def _update_plan(self, session: InvestigationSession, action: Any) -> None:
        state = session.state
        for line_text in action.lines:
            if not any(line["line"] == line_text for line in state.lines):
                state.lines.append({"line": line_text, "status": "open", "note": None})
        for entry in action.line_status:
            for line in state.lines:
                if line["line"] == entry.get("line"):
                    line["status"] = entry.get("status", line["status"])
                    line["note"] = entry.get("note")
        await session.publish(
            "plan.updated",
            {"lines": state.lines, "motivation": action.motivation},
        )

    def _cover_line(self, session: InvestigationSession, line_text: str | None) -> None:
        if not line_text:
            return
        state = session.state
        for line in state.lines:
            if line["line"] == line_text and line["status"] == "open":
                line["status"] = "covered"

    async def _record_claim(self, session: InvestigationSession, action: Any) -> None:
        state = session.state
        # 明暗线升降格：带 claim_id 的 claim 动作是对既有判断的状态更新
        if action.claim_id:
            for claim in state.claims:
                if claim["claim_id"] == action.claim_id and action.status:
                    if claim["status"] == action.status:
                        # 空转守卫：状态未变化的重复升级不发布事件，并告知模型继续推进
                        state.observations.append(
                            {
                                "tool": "system",
                                "status": "no_op",
                                "message": f"{action.claim_id} 已是 {action.status}，无需重复更新；请推进其他线索或收束。",
                            }
                        )
                        return
                    claim["status"] = action.status
                    await session.publish(
                        "claim.updated",
                        {"claim": claim, "motivation": action.motivation},
                    )
                    if self.claim_store is not None:
                        self.claim_store.save_claim(session.id, claim)
                    return
        claim_id = f"c{len(state.claims) + 1}"
        claim_payload = {
            "claim_id": claim_id,
            "text": action.claim or action.text or "",
            "line": action.line,
            "status": action.status or "open",
            "evidence_level": action.evidence_level or "view_model",
            "event_year_start": action.event_year_start,
            "event_year_end": action.event_year_end,
            "motivation": action.motivation,
        }
        state.claims.append(claim_payload)
        self._cover_line(session, action.line)
        await session.publish("claim.added", {"claim": claim_payload})
        if self.claim_store is not None:
            self.claim_store.save_claim(session.id, claim_payload)
        for link in action.links:
            relation_payload = {
                "relation_id": f"r{len(state.relations) + 1}",
                "subject_id": claim_id,
                "predicate": link.predicate,
                "object_id": self._resolve_link_target(state, link.target, exclude=claim_id),
                "note": link.note,
            }
            state.relations.append(relation_payload)
            await session.publish("relation.added", {"relation": relation_payload})
            if self.claim_store is not None:
                self.claim_store.save_relation(session.id, relation_payload)

    async def _record_curation_event(self, session: InvestigationSession, action: Any) -> None:
        if action.event is None:
            return
        payload = action.event.model_dump()
        references = payload["source_ids"] + payload["claim_ids"] + payload["evidence_ids"]
        if not references and payload["epistemic_status"] != "gap":
            session.state.observations.append(
                {
                    "tool": "system",
                    "status": "continue_required",
                    "message": "策展节点缺少来源、判断或证据引用，请先检索再生成。",
                }
            )
            return
        if not payload.get("event_id"):
            identity = ":".join(
                [
                    *payload["subject_ids"],
                    payload["branch"],
                    payload["title"],
                    str(payload.get("event_year_start")),
                    str(payload.get("event_year_end")),
                ]
            )
            payload["event_id"] = "evt:" + uuid.uuid5(uuid.NAMESPACE_URL, identity).hex
        previous = next(
            (item for item in session.state.curation_events if item["event_id"] == payload["event_id"]),
            None,
        )
        if previous is None:
            session.state.curation_events.append(payload)
            event_type = "curation.event_added"
        else:
            previous.update(payload)
            payload = previous
            event_type = "curation.event_updated"
        await session.publish(event_type, {"event": payload})

    async def _research_gap(
        self,
        session: InvestigationSession,
        state: InvestigationState,
        question: str,
        tool_name: str,
        tool_arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if self.research_agent is None:
            return
        source_focus = {
            "search_literature": "同行评议论文、正式考古报告、学术专著或学位论文",
            "search_ancient_samples": "古基因组原始论文、补充材料或权威样本数据库",
            "search_genetic_relations": "亲缘分析原始论文、补充材料或正式数据记录",
            "search_archaeological_sites": "正式发掘报告、考古期刊论文、科研机构或博物馆目录",
            "search_place_history": "历史地理学术成果、方志原文或权威地名数据库",
            "search_curated_sources": "史传、作品集、方志、发掘报告、古基因组数据集或同行评议论文",
        }.get(tool_name, "可核验的学术原始来源")
        query = (
            f"研究问题：{question}\n"
            f"待补证环节：{tool_name}；本轮检索参数："
            f"{json.dumps(tool_arguments, ensure_ascii=False, sort_keys=True)}；"
            f"{result.message or '证据仍为空白'}\n"
            f"来源门槛：{source_focus}。排除新闻、门户转载、自媒体、百科和聚合页。"
            "寻找能推进故事脉络的不同证据环节，避免多条来源重复同一消息。"
        )
        await session.publish(
            "research.dispatched",
            {"query": query, "gap_tool": tool_name},
        )
        outcome = await self.research_agent.investigate(query)
        outcome_items = [item.model_dump() for item in outcome.items]
        for item in outcome_items:
            self._ensure_evidence_id(item)
        state.observations.append(
            {
                "tool": "research_agent",
                "status": outcome.status,
                "items": outcome_items,
                "message": outcome.message,
            }
        )
        event_type = {
            "ok": "research.returned",
            "no_data": "research.no_data",
            "rejected": "research.rejected",
        }[outcome.status]
        await session.publish(
            event_type,
            {
                "query": query,
                "gap_tool": tool_name,
                **outcome.model_dump(),
            },
        )
        for item in outcome_items:
            await session.publish(
                "evidence.added",
                {
                    "tool": "research_agent",
                    "status": "ok",
                    "evidence": item,
                },
            )

    async def _run(self, session: InvestigationSession, resumed: bool = False) -> None:
        state = session.state
        pending_research: set[asyncio.Task[None]] = set()
        if not resumed:
            await session.publish(
                "investigation.started",
                {"question": session.question, "provider": session.provider},
            )
        await self._publish_agent_status(
            session,
            "planning" if not state.lines else "investigating",
            "正在拆解问题。" if not state.lines else "正在继续调查。",
        )
        try:
            for _ in range(self.maximum_steps):
                # 真异步：只清理已完成的外勤任务，绝不原地等待
                pending_research = {task for task in pending_research if not task.done()}
                await self._apply_redirect(session)
                action = await self.provider.next_action(state)
                if await self._apply_redirect(session):
                    continue
                if action.motivation:
                    await session.publish("agent.motivation", {"text": action.motivation})
                if action.type == "tool_call":
                    if not action.tool:
                        await session.publish(
                            "agent.error", {"message": "模型动作缺少工具名。"}
                        )
                        break
                    await session.publish(
                        "tool.called",
                        {"tool": action.tool, "arguments": action.arguments},
                    )
                    await self._publish_agent_status(
                        session,
                        "investigating",
                        action.motivation or "正在检索证据。",
                        activity=action.tool,
                        pending_research=len(pending_research),
                    )
                    result = self.evidence_tools.execute(action.tool, action.arguments)
                    for item in result.items:
                        self._ensure_evidence_id(item)
                    result_payload = result.model_dump()
                    state.observations.append(result_payload)
                    await session.publish("tool.result", result_payload)
                    for item in result.items:
                        await session.publish(
                            "evidence.added",
                            {
                                "tool": action.tool,
                                "status": result.status,
                                "evidence": item,
                            },
                        )
                    if self._is_gap(action.tool, result) and self.research_agent is not None:
                        state.observations.append(
                            {
                                "tool": "research_agent",
                                "status": "pending",
                                "message": f"正在联网追查 {action.tool} 的证据缺口。",
                            }
                        )
                        task = asyncio.create_task(
                            self._research_gap(
                                session,
                                state,
                                state.question,
                                action.tool,
                                action.arguments,
                                result,
                            )
                        )
                        pending_research.add(task)
                        await self._publish_agent_status(
                            session,
                            "researching",
                            "本地证据不足，正在外部补证。",
                            activity=action.tool,
                            pending_research=len(pending_research),
                        )
                    continue
                if action.type == "plan":
                    await self._update_plan(session, action)
                    await self._publish_agent_status(
                        session,
                        "investigating",
                        "调查主线已更新。",
                        pending_research=len(pending_research),
                    )
                    continue
                if action.type == "claim":
                    await self._record_claim(session, action)
                    await self._publish_agent_status(
                        session,
                        "synthesizing",
                        "正在校准判断与证据关系。",
                        pending_research=len(pending_research),
                    )
                    continue
                if action.type == "curation_event":
                    await self._record_curation_event(session, action)
                    await self._publish_agent_status(
                        session,
                        "synthesizing",
                        "正在把证据投影到地图、生命树与时间轴。",
                        pending_research=len(pending_research),
                    )
                    continue
                if action.type == "narration":
                    await session.publish("narration", {"text": action.text or ""})
                    continue
                if pending_research:
                    await asyncio.gather(*tuple(pending_research))
                    pending_research.clear()
                    continue
                if await self._apply_redirect(session):
                    continue
                unresolved = [line["line"] for line in state.lines if line["status"] == "open"]
                if unresolved:
                    state.observations.append(
                        {
                            "tool": "system",
                            "status": "continue_required",
                            "message": f"收束被驳回：以下主线尚未了断：{'、'.join(unresolved)}。每条主线需形成带外部证据的 claim（covered）或明确声明缺口（gap）。",
                        }
                    )
                    await session.publish(
                        "investigation.continue_required",
                        {"message": f"主线未了断：{'、'.join(unresolved)}", "unresolved": unresolved},
                    )
                    continue
                if not state.claims and not self._has_marked_gap(state):
                    state.observations.append(
                        {
                            "tool": "system",
                            "status": "continue_required",
                            "message": "收束被驳回：至少形成一个 claim，或用 mark_evidence_gap 明确声明缺口。",
                        }
                    )
                    await session.publish(
                        "investigation.continue_required",
                        {"message": "尚未形成任何 claim 或缺口声明，调查继续。"},
                    )
                    continue
                await session.publish(
                    "investigation.completed",
                    {
                        "summary": action.text or "调查完成。",
                        "steps": state.provider_cursor,
                        "scenario": state.provider_scenario,
                        "claims": len(state.claims),
                        "relations": len(state.relations),
                    },
                )
                await self._publish_agent_status(session, "completed", "策展调查已完成。")
                await session.finish()
                return
            if pending_research:
                await asyncio.gather(*tuple(pending_research))
            await session.publish(
                "investigation.completed",
                {"summary": "调查达到本轮步数上限。", "steps": state.provider_cursor},
            )
            await self._publish_agent_status(session, "completed", "本轮调查已收束。")
        except asyncio.CancelledError:
            for task in pending_research:
                task.cancel()
            if pending_research:
                await asyncio.gather(*tuple(pending_research), return_exceptions=True)
            raise
        except Exception as error:
            if pending_research:
                await asyncio.gather(*tuple(pending_research), return_exceptions=True)
            await self._publish_agent_status(session, "failed", "调查中断。")
            await session.publish(
                "investigation.failed",
                {"message": str(error), "error_type": type(error).__name__},
            )
        finally:
            await session.finish()


def encode_sse(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['sequence']}\nevent: {event['type']}\ndata: {payload}\n\n"
