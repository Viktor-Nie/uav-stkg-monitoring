"""Unchanged historical validator functions, extracted for v33 regression.

The source experiment is not rerun or rewritten. This standalone reference
retains its original predicates; provenance is in frozen_reference_provenance.json.
"""
from __future__ import annotations
import json
import math
import re
import pandas as pd

CONTEXT_FIELDS = (
    "source_type", "source_reference", "source_version", "adoption_status",
    "platform_context", "vehicle_context", "flight_mode_context",
    "firmware_context", "applicability_status", "binding_version",
)

def expected_roles(template_id: str) -> tuple[str, ...]:
    if template_id == "invariant_upper":
        return ("upper_bound", "value_epsilon")
    if template_id == "bounded_response":
        return ("trigger_upper", "recovery_upper", "deadline_seconds", "dwell_seconds", "value_epsilon")
    raise ValueError(f"unsupported template: {template_id}")

def properties(nodes: pd.DataFrame) -> dict[str, dict[str, object]]:
    return {
        str(row.id): json.loads(str(row.properties_json))
        for row in nodes.itertuples(index=False)
    }

def single_target(edges: pd.DataFrame, source: str, relation: str) -> str:
    targets = edges.loc[
        edges["source"].eq(source) & edges["relation"].eq(relation), "target"
    ].tolist()
    if len(targets) != 1:
        raise AssertionError(f"{source} requires exactly one {relation} edge")
    return str(targets[0])

def parameterized_formula_skeleton(template_id: str, signal_id: str) -> str:
    """Reconstruct the exact supported graph formula skeleton from its descriptor."""

    if template_id == "invariant_upper":
        return f"G[0,T]({signal_id} <= upper_bound)"
    if template_id == "bounded_response":
        return (
            f"G[0,T](({signal_id} > trigger_upper) -> "
            f"F[0,deadline_seconds]({signal_id} <= recovery_upper))"
        )
    raise ValueError(f"unsupported template for formula skeleton: {template_id}")

def canonical_formula_serialization(formula: str) -> str:
    """Canonicalize only serialization-level whitespace for an exact comparison."""

    return re.sub(r"\s+", "", str(formula))

def validate_variant(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    disabled: frozenset[str] = frozenset(),
) -> None:
    """Validate the six selectively ablated graph safeguard modules."""

    if nodes["id"].duplicated().any() or edges.duplicated().any():
        raise AssertionError("duplicate graph records")
    props = properties(nodes)
    ids = set(nodes["id"])
    formulas = sorted(item for item in ids if str(item).startswith("formula:"))

    for formula_id in formulas:
        short_id = formula_id.removeprefix("formula:")
        fprops = props[formula_id]
        template_id = str(fprops["template_id"])
        signal_id = single_target(edges, formula_id, "READS_SIGNAL")
        monitor_id = single_target(edges, formula_id, "EXECUTED_BY")
        expected_monitor = f"monitor:sampled_point_{template_id}_v2"
        if "topology_and_cardinality" not in disabled:
            requirement_id = f"requirement:{short_id}"
            if single_target(edges, requirement_id, "FORMALIZED_AS") != formula_id:
                raise AssertionError("requirement/formula link mismatch")
            template_node = single_target(edges, formula_id, "USES_TEMPLATE")
            if template_node != f"template:{template_id}":
                raise AssertionError("formula/template link mismatch")
            if single_target(edges, template_node, "IMPLEMENTED_BY") != expected_monitor:
                raise AssertionError("template/monitor implementation link mismatch")
        if "monitor_compatibility_and_profiles" not in disabled:
            if monitor_id != expected_monitor:
                raise AssertionError("monitor/template mismatch")
            profiles = str(props[monitor_id].get("supported_input_profiles", ""))
            for required_profile in (
                "fixed_rate_sampled_point_v2",
                "native_event_time_single_signal_v1",
            ):
                if required_profile not in profiles:
                    raise AssertionError("monitor input profile missing")
        if "formula_signal_alignment" not in disabled:
            signal_name = signal_id.removeprefix("signal:")
            stored_formula = str(fprops.get("parameterized_formula", ""))
            reconstructed_formula = parameterized_formula_skeleton(
                template_id, signal_name
            )
            if canonical_formula_serialization(
                stored_formula
            ) != canonical_formula_serialization(reconstructed_formula):
                raise AssertionError(
                    "stored parameterized formula disagrees with descriptor skeleton"
                )

        binding_ids = edges.loc[
            edges["source"].eq(formula_id)
            & edges["relation"].eq("HAS_PARAMETER_BINDING"),
            "target",
        ].tolist()
        roles = [str(props[binding_id]["role"]) for binding_id in binding_ids]
        if "topology_and_cardinality" not in disabled:
            if set(roles) != set(expected_roles(template_id)) or len(roles) != len(
                expected_roles(template_id)
            ):
                raise AssertionError("incomplete or duplicate role set")

        signal_unit = str(props[signal_id]["unit"])
        role_to_parameter: dict[str, dict[str, object]] = {}
        for binding_id in binding_ids:
            binding = props[binding_id]
            role = str(binding["role"])
            parameter_id = single_target(edges, binding_id, "BINDS_PARAMETER")
            applied_signal = single_target(edges, binding_id, "APPLIES_TO_SIGNAL")
            if parameter_id not in ids or applied_signal not in ids:
                raise AssertionError("dangling binding target")
            if "exact_binding_identity" not in disabled:
                if (
                    str(binding["formula_id"]) != formula_id
                    or str(binding["signal_id"]) != signal_id.removeprefix("signal:")
                    or str(binding["parameter_id"]) != parameter_id
                    or applied_signal != signal_id
                ):
                    raise AssertionError("binding/signal mismatch")
            parameter = props[parameter_id]
            if "provenance_context" not in disabled:
                if any(not str(parameter.get(field, "")).strip() for field in CONTEXT_FIELDS):
                    raise AssertionError("missing provenance/context field")
            role_to_parameter[role] = parameter

        if "semantic_typing_and_policy" not in disabled:
            for role in ("upper_bound", "trigger_upper", "recovery_upper", "value_epsilon"):
                if role in role_to_parameter and str(role_to_parameter[role]["unit"]) != signal_unit:
                    raise AssertionError("signal/parameter unit mismatch")
            for role in ("deadline_seconds", "dwell_seconds"):
                if role in role_to_parameter and str(role_to_parameter[role]["unit"]) != "s":
                    raise AssertionError("temporal role unit mismatch")

            for role, parameter in role_to_parameter.items():
                value = float(parameter["value"])
                if not math.isfinite(value):
                    raise AssertionError("non-finite parameter value")
                if role in ("upper_bound", "trigger_upper", "recovery_upper"):
                    if parameter.get("parameter_kind") != "threshold":
                        raise AssertionError("threshold role bound to non-threshold")
                    if str(parameter.get("signal_scope")) != signal_id.removeprefix("signal:"):
                        raise AssertionError("parameter belongs to another signal")
                    expected_policy = (
                        "HIL_train_quantile_95"
                        if role == "recovery_upper"
                        else "HIL_train_quantile_99"
                    )
                    if str(parameter.get("policy")) != expected_policy:
                        raise AssertionError("threshold policy incompatible with formula role")
                elif role in ("deadline_seconds", "dwell_seconds"):
                    if str(parameter.get("parameter_role")) != role:
                        raise AssertionError("runtime parameter role mismatch")
                elif role == "value_epsilon":
                    if (
                        parameter.get("parameter_kind") != "numeric_tolerance"
                        or str(parameter.get("signal_scope"))
                        != signal_id.removeprefix("signal:")
                    ):
                        raise AssertionError("numeric tolerance signal scope mismatch")

        if "semantic_typing_and_policy" not in disabled:
            if template_id == "bounded_response":
                required_operands = (
                    "trigger_upper",
                    "recovery_upper",
                    "deadline_seconds",
                    "dwell_seconds",
                )
                missing_operands = [
                    role for role in required_operands if role not in role_to_parameter
                ]
                if missing_operands:
                    raise AssertionError(
                        "missing semantic operand: " + ",".join(missing_operands)
                    )
                trigger = float(role_to_parameter["trigger_upper"]["value"])
                recovery = float(role_to_parameter["recovery_upper"]["value"])
                deadline = float(role_to_parameter["deadline_seconds"]["value"])
                dwell = float(role_to_parameter["dwell_seconds"]["value"])
                if recovery > trigger:
                    raise AssertionError("recovery exceeds trigger")
                if deadline <= 0 or dwell < 0 or dwell >= deadline:
                    raise AssertionError("deadline/dwell domain constraint violated")
            epsilon = role_to_parameter.get("value_epsilon")
            if epsilon is None or float(epsilon["value"]) != 0.0:
                raise AssertionError("invalid value tolerance")

def validate_flat_binding_export(
    nodes: pd.DataFrame, edges: pd.DataFrame, bindings: pd.DataFrame
) -> None:
    """Cross-check the flat execution table against graph nodes and edges."""

    props = properties(nodes)
    parameter_fields = (
        "value",
        "unit",
        "source_type",
        "source_reference",
        "source_version",
        "adoption_status",
        "platform_context",
        "vehicle_context",
        "flight_mode_context",
        "firmware_context",
        "applicability_status",
    )
    reconstructed: list[dict[str, object]] = []
    binding_nodes = sorted(
        node_id for node_id in props if node_id.startswith("binding:")
    )
    for binding_node in binding_nodes:
        binding = props[binding_node]
        formula_node = str(binding["formula_id"])
        parameter_node = single_target(edges, binding_node, "BINDS_PARAMETER")
        signal_node = single_target(edges, binding_node, "APPLIES_TO_SIGNAL")
        formula = props[formula_node]
        parameter = props[parameter_node]
        monitor_node = single_target(edges, formula_node, "EXECUTED_BY")
        record: dict[str, object] = {
            "binding_id": binding_node.removeprefix("binding:"),
            "formula_id": formula_node.removeprefix("formula:"),
            "template_id": str(formula["template_id"]),
            "monitor_id": monitor_node.removeprefix("monitor:"),
            "signal_id": signal_node.removeprefix("signal:"),
            "role": str(binding["role"]),
            "parameter_id": parameter_node.removeprefix("parameter:"),
            "binding_version": str(binding["binding_version"]),
        }
        record.update({field: parameter[field] for field in parameter_fields})
        reconstructed.append(record)

    columns = list(bindings.columns)
    graph_frame = pd.DataFrame(reconstructed)[columns].sort_values("binding_id").reset_index(drop=True)
    flat_frame = bindings[columns].sort_values("binding_id").reset_index(drop=True)
    if graph_frame.shape != flat_frame.shape:
        raise AssertionError("flat binding export shape differs from graph traversal")
    for column in columns:
        if column == "value":
            equal = pd.to_numeric(graph_frame[column]).equals(pd.to_numeric(flat_frame[column]))
        else:
            equal = graph_frame[column].astype(str).equals(flat_frame[column].astype(str))
        if not equal:
            raise AssertionError(f"flat binding export differs in column {column}")
