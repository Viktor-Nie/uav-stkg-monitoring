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



def validate_current_review(output, hashes):
    """Validate received core fields, without authenticating workflow from agreement."""
    from datetime import date, datetime
    base = ROOT / "data/annotation"
    canonical_path = ROOT / "research/ablation/gold_reference_19_human_reviewed.csv"
    alias_path = ROOT / "research/ablation/reference_19_v33_source_reviewed.csv"
    provenance_path = ROOT / "data/provenance/human_review_20261019_receipt.json"
    fidelity_path = base / "source_fidelity_19_human_reviewed.csv"
    rewrite_path = base / "source_fidelity_8_requires_rewrite.csv"
    inputs = [canonical_path, alias_path, provenance_path, fidelity_path, rewrite_path]
    canonical_rows = read(canonical_path)
    canonical = {r["source_item_id"]: r for r in canonical_rows}
    assert len(canonical) == len(canonical_rows) == 19
    assert canonical_path.read_bytes() == alias_path.read_bytes()
    version = "human_review_20261019"
    assert all(r["reference_version"] == version for r in canonical_rows)
    assert Counter(r["adjudicated_scope"] for r in canonical_rows) == {"in_scope": 5, "out_of_scope": 14}
    tables = {}
    for role in "ABC":
        path = base / f"review_{role}_19_human_reviewed.csv"
        inputs.append(path)
        source = read(path)
        assert len(source) == 19
        table = {r["source_item_id"]: r for r in source}
        assert len(table) == 19 and table.keys() == canonical.keys()
        assert all(r["reviewer_role"] == role and r["reference_version"] == version for r in source)
        tables[role] = table
    fidelity_rows = read(fidelity_path)
    fidelity = {r["source_item_id"]: r for r in fidelity_rows}
    assert len(fidelity_rows) == len(fidelity) == 19 and fidelity.keys() == canonical.keys()
    assert Counter(r["C_source_consistency"] for r in fidelity_rows) == {"一致": 11, "需改写": 8}
    rewrites = read(rewrite_path)
    expected_rewrites = {r["source_item_id"] for r in fidelity_rows if r["C_source_consistency"] == "需改写"}
    assert len(rewrites) == len(expected_rewrites) == 8
    assert {r["source_item_id"] for r in rewrites} == expected_rewrites
    validation_rows = []
    for sid, reference in canonical.items():
        expected = (reference["adjudicated_scope"], reference["reference_signal_id"], reference["reference_template_id"], reference["reference_language_role_set"])
        for role in "ABC":
            row = tables[role][sid]
            assert row["frozen_chinese_model_input"] == reference["normalized_requirement"]
            assert row["source_family_id"] == reference["source_family_id"]
            assert tuple(row[k] for k in ("scope", "signal_id", "template_id", "language_role_set")) == expected
            assert row["source_consistency"] == fidelity[sid][role + "_source_consistency"]
        assert tables["C"][sid]["original_physical_context"] == ""
        assert fidelity[sid]["C_original_physical_context"] == ""
        assert tables["C"][sid]["source_consistency"] == fidelity[sid]["C_source_consistency"]
        assert tables["C"][sid]["proposed_rendering"] == fidelity[sid]["C_proposed_source_faithful_rendering"]
        assert tables["C"][sid]["original_rationale"] == fidelity[sid]["C_original_rationale"]
        validation_rows.append({"source_item_id": sid, "reference_version": version,
            "canonical_scope": expected[0], "canonical_signal": expected[1], "canonical_template": expected[2], "canonical_language_role_set": expected[3],
            "A_B_C_core_equal_to_canonical": True, "frozen_chinese_input_equal": True,
            "source_consistency_C": fidelity[sid]["C_source_consistency"], "original_C_physical_context_empty": True})
    provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
    assert provenance["reference_version"] == version
    completed = provenance["completion_date_author_reported"]
    precision = provenance["completion_date_precision"]
    if precision == "day":
        assert len(completed) == 10 and date.fromisoformat(completed).isoformat() == completed
    else:
        assert precision in ("minute", "second")
        datetime.fromisoformat(completed)
    assert "author" in provenance["human_origin"].lower()
    assert provenance["original_C_physical_context_nonempty"] == 0
    editor_files = {
        "editor_physical_context_19_20261020.csv": 19,
        "editor_source_corrections_20261020.csv": 3,
    }
    for name, count in editor_files.items():
        path = base / name
        editor = read(path)
        assert len(editor) == count and len({r["source_item_id"] for r in editor}) == count
        assert {r["source_item_id"] for r in editor} <= canonical.keys()
        assert all(r["counts_as_original_C_judgment"].lower() == "false" for r in editor)
        assert all(r["physical_applicability_verified"].lower() == "false" for r in editor)
        inputs.append(path)
    for path in inputs:
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(output / "human_review_19_core_validation.csv", validation_rows)
    return {"status": "passed", "reference_version": version, "items": 19,
        "core_four_tuple_agreement_with_canonical": {"A": 19, "B": 19, "C": 19},
        "in_scope": 5, "out_of_scope": 14, "source_consistent": 11, "source_requires_rewrite": 8,
        "C_original_physical_context_nonempty": 0,
        "completion_date_author_reported": completed, "completion_date_precision": precision,
        "human_origin_evidence": "Author confirmation; only merged workbook recovered in this intake. Separate independent original files were not recovered.",
        "independence_interpretation": "Equal answers and file hashes do not establish independence; independence is reported and confirmed by the author.",
        "editor_physical_context_items": 19, "editor_source_correction_items": 3,
        "editor_material_is_original_C_judgment": False, "field_physical_validation_claimed": False,
        "human_decisions_created": 0}


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
    current_review = validate_current_review(output, hashes)
    receipt = {"status": "passed", "current_human_review": current_review, "collections": summaries, "input_sha256": hashes, "interpretation": "Descriptive agreement of retained historical scope decisions; neither a semantic correctness estimate nor authentication of independent collection. The separate current reference human_review_20261019 has author-confirmed completed core A/B/C review; this driver preserves historical scope agreement and separately validates the current nineteen core decisions, source-fidelity counts and empty C physical-context fields.", "human_decisions_created": 0}
    (output / "annotation_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
