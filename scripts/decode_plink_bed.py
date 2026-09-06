#!/usr/bin/env python3
"""Decode a small SNP-major PLINK BED subset into the numeric builder input."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


DOSAGE = np.array([0, -1, 1, 2], dtype=np.int8)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--block-snps", type=int, default=2_000)
    args = parser.parse_args()

    fam_path = args.prefix.with_suffix(".fam")
    bim_path = args.prefix.with_suffix(".bim")
    bed_path = args.prefix.with_suffix(".bed")
    fam_rows = [line.split() for line in fam_path.read_text().splitlines() if line.strip()]
    sample_ids = np.array([row[1] for row in fam_rows])
    snp_ids = np.array(
        [line.split()[1] for line in bim_path.read_text().splitlines() if line.strip()]
    )
    with args.cohort.open(encoding="utf-8", newline="") as handle:
        roles = {row["iid"]: row["role"] for row in csv.DictReader(handle, delimiter="\t")}
    if set(sample_ids) != set(roles):
        raise SystemExit("PLINK subset samples do not match the cohort file")
    reference_mask = np.array([roles[sample_id] == "reference" for sample_id in sample_ids])

    bytes_per_snp = (len(sample_ids) + 3) // 4
    expected_size = 3 + len(snp_ids) * bytes_per_snp
    if bed_path.stat().st_size != expected_size:
        raise SystemExit(
            f"unexpected BED size: found {bed_path.stat().st_size}, expected {expected_size}"
        )
    with bed_path.open("rb") as handle:
        if handle.read(3) != bytes((0x6C, 0x1B, 0x01)):
            raise SystemExit("BED is not SNP-major PLINK binary format")

    packed = np.memmap(
        bed_path,
        mode="r",
        dtype=np.uint8,
        offset=3,
        shape=(len(snp_ids), bytes_per_snp),
    )
    genotypes = np.empty((len(sample_ids), len(snp_ids)), dtype=np.int8)
    sample_index = np.arange(len(sample_ids))
    byte_index = sample_index // 4
    bit_shift = (sample_index % 4) * 2
    for start in range(0, len(snp_ids), args.block_snps):
        stop = min(start + args.block_snps, len(snp_ids))
        codes = (packed[start:stop, byte_index] >> bit_shift) & 0b11
        genotypes[:, start:stop] = DOSAGE[codes].T

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        genotypes=genotypes,
        sample_ids=sample_ids,
        reference_mask=reference_mask,
        snp_ids=snp_ids,
        data_status=np.array("published"),
    )
    print(
        f"decoded {len(sample_ids)} samples x {len(snp_ids)} SNPs; "
        f"references={int(reference_mask.sum())}"
    )


if __name__ == "__main__":
    main()

