"""Run separately denominated v33 structural/context variants and controls.

These variants are synthetic graph configurations, not requirements, flights,
expert annotations, or independent physical evidence. The frozen 354-variant
experiment is neither modified nor rerun here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import pandas as pd

from frozen_validator_reference import validate_variant, validate_flat_binding_export
from validation_extension import (
    ENDPOINT_TYPES, EXECUTION_CONTEXT_FIELDS, PRIMARY_TYPES,
    REQUIRED_STRING_PROPERTIES, validate_extended,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NODE_SOURCE = ROOT / "data/graph/nodes.csv"
EDGE_SOURCE = ROOT / "data/graph/relationships.csv"
BINDING_SOURCE = ROOT / "data/graph/bindings.csv"
DEFAULT_OUT = ROOT / "outputs/graph_extension/extension"


def digest_frame(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def change_property(nodes: pd.DataFrame, identifier: str, changes: dict) -> pd.DataFrame:
    changed = nodes.copy()
    index = changed.index[changed["id"].eq(identifier)]
    assert len(index) == 1
    properties = json.loads(changed.at[index[0], "properties_json"])
    properties.update(changes)
    changed.at[index[0], "properties_json"] = json.dumps(properties, ensure_ascii=False, sort_keys=True)
    return changed


def baseline_accepts(nodes: pd.DataFrame, edges: pd.DataFrame) -> bool:
    try:
        validate_variant(nodes, edges)
        return True
    except (AssertionError, KeyError, IndexError, TypeError, ValueError):
        return False


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    nodes = pd.read_csv(NODE_SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    edges = pd.read_csv(EDGE_SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    flat = pd.read_csv(BINDING_SOURCE, encoding="utf-8-sig")
    validate_flat_binding_export(nodes, edges, flat)
    clean = validate_extended(nodes, edges)
    assert clean["accepted"], clean["errors"]
    assert clean["execution_context_fully_known_equal_checks"] == 0
    assert clean["execution_context_unknown_or_not_applicable_checks"] == 84 * 4
    meta = {row.id: json.loads(row.properties_json) for row in nodes.itertuples(index=False)}
    labels = {row.id: set(row.labels.split(";")) for row in nodes.itertuples(index=False)}
    ids_by_type = {kind: sorted(identifier for identifier, label in labels.items() if kind in label) for kind in PRIMARY_TYPES}
    records = []
    controls = [{"control": "frozen_clean_export", "accepted": True, "known_equal": 0, "unknown_context_checks": clean["execution_context_unknown_or_not_applicable_checks"]}]

    def add(family: str, target: str, changed_nodes: pd.DataFrame, changed_edges: pd.DataFrame, operation: dict, disabled: str):
        result = validate_extended(changed_nodes, changed_edges)
        without = validate_extended(changed_nodes, changed_edges, frozenset({disabled}))
        records.append({
            "variant_id": f"V33_{len(records)+1:04d}", "family": family, "target": target,
            "operation_json": json.dumps(operation, ensure_ascii=False, sort_keys=True),
            "nodes_sha256": digest_frame(changed_nodes), "relationships_sha256": digest_frame(changed_edges),
            "historical_validator_accepted": baseline_accepts(changed_nodes, changed_edges),
            "extended_validator_accepted": result["accepted"],
            "rejection_codes": "|".join(sorted({error["code"] for error in result["errors"]})),
            "rejection_details_json": json.dumps(result["errors"], ensure_ascii=False, sort_keys=True),
            "disabled_extension": disabled, "disabled_extension_accepted": without["accepted"],
            "disabled_rejection_codes": "|".join(sorted({error["code"] for error in without["errors"]})),
        })
        assert not result["accepted"], f"Unexpected accepted variant {family}/{target}"

    for relation, (source_type, target_type) in sorted(ENDPOINT_TYPES.items()):
        index = edges.index[edges["relation"].eq(relation)][0]
        for side, kind in (("source", source_type), ("target", target_type)):
            replacement = next(identifier for identifier in sorted(labels) if kind not in labels[identifier])
            changed = edges.copy()
            changed.at[index, side] = replacement
            add("wrong_endpoint_" + side + "_type", relation, nodes, changed,
                {"edge_row": int(index), "field": side, "replacement": replacement}, "endpoint_types")

    for kind in sorted(PRIMARY_TYPES):
        identifier = ids_by_type[kind][0]
        field = REQUIRED_STRING_PROPERTIES[kind][0]
        changed = change_property(nodes, identifier, {field: True})
        add("required_property_type", identifier + "." + field, changed, edges,
            {"node": identifier, "field": field, "value": True}, "record_types")
    reachable_parameters = sorted(set(edges.loc[edges["relation"].eq("BINDS_PARAMETER"), "target"]))
    assert len(reachable_parameters) == 16
    for identifier in reachable_parameters:
        changed = change_property(nodes, identifier, {"value": True})
        add("numeric_boolean_type", identifier, changed, edges,
            {"node": identifier, "field": "value", "value": True}, "record_types")

    formulas = ids_by_type["STLFormula"]
    for index, requirement in enumerate(ids_by_type["Requirement"]):
        original = "formula:" + requirement.removeprefix("requirement:")
        target = formulas[(formulas.index(original) + 1) % len(formulas)]
        new_edge = {"source": requirement, "relation": "FORMALIZED_AS", "target": target, "properties_json": "{}"}
        changed = pd.concat([edges, pd.DataFrame([new_edge])], ignore_index=True)
        add("duplicate_requirement_mapping", requirement, nodes, changed,
            {"append_edge": new_edge}, "requirement_bijection")

    for binding_id in ids_by_type["ParameterBinding"]:
        owner = meta[binding_id]["formula_id"]
        another_owner = formulas[(formulas.index(owner) + 1) % len(formulas)]
        shared_edge = {"source": another_owner, "relation": "HAS_PARAMETER_BINDING", "target": binding_id, "properties_json": "{}"}
        shared = pd.concat([edges, pd.DataFrame([shared_edge])], ignore_index=True)
        add("shared_parameter_binding", binding_id, nodes, shared,
            {"append_edge": shared_edge}, "binding_ownership")
        orphan = nodes.loc[nodes["id"].eq(binding_id)].copy()
        orphan_id = "binding:unowned_v33:" + binding_id.removeprefix("binding:")
        orphan.loc[:, "id"] = orphan_id
        orphan.loc[:, "name"] = "unowned_v33:" + binding_id.removeprefix("binding:")
        changed_nodes = pd.concat([nodes, orphan], ignore_index=True)
        add("isolated_parameter_binding", orphan_id, changed_nodes, edges,
            {"copy_node": binding_id, "new_id": orphan_id, "owner_edges": 0}, "binding_ownership")
        changed_nodes = change_property(nodes, binding_id, {"formula_id": another_owner})
        add("binding_owner_property", binding_id, changed_nodes, edges,
            {"node": binding_id, "field": "formula_id", "value": another_owner}, "binding_ownership")

    # Explicit applicability fixture: these TEST_ONLY values are never added to
    # the archived graph, imported snapshot, flight data or manuscript claims.
    for binding_id in ids_by_type["ParameterBinding"]:
        owner = meta[binding_id]["formula_id"]
        signal = "signal:" + meta[binding_id]["signal_id"]
        parameter = meta[binding_id]["parameter_id"]
        applicable = {field: "TEST_ONLY_" + field.upper() + "_A" for field in EXECUTION_CONTEXT_FIELDS}
        fixture = nodes
        for participant in (owner, signal, parameter):
            fixture = change_property(fixture, participant, applicable)
        positive = validate_extended(fixture, edges)
        assert positive["accepted"]
        assert positive["execution_context_fully_known_equal_checks"] >= 4
        controls.append({"control": "known_same_use_context:" + binding_id, "accepted": True,
            "known_equal": positive["execution_context_fully_known_equal_checks"],
            "unknown_context_checks": positive["execution_context_unknown_or_not_applicable_checks"]})
        for field in EXECUTION_CONTEXT_FIELDS:
            changed_nodes = change_property(fixture, parameter, {field: applicable[field][:-1] + "B"})
            add("known_conflict_" + field.removeprefix("execution_"), binding_id, changed_nodes, edges,
                {"fixture_participants": [owner, signal, parameter], "fixture_context": applicable,
                 "mutated_node": parameter, "field": field, "value": applicable[field][:-1] + "B"}, "context_consistency")

    # Unknown values cannot become equality evidence. Distinct source platforms
    # in the clean HIL/reference and real/offline records are not compared as
    # if they describe the same execution platform.
    binding = "binding:N06:trigger_upper"
    owner, signal, parameter = "formula:N06", "signal:speed_3d_mps", meta[binding]["parameter_id"]
    for unknown in ("not_recorded", "not_applicable", "unknown"):
        fixture = nodes
        for participant in (owner, signal):
            fixture = change_property(fixture, participant, {field: "TEST_ONLY_" + field.upper() + "_A" for field in EXECUTION_CONTEXT_FIELDS})
        fixture = change_property(fixture, parameter, {field: unknown for field in EXECUTION_CONTEXT_FIELDS})
        result = validate_extended(fixture, edges)
        assert result["accepted"]
        assert result["execution_context_fully_known_equal_checks"] == 0
        controls.append({"control": "unknown_is_not_match:" + unknown, "accepted": True, "known_equal": 0,
            "unknown_context_checks": result["execution_context_unknown_or_not_applicable_checks"]})

    frame = pd.DataFrame(records)
    frame.to_csv(out / "v33_constraint_extension_details.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(controls).to_csv(out / "v33_constraint_extension_positive_controls.csv", index=False, encoding="utf-8-sig")
    grouped = []
    for family, subset in frame.groupby("family", sort=True):
        grouped.append({"family": family, "variants": len(subset),
            "historical_rejected": int((~subset["historical_validator_accepted"]).sum()),
            "extended_rejected": int((~subset["extended_validator_accepted"]).sum()),
            "accepted_when_assigned_extension_disabled": int(subset["disabled_extension_accepted"].sum())})
    pd.DataFrame(grouped).to_csv(out / "v33_constraint_extension_by_family.csv", index=False, encoding="utf-8-sig")
    receipt = {
        "status": "passed", "denominator": "new independently generated v33 graph/configuration variants only",
        "new_variant_count": len(frame), "new_variant_rejected_count": int((~frame["extended_validator_accepted"]).sum()),
        "historical_validator_rejected": int((~frame["historical_validator_accepted"]).sum()),
        "historical_validator_accepted": int(frame["historical_validator_accepted"].sum()),
        "positive_control_count": len(controls), "positive_controls_accepted": len(controls),
        "clean_graph": {"nodes": len(nodes), "relationships": len(edges), "bindings": len(flat), **clean},
        "families": grouped,
        "input_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (NODE_SOURCE, EDGE_SOURCE, BINDING_SOURCE)},
        "execution_context_fields": list(EXECUTION_CONTEXT_FIELDS),
        "limitations": ["Variants and applicability fixtures are constructed configuration checks, not new independent requirements or flight measurements.",
            "Historical 354 variants and their reported outcomes remain unchanged and are not combined with this denominator.",
            "Safeguards can overlap; disabling an assigned extension may still leave a mutant rejected by another predicate.",
            "The clean graph has no fully known execution-context matches; unknown/not_recorded markers are preserved.",
            "Record-chain integrity and absence of known conflicts do not establish physical applicability, safety or deployment calibration."],
    }
    (out / "v33_constraint_extension_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("status", "new_variant_count", "new_variant_rejected_count", "historical_validator_rejected", "historical_validator_accepted", "positive_control_count")}, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    arguments = parser.parse_args()
    run(arguments.output)
