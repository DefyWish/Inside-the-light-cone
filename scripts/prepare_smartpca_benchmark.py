#!/usr/bin/env python3
"""Write the small smartpca projection benchmark parameter files."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with args.cohort.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    reference_groups = sorted({row["fid"] for row in rows if row["role"] == "reference"})
    populations_path = (args.output_dir / "reference_populations.txt").resolve()
    populations_path.write_text("\n".join(reference_groups) + "\n")

    prefix = args.prefix.resolve()
    parameter_path = args.output_dir / "smartpca.par"
    values = {
        "genotypename": prefix.with_suffix(".bed"),
        "snpname": prefix.with_suffix(".bim"),
        "indivname": prefix.with_suffix(".fam"),
        "evecoutname": (args.output_dir / "smartpca.evec").resolve(),
        "evaloutname": (args.output_dir / "smartpca.eval").resolve(),
        "poplistname": populations_path,
    }
    lines = [f"{key}: {value}" for key, value in values.items()]
    lines.extend(
        (
            "numoutevec: 6",
            "lsqproject: YES",
            "shrinkmode: NO",
            "killr2: NO",
            "numoutlieriter: 0",
        )
    )
    parameter_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {parameter_path} with {len(reference_groups)} reference populations")


if __name__ == "__main__":
    main()

