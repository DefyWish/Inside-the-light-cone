#!/usr/bin/env python3
"""Verify the current M1 catalog and numeric artifact slice."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    catalog = ROOT / "artifacts/catalog.sqlite"
    numeric = ROOT / "artifacts/numeric"
    if not catalog.exists():
        raise SystemExit(f"missing {catalog}")
    with sqlite3.connect(catalog) as connection:
        genetic_records = connection.execute("SELECT COUNT(*) FROM genetic_records").fetchone()[0]
        individuals = connection.execute("SELECT COUNT(*) FROM individuals").fetchone()[0]
        columns = connection.execute(
            "SELECT value FROM catalog_meta WHERE key='aadr_annotation_column_count'"
        ).fetchone()[0]
        if genetic_records != 23089 or individuals != 21433 or columns != "49":
            raise SystemExit(
                f"unexpected catalog counts: records={genetic_records}, "
                f"individuals={individuals}, columns={columns}"
            )

    manifest = json.loads((numeric / "manifest.json").read_text())
    sample_ids = np.load(numeric / "sample_ids.npy", allow_pickle=False)
    pca = np.load(numeric / "pca_coordinates.npy", allow_pickle=False)
    distance = np.load(numeric / "allele_distance.npy", allow_pickle=False)
    overlap = np.load(numeric / "overlap_snp_count.npy", allow_pickle=False)
    benchmark = json.loads((numeric / "pca_smartpca_benchmark.json").read_text())
    if manifest["data_status"] != "published":
        raise SystemExit("numeric artifacts must be marked published")
    if len(sample_ids) != 320 or manifest["shape"] != {"samples": 320, "snps": 20000}:
        raise SystemExit("unexpected real benchmark shape")
    if benchmark["projection_r_squared"] < 0.99:
        raise SystemExit("NumPy projection does not meet the smartpca benchmark threshold")
    if pca.shape[0] != len(sample_ids) or distance.shape != overlap.shape:
        raise SystemExit("numeric artifact shapes do not agree")
    if not np.allclose(distance, distance.T, equal_nan=True):
        raise SystemExit("distance matrix is not symmetric")
    if not np.array_equal(overlap, overlap.T):
        raise SystemExit("overlap matrix is not symmetric")
    print(
        f"M1 verified: {individuals} people, {genetic_records} genetic records, "
        f"numeric={manifest['data_status']} ({len(sample_ids)} samples)"
    )


if __name__ == "__main__":
    main()

