from __future__ import annotations

import re
from typing import Any, Literal

from .investigation import InvestigationSession


Audience = Literal["professional", "public"]

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


def _completed_data(session: InvestigationSession) -> dict[str, Any]:
    for event in reversed(session.events):
        if event["type"] == "investigation.completed":
            return event["data"]
    return {}


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _is_substantial(text: str | None) -> bool:
    if not text or len(text.strip()) < 180:
        return False
    return not any(marker in text for marker in ("达到本轮步数上限", "调查已经完成", "调查完成。"))


def _sentence(text: str) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if compact and compact[-1] not in "。！？；":
        compact += "。"
    return compact


def _subject_name(session: InvestigationSession) -> str:
    for event in session.state.curation_events:
        for subject in event.get("subject_ids", []):
            name = str(subject).strip()
            if name and ":" not in name and not name.isdigit():
                return name
    question = session.question.strip("？?。 ")
    return question[:28] + ("…" if len(question) > 28 else "")


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


def _claim_paragraphs(session: InvestigationSession) -> list[str]:
    claims = [
        claim for claim in session.state.claims
        if claim.get("status") != "dropped" and claim.get("text")
    ]
    claims.sort(
        key=lambda claim: (
            claim.get("event_year_start") is None,
            claim.get("event_year_start") or 0,
        )
    )
    paragraphs: list[str] = []
    for index in range(0, len(claims), 2):
        pair = claims[index:index + 2]
        first = _sentence(pair[0]["text"])
        if len(pair) == 1:
            paragraphs.append(first)
            continue
        paragraphs.append(f"{first}与这一进程相连，{_sentence(pair[1]['text'])}")
    return paragraphs


def _professional_narrative(session: InvestigationSession, summary: str) -> list[str]:
    if _is_substantial(summary):
        return _paragraphs(summary)
    paragraphs = _claim_paragraphs(session)
    if paragraphs:
        return paragraphs
    return ["现有材料尚不足以形成一篇可核验的综合论述，调查已保留证据缺口，等待继续补证。"]


def _date_label(year: int | None) -> str:
    if year is None:
        return "此后"
    if year < 0:
        return f"公元前{abs(year)}年左右"
    return f"{year}年"


def _public_excerpt(text: str, limit: int = 280) -> str:
    compact = " ".join(str(text or "").split())
    compact = compact.replace("现代分子人类学证据", "DNA留下的线索")
    compact = compact.replace("Y染色体/Y-STR", "父系遗传标记")
    compact = compact.replace("Y染色体", "父系遗传标记")
    compact = compact.replace("Y-STR", "父系遗传标记")
    compact = compact.replace("线粒体DNA", "母系遗传标记")
    compact = compact.replace("mtDNA", "母系遗传标记")
    if len(compact) <= limit:
        return _sentence(compact)
    clipped = compact[:limit]
    sentence_end = max(clipped.rfind(mark) for mark in "。！？")
    if sentence_end >= limit // 2:
        return clipped[:sentence_end + 1]
    clause_end = max(clipped.rfind(mark) for mark in "；，")
    if clause_end >= limit // 2:
        return clipped[:clause_end].rstrip("，；") + "。"
    return clipped.rstrip("，；：") + "……"


def _remove_repeated_date(text: str, year: int | None) -> str:
    if year is None:
        return text
    return re.sub(
        rf"^(?:约|大约)?{abs(year)}(?:\s*[—–-]\s*\d+)?\s*年(?:左右)?[，、：:]?",
        "",
        text,
    ).lstrip()


def _public_moments(session: InvestigationSession) -> list[dict[str, Any]]:
    moments: list[dict[str, Any]] = []
    covered_claims: set[str] = set()
    for event in session.state.curation_events:
        if event.get("epistemic_status") == "gap" or not event.get("summary"):
            continue
        covered_claims.update(str(claim_id) for claim_id in event.get("claim_ids", []))
        moments.append(
            {
                "year": event.get("event_year_start"),
                "place": event.get("historical_place") or event.get("modern_place"),
                "text": event.get("summary"),
            }
        )
    for claim in session.state.claims:
        line = str(claim.get("line") or "")
        if (
            claim.get("claim_id") in covered_claims
            or claim.get("status") == "dropped"
            or not claim.get("text")
            or any(marker in line for marker in ("文献记载", "史传证据"))
        ):
            continue
        moments.append(
            {
                "year": claim.get("event_year_start"),
                "place": None,
                "text": claim.get("text"),
            }
        )
    moments.sort(key=lambda item: (item["year"] is None, item["year"] or 0))
    return moments


def _public_narrative(
    session: InvestigationSession,
    summary: str,
    public_summary: str | None,
) -> list[str]:
    if _is_substantial(public_summary):
        return _paragraphs(public_summary or "")

    moments = _public_moments(session)
    if not moments:
        if _is_substantial(summary):
            return _paragraphs(summary)
        return ["这段历史仍在等待更多材料进入展厅。"]

    subject = _subject_name(session)
    first_event = next(
        (
            event for event in session.state.curation_events
            if event.get("epistemic_status") != "gap" and event.get("summary")
        ),
        None,
    )
    first = (
        {
            "year": first_event.get("event_year_start"),
            "place": first_event.get("historical_place") or first_event.get("modern_place"),
            "text": first_event.get("summary"),
        }
        if first_event
        else moments[0]
    )
    moments = [moment for moment in moments if moment != first]
    opening_place = f"从{first['place']}" if first.get("place") else "从时间轴的起点"
    paragraphs = [
        f"如果把{subject}的历史铺成一张地图，故事会{opening_place}展开。{_public_excerpt(first['text'])}"
    ]
    for index in range(0, len(moments), 2):
        group = moments[index:index + 2]
        parts: list[str] = []
        for offset, moment in enumerate(group):
            lead = _date_label(moment.get("year"))
            if moment.get("place"):
                lead += f"，镜头来到{moment['place']}"
            elif offset:
                lead = f"到了{lead}"
            moment_text = _remove_repeated_date(str(moment["text"]), moment.get("year"))
            parts.append(f"{lead}，{_public_excerpt(moment_text)}")
        paragraphs.append("".join(parts))

    summary_paragraphs = _paragraphs(summary) if _is_substantial(summary) else []
    if summary_paragraphs:
        closing = summary_paragraphs[-1]
        if closing not in paragraphs[-1]:
            paragraphs.append(closing)
    return paragraphs


def build_investigation_report(
    session: InvestigationSession,
    audience: Audience = "professional",
) -> dict[str, Any]:
    evidence = _unique_evidence(session)
    completed = _completed_data(session)
    summary = str(completed.get("summary") or "")
    public_summary = completed.get("public_summary")
    professional = audience == "professional"
    subject = _subject_name(session)
    narrative = (
        _professional_narrative(session, summary)
        if professional
        else _public_narrative(session, summary, public_summary)
    )
    return {
        "investigation_id": session.id,
        "audience": audience,
        "title": f"{subject}｜综合调查" if professional else f"{subject}｜展厅叙事",
        "subtitle": "专业历史文博版" if professional else "博物馆公众版",
        "overview": "一篇由时间、空间与多尺度证据共同推进的综合论述。" if professional else "沿着地图与生命树，进入这段仍在生长的历史。",
        "narrative": narrative,
        "sources": _source_rows(evidence),
        "stats": {
            "lines": len(session.state.lines),
            "claims": len(session.state.claims),
            "curation_events": len(session.state.curation_events),
            "evidence": len(evidence),
        },
    }
