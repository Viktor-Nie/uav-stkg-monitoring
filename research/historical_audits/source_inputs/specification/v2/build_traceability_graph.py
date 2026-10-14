"""Build the v2 formula--parameter-role--monitor traceability export.

Unlike the frozen v1 graph, a formula is not considered traceable merely
because its signal has candidate thresholds. Each parameter slot is represented
by a ParameterBinding node with an exact target, role, source and applicability
context. The output remains CSV-only; it does not claim a Neo4j database write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


V2 = Path(__file__).resolve().parent
SPEC = V2.parent
OUT = V2 / "results" / "traceability_graph"

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


def node(identifier: str, labels: str, name: str, **properties: object) -> dict[str, str]:
    return {
        "id": identifier,
        "labels": labels,
        "name": name,
        "properties_json": json.dumps(properties, ensure_ascii=False, sort_keys=True),
    }


def edge(source: str, relation: str, target: str, **properties: object) -> dict[str, str]:
    return {
        "source": source,
        "relation": relation,
        "target": target,
        "properties_json": json.dumps(properties, ensure_ascii=False, sort_keys=True),
    }


def parameterized_formula(template_id: str, signal_id: str) -> str:
    if template_id == "invariant_upper":
        return f"G[0,T]({signal_id} <= upper_bound)"
    if template_id == "bounded_response":
        return f"G[0,T](({signal_id} > trigger_upper) -> F[0,deadline_seconds]({signal_id} <= recovery_upper))"
    raise ValueError(f"unsupported v2 template: {template_id}")


def expected_roles(template_id: str) -> tuple[str, ...]:
    if template_id == "invariant_upper":
        return ("upper_bound", "value_epsilon")
    if template_id == "bounded_response":
        return ("trigger_upper", "recovery_upper", "deadline_seconds", "dwell_seconds", "value_epsilon")
    raise ValueError(f"unsupported v2 template: {template_id}")


def threshold_for(thresholds: pd.DataFrame, signal_id: str, percentile: int) -> pd.Series:
    policy = f"HIL_train_quantile_{percentile}"
    found = thresholds[(thresholds["signal_id"] == signal_id) & (thresholds["policy"] == policy)]
    if len(found) != 1:
        raise ValueError(f"expected one {policy} threshold for {signal_id}, found {len(found)}")
    return found.iloc[0]


def context_properties(row: pd.Series) -> dict[str, object]:
    return {field: str(row[field]) for field in CONTEXT_FIELDS}


def build_export(output_dir: Path = OUT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairs = pd.read_csv(SPEC / "data" / "nl_stl_pairs.csv", encoding="utf-8-sig")
    thresholds = pd.read_csv(SPEC / "results" / "research_monitor_thresholds.csv", encoding="utf-8-sig")
    signal_context = pd.read_csv(V2 / "data" / "signal_context_v2.csv", encoding="utf-8-sig")
    runtime_parameters = pd.read_csv(V2 / "data" / "monitor_runtime_parameters_v2.csv", encoding="utf-8-sig")
    templates = pd.read_csv(SPEC / "data" / "stl_templates.csv", encoding="utf-8-sig")

    if set(pairs["template_id"]) - {"invariant_upper", "bounded_response"}:
        raise ValueError("pairs contain a template outside the v2 fragment")
    if signal_context["signal_id"].duplicated().any() or runtime_parameters["parameter_id"].duplicated().any():
        raise ValueError("v2 context configuration has duplicate identifiers")

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    flat_bindings: list[dict[str, object]] = []

    for signal in signal_context.itertuples(index=False):
        props = signal._asdict()
        nodes.append(node(f"signal:{signal.signal_id}", "Entity;Signal", signal.signal_id, **props))

    for template in templates.itertuples(index=False):
        if template.template_id not in {"invariant_upper", "bounded_response"}:
            continue
        monitor_id = f"monitor:sampled_point_{template.template_id}_v2"
        nodes.append(node(
            f"template:{template.template_id}",
            "Entity;STLTemplate",
            template.template_id,
            stl_shape=template.stl_shape,
            v2_parameterized_shape=(
                "G[0,T](x <= upper_bound)"
                if template.template_id == "invariant_upper"
                else "G[0,T]((x > trigger_upper) -> F[0,deadline_seconds](x <= recovery_upper))"
            ),
        ))
        nodes.append(node(
            monitor_id,
            "Entity;RuntimeMonitor",
            monitor_id.removeprefix("monitor:"),
            implementation=(
                "specification/v2/sampled_monitor.py:monitor_invariant"
                if template.template_id == "invariant_upper"
                else "specification/v2/sampled_monitor.py:monitor_bounded_response"
            ),
            trigger_policy=("not_applicable" if template.template_id == "invariant_upper" else "level_triggered"),
            finite_trace_verdicts="satisfied|violated|inconclusive_end_of_trace|rejected_input_contract",
            supported_input_profiles="fixed_rate_sampled_point_v2|native_event_time_single_signal_v1",
            semantic_version="v2.1",
        ))
        edges.append(edge(f"template:{template.template_id}", "IMPLEMENTED_BY", monitor_id))

    threshold_context = {
        "source_type": "derived_statistical_reference",
        "source_reference": "specification/results/research_monitor_thresholds.csv",
        "source_version": "v1_frozen_2026-08-09",
        "adoption_status": "research_reference_not_engineering_safety_limit",
        "platform_context": "RflyMAD HIL cached causal-window features",
        "vehicle_context": "not_recorded_in_threshold_export",
        "flight_mode_context": "not_recorded_in_threshold_export",
        "firmware_context": "not_recorded_in_threshold_export",
        "applicability_status": "not_deployment_calibrated",
        "binding_version": "v2.0",
    }
    for threshold in thresholds.itertuples(index=False):
        nodes.append(node(
            f"parameter:{threshold.threshold_id}",
            "Entity;FormulaParameter;Threshold",
            threshold.threshold_id,
            parameter_kind="threshold",
            value=float(threshold.value),
            unit=threshold.unit,
            policy=threshold.policy,
            scope=threshold.scope,
            train_windows=int(threshold.train_windows),
            **threshold_context,
        ))

    for parameter in runtime_parameters.itertuples(index=False):
        props = parameter._asdict()
        nodes.append(node(
            f"parameter:{parameter.parameter_id}",
            "Entity;FormulaParameter;RuntimeParameter",
            parameter.parameter_id,
            parameter_kind="runtime_parameter",
            **props,
        ))

    # Epsilon has the same physical unit as the signal. It is a declared
    # numerical semantic parameter, not a safety margin inferred from data.
    for signal in signal_context.itertuples(index=False):
        epsilon_id = f"zero_epsilon_{signal.signal_id}"
        nodes.append(node(
            f"parameter:{epsilon_id}",
            "Entity;FormulaParameter;NumericTolerance",
            epsilon_id,
            parameter_kind="numeric_tolerance",
            value=0.0,
            unit=signal.unit,
            source_type="semantic_default",
            source_reference="docs/重构工作台/01_采样数据STL语义与监测契约.md",
            source_version="v2.0",
            adoption_status="research_definition",
            platform_context="sampled-point semantic definition",
            vehicle_context="not_applicable",
            flight_mode_context="not_applicable",
            firmware_context="not_applicable",
            applicability_status="not_deployment-calibrated",
            binding_version="v2.0",
        ))

    runtime_by_role = runtime_parameters.set_index("parameter_role")
    signal_by_id = signal_context.set_index("signal_id")
    for pair in pairs.itertuples(index=False):
        signal_id = next(signal for signal in signal_by_id.index if signal in pair.stl)
        formula_id = f"formula:{pair.id}"
        requirement_id = f"requirement:{pair.id}"
        monitor_id = f"monitor:sampled_point_{pair.template_id}_v2"
        nodes.extend([
            node(requirement_id, "Entity;Requirement", pair.id, text=pair.nl, split=pair.split),
            node(
                formula_id,
                "Entity;STLFormula",
                pair.id,
                legacy_formula=pair.stl,
                parameterized_formula=parameterized_formula(pair.template_id, signal_id),
                template_id=pair.template_id,
                semantic_version="v2.1",
            ),
        ])
        edges.extend([
            edge(requirement_id, "FORMALIZED_AS", formula_id),
            edge(formula_id, "USES_TEMPLATE", f"template:{pair.template_id}"),
            edge(formula_id, "EXECUTED_BY", monitor_id),
            edge(formula_id, "READS_SIGNAL", f"signal:{signal_id}"),
        ])

        binding_targets = {
            "upper_bound": f"parameter:{threshold_for(thresholds, signal_id, 99).threshold_id}",
            "trigger_upper": f"parameter:{threshold_for(thresholds, signal_id, 99).threshold_id}",
            "recovery_upper": f"parameter:{threshold_for(thresholds, signal_id, 95).threshold_id}",
            "deadline_seconds": f"parameter:{runtime_by_role.loc['deadline_seconds'].parameter_id}",
            "dwell_seconds": f"parameter:{runtime_by_role.loc['dwell_seconds'].parameter_id}",
            "value_epsilon": f"parameter:zero_epsilon_{signal_id}",
        }
        for role in expected_roles(pair.template_id):
            binding_id = f"binding:{pair.id}:{role}"
            parameter_id = binding_targets[role]
            nodes.append(node(
                binding_id,
                "Entity;ParameterBinding",
                binding_id.removeprefix("binding:"),
                formula_id=formula_id,
                role=role,
                parameter_id=parameter_id,
                signal_id=signal_id,
                binding_version="v2.0",
            ))
            edges.extend([
                edge(formula_id, "HAS_PARAMETER_BINDING", binding_id, role=role),
                edge(binding_id, "BINDS_PARAMETER", parameter_id),
                edge(binding_id, "APPLIES_TO_SIGNAL", f"signal:{signal_id}"),
            ])
            parameter_properties = json.loads(next(item["properties_json"] for item in nodes if item["id"] == parameter_id))
            flat_bindings.append({
                "binding_id": binding_id.removeprefix("binding:"),
                "formula_id": pair.id,
                "template_id": pair.template_id,
                "monitor_id": monitor_id.removeprefix("monitor:"),
                "signal_id": signal_id,
                "role": role,
                "parameter_id": parameter_id.removeprefix("parameter:"),
                "value": parameter_properties["value"],
                "unit": parameter_properties["unit"],
                **{field: parameter_properties[field] for field in CONTEXT_FIELDS},
            })

    node_frame = pd.DataFrame(nodes).drop_duplicates("id").sort_values("id").reset_index(drop=True)
    edge_frame = pd.DataFrame(edges).drop_duplicates().sort_values(["source", "relation", "target"]).reset_index(drop=True)
    binding_frame = pd.DataFrame(flat_bindings).sort_values(["formula_id", "role"]).reset_index(drop=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    node_frame.to_csv(output_dir / "nodes.csv", index=False, encoding="utf-8-sig")
    edge_frame.to_csv(output_dir / "relationships.csv", index=False, encoding="utf-8-sig")
    binding_frame.to_csv(output_dir / "formula_parameter_bindings.csv", index=False, encoding="utf-8-sig")
    return node_frame, edge_frame, binding_frame


def main() -> None:
    nodes, edges, bindings = build_export()
    print(f"wrote {len(nodes)} nodes, {len(edges)} relationships and {len(bindings)} exact parameter bindings")


if __name__ == "__main__":
    main()
