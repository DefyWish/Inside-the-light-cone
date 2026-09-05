from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field


ToolStatus = Literal["ok", "no_data", "no_genotype", "unknown_place"]


class ToolCall(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool: str
    status: ToolStatus
    items: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    alias_only: bool = False


TOOL_DEFINITIONS = [
    {
        "name": "search_ancient_samples",
        "description": "按地点或个体标识查询 AADR 古样本、测年和出土地点元数据。按地点查询必须给出 min_bp/max_bp，或在用户明确要求跨时代覆盖时传 time_scope=all_periods。不得用同地不同时代样本替代历史人物证据。",
        "arguments": {
            "place": "string?",
            "individual": "string?",
            "min_bp": "number?",
            "max_bp": "number?",
            "time_scope": "all_periods?",
            "limit": "integer?",
        },
    },
    {
        "name": "search_genetic_relations",
        "description": "查询论文/AADR 已报告亲缘文本及已预计算的等位共享近邻。",
        "arguments": {"individual": "string"},
    },
    {
        "name": "search_archaeological_sites",
        "description": "查询独立考古证据记录；当前未导入时返回正常空结果。",
        "arguments": {"place": "string", "limit": "integer?"},
    },
    {
        "name": "search_place_history",
        "description": "查询人工确认的历史地名沿革子集；当前未导入时返回正常空结果。",
        "arguments": {"place": "string"},
    },
    {
        "name": "search_literature",
        "description": "按关键词、DOI、论文简称或古样本查询本地文献索引。",
        "arguments": {"query": "string?", "individual": "string?", "limit": "integer?"},
    },
    {
        "name": "mark_evidence_gap",
        "description": "显式记录当前调查无法填补的证据空白。",
        "arguments": {"topic": "string", "reason": "string?"},
    },
]


class NumericArtifacts:
    def __init__(self, directory: Path) -> None:
        self.available = False
        if not (directory / "manifest.json").exists():
            return
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("data_status") != "published":
            return
        self.manifest = manifest
        self.sample_ids = np.load(directory / "sample_ids.npy", allow_pickle=False)
        self.neighbor_indices = np.load(directory / "neighbor_indices.npy", allow_pickle=False)
        self.neighbor_distances = np.load(directory / "neighbor_distances.npy", allow_pickle=False)
        self.neighbor_overlap_counts = np.load(
            directory / "neighbor_overlap_counts.npy", allow_pickle=False
        )
        self.index = {sample_id: index for index, sample_id in enumerate(self.sample_ids)}
        self.available = True

    def neighbors(self, genetic_id: str) -> list[dict[str, Any]] | None:
        if not self.available or genetic_id not in self.index:
            return None
        row = self.index[genetic_id]
        items = []
        for neighbor_index, distance, overlap in zip(
            self.neighbor_indices[row],
            self.neighbor_distances[row],
            self.neighbor_overlap_counts[row],
        ):
            if neighbor_index < 0 or not np.isfinite(distance):
                continue
            items.append(
                {
                    "record_type": "genetic_neighbor",
                    "subject_genetic_id": genetic_id,
                    "neighbor_genetic_id": str(self.sample_ids[neighbor_index]),
                    "distance": float(distance),
                    "overlap_snp_count": int(overlap),
                    "method": self.manifest["parameters"]["distance"],
                    "panel": "AADR v66.p1 Human Origins; M1 region-neutral benchmark",
                    "evidence_level": "fact_genomic",
                    "source_id": "aadr:v66.p1:ho",
                    "derived_from_published_genotypes": True,
                }
            )
        return items


class EvidenceTools:
    def __init__(
        self,
        catalog_path: Path,
        numeric_dir: Path,
        research_staging_path: Path | None = None,
        aliases_path: Path | None = None,
    ) -> None:
        self.catalog_path = catalog_path
        self.research_staging_path = research_staging_path
        self.numeric = NumericArtifacts(numeric_dir)
        self.aliases: dict[str, Any] = {}
        if aliases_path and aliases_path.exists():
            self.aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        self._dispatch = {
            "search_ancient_samples": self._search_ancient_samples,
            "search_genetic_relations": self._search_genetic_relations,
            "search_archaeological_sites": self._search_archaeological_sites,
            "search_place_history": self._search_place_history,
            "search_literature": self._search_literature,
            "mark_evidence_gap": self._mark_evidence_gap,
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.catalog_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _connect_ro(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _alias_card(self, term: str) -> dict[str, Any] | None:
        cleaned = term.strip()
        if not cleaned or not self.aliases:
            return None
        for key, card in self.aliases.items():
            names = [key, *card.get("aliases", []), *card.get("related_places", [])]
            if any(cleaned == name or cleaned in name or name in cleaned for name in names if name):
                return {"key": key, **card}
        return None

    @staticmethod
    def _alias_terms(card: dict[str, Any]) -> list[str]:
        terms = [card["key"], *card.get("aliases", []), *card.get("seed_queries", [])]
        seen: set[str] = set()
        return [t for t in terms if t and not (t in seen or seen.add(t))]

    def _search_staging(self, query: str, limit: int) -> list[dict[str, Any]]:
        """回读研究Agent的既有成果；trigram FTS 优先，短词回退 LIKE。"""
        if self.research_staging_path is None or not self.research_staging_path.exists():
            return []
        tokens = [token for token in query.split() if token.strip()]
        if not tokens:
            return []
        with self._connect_ro(self.research_staging_path) as connection:
            use_fts = all(len(token) >= 3 for token in tokens)
            rows: list[sqlite3.Row] = []
            if use_fts:
                match = " AND ".join(f'"{token}"' for token in tokens)
                try:
                    rows = connection.execute(
                        """SELECT f.* FROM research_findings f
                           JOIN research_fts ON research_fts.rowid = f.rowid
                           WHERE research_fts MATCH ?
                           ORDER BY f.created_at DESC LIMIT ?""",
                        (match, limit),
                    ).fetchall()
                except sqlite3.Error:
                    rows = []
            if not rows:
                like_clause = " AND ".join(
                    "(title LIKE ? OR quote LIKE ? OR summary LIKE ?)" for _ in tokens
                )
                parameters: list[Any] = []
                for token in tokens:
                    parameters.extend([f"%{token}%"] * 3)
                parameters.append(limit)
                rows = connection.execute(
                    f"""SELECT * FROM research_findings
                        WHERE {like_clause}
                        ORDER BY created_at DESC LIMIT ?""",
                    tuple(parameters),
                ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            if item.get("finding_json"):
                try:
                    item = {**json.loads(item["finding_json"]), "staging_id": item["id"]}
                except (json.JSONDecodeError, TypeError):
                    pass
            item.update(
                {
                    "record_type": "research_finding",
                    "evidence_level": item.get("evidence_level") or "view_model",
                    "source_id": item.get("source_url") or "research_staging",
                }
            )
            items.append(item)
        return items

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if tool_name not in self._dispatch:
            return ToolResult(tool=tool_name, status="no_data", message="未知工具。")
        try:
            return self._dispatch[tool_name](arguments)
        except Exception:
            return ToolResult(
                tool=tool_name,
                status="no_data",
                message="本地制品暂不可用；该结果按空数据处理。",
            )

    @staticmethod
    def _limit(arguments: dict[str, Any]) -> int:
        return min(max(int(arguments.get("limit", 20)), 1), 100)

    def _place_known(self, connection: sqlite3.Connection, place: str) -> bool:
        pattern = f"%{place}%"
        return (
            connection.execute(
                """SELECT 1 FROM sites
                   WHERE name LIKE ? OR political_entity LIKE ? LIMIT 1""",
                (pattern, pattern),
            ).fetchone()
            is not None
        )

    def _search_ancient_samples(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "search_ancient_samples"
        place = str(arguments.get("place", "")).strip()
        individual = str(arguments.get("individual", "")).strip()
        if not place and not individual:
            return ToolResult(tool=tool, status="no_data", message="需要地点或个体标识。")
        min_bp = arguments.get("min_bp")
        max_bp = arguments.get("max_bp")
        time_scope = str(arguments.get("time_scope", "")).strip()
        if place and min_bp is None and max_bp is None and time_scope != "all_periods":
            return ToolResult(
                tool=tool,
                status="no_data",
                message="按地点查询古样本需要明确时间范围；只有用户要求跨时代覆盖时才能使用 all_periods。",
            )
        limit = self._limit(arguments)
        with self._connect() as connection:
            if place:
                pattern = f"%{place}%"
                where = "(s.name LIKE ? OR s.political_entity LIKE ?)"
                parameters: list[Any] = [pattern, pattern]
            else:
                pattern = f"%{individual}%"
                where = """(
                    i.display_name LIKE ? OR g.genetic_id LIKE ?
                    OR g.persistent_genetic_id LIKE ?
                )"""
                parameters = [pattern, pattern, pattern]
            time_filters = []
            if min_bp is not None:
                time_filters.append("t.mean_bp >= ?")
                parameters.append(float(min_bp))
            if max_bp is not None:
                time_filters.append("t.mean_bp <= ?")
                parameters.append(float(max_bp))
            time_clause = " AND " + " AND ".join(time_filters) if time_filters else ""
            parameters.append(limit)
            rows = connection.execute(
                f"""SELECT DISTINCT
                        i.id AS person_uuid, i.display_name AS individual_id,
                        g.genetic_id, g.persistent_genetic_id, g.group_label,
                        g.molecular_sex, g.snps_1240k, t.mean_bp, t.sd_bp,
                        t.source_text AS date_text, s.name AS site,
                        s.political_entity, s.latitude, s.longitude
                    FROM individuals i
                    JOIN genetic_records g ON g.individual_id = i.id
                    JOIN time_spans t ON t.genetic_record_id = g.id
                    LEFT JOIN individual_sites ix ON ix.individual_id = i.id
                    LEFT JOIN sites s ON s.id = ix.site_id
                    WHERE t.mean_bp > 0 AND {where}{time_clause}
                    ORDER BY t.mean_bp DESC
                    LIMIT ?""",
                tuple(parameters),
            ).fetchall()
            if not rows:
                status: ToolStatus = "unknown_place" if place else "no_data"
                card = self._alias_card(place or individual)
                if card:
                    return ToolResult(
                        tool=tool,
                        status="no_data",
                        items=[
                            {
                                "record_type": "alias_card",
                                "evidence_level": "view_model",
                                "source_id": "editorial:curated_aliases",
                                "title": f"策展别名卡：{card['key']}",
                                **card,
                            }
                        ],
                        message="本地古基因组目录没有匹配记录；已返回策展别名卡供后续调查。",
                    )
                return ToolResult(tool=tool, status=status, message="本地古基因组目录没有匹配记录。")
        items = []
        for row in rows:
            item = dict(row)
            item.update(
                {
                    "record_type": "ancient_sample",
                    "evidence_level": "fact_genomic",
                    "source_id": "aadr:v66.p1:1240k",
                }
            )
            items.append(item)
        return ToolResult(tool=tool, status="ok", items=items)

    def _resolve_genetic_records(
        self, connection: sqlite3.Connection, individual: str
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """SELECT DISTINCT g.*, i.display_name AS aadr_individual_id
               FROM genetic_records g
               JOIN individuals i ON i.id = g.individual_id
               LEFT JOIN id_mappings m
                 ON m.entity_type = 'genetic_record' AND m.entity_id = g.id
               WHERE i.display_name = ? OR g.genetic_id = ?
                  OR g.persistent_genetic_id = ? OR m.external_id = ?""",
            (individual, individual, individual, individual),
        ).fetchall()

    def _search_genetic_relations(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "search_genetic_relations"
        individual = str(arguments.get("individual", "")).strip()
        if not individual:
            return ToolResult(tool=tool, status="no_data", message="需要个体标识。")
        with self._connect() as connection:
            records = self._resolve_genetic_records(connection, individual)
        if not records:
            return ToolResult(tool=tool, status="no_data", message="未找到该个体。")
        items = []
        for record in records:
            if record["family_relations_raw"]:
                items.append(
                    {
                        "record_type": "reported_family_relation",
                        "individual_id": record["aadr_individual_id"],
                        "genetic_id": record["genetic_id"],
                        "reported_text": record["family_relations_raw"],
                        "method": "AADR reported Family relations; unparsed",
                        "evidence_level": "fact_genomic",
                        "source_id": "aadr:v66.p1:1240k",
                    }
                )
            neighbors = self.numeric.neighbors(record["genetic_id"])
            if neighbors:
                items.extend(neighbors)
        if items:
            return ToolResult(tool=tool, status="ok", items=items)
        return ToolResult(
            tool=tool,
            status="no_genotype",
            message="个体存在，但当前运行制品没有可查询的亲缘文本或预计算近邻。",
        )

    def _search_archaeological_sites(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "search_archaeological_sites"
        place = str(arguments.get("place", "")).strip()
        if not place:
            return ToolResult(tool=tool, status="unknown_place", message="需要地点。")
        with self._connect() as connection:
            known = self._place_known(connection, place)
        if not known:
            return ToolResult(tool=tool, status="unknown_place", message="本地目录无法识别该地点。")
        return ToolResult(
            tool=tool,
            status="no_data",
            message="该地点可识别，但当前制品尚未导入独立考古证据记录。",
        )

    def _search_place_history(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "search_place_history"
        place = str(arguments.get("place", "")).strip()
        if not place:
            return ToolResult(tool=tool, status="unknown_place", message="需要地点。")
        card = self._alias_card(place)
        if card and (card.get("place_history") or card.get("timeline")):
            entries = card.get("place_history") or card.get("timeline")
            items = [
                {
                    "record_type": "place_history",
                    "evidence_level": "fact_archaeology",
                    "source_id": "editorial:curated_aliases",
                    **entry,
                }
                for entry in entries
            ]
            return ToolResult(tool=tool, status="ok", items=items)
        with self._connect() as connection:
            known = self._place_known(connection, place)
        if not known:
            return ToolResult(tool=tool, status="unknown_place", message="本地目录无法识别该地点。")
        return ToolResult(
            tool=tool,
            status="no_data",
            message="该地点可识别，但当前制品尚未导入人工确认的地名沿革子集。",
        )

    def _search_literature(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "search_literature"
        query = str(arguments.get("query", "")).strip()
        individual = str(arguments.get("individual", "")).strip()
        if not query and not individual:
            return ToolResult(tool=tool, status="no_data", message="需要关键词或个体标识。")
        limit = self._limit(arguments)
        items: list[dict[str, Any]] = []

        card = self._alias_card(query or individual)
        if card:
            items.append(
                {
                    "record_type": "alias_card",
                    "evidence_level": "view_model",
                    "source_id": "editorial:curated_aliases",
                    "title": f"策展别名卡：{card['key']}",
                    **card,
                }
            )

        with self._connect() as connection:
            if individual:
                rows = connection.execute(
                    """SELECT DISTINCT p.*
                       FROM publications p
                       JOIN genetic_publications gp ON gp.publication_id = p.id
                       JOIN genetic_records g ON g.id = gp.genetic_record_id
                       JOIN individuals i ON i.id = g.individual_id
                       WHERE i.display_name = ? OR g.genetic_id = ?
                          OR g.persistent_genetic_id = ?
                       LIMIT ?""",
                    (individual, individual, individual, limit),
                ).fetchall()
            else:
                terms = [query] if not card else [query, *self._alias_terms(card)]
                seen_terms: set[str] = set()
                rows = []
                for term in terms:
                    if term in seen_terms:
                        continue
                    seen_terms.add(term)
                    pattern = f"%{term}%"
                    rows.extend(
                        connection.execute(
                            """SELECT DISTINCT p.* FROM publications p
                               WHERE p.abbreviation LIKE ? OR p.doi LIKE ?
                                  OR p.repository_url LIKE ?
                               LIMIT ?""",
                            (pattern, pattern, pattern, limit),
                        ).fetchall()
                    )
        seen_ids: set[Any] = set()
        for row in rows:
            row_dict = dict(row)
            marker = row_dict.get("id") or row_dict.get("doi") or row_dict.get("abbreviation")
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            row_dict.update(
                {
                    "record_type": "literature_index",
                    "evidence_level": "view_model",
                    "source_id": "aadr:v66.p1:1240k",
                }
            )
            items.append(row_dict)

        if query:
            staging_terms = [query] if not card else self._alias_terms(card)
            seen_urls: set[str] = set()
            for term in staging_terms:
                for staged in self._search_staging(term, limit):
                    marker = staged.get("staging_id") or staged.get("source_url") or staged.get("title")
                    if marker in seen_urls:
                        continue
                    seen_urls.add(marker)
                    items.append(staged)

        if items:
            alias_only = all(item.get("record_type") == "alias_card" for item in items)
            message = None
            if alias_only:
                message = "仅命中策展别名卡（线索，非证据）；需以外部来源核实。"
            return ToolResult(
                tool=tool, status="ok", items=items[: max(limit, 10)],
                message=message, alias_only=alias_only,
            )
        return ToolResult(tool=tool, status="no_data", message="本地文献索引没有匹配记录。")

    def _mark_evidence_gap(self, arguments: dict[str, Any]) -> ToolResult:
        tool = "mark_evidence_gap"
        topic = str(arguments.get("topic", "")).strip()
        reason = str(arguments.get("reason", "")).strip()
        if not topic:
            return ToolResult(tool=tool, status="no_data", message="需要空白主题。")
        gap_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jialuo-tree:gap:{topic}:{reason}"))
        return ToolResult(
            tool=tool,
            status="ok",
            items=[
                {
                    "record_type": "evidence_gap",
                    "gap_id": gap_id,
                    "topic": topic,
                    "reason": reason or "当前本地证据不足",
                    "evidence_level": "view_model",
                    "source_id": "editorial:agent",
                }
            ],
        )
