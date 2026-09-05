#!/usr/bin/env python3
"""Create a deterministic development-only genotype fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rng = np.random.default_rng(20260831)
    sample_count = 16
    snp_count = 400
    reference_count = 10
    allele_frequency = rng.uniform(0.08, 0.92, size=snp_count)
    genotypes = rng.binomial(2, allele_frequency, size=(sample_count, snp_count)).astype(np.int8)

    # Add two mild synthetic gradients so the projection and neighbor outputs are testable.
    genotypes[5:10, :80] = rng.binomial(2, np.clip(allele_frequency[:80] + 0.18, 0, 1), size=(5, 80))
    genotypes[10:, 80:160] = rng.binomial(2, np.clip(allele_frequency[80:160] - 0.18, 0, 1), size=(6, 80))
    missing = rng.random(genotypes.shape) < 0.06
    missing[12:, :] |= rng.random((sample_count - 12, snp_count)) < 0.22
    genotypes[missing] = -1

    sample_ids = np.array(
        [f"fixture_ref_{index + 1:03d}" for index in range(reference_count)]
        + [f"fixture_project_{index + 1:03d}" for index in range(sample_count - reference_count)]
    )
    reference_mask = np.zeros(sample_count, dtype=bool)
    reference_mask[:reference_count] = True
    snp_ids = np.array([f"fixture_snp_{index + 1:05d}" for index in range(snp_count)])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        genotypes=genotypes,
        sample_ids=sample_ids,
        reference_mask=reference_mask,
        snp_ids=snp_ids,
        data_status=np.array("fixture"),
    )
    print(f"built {args.output}: {sample_count} samples x {snp_count} SNPs")


if __name__ == "__main__":
    main()

