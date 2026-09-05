#!/usr/bin/env python3
"""Build the local AADR metadata catalog used by the demo runtime."""

from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
import uuid
from pathlib import Path


AADR_RELEASE = "v66.p1"
AADR_SOURCE_ID = "aadr:v66.p1:1240k"
AADR_URL = "https://dataverse.harvard.edu/api/access/datafile/13994515"
CATALOG_NAMESPACE = uuid.UUID("edc15bd4-1df2-45f3-9285-acde6750520f")
MISSING = {"", "..", "n/a", "N/A", "na", "NA"}


def stable_uuid(kind: str, *parts: object) -> str:
    value = ":".join(str(part).strip() for part in parts)
    return str(uuid.uuid5(CATALOG_NAMESPACE, f"{kind}:{value}"))


def clean(value: str) -> str | None:
    value = value.strip()
    return None if value in MISSING else value


def as_float(value: str) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def as_int(value: str) -> int | None:
    number = as_float(value)
    return None if number is None else int(number)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE catalog_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    license TEXT,
    release TEXT,
    sha256 TEXT NOT NULL
);

CREATE TABLE individuals (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE TABLE genetic_records (
    id TEXT PRIMARY KEY,
    individual_id TEXT NOT NULL REFERENCES individuals(id),
    release TEXT NOT NULL,
    genetic_id TEXT NOT NULL UNIQUE,
    persistent_genetic_id TEXT NOT NULL,
    skeletal_code TEXT,
    skeletal_element TEXT,
    group_label TEXT,
    molecular_sex TEXT,
    family_relations_raw TEXT,
    snps_1240k INTEGER,
    y_haplogroup TEXT,
    mt_haplogroup TEXT,
    assessment TEXT,
    assessment_warnings TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE TABLE sites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    political_entity TEXT,
    latitude REAL,
    longitude REAL,
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE TABLE individual_sites (
    individual_id TEXT NOT NULL REFERENCES individuals(id),
    site_id TEXT NOT NULL REFERENCES sites(id),
    PRIMARY KEY (individual_id, site_id)
);

CREATE TABLE time_spans (
    id TEXT PRIMARY KEY,
    genetic_record_id TEXT NOT NULL REFERENCES genetic_records(id),
    method TEXT,
    mean_bp REAL,
    sd_bp REAL,
    source_text TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE TABLE publications (
    id TEXT PRIMARY KEY,
    abbreviation TEXT,
    doi TEXT,
    repository_url TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE TABLE genetic_publications (
    genetic_record_id TEXT NOT NULL REFERENCES genetic_records(id),
    publication_id TEXT NOT NULL REFERENCES publications(id),
    role TEXT NOT NULL,
    PRIMARY KEY (genetic_record_id, publication_id, role)
);

CREATE TABLE id_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    external_id TEXT NOT NULL,
    release TEXT,
    UNIQUE (entity_type, entity_id, namespace, external_id, release)
);

CREATE TABLE evidence_edges (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT,
    evidence_level TEXT NOT NULL CHECK (
        evidence_level IN ('fact_genomic', 'fact_archaeology', 'view_model')
    ),
    source_id TEXT NOT NULL REFERENCES sources(id),
    source_locator TEXT,
    note TEXT
);

CREATE INDEX idx_genetic_individual ON genetic_records(individual_id);
CREATE INDEX idx_genetic_persistent ON genetic_records(persistent_genetic_id);
CREATE INDEX idx_genetic_group ON genetic_records(group_label);
CREATE INDEX idx_sites_name ON sites(name);
CREATE INDEX idx_sites_coordinates ON sites(latitude, longitude);
CREATE INDEX idx_times_mean_bp ON time_spans(mean_bp);
CREATE INDEX idx_id_mappings_lookup ON id_mappings(namespace, external_id);
"""


def insert_publication(
    connection: sqlite3.Connection,
    genetic_record_id: str,
    abbreviation: str | None,
    doi: str | None,
    repository_url: str | None,
    role: str,
) -> None:
    if not any((abbreviation, doi, repository_url)):
        return
    publication_key = doi or abbreviation or repository_url
    publication_id = stable_uuid("publication", publication_key)
    connection.execute(
        """INSERT OR IGNORE INTO publications
           (id, abbreviation, doi, repository_url, source_id)
           VALUES (?, ?, ?, ?, ?)""",
        (publication_id, abbreviation, doi, repository_url, AADR_SOURCE_ID),
    )
    connection.execute(
        """INSERT OR IGNORE INTO genetic_publications
           (genetic_record_id, publication_id, role) VALUES (?, ?, ?)""",
        (genetic_record_id, publication_id, role),
    )


def build_catalog(input_path: Path, output_path: Path) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.unlink(missing_ok=True)

    connection = sqlite3.connect(temporary_path)
    try:
        connection.executescript(SCHEMA)
        source_hash = sha256(input_path)
        connection.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
            (
                AADR_SOURCE_ID,
                "Allen Ancient DNA Resource 1240K annotation",
                AADR_URL,
                "CC0 1.0",
                AADR_RELEASE,
                source_hash,
            ),
        )
        connection.executemany(
            "INSERT INTO catalog_meta VALUES (?, ?)",
            [
                ("schema_version", "1"),
                ("aadr_release", AADR_RELEASE),
                ("aadr_annotation_sha256", source_hash),
            ],
        )

        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header = next(reader)
            if len(header) != 49:
                raise ValueError(f"Expected 49 AADR columns, found {len(header)}")
            connection.execute(
                "INSERT INTO catalog_meta VALUES (?, ?)",
                ("aadr_annotation_column_count", str(len(header))),
            )

            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise ValueError(
                        f"Line {line_number}: expected {len(header)} columns, found {len(row)}"
                    )

                genetic_id = clean(row[0])
                persistent_id = clean(row[1])
                aadr_individual_id = clean(row[2])
                if not genetic_id or not persistent_id or not aadr_individual_id:
                    raise ValueError(f"Line {line_number}: missing required AADR identifier")

                individual_uuid = stable_uuid("individual:aadr", aadr_individual_id)
                genetic_uuid = stable_uuid("genetic:aadr", AADR_RELEASE, genetic_id)
                connection.execute(
                    "INSERT OR IGNORE INTO individuals VALUES (?, ?, ?)",
                    (individual_uuid, aadr_individual_id, AADR_SOURCE_ID),
                )
                connection.execute(
                    """INSERT INTO genetic_records (
                        id, individual_id, release, genetic_id, persistent_genetic_id,
                        skeletal_code, skeletal_element, group_label, molecular_sex,
                        family_relations_raw, snps_1240k, y_haplogroup, mt_haplogroup,
                        assessment, assessment_warnings, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        genetic_uuid,
                        individual_uuid,
                        AADR_RELEASE,
                        genetic_id,
                        persistent_id,
                        clean(row[3]),
                        clean(row[4]),
                        clean(row[14]),
                        clean(row[30]),
                        clean(row[31]),
                        as_int(row[26]),
                        clean(row[36]) or clean(row[35]) or clean(row[34]),
                        clean(row[38]),
                        clean(row[47]),
                        clean(row[48]),
                        AADR_SOURCE_ID,
                    ),
                )

                for namespace, external_id, entity_type, entity_id in (
                    ("AADR_Individual_ID", aadr_individual_id, "individual", individual_uuid),
                    ("AADR_Genetic_ID", genetic_id, "genetic_record", genetic_uuid),
                    ("AADR_Persistent_Genetic_ID", persistent_id, "genetic_record", genetic_uuid),
                ):
                    connection.execute(
                        """INSERT OR IGNORE INTO id_mappings
                           (entity_type, entity_id, namespace, external_id, release)
                           VALUES (?, ?, ?, ?, ?)""",
                        (entity_type, entity_id, namespace, external_id, AADR_RELEASE),
                    )

                locality = clean(row[15])
                political_entity = clean(row[16])
                latitude = as_float(row[17])
                longitude = as_float(row[18])
                if locality:
                    site_uuid = stable_uuid(
                        "site:aadr", locality, political_entity or "", latitude or "", longitude or ""
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO sites VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            site_uuid,
                            locality,
                            political_entity,
                            latitude,
                            longitude,
                            AADR_SOURCE_ID,
                        ),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO individual_sites VALUES (?, ?)",
                        (individual_uuid, site_uuid),
                    )

                if any(clean(row[index]) for index in (9, 10, 11, 12)):
                    time_uuid = stable_uuid("time_span:aadr", AADR_RELEASE, genetic_id)
                    connection.execute(
                        "INSERT INTO time_spans VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            time_uuid,
                            genetic_uuid,
                            clean(row[9]),
                            as_float(row[10]),
                            as_float(row[11]),
                            clean(row[12]),
                            AADR_SOURCE_ID,
                        ),
                    )

                first_publication = clean(row[5])
                representation_publication = clean(row[6])
                doi = clean(row[7])
                repository_url = clean(row[8])
                insert_publication(
                    connection,
                    genetic_uuid,
                    first_publication,
                    None,
                    None,
                    "first_publication",
                )
                insert_publication(
                    connection,
                    genetic_uuid,
                    representation_publication,
                    doi,
                    repository_url,
                    "data_representation",
                )

        connection.commit()
        counts = {}
        for table in (
            "individuals",
            "genetic_records",
            "sites",
            "time_spans",
            "publications",
            "id_mappings",
        ):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        connection.close()
        temporary_path.replace(output_path)
        return counts
    except Exception:
        connection.close()
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    counts = build_catalog(args.input, args.output)
    print(f"built {args.output}")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()

