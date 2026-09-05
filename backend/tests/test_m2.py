from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from backend.app.evidence_tools import EvidenceTools


ROOT = Path(__file__).resolve().parents[2]


class EvidenceToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ROOT / "artifacts/catalog.sqlite"
        cls.tools = EvidenceTools(cls.catalog, ROOT / "artifacts/numeric")
        with sqlite3.connect(cls.catalog) as connection:
            cls.ancient_individual = connection.execute(
                """SELECT i.display_name
                   FROM individuals i
                   JOIN genetic_records g ON g.individual_id = i.id
                   JOIN time_spans t ON t.genetic_record_id = g.id
                   WHERE t.mean_bp > 0 LIMIT 1"""
            ).fetchone()[0]
            cls.known_place = connection.execute("SELECT name FROM sites LIMIT 1").fetchone()[0]
            cls.publication = connection.execute(
                "SELECT abbreviation FROM publications WHERE abbreviation IS NOT NULL LIMIT 1"
            ).fetchone()[0]

    def test_ancient_sample_query(self) -> None:
        result = self.tools.execute(
            "search_ancient_samples", {"individual": self.ancient_individual}
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.items)
        self.assertEqual(result.items[0]["evidence_level"], "fact_genomic")

    def test_unknown_place_is_typed(self) -> None:
        result = self.tools.execute(
            "search_ancient_samples",
            {"place": "__not_a_real_catalog_place__", "time_scope": "all_periods"},
        )
        self.assertEqual(result.status, "unknown_place")

    def test_place_sample_query_requires_explicit_time_scope(self) -> None:
        guarded = self.tools.execute("search_ancient_samples", {"place": self.known_place})
        self.assertEqual(guarded.status, "no_data")
        self.assertIn("明确时间范围", guarded.message)

        all_periods = self.tools.execute(
            "search_ancient_samples",
            {"place": self.known_place, "time_scope": "all_periods", "limit": 2},
        )
        self.assertEqual(all_periods.status, "ok")
        self.assertTrue(all_periods.items)

    def test_known_place_without_archaeology_is_normal_empty(self) -> None:
        result = self.tools.execute("search_archaeological_sites", {"place": self.known_place})
        self.assertEqual(result.status, "no_data")

    def test_place_history_empty_branch(self) -> None:
        result = self.tools.execute("search_place_history", {"place": self.known_place})
        self.assertEqual(result.status, "no_data")

    def test_literature_query(self) -> None:
        result = self.tools.execute("search_literature", {"query": self.publication})
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.items)

    def test_genetic_relation_status_is_typed(self) -> None:
        result = self.tools.execute(
            "search_genetic_relations", {"individual": self.ancient_individual}
        )
        self.assertIn(result.status, {"ok", "no_genotype"})

    def test_mark_gap(self) -> None:
        result = self.tools.execute(
            "mark_evidence_gap", {"topic": "缺失的独立考古证据", "reason": "尚未导入"}
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items[0]["record_type"], "evidence_gap")

    def test_unknown_tool_does_not_raise(self) -> None:
        result = self.tools.execute("unknown", {})
        self.assertEqual(result.status, "no_data")


if __name__ == "__main__":
    unittest.main()
