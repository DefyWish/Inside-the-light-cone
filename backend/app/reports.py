from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from .investigation import InvestigationSession


Audience = Literal["professional", "public"]

LEVEL_LABELS = {
    "fact_genomic": "古基因组事实",
    "fact_archaeology": "考古事实",
    "fact_documentary": "文献事实",
    "view_model": "研究观点",
}

SOURCE_LABELS = {
    "primary_chronicle": "史传",
    "collected_works": "作品集",
    "local_gazetteer": "方志",
    "rare_book": "善本",
    "memoir": "回忆录",
    "ancient_genome_dataset": "古基因组数据集",
    "peer_reviewed_article": "同行评议论文",
    "excavation_report": "发掘报告",
    "academic_monograph": "学术专著",
    "thesis": "学位论文",
    "official_database": "权威数据库",
    "institutional_repository": "机构仓储",
    "museum_catalog": "博物馆资料",
}


def _unique_evidence(session: InvestigationSession) -> list[dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for observation in session.state.observations:
        for item in observation.get("items", []):
            if item.get("record_type") == "evidence_gap":
                continue
            identity = str(
                item.get("evidence_id")
                or item.get("source_id")
                or item.get("source_url")
                or item.get("title")
            )
            evidence[identity] = item
    return list(evidence.values())


def _final_summary(session: InvestigationSession) -> str:
    for event in reversed(session.events):
        if event["type"] == "investigation.completed":
            return str(event["data"].get("summary") or "调查已经完成。")
    return "调查已经完成。"


def _shorten(text: str, limit: int = 260) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip("，。；：") + "…"


def _source_rows(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in evidence:
        if not item.get("source_url"):
            continue
        rows.append(
            {
                "source_id": item.get("source_id") or item.get("evidence_id"),
                "title": item.get("title") or item.get("publication_title") or "来源",
                "source_kind": item.get("source_kind"),
                "source_label": SOURCE_LABELS.get(item.get("source_kind"), "来源"),
                "publication_year": item.get("publication_year"),
                "url": item["source_url"],
            }
        )
    return rows


def _professional_sections(session: InvestigationSession, summary: str) -> list[dict[str, Any]]:
    claims_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in session.state.claims:
        claims_by_line[str(claim.get("line") or "综合判断")].append(claim)

    sections: list[dict[str, Any]] = [
        {
            "heading": "调查摘要",
            "paragraphs": [paragraph.strip() for paragraph in summary.split("\n\n") if paragraph.strip()],
            "items": [],
        }
    ]
    ordered_lines = [line.get("line") for line in session.state.lines if line.get("line")]
    for line in [*ordered_lines, *claims_by_line.keys()]:
        if not line or not claims_by_line.get(line):
            continue
        if any(section["heading"] == line for section in sections):
            continue
        sections.append(
            {
                "heading": line,
                "paragraphs": [],
                "items": [
                    {
                        "title": LEVEL_LABELS.get(claim.get("evidence_level"), "调查判断"),
                        "text": claim.get("text") or "",
                        "status": claim.get("status") or "open",
                    }
                    for claim in claims_by_line[line]
                ],
            }
        )
    return sections


def _public_sections(session: InvestigationSession, summary: str) -> list[dict[str, Any]]:
    events_by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in sorted(
        session.state.curation_events,
        key=lambda item: item.get("event_year_start") if item.get("event_year_start") is not None else 10**9,
    ):
        if event.get("epistemic_status") == "gap":
            continue
        events_by_branch[str(event.get("branch") or "故事主线")].append(event)

    sections = []
    for branch, events in events_by_branch.items():
        sections.append(
            {
                "heading": branch,
                "paragraphs": [],
                "items": [
                    {"title": event.get("title") or "故事节点", "text": _shorten(event.get("summary") or "")}
                    for event in events
                ],
            }
        )
    if not sections:
        paragraphs = [paragraph.strip() for paragraph in summary.split("\n\n") if paragraph.strip()]
        sections.append(
            {
                "heading": "故事脉络",
                "paragraphs": [_shorten(paragraph, 320) for paragraph in paragraphs[:6]],
                "items": [],
            }
        )

    boundary_claims = [
        claim for claim in session.state.claims
        if claim.get("status") in {"challenged", "dropped"}
        or any(term in str(claim.get("text") or "") for term in ("没有任何", "不能直接", "不直接等同", "缺乏", "证据边界"))
    ]
    if boundary_claims:
        sections.append(
            {
                "heading": "还不能确定的部分",
                "paragraphs": [],
                "items": [
                    {"title": "证据边界", "text": _shorten(claim.get("text") or "", 230)}
                    for claim in boundary_claims[:4]
                ],
            }
        )
    return sections


def build_investigation_report(
    session: InvestigationSession,
    audience: Audience = "professional",
) -> dict[str, Any]:
    evidence = _unique_evidence(session)
    summary = _final_summary(session)
    professional = audience == "professional"
    return {
        "investigation_id": session.id,
        "audience": audience,
        "title": f"{session.question}：调查报告",
        "subtitle": "专业历史文博版" if professional else "博物馆公众版",
        "overview": (
            f"本报告由本次调查形成的 {len(session.state.lines)} 条主线、"
            f"{len(session.state.claims)} 项判断、{len(session.state.curation_events)} 个策展节点和"
            f" {len(evidence)} 条去重证据整理而成。"
            if professional
            else "沿着地图、时间轴和生命树，我们把这次调查里最重要的故事节点依次展开。"
        ),
        "sections": (
            _professional_sections(session, summary)
            if professional
            else _public_sections(session, summary)
        ),
        "sources": _source_rows(evidence),
        "stats": {
            "lines": len(session.state.lines),
            "claims": len(session.state.claims),
            "curation_events": len(session.state.curation_events),
            "evidence": len(evidence),
        },
    }
