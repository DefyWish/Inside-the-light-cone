#!/usr/bin/env python3
"""Build PCA, allele-sharing distance, and nearest-neighbor artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def standardized_pca_projection(
    genotypes: np.ndarray,
    reference_mask: np.ndarray,
    component_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    reference = genotypes[reference_mask].astype(np.float64)
    observed_reference = reference >= 0
    allele_counts = np.where(observed_reference, reference, 0).sum(axis=0)
    chromosome_counts = observed_reference.sum(axis=0) * 2
    allele_frequency = np.divide(
        allele_counts,
        chromosome_counts,
        out=np.zeros_like(allele_counts, dtype=np.float64),
        where=chromosome_counts > 0,
    )
    variance = 2 * allele_frequency * (1 - allele_frequency)
    usable = (chromosome_counts > 0) & (variance > 1e-8)
    if usable.sum() < 2:
        raise ValueError("Too few polymorphic SNPs in the reference cohort")

    scale = np.sqrt(variance[usable])
    center = 2 * allele_frequency[usable]
    reference_values = reference[:, usable]
    reference_z = np.where(reference_values >= 0, (reference_values - center) / scale, 0.0)
    reference_z -= reference_z.mean(axis=0, keepdims=True)
    _, _, right_vectors = np.linalg.svd(reference_z, full_matrices=False)
    component_count = min(component_count, right_vectors.shape[0])
    loadings = right_vectors[:component_count].T

    all_values = genotypes[:, usable].astype(np.float64)
    coordinates = np.empty((len(genotypes), component_count), dtype=np.float64)
    for sample_index, values in enumerate(all_values):
        observed = values >= 0
        standardized = (values[observed] - center[observed]) / scale[observed]
        if reference_mask[sample_index]:
            complete = np.zeros(len(usable.nonzero()[0]), dtype=np.float64)
            complete[observed] = standardized
            coordinates[sample_index] = complete @ loadings
        else:
            coordinates[sample_index], _, _, _ = np.linalg.lstsq(
                loadings[observed], standardized, rcond=None
            )
    return coordinates.astype(np.float32), np.flatnonzero(usable).astype(np.int32)


def allele_distance(
    genotypes: np.ndarray,
    minimum_overlap: int,
) -> tuple[np.ndarray, np.ndarray]:
    sample_count = genotypes.shape[0]
    distances = np.full((sample_count, sample_count), np.nan, dtype=np.float32)
    overlaps = np.zeros((sample_count, sample_count), dtype=np.int32)
    for left in range(sample_count):
        distances[left, left] = 0.0
        overlaps[left, left] = int(np.count_nonzero(genotypes[left] >= 0))
        for right in range(left + 1, sample_count):
            observed = (genotypes[left] >= 0) & (genotypes[right] >= 0)
            overlap = int(observed.sum())
            overlaps[left, right] = overlaps[right, left] = overlap
            if overlap < minimum_overlap:
                continue
            value = np.abs(
                genotypes[left, observed].astype(np.float32)
                - genotypes[right, observed].astype(np.float32)
            ).mean() / 2.0
            distances[left, right] = distances[right, left] = value
    return distances, overlaps


def top_neighbors(
    distances: np.ndarray,
    overlaps: np.ndarray,
    neighbor_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sample_count = distances.shape[0]
    neighbor_count = min(neighbor_count, max(0, sample_count - 1))
    indices = np.full((sample_count, neighbor_count), -1, dtype=np.int32)
    values = np.full((sample_count, neighbor_count), np.nan, dtype=np.float32)
    counts = np.zeros((sample_count, neighbor_count), dtype=np.int32)
    for sample_index in range(sample_count):
        order = np.argsort(np.where(np.isnan(distances[sample_index]), np.inf, distances[sample_index]))
        order = order[order != sample_index]
        order = order[np.isfinite(distances[sample_index, order])][:neighbor_count]
        indices[sample_index, : len(order)] = order
        values[sample_index, : len(order)] = distances[sample_index, order]
        counts[sample_index, : len(order)] = overlaps[sample_index, order]
    return indices, values, counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-status", required=True, choices=("fixture", "published"))
    parser.add_argument("--components", type=int, default=6)
    parser.add_argument("--minimum-overlap", type=int, default=100)
    parser.add_argument("--neighbors", type=int, default=8)
    args = parser.parse_args()

    payload = np.load(args.input, allow_pickle=False)
    genotypes = payload["genotypes"]
    sample_ids = payload["sample_ids"]
    reference_mask = payload["reference_mask"].astype(bool)
    embedded_status = str(payload["data_status"].item())
    if embedded_status != args.source_status:
        raise ValueError(
            f"Input status {embedded_status!r} does not match --source-status {args.source_status!r}"
        )
    if genotypes.ndim != 2 or genotypes.shape[0] != len(sample_ids):
        raise ValueError("Genotype matrix and sample IDs have incompatible shapes")
    if reference_mask.shape != (len(sample_ids),) or reference_mask.sum() < 2:
        raise ValueError("reference_mask must select at least two samples")
    if not np.isin(genotypes, (-1, 0, 1, 2)).all():
        raise ValueError("Genotypes must use -1 for missing and 0/1/2 allele dosage")

    coordinates, usable_snp_indices = standardized_pca_projection(
        genotypes, reference_mask, args.components
    )
    distances, overlaps = allele_distance(genotypes, args.minimum_overlap)
    neighbor_indices, neighbor_distances, neighbor_overlaps = top_neighbors(
        distances, overlaps, args.neighbors
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "sample_ids": sample_ids,
        "reference_mask": reference_mask,
        "pca_coordinates": coordinates,
        "pca_usable_snp_indices": usable_snp_indices,
        "allele_distance": distances,
        "overlap_snp_count": overlaps,
        "neighbor_indices": neighbor_indices,
        "neighbor_distances": neighbor_distances,
        "neighbor_overlap_counts": neighbor_overlaps,
    }
    output_hashes = {}
    for name, values in outputs.items():
        path = args.output_dir / f"{name}.npy"
        np.save(path, values, allow_pickle=False)
        output_hashes[path.name] = sha256(path)

    manifest = {
        "schema_version": 1,
        "data_status": args.source_status,
        "aadr_release": "v66.p1" if args.source_status == "published" else None,
        "input": {"path": str(args.input), "sha256": sha256(args.input)},
        "shape": {"samples": int(genotypes.shape[0]), "snps": int(genotypes.shape[1])},
        "parameters": {
            "pca_components": int(coordinates.shape[1]),
            "pca_reference_samples": int(reference_mask.sum()),
            "minimum_overlap": args.minimum_overlap,
            "neighbors": args.neighbors,
            "distance": "mean absolute allele-dosage difference / 2 on jointly observed SNPs",
            "missing_genotype": -1,
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "outputs": output_hashes,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        f"built {args.output_dir}: {genotypes.shape[0]} samples, "
        f"{len(usable_snp_indices)} PCA SNPs, status={args.source_status}"
    )


if __name__ == "__main__":
    main()

