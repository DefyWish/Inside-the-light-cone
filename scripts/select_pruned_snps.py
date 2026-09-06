#!/usr/bin/env python3
"""Choose a reproducible cap from PLINK's LD-pruned SNP list."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", type=int, default=20_000)
    args = parser.parse_args()
    snps = [line.strip() for line in args.input.read_text().splitlines() if line.strip()]
    selected = sorted(
        sorted(snps, key=lambda snp: hashlib.sha256(snp.encode("utf-8")).hexdigest())[
            : args.count
        ]
    )
    args.output.write_text("\n".join(selected) + "\n")
    print(f"selected {len(selected)} of {len(snps)} LD-pruned SNPs")


if __name__ == "__main__":
    main()

