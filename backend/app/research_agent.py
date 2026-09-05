from __future__ import annotations

import asyncio
import http.client
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .providers import HTTP_USER_AGENT, REMOTE_HTTP_LOCK, SSL_CONTEXT


class ResearchFinding(BaseModel):
    record_type: Literal["research_finding"] = "research_finding"
    title: str
    source_url: str
    quote: str
    summary: str
    claim: str
    relation_to_question: str
    source_kind: Literal[
        "peer_reviewed_article",
        "excavation_report",
        "academic_monograph",
        "thesis",
        "official_database",
        "institutional_repository",
        "museum_catalog",
    ]
    authors: list[str] = Field(default_factory=list)
    publication_title: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    event_year_start: int | None = None
    event_year_end: int | None = None
    narrative_role: Literal[
        "context", "event", "evidence", "debate", "gap", "legacy"
    ] = "evidence"
    curation_role: Literal["event", "context"] = "context"
    scope_note: str | None = None
    evidence_level: Literal["view_model"] = "view_model"
    source_id: str
    date_text: str | None = None
    mean_bp: float | None = None
    site: str | None = None
    political_entity: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    review_status: Literal["temporary"] = "temporary"


class ResearchOutcome(BaseModel):
    status: Literal["ok", "no_data", "rejected"]
    items: list[ResearchFinding] = Field(default_factory=list)
    message: str


class ResearchProvider(Protocol):
    name: str

    async def investigate(self, query: str) -> list[dict[str, Any]]: ...


class MockResearchLLM:
    """Fixture-driven stand-in for the research Agent's remote model and search."""

    name = "mock-research"

    def __init__(self, corpus_path: Path, delay_seconds: float = 0.05) -> None:
        payload = json.loads(corpus_path.read_text())
        self.entries = payload["entries"]
        self.delay_seconds = delay_seconds

    async def investigate(self, query: str) -> list[dict[str, Any]]:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        normalized = query.casefold()
        return [
            entry
            for entry in self.entries
            if any(term.casefold() in normalized for term in entry.get("match_contains", []))
        ]


class KimiWebSearchResearchProvider:
    """Kimi adapter for the official web-search Formula API."""

    formula_uri = "moonshot/web-search:latest"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.name = f"kimi-web-search:{model}"

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": HTTP_USER_AGENT,
            },
            method=method,
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=SSL_CONTEXT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                last_error = error
                if attempt == 0 and (error.code == 429 or error.code >= 500):
                    time.sleep(1)
                    continue
                raise RuntimeError(f"Kimi web search HTTP {error.code}") from error
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as error:
                last_error = error
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Kimi web search request failed")

    @staticmethod
    def _json_payload(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Kimi web search response did not contain JSON")
        return json.loads(cleaned[start : end + 1])

    def _investigate_locked(self, query: str) -> list[dict[str, Any]]:
        tools = self._call("GET", f"/formulas/{self.formula_uri}/tools").get("tools", [])
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是历史、考古与古基因组文献研究 Agent。仅使用联网搜索实际找到的页面。"
                    "只检索同行评议论文、正式考古发掘报告、学术专著、学位论文、大学或科研院所仓储、"
                    "博物馆藏品目录和权威学术数据库。禁止新闻报道、门户转载、自媒体、百科、营销文章和聚合页。"
                    "最终只输出 JSON：{\"items\":[...]}; 每项必须包含 title、source_url、"
                    "quote、summary、claim、relation_to_question、source_kind、source_id。"
                    "source_kind 只能是 peer_reviewed_article、excavation_report、academic_monograph、thesis、"
                    "official_database、institutional_repository、museum_catalog。"
                    "quote 必须是来源原文，source_url 必须直达论文、报告、数据库记录或机构仓储页面。"
                    "claim 写该来源支持的一个历史事件或判断；relation_to_question 写它怎样推进当前问题。"
                    "同时输出 authors、publication_title、publication_year、doi、event_year_start、event_year_end、"
                    "narrative_role、date_text、mean_bp、site、political_entity、latitude、longitude。"
                    "event_year 使用公历整数，公元前为负数，表示 claim 所属的历史时间；不得拿网页发布年份代替。"
                    "mean_bp 只用于古样本或考古对象的科学测年，表示相对 1950 年的距今年数。"
                    "narrative_role 只能是 context、event、evidence、debate、gap、legacy。无法确认的字段填 null。"
                    "只有与调查对象直接对应的历史事件才标为event或legacy；区域背景、对照样本、阴性结果和证据缺口标为context、evidence、debate或gap。"
                    "最多返回 5 条能组成前后脉络、彼此作用不同的来源，避免用多篇文章重复同一消息。"
                    "找不到合格来源时输出 {\"items\":[]}."
                ),
            },
            {"role": "user", "content": query},
        ]
        for _ in range(4):
            response = self._call(
                "POST",
                "/chat/completions",
                {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "reasoning_effort": "low",
                },
            )
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                payload = self._json_payload(str(message.get("content") or ""))
                items = payload.get("items", [])
                return items if isinstance(items, list) else []
            messages.append(
                {key: value for key, value in message.items() if key in {"role", "content", "tool_calls"}}
            )
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                fiber = self._call(
                    "POST",
                    f"/formulas/{self.formula_uri}/fibers",
                    {
                        "name": function.get("name"),
                        "arguments": function.get("arguments", "{}"),
                    },
                )
                context = fiber.get("context", {})
                result = context.get("output") or context.get("encrypted_output") or ""
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": result,
                    }
                )
        return []

    def _investigate(self, query: str) -> list[dict[str, Any]]:
        with REMOTE_HTTP_LOCK:
            return self._investigate_locked(query)

    async def investigate(self, query: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._investigate, query)


def research_provider_from_environment(corpus_path: Path) -> ResearchProvider:
    mode = os.getenv("LIGHTCONE_RESEARCH_MODE", "auto").strip().casefold()
    if mode == "mock":
        return MockResearchLLM(corpus_path)
    for slot in ("PRIMARY", "BACKUP"):
        base_url = os.getenv(f"LIGHTCONE_{slot}_BASE_URL", "").strip()
        api_key = os.getenv(f"LIGHTCONE_{slot}_API_KEY", "").strip()
        model = os.getenv(f"LIGHTCONE_{slot}_MODEL", "").strip()
        if base_url and api_key and model and (
            "moonshot" in base_url.casefold() or model.casefold().startswith("kimi")
        ):
            return KimiWebSearchResearchProvider(base_url, api_key, model)
    return MockResearchLLM(corpus_path)


class ResearchStagingStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS research_findings (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(research_findings)")
            }
            if "finding_json" not in columns:
                connection.execute(
                    "ALTER TABLE research_findings ADD COLUMN finding_json TEXT"
                )
            connection.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS research_fts USING fts5(
                    title, quote, summary,
                    content='research_findings', content_rowid='rowid',
                    tokenize='trigram'
                )"""
            )
            total = connection.execute("SELECT COUNT(*) FROM research_findings").fetchone()[0]
            indexed = connection.execute("SELECT COUNT(*) FROM research_fts").fetchone()[0]
            if total != indexed:
                connection.execute("DELETE FROM research_fts")
                connection.execute(
                    """INSERT INTO research_fts(rowid, title, quote, summary)
                       SELECT rowid, title, quote, summary FROM research_findings"""
                )

    def stage(self, query: str, finding: ResearchFinding) -> str:
        finding_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"kalpatower:research:{query}:{finding.source_url}:{finding.quote}",
            )
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO research_findings (
                    id, query, title, source_url, quote, summary,
                    evidence_level, provenance_json, review_status, created_at, finding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding_id,
                    query,
                    finding.title,
                    finding.source_url,
                    finding.quote,
                    finding.summary,
                    finding.evidence_level,
                    json.dumps(finding.provenance, ensure_ascii=False, sort_keys=True),
                    finding.review_status,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(finding.model_dump(), ensure_ascii=False),
                ),
            )
            connection.execute(
                """INSERT OR IGNORE INTO research_fts(rowid, title, quote, summary)
                   SELECT rowid, title, quote, summary FROM research_findings
                   WHERE id = ?""",
                (finding_id,),
            )
        return finding_id


class ResearchAgent:
    LOW_QUALITY_HOSTS = {
        "news.cn",
        "xinhuanet.com",
        "chinanews.com.cn",
        "cnr.cn",
        "sina.com.cn",
        "sohu.com",
        "163.com",
        "qq.com",
        "thepaper.cn",
        "shobserver.com",
        "baijiahao.baidu.com",
        "mp.weixin.qq.com",
    }
    ACADEMIC_HOST_MARKERS = (
        "doi.org",
        "springer.com",
        "nature.com",
        "sciencedirect.com",
        "wiley.com",
        "tandfonline.com",
        "jstor.org",
        "cambridge.org",
        "oup.com",
        "plos.org",
        "frontiersin.org",
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "kaogu.cssn.cn",
    )

    def __init__(self, provider: ResearchProvider, staging: ResearchStagingStore) -> None:
        self.provider = provider
        self.staging = staging

    @classmethod
    def _is_low_quality_host(cls, source_url: str) -> bool:
        host = (urlparse(source_url).hostname or "").casefold()
        return any(host == blocked or host.endswith(f".{blocked}") for blocked in cls.LOW_QUALITY_HOSTS)

    @classmethod
    def _infer_source_kind(cls, candidate: dict[str, Any], source_url: str) -> str | None:
        declared = str(candidate.get("source_kind") or "").strip()
        allowed = ResearchFinding.model_fields["source_kind"].annotation
        if declared and declared in getattr(allowed, "__args__", ()):
            return declared
        host = (urlparse(source_url).hostname or "").casefold()
        doi = str(candidate.get("doi") or "").strip()
        if doi or any(marker in host for marker in cls.ACADEMIC_HOST_MARKERS):
            return "peer_reviewed_article"
        if host.endswith((".edu", ".edu.cn", ".ac.cn")):
            return "institutional_repository"
        if host.endswith(".gov.cn"):
            return "official_database"
        return None

    async def investigate(self, query: str) -> ResearchOutcome:
        try:
            candidates = await self.provider.investigate(query)
        except Exception as error:
            return ResearchOutcome(
                status="no_data",
                message=f"研究 Agent 联网检索失败：{type(error).__name__}: {error}",
            )
        if not candidates:
            return ResearchOutcome(
                status="no_data",
                message="研究 Agent 没有找到满足引文门槛的结果。",
            )

        accepted: list[ResearchFinding] = []
        rejected = 0
        for candidate in candidates:
            quote = str(candidate.get("quote", "")).strip()
            source_url = str(candidate.get("source_url", "")).strip()
            source_kind = self._infer_source_kind(candidate, source_url)
            if (
                not quote
                or not source_url.startswith(("https://", "http://"))
                or self._is_low_quality_host(source_url)
                or source_kind is None
            ):
                rejected += 1
                continue
            normalized = {
                **candidate,
                "source_id": str(candidate.get("source_id") or source_url),
                "evidence_level": "view_model",
                "source_kind": source_kind,
                "authors": candidate.get("authors") if isinstance(candidate.get("authors"), list) else [],
                "narrative_role": candidate.get("narrative_role") or "evidence",
                "curation_role": (
                    "event"
                    if candidate.get("narrative_role") in {"event", "legacy"}
                    else "context"
                ),
                "claim": str(candidate.get("claim") or candidate.get("summary") or candidate.get("title") or "").strip(),
                "relation_to_question": str(
                    candidate.get("relation_to_question")
                    or candidate.get("scope_note")
                    or candidate.get("summary")
                    or ""
                ).strip(),
            }
            finding = ResearchFinding.model_validate(
                {
                    **normalized,
                    "provenance": {
                        **candidate.get("provenance", {}),
                        "provider": self.provider.name,
                        "admission_gate": "scholarly_source_and_verbatim_quote",
                    },
                }
            )
            finding_id = self.staging.stage(query, finding)
            accepted.append(finding.model_copy(update={"provenance": {**finding.provenance, "staging_id": finding_id}}))

        if accepted:
            return ResearchOutcome(
                status="ok",
                items=accepted,
                message=f"研究 Agent 返回 {len(accepted)} 条带原文引文的临时结果。",
            )
        return ResearchOutcome(
            status="rejected",
            message=f"拒收 {rejected} 条不符合学术来源、原文引文或直达地址门槛的结果。",
        )
