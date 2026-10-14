"""Frozen graph integrity constraints and targeted component experiments."""
from __future__ import annotations

import json
import math
import re
from collections import Counter

import pandas as pd

CONTEXT_FIELDS = (
    "source_type",
    "source_reference",
    "source_version",
    "adoption_status",
    "platform_context",
    "vehicle_context",
    "flight_mode_context",
    "firmware_context",
    "applicability_status",
    "binding_version",
)

def expected_roles(template_id: str) -> tuple[str, ...]:
    if template_id == "invariant_upper":
        return ("upper_bound", "value_epsilon")
    if template_id == "bounded_response":
        return ("trigger_upper", "recovery_upper", "deadline_seconds", "dwell_seconds", "value_epsilon")
    raise ValueError(f"unsupported v2 template: {template_id}")

MODULES = (
    "topology_and_cardinality",
    "exact_binding_identity",
    "semantic_typing_and_policy",
    "monitor_compatibility_and_profiles",
    "provenance_context",
    "formula_signal_alignment",
)

MUTATION_TO_MODULE = {
    "requirement_formula_link": "topology_and_cardinality",
    "template_implementation_link": "topology_and_cardinality",
    "role_completeness": "topology_and_cardinality",
    "binding_parameter_identity": "exact_binding_identity",
    "signal_consistency": "exact_binding_identity",
    "unit_compatibility": "semantic_typing_and_policy",
    "parameter_signal_scope": "semantic_typing_and_policy",
    "role_semantics": "semantic_typing_and_policy",
    "finite_numeric_value": "semantic_typing_and_policy",
    "monitor_compatibility": "monitor_compatibility_and_profiles",
    "monitor_input_profiles": "monitor_compatibility_and_profiles",
    "provenance_context": "provenance_context",
    "formula_signal_alignment": "formula_signal_alignment",
}

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

def replace_properties(
    nodes: pd.DataFrame, node_id: str, **changes: object
) -> pd.DataFrame:
    mutated = nodes.copy()
    index = mutated.index[mutated["id"].eq(node_id)]
    if len(index) != 1:
        raise AssertionError(f"missing node {node_id}")
    item = int(index[0])
    payload = json.loads(str(mutated.at[item, "properties_json"]))
    payload.update(changes)
    mutated.at[item, "properties_json"] = json.dumps(
        payload, ensure_ascii=False, sort_keys=True
    )
    return mutated

def graph_mutations(
    nodes: pd.DataFrame, edges: pd.DataFrame
) -> list[tuple[str, str, pd.DataFrame, pd.DataFrame]]:
    props = properties(nodes)
    formula_ids = sorted(item for item in nodes["id"] if str(item).startswith("formula:"))
    signal_ids = sorted(item for item in nodes["id"] if str(item).startswith("signal:"))
    mutations: list[tuple[str, str, pd.DataFrame, pd.DataFrame]] = []

    def retarget_binding(
        base_nodes: pd.DataFrame,
        base_edges: pd.DataFrame,
        binding_id: str,
        parameter_id: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        changed_nodes = replace_properties(base_nodes, binding_id, parameter_id=parameter_id)
        changed_edges = base_edges.copy()
        target_index = changed_edges.index[
            changed_edges["source"].eq(binding_id)
            & changed_edges["relation"].eq("BINDS_PARAMETER")
        ]
        changed_edges.loc[target_index, "target"] = parameter_id
        return changed_nodes, changed_edges

    # Topology mutation: each template loses its unique implementation edge once.
    for template_id in ("invariant_upper", "bounded_response"):
        template_node = f"template:{template_id}"
        implementation_edges = edges.drop(
            edges.index[
                edges["source"].eq(template_node)
                & edges["relation"].eq("IMPLEMENTED_BY")
            ]
        ).reset_index(drop=True)
        mutations.append(
            (
                "template_implementation_link",
                template_id,
                nodes.copy(),
                implementation_edges,
            )
        )

    # Monitor-profile mutation: each monitor loses the fixed-rate profile once.
    for monitor_id in sorted(
        item for item in nodes["id"] if str(item).startswith("monitor:")
    ):
        profile_nodes = replace_properties(
            nodes,
            monitor_id,
            supported_input_profiles="native_event_time_single_signal_v1",
        )
        mutations.append(
            ("monitor_input_profiles", monitor_id, profile_nodes, edges.copy())
        )

    # Parameter-level mutations are applied once per distinct parameter node.
    # Mutate only parameters that participate in at least one executable
    # binding.  The clean export intentionally retains height_p95_train for
    # provenance, but no current formula binds it; corrupting an unreachable
    # catalogue row cannot test an executable-configuration safeguard.
    all_parameter_ids = sorted(
        item for item in nodes["id"] if str(item).startswith("parameter:")
    )
    parameter_ids = sorted(
        set(
            edges.loc[
                edges["relation"].eq("BINDS_PARAMETER"), "target"
            ].astype(str)
        )
    )
    for parameter_id in parameter_ids:
        unit_nodes = replace_properties(nodes, parameter_id, unit="kg")
        mutations.append(("unit_compatibility", parameter_id, unit_nodes, edges.copy()))
        finite_nodes = replace_properties(nodes, parameter_id, value=float("nan"))
        mutations.append(
            ("finite_numeric_value", parameter_id, finite_nodes, edges.copy())
        )
        provenance_nodes = replace_properties(nodes, parameter_id, source_reference="")
        mutations.append(
            ("provenance_context", parameter_id, provenance_nodes, edges.copy())
        )
        if str(props[parameter_id].get("signal_scope")) != "global":
            own_scope = str(props[parameter_id].get("signal_scope"))
            other_scope = next(
                item.removeprefix("signal:")
                for item in signal_ids
                if item.removeprefix("signal:") != own_scope
            )
            scope_nodes = replace_properties(
                nodes, parameter_id, signal_scope=other_scope
            )
            mutations.append(
                ("parameter_signal_scope", parameter_id, scope_nodes, edges.copy())
            )

    # Binding-level mutations exercise every one of the 84 role bindings.
    binding_ids_all = sorted(
        item for item in nodes["id"] if str(item).startswith("binding:")
    )
    for binding_id in binding_ids_all:
        parameter_id = single_target(edges, binding_id, "BINDS_PARAMETER")
        wrong_property_target = next(
            item for item in all_parameter_ids if item != parameter_id
        )
        identity_nodes = replace_properties(
            nodes, binding_id, parameter_id=wrong_property_target
        )
        mutations.append(
            ("binding_parameter_identity", binding_id, identity_nodes, edges.copy())
        )

        own_signal = single_target(edges, binding_id, "APPLIES_TO_SIGNAL")
        other_signal = next(item for item in signal_ids if item != own_signal)
        signal_edges = edges.copy()
        idx = signal_edges.index[
            signal_edges["source"].eq(binding_id)
            & signal_edges["relation"].eq("APPLIES_TO_SIGNAL")
        ]
        signal_edges.loc[idx, "target"] = other_signal
        mutations.append(
            ("signal_consistency", binding_id, nodes.copy(), signal_edges)
        )

    # Formula-level mutations exercise all 24 Requirement--Formula instances.
    for formula_id in formula_ids:
        short_id = formula_id.removeprefix("formula:")
        template_id = str(props[formula_id]["template_id"])
        own_signal = single_target(edges, formula_id, "READS_SIGNAL")
        binding_ids = edges.loc[
            edges["source"].eq(formula_id)
            & edges["relation"].eq("HAS_PARAMETER_BINDING"),
            "target",
        ].tolist()
        by_role = {str(props[b]["role"]): str(b) for b in binding_ids}

        requirement_id = f"requirement:{short_id}"
        requirement_edges = edges.drop(
            edges.index[
                edges["source"].eq(requirement_id)
                & edges["relation"].eq("FORMALIZED_AS")
            ]
        ).reset_index(drop=True)
        mutations.append(
            ("requirement_formula_link", short_id, nodes.copy(), requirement_edges)
        )

        removable_role = "dwell_seconds" if template_id == "bounded_response" else "upper_bound"
        removable_binding = by_role[removable_role]
        role_edges = edges.drop(
            edges.index[
                edges["source"].eq(formula_id)
                & edges["relation"].eq("HAS_PARAMETER_BINDING")
                & edges["target"].eq(removable_binding)
            ]
        ).reset_index(drop=True)
        mutations.append(("role_completeness", short_id, nodes.copy(), role_edges))

        value_role = "trigger_upper" if template_id == "bounded_response" else "upper_bound"
        value_binding = by_role[value_role]

        opposite_policy = (
            "HIL_train_quantile_95"
            if value_role in ("upper_bound", "trigger_upper")
            else "HIL_train_quantile_99"
        )
        semantic_target = next(
            node_id
            for node_id, payload in props.items()
            if node_id.startswith("parameter:")
            and payload.get("parameter_kind") == "threshold"
            and payload.get("signal_scope") == own_signal.removeprefix("signal:")
            and payload.get("policy") == opposite_policy
        )
        semantic_nodes, semantic_edges = retarget_binding(
            nodes, edges, value_binding, semantic_target
        )
        mutations.append(
            ("role_semantics", short_id, semantic_nodes, semantic_edges)
        )

        other_monitor = (
            "monitor:sampled_point_invariant_upper_v2"
            if template_id == "bounded_response"
            else "monitor:sampled_point_bounded_response_v2"
        )
        monitor_edges = edges.copy()
        idx = monitor_edges.index[
            monitor_edges["source"].eq(formula_id)
            & monitor_edges["relation"].eq("EXECUTED_BY")
        ]
        monitor_edges.loc[idx, "target"] = other_monitor
        mutations.append(("monitor_compatibility", short_id, nodes.copy(), monitor_edges))

        other_signal = next(item for item in signal_ids if item != own_signal)
        formula_text = str(props[formula_id]["parameterized_formula"])
        misaligned_nodes = replace_properties(
            nodes,
            formula_id,
            parameterized_formula=formula_text.replace(
                own_signal.removeprefix("signal:"),
                other_signal.removeprefix("signal:"),
            ),
        )
        mutations.append(
            ("formula_signal_alignment", short_id, misaligned_nodes, edges.copy())
        )

    return mutations

def run_mutation_ablation(
    nodes: pd.DataFrame, edges: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mutations = graph_mutations(nodes, edges)
    variants = [("full_validator", frozenset())]
    variants.extend((f"without_{module}", frozenset({module})) for module in MODULES)
    variants.append(("schema_only_all_six_modules_removed", frozenset(MODULES)))

    detail: list[dict[str, object]] = []
    for variant, disabled in variants:
        for mutation, mutation_target, mutant_nodes, mutant_edges in mutations:
            try:
                validate_variant(mutant_nodes, mutant_edges, disabled)
                accepted = True
                rejection_reason = "not_rejected"
            except (AssertionError, KeyError, ValueError) as exc:
                accepted = False
                rejection_reason = f"{type(exc).__name__}: {exc}"
            detail.append(
                {
                    "validator_variant": variant,
                    "disabled_check": "none" if not disabled else ";".join(sorted(disabled)),
                    "mutation_type": mutation,
                    "mutation_module": MUTATION_TO_MODULE[mutation],
                    "mutation_target": mutation_target,
                    "mutant_accepted": accepted,
                    "rejection_reason": rejection_reason,
                }
            )

    detail_frame = pd.DataFrame(detail)
    summary = (
        detail_frame.groupby(["validator_variant", "disabled_check"], as_index=False)
        .agg(
            accepted_mutants=("mutant_accepted", "sum"),
            total_mutants=("mutant_accepted", "size"),
        )
        .sort_values("validator_variant")
        .reset_index(drop=True)
    )
    summary["mutation_rejection_rate"] = 1.0 - (
        summary["accepted_mutants"] / summary["total_mutants"]
    )
    return detail_frame, summary

def compatible_assignment_counts(
    nodes: pd.DataFrame, edges: pd.DataFrame
) -> pd.DataFrame:
    props = properties(nodes)
    parameters = {
        node_id: payload
        for node_id, payload in props.items()
        if node_id.startswith("parameter:")
    }
    rows: list[dict[str, object]] = []
    formulas = sorted(item for item in props if item.startswith("formula:"))
    for formula_id in formulas:
        fprops = props[formula_id]
        template_id = str(fprops["template_id"])
        signal_id = single_target(edges, formula_id, "READS_SIGNAL")
        unit = str(props[signal_id]["unit"])
        thresholds = [
            payload
            for payload in parameters.values()
            if payload.get("parameter_kind") == "threshold" and str(payload.get("unit")) == unit
        ]
        epsilons = [
            payload
            for payload in parameters.values()
            if payload.get("parameter_kind") == "numeric_tolerance"
            and str(payload.get("unit")) == unit
        ]
        runtimes = [
            payload
            for payload in parameters.values()
            if payload.get("parameter_kind") == "runtime_parameter"
            and str(payload.get("unit")) == "s"
        ]
        if template_id == "invariant_upper":
            candidate_count = len(thresholds) * len(epsilons)
        else:
            ordered_threshold_pairs = sum(
                1
                for trigger in thresholds
                for recovery in thresholds
                if float(recovery["value"]) <= float(trigger["value"])
            )
            candidate_count = (
                ordered_threshold_pairs * len(runtimes) ** 2 * len(epsilons)
            )
        rows.append(
            {
                "formula_id": formula_id.removeprefix("formula:"),
                "template_id": template_id,
                "signal_id": signal_id.removeprefix("signal:"),
                "full_graph_candidate_configurations": 1,
                "without_parameter_binding_candidate_configurations": candidate_count,
                "unique_without_parameter_binding": candidate_count == 1,
            }
        )
    return pd.DataFrame(rows)
