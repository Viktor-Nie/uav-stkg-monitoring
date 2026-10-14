"""Strict v33 graph record, endpoint, ownership and known-context checks.

Application context is distinct from a parameter's measurement/source context.
Absent or not_recorded execution context stays unknown. It never establishes
physical applicability or deployment calibration.
"""
from __future__ import annotations
import json
import math
from collections import defaultdict
import pandas as pd

from frozen_validator_reference import CONTEXT_FIELDS, validate_variant

ENDPOINT_TYPES = {
    "FORMALIZED_AS": ("Requirement", "STLFormula"),
    "USES_TEMPLATE": ("STLFormula", "STLTemplate"),
    "IMPLEMENTED_BY": ("STLTemplate", "RuntimeMonitor"),
    "EXECUTED_BY": ("STLFormula", "RuntimeMonitor"),
    "READS_SIGNAL": ("STLFormula", "Signal"),
    "HAS_PARAMETER_BINDING": ("STLFormula", "ParameterBinding"),
    "BINDS_PARAMETER": ("ParameterBinding", "FormulaParameter"),
    "APPLIES_TO_SIGNAL": ("ParameterBinding", "Signal"),
}
PRIMARY_TYPES = {value for pair in ENDPOINT_TYPES.values() for value in pair}
LABELS = PRIMARY_TYPES | {"Entity", "Threshold", "RuntimeParameter", "NumericTolerance"}
REQUIRED_STRING_PROPERTIES = {
    "Requirement": ("text", "split", "source_artifact", "source_record_id", "provenance_status"),
    "STLFormula": ("legacy_formula", "parameterized_formula", "semantic_version", "template_id"),
    "STLTemplate": ("stl_shape", "v2_parameterized_shape"),
    "RuntimeMonitor": ("finite_trace_verdicts", "implementation", "semantic_version", "supported_input_profiles", "trigger_policy"),
    "ParameterBinding": ("binding_version", "formula_id", "parameter_id", "role", "signal_id"),
    "Signal": ("signal_id", "unit", "coordinate_frame", "coordinate_frame_status", "source_trace", "platform_context", "vehicle_context", "flight_mode_context", "firmware_context", "applicability_status", "mapping_version"),
    "FormulaParameter": ("parameter_kind", "unit", "signal_scope", *CONTEXT_FIELDS),
}
EXECUTION_CONTEXT_FIELDS = (
    "execution_vehicle_context", "execution_flight_mode_context",
    "execution_firmware_context", "execution_coordinate_frame",
)


def known_context(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower().startswith(("not_recorded", "not_applicable", "unknown", "unspecified")):
        return None
    return value


def validate_extended(nodes: pd.DataFrame, edges: pd.DataFrame, disabled: frozenset[str] = frozenset()) -> dict:
    """Return deterministic reason codes; historical predicates remain active."""
    errors = []
    missing_context = 0
    compared_context = 0

    def reject(code: str, detail: str):
        errors.append({"code": code, "detail": detail})

    ids, labels, props = {}, {}, {}
    if nodes["id"].duplicated().any():
        reject("duplicate_node", "logical node identifier")
    for row in nodes.itertuples(index=False):
        if not isinstance(row.id, str) or not row.id.strip() or not isinstance(row.name, str) or not row.name.strip():
            reject("invalid_node_record", str(row.id))
            continue
        ids[row.id] = row
        try:
            payload = json.loads(row.properties_json)
            if not isinstance(payload, dict):
                raise ValueError()
            props[row.id] = payload
        except (ValueError, TypeError):
            reject("invalid_properties_json", row.id)
            continue
        label_set = set(row.labels.split(";")) if isinstance(row.labels, str) else set()
        labels[row.id] = label_set
        if "record_types" not in disabled:
            kinds = label_set & PRIMARY_TYPES
            if len(kinds) != 1 or "Entity" not in label_set or label_set - LABELS:
                reject("invalid_node_type", row.id)
                continue
            kind = next(iter(kinds))
            for field in REQUIRED_STRING_PROPERTIES[kind]:
                if not isinstance(payload.get(field), str) or not payload[field].strip():
                    reject("invalid_property_type", f"{row.id}.{field}")
            for field in EXECUTION_CONTEXT_FIELDS:
                if field in payload and not isinstance(payload[field], str):
                    reject("invalid_execution_context_type", f"{row.id}.{field}")
            if kind == "FormulaParameter":
                value = payload.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    reject("invalid_numeric_type", f"{row.id}.value")
                subtype = payload.get("parameter_kind")
                if subtype == "threshold":
                    if not {"Threshold"}.issubset(label_set) or not isinstance(payload.get("policy"), str) or not isinstance(payload.get("scope"), str):
                        reject("invalid_parameter_subtype", row.id)
                    if isinstance(payload.get("train_windows"), bool) or not isinstance(payload.get("train_windows"), int) or payload["train_windows"] <= 0:
                        reject("invalid_training_count_type", row.id)
                elif subtype == "runtime_parameter":
                    if "RuntimeParameter" not in label_set or not isinstance(payload.get("parameter_role"), str):
                        reject("invalid_parameter_subtype", row.id)
                elif subtype == "numeric_tolerance":
                    if "NumericTolerance" not in label_set:
                        reject("invalid_parameter_subtype", row.id)
                else:
                    reject("invalid_parameter_kind", row.id)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    if edges.duplicated(subset=["source", "relation", "target"]).any():
        reject("duplicate_relationship", "logical source/type/target tuple")
    for row in edges.itertuples(index=False):
        outgoing[(row.source, row.relation)].append(row.target)
        incoming[(row.target, row.relation)].append(row.source)
        if row.source not in ids or row.target not in ids:
            reject("dangling_relationship", f"{row.source}/{row.relation}/{row.target}")
            continue
        if row.relation not in ENDPOINT_TYPES:
            reject("undeclared_relationship", str(row.relation))
            continue
        if "endpoint_types" not in disabled:
            source_type, target_type = ENDPOINT_TYPES[row.relation]
            if source_type not in labels.get(row.source, set()) or target_type not in labels.get(row.target, set()):
                reject("endpoint_type_mismatch", f"{row.source}/{row.relation}/{row.target}")
        try:
            if not isinstance(json.loads(row.properties_json), dict):
                raise ValueError()
        except (ValueError, TypeError):
            reject("invalid_relationship_properties", f"{row.source}/{row.relation}/{row.target}")
    if "requirement_bijection" not in disabled:
        for identifier, kind in labels.items():
            if "Requirement" in kind and len(outgoing[(identifier, "FORMALIZED_AS")]) != 1:
                reject("requirement_formula_cardinality", identifier)
            if "STLFormula" in kind and len(incoming[(identifier, "FORMALIZED_AS")]) != 1:
                reject("formula_requirement_cardinality", identifier)
    for binding_id, kind in labels.items():
        if "ParameterBinding" not in kind:
            continue
        owners = incoming[(binding_id, "HAS_PARAMETER_BINDING")]
        binding = props.get(binding_id, {})
        if "binding_ownership" not in disabled:
            if len(owners) != 1:
                reject("binding_owner_cardinality", binding_id)
            elif binding.get("formula_id") != owners[0]:
                reject("binding_owner_identity", binding_id)
        if "context_consistency" not in disabled and len(owners) == 1:
            formula_id = owners[0]
            signals = outgoing[(formula_id, "READS_SIGNAL")]
            parameters = outgoing[(binding_id, "BINDS_PARAMETER")]
            if len(signals) == 1 and len(parameters) == 1:
                participants = (formula_id, signals[0], parameters[0])
                for field in EXECUTION_CONTEXT_FIELDS:
                    values = [(identifier, known_context(props.get(identifier, {}).get(field))) for identifier in participants]
                    known = {value for _, value in values if value is not None}
                    if len(known) > 1:
                        reject("known_execution_context_conflict", f"{binding_id}.{field}")
                    if all(value is not None for _, value in values) and len(known) == 1:
                        compared_context += 1
                    else:
                        missing_context += 1
    if not errors:
        try:
            validate_variant(nodes, edges)
        except (AssertionError, KeyError, IndexError, TypeError, ValueError) as error:
            reject("historical_constraint_failure", str(error))
    return {
        "accepted": not errors,
        "errors": errors,
        "execution_context_fully_known_equal_checks": compared_context,
        "execution_context_unknown_or_not_applicable_checks": missing_context,
        "interpretation": "Record-chain integrity and absence of declared known conflicts do not prove deployment applicability or physical calibration.",
    }
