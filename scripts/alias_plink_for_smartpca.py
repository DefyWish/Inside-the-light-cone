#!/usr/bin/env python3
"""Create a short-ID PLINK working copy for EIGENSOFT's 39-character limit."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--output-cohort", required=True, type=Path)
    args = parser.parse_args()

    with args.cohort.open(encoding="utf-8", newline="") as handle:
        cohort = list(csv.DictReader(handle, delimiter="\t"))
    by_iid = {row["iid"]: row for row in cohort}
    fam_rows = [line.split() for line in args.prefix.with_suffix(".fam").read_text().splitlines()]
    if {row[1] for row in fam_rows} != set(by_iid):
        raise SystemExit("PLINK FAM and cohort IDs do not agree")

    reference_groups = sorted({row["group"] for row in cohort if row["role"] == "reference"})
    group_alias = {group: f"R{index:03d}" for index, group in enumerate(reference_groups, 1)}
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.prefix.with_suffix(".bed"), args.output_prefix.with_suffix(".bed"))
    shutil.copyfile(args.prefix.with_suffix(".bim"), args.output_prefix.with_suffix(".bim"))

    alias_rows = []
    output_fam = []
    for index, fam_row in enumerate(fam_rows, 1):
        original_fid, original_iid = fam_row[:2]
        source = by_iid[original_iid]
        alias_fid = group_alias[source["group"]] if source["role"] == "reference" else "Projected"
        alias_iid = f"S{index:04d}"
        output_fam.append([alias_fid, alias_iid, fam_row[2], fam_row[3], fam_row[4], alias_fid])
        alias_rows.append(
            {
                "fid": alias_fid,
                "iid": alias_iid,
                "role": source["role"],
                "group": source["group"],
                "mean_bp": source["mean_bp"],
                "snps_ho": source["snps_ho"],
                "original_fid": original_fid,
                "original_iid": original_iid,
            }
        )
    args.output_prefix.with_suffix(".fam").write_text(
        "\n".join("\t".join(row) for row in output_fam) + "\n"
    )
    with args.output_cohort.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(alias_rows[0])
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(alias_rows)
    print(
        f"created smartpca aliases for {len(alias_rows)} samples; "
        f"mapping={args.output_cohort}"
    )


if __name__ == "__main__":
    main()

