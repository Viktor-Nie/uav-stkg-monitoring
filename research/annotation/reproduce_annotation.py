"""Describe retained annotation tables without inferring their collection process."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ("in_scope", "conditional", "out_of_scope")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or any(output.is_relative_to(ROOT / d) for d in ("data", "src", "research")):
        parser.error("output must not overwrite release inputs or source")
    if output.exists():
        parser.error("output must be a new directory")
    output.mkdir(parents=True)
    summaries, paired, families, hashes = [], [], [], {}
    for n in (19, 215):
        tables = {}
        for slot in "ABC":
            path = ROOT / "data/annotation" / f"historical_{slot}_{n}.csv"
            rows = read(path)
            assert len(rows) == n and len({r["source_item_id"] for r in rows}) == n
            assert all(r["scope"] in LABELS for r in rows)
            tables[slot] = {r["source_item_id"]: r for r in rows}
            hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert tables["A"].keys() == tables["B"].keys() == tables["C"].keys()
        data = []
        for key in sorted(tables["A"]):
            a, b, c = (tables[slot][key] for slot in "ABC")
            assert a["source_family_id"] == b["source_family_id"] == c["source_family_id"]
            row = {"collection_n": n, "source_item_id": key, "source_family_id": a["source_family_id"], "A_scope": a["scope"], "B_scope": b["scope"], "C_scope": c["scope"], "AB_scope_agree": a["scope"] == b["scope"], "C_differs_from_A": c["scope"] != a["scope"], "C_differs_from_B": c["scope"] != b["scope"]}
            data.append(row)
        paired.extend(data)
        observed = sum(r["AB_scope_agree"] for r in data) / n
        marginal_a = Counter(r["A_scope"] for r in data)
        marginal_b = Counter(r["B_scope"] for r in data)
        expected = sum(marginal_a[k] * marginal_b[k] for k in LABELS) / n**2
        summaries.append({"collection_n": n, "families": len({r["source_family_id"] for r in data}), "A_scope_counts": dict(marginal_a), "B_scope_counts": dict(marginal_b), "C_scope_counts": dict(Counter(r["C_scope"] for r in data)), "AB_scope_agreements": sum(r["AB_scope_agree"] for r in data), "AB_scope_disagreements": sum(not r["AB_scope_agree"] for r in data), "AB_scope_agreement_rate": observed, "AB_scope_cohen_kappa": (observed - expected) / (1 - expected) if expected < 1 else None, "C_differs_from_A": sum(r["C_differs_from_A"] for r in data), "C_differs_from_B": sum(r["C_differs_from_B"] for r in data)})
        for family in sorted({r["source_family_id"] for r in data}):
            selected = [r for r in data if r["source_family_id"] == family]
            families.append({"collection_n": n, "source_family_id": family, "n": len(selected), "AB_scope_agreements": sum(r["AB_scope_agree"] for r in selected), "AB_scope_disagreements": sum(not r["AB_scope_agree"] for r in selected)})
    write(output / "annotation_scope_pairs.csv", paired)
    write(output / "annotation_scope_family_counts.csv", families)
    receipt = {"status": "passed", "collections": summaries, "input_sha256": hashes, "interpretation": "Descriptive agreement of retained historical scope decisions; neither a semantic correctness estimate nor authentication of independent collection. The revised nineteen-item reference remains computational and awaits human review.", "human_decisions_created": 0}
    (output / "annotation_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
