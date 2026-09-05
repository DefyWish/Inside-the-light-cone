#!/usr/bin/env python3
"""Compare NumPy PCA projection with smartpca on the real M1 benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def distance_correlation(left: np.ndarray, right: np.ndarray) -> float:
    row, column = np.triu_indices(len(left), 1)
    left_distance = np.linalg.norm(left[row] - left[column], axis=1)
    right_distance = np.linalg.norm(right[row] - right[column], axis=1)
    return float(np.corrcoef(left_distance, right_distance)[0, 1])


def r_squared(observed: np.ndarray, predicted: np.ndarray) -> float:
    residual = np.square(observed - predicted).sum()
    total = np.square(observed - observed.mean(axis=0, keepdims=True)).sum()
    return float(1 - residual / total)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numeric-dir", required=True, type=Path)
    parser.add_argument("--smartpca-evec", required=True, type=Path)
    parser.add_argument("--aliases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with args.aliases.open(encoding="utf-8", newline="") as handle:
        alias_rows = list(csv.DictReader(handle, delimiter="\t"))
    alias_to_original = {
        f"{row['fid']}:{row['iid']}": (row["original_iid"], row["role"])
        for row in alias_rows
    }
    smartpca = {}
    with args.smartpca_evec.open() as handle:
        for line in handle:
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            alias_id = fields[0]
            if alias_id not in alias_to_original:
                continue
            original_id, role = alias_to_original[alias_id]
            smartpca[original_id] = (np.array(fields[1:7], dtype=np.float64), role)

    sample_ids = np.load(args.numeric_dir / "sample_ids.npy", allow_pickle=False)
    numpy_coordinates = np.load(
        args.numeric_dir / "pca_coordinates.npy", allow_pickle=False
    ).astype(np.float64)
    if set(sample_ids) != set(smartpca):
        raise SystemExit("NumPy and smartpca sample IDs do not agree")
    smartpca_coordinates = np.vstack([smartpca[sample_id][0] for sample_id in sample_ids])
    reference_mask = np.array([smartpca[sample_id][1] == "reference" for sample_id in sample_ids])
    projection_mask = ~reference_mask

    numpy_reference = numpy_coordinates[reference_mask]
    smartpca_reference = smartpca_coordinates[reference_mask]
    numpy_center = numpy_reference.mean(axis=0, keepdims=True)
    smartpca_center = smartpca_reference.mean(axis=0, keepdims=True)
    transform, _, _, _ = np.linalg.lstsq(
        numpy_reference - numpy_center,
        smartpca_reference - smartpca_center,
        rcond=None,
    )
    aligned = (numpy_coordinates - numpy_center) @ transform + smartpca_center
    correlations = [
        float(np.corrcoef(aligned[:, index], smartpca_coordinates[:, index])[0, 1])
        for index in range(6)
    ]
    result = {
        "schema_version": 1,
        "method": "linear coordinate alignment fitted on modern references only",
        "reference_samples": int(reference_mask.sum()),
        "projection_samples": int(projection_mask.sum()),
        "snps": 20_000,
        "smartpca": {
            "eigensoft_version": "8.0.0",
            "lsqproject": True,
            "shrinkmode": False,
        },
        "reference_r_squared": r_squared(
            smartpca_coordinates[reference_mask], aligned[reference_mask]
        ),
        "projection_r_squared": r_squared(
            smartpca_coordinates[projection_mask], aligned[projection_mask]
        ),
        "reference_pairwise_distance_correlation": distance_correlation(
            smartpca_coordinates[reference_mask], aligned[reference_mask]
        ),
        "projection_pairwise_distance_correlation": distance_correlation(
            smartpca_coordinates[projection_mask], aligned[projection_mask]
        ),
        "aligned_component_correlations_all_samples": correlations,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    manifest_path = args.numeric_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["validation"] = {
        "smartpca_benchmark": {
            "result": str(args.output),
            "sha256": sha256(args.output),
            **{key: value for key, value in result.items() if key != "smartpca"},
            "smartpca": result["smartpca"],
        }
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

