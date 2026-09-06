#!/usr/bin/env python3
"""Select a deterministic, region-neutral real-data cohort for M1 numerics."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path


MISSING = {"", "..", "n/a", "N/A"}


def rank(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def number(value: str) -> float | None:
    return None if value in MISSING else float(value)


def choose_one_per_group(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["Group_Name"]].append(row)
    return [min(group_rows, key=lambda row: rank(row["Poseidon_ID"])) for group_rows in grouped.values()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--janno", required=True, type=Path)
    parser.add_argument("--fam", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-count", type=int, default=256)
    parser.add_argument("--projection-count", type=int, default=64)
    parser.add_argument("--reference-min-snps", type=int, default=300_000)
    parser.add_argument("--projection-min-snps", type=int, default=100_000)
    args = parser.parse_args()

    fam = {}
    with args.fam.open() as handle:
        for line in handle:
            fields = line.split()
            fam[fields[1]] = fields[0]

    with args.janno.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    eligible_references = []
    eligible_projections = []
    for row in rows:
        sample_id = row["Poseidon_ID"]
        group = row["Group_Name"]
        mean_bp = number(row["AADR_Date_Mean_BP"])
        snps_ho = number(row["AADR_SNPs_HO"])
        if sample_id not in fam or mean_bp is None or snps_ho is None:
            continue
        if (
            row["AADR_Assessment"] != "Pass"
            or group.startswith("Ignore_")
            or "-o" in group
            or "_oPCA" in group
        ):
            continue
        if (
            row["AADR_Call_Suffix"] == "HO"
            and mean_bp <= 0
            and row["Genotype_Ploidy"] == "diploid"
            and snps_ho >= args.reference_min_snps
        ):
            eligible_references.append(row)
        elif mean_bp > 0 and snps_ho >= args.projection_min_snps:
            eligible_projections.append(row)

    reference_candidates = choose_one_per_group(eligible_references)
    projection_candidates = choose_one_per_group(eligible_projections)
    references = sorted(
        reference_candidates, key=lambda row: rank("reference:" + row["Group_Name"])
    )[: args.reference_count]
    projections = sorted(
        projection_candidates, key=lambda row: rank("projection:" + row["Group_Name"])
    )[: args.projection_count]
    if len(references) < args.reference_count or len(projections) < args.projection_count:
        raise SystemExit(
            f"insufficient candidates: references={len(references)}, projections={len(projections)}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = args.output_dir / "benchmark_samples.tsv"
    keep_all_path = args.output_dir / "benchmark.keep"
    keep_reference_path = args.output_dir / "benchmark_reference.keep"
    selected = [("reference", row) for row in references] + [
        ("projection", row) for row in projections
    ]
    with cohort_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("fid", "iid", "role", "group", "mean_bp", "snps_ho"))
        for role, row in selected:
            writer.writerow(
                (
                    fam[row["Poseidon_ID"]],
                    row["Poseidon_ID"],
                    role,
                    row["Group_Name"],
                    row["AADR_Date_Mean_BP"],
                    row["AADR_SNPs_HO"],
                )
            )
    with keep_all_path.open("w", encoding="utf-8") as handle:
        for _, row in selected:
            handle.write(f"{fam[row['Poseidon_ID']]}\t{row['Poseidon_ID']}\n")
    with keep_reference_path.open("w", encoding="utf-8") as handle:
        for row in references:
            handle.write(f"{fam[row['Poseidon_ID']]}\t{row['Poseidon_ID']}\n")
    print(
        f"selected {len(references)} modern HO references from "
        f"{len(reference_candidates)} eligible groups and {len(projections)} ancient projections "
        f"from {len(projection_candidates)} eligible groups"
    )


if __name__ == "__main__":
    main()

