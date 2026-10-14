"""Graph-bound v33 replay using the formal precision-aware monitor entry.

The frozen graph gate remains a separate acceptance step. This reader checks
unambiguous signal and parameter-role bindings when instantiating an accepted
export; it does not replace the full graph/source/schema verifier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

if __package__:
    from .sampled_data_contract import SamplingContract
    from .sampled_monitor import (
        BoundedResponseSpecification, InvariantSpecification,
        monitor_bounded_response, monitor_invariant,
    )
else:
    from sampled_data_contract import SamplingContract
    from sampled_monitor import (
        BoundedResponseSpecification, InvariantSpecification,
        monitor_bounded_response, monitor_invariant,
    )


OUT = Path(__file__).resolve().parents[3] / "data" / "graph"


def node_properties(graph_directory: Path | str = OUT) -> dict[str, dict[str, object]]:
    nodes = pd.read_csv(Path(graph_directory) / "nodes.csv", encoding="utf-8-sig")
    if nodes["id"].duplicated().any():
        raise ValueError("graph export contains duplicate node identifiers")
    return {str(row.id): json.loads(str(row.properties_json)) for row in nodes.itertuples(index=False)}


def parameter_values_for_formula(
    formula_id: str, graph_directory: Path | str = OUT,
) -> tuple[dict[str, object], str, str]:
    nodes = node_properties(graph_directory)
    edges = pd.read_csv(Path(graph_directory) / "relationships.csv", encoding="utf-8-sig")
    identifier = formula_id if formula_id.startswith("formula:") else "formula:" + formula_id
    formula = nodes[identifier]
    signal_nodes = edges[(edges["source"] == identifier) & (edges["relation"] == "READS_SIGNAL")]["target"].tolist()
    if len(signal_nodes) != 1:
        raise ValueError(f"{identifier} must have one signal after graph verification")
    bindings = edges[(edges["source"] == identifier) & (edges["relation"] == "HAS_PARAMETER_BINDING")]["target"].tolist()
    values = {}
    for binding_id in bindings:
        binding = nodes[str(binding_id)]
        targets = edges[(edges["source"] == binding_id) & (edges["relation"] == "BINDS_PARAMETER")]["target"].tolist()
        if len(targets) != 1:
            raise ValueError(f"{binding_id} has no exact parameter after graph verification")
        role = str(binding["role"])
        if role in values:
            raise ValueError(f"{identifier} has duplicate binding for {role}")
        values[role] = nodes[str(targets[0])]
    return values, str(formula["template_id"]), str(signal_nodes[0]).removeprefix("signal:")


def instantiate_formula(
    formula_id: str, graph_directory: Path | str = OUT,
) -> InvariantSpecification | BoundedResponseSpecification:
    values, template, signal = parameter_values_for_formula(formula_id, graph_directory)
    if template == "invariant_upper":
        roles = ("upper_bound", "value_epsilon")
        definition = InvariantSpecification
    elif template == "bounded_response":
        roles = ("trigger_upper", "recovery_upper", "deadline_seconds", "dwell_seconds", "value_epsilon")
        definition = BoundedResponseSpecification
    else:
        raise ValueError(f"unsupported template {template}")
    if set(values) != set(roles):
        raise ValueError(f"{formula_id} has unexpected role set")
    return definition(signal=signal, **{role: float(values[role]["value"]) for role in roles})


def monitor_formula_from_graph(
    trace: pd.DataFrame, formula_id: str,
    *, graph_directory: Path | str = OUT, contract=None,
):
    """Instantiate one accepted graph binding and return its definition/result."""
    definition = instantiate_formula(formula_id, graph_directory)
    function = monitor_invariant if isinstance(definition, InvariantSpecification) else monitor_bounded_response
    result = function(trace, definition, contract or SamplingContract(0.05, 0.05, 0.10))
    return definition, result


def _results(trace, formula_ids, graph_directory, contract):
    if formula_ids is None:
        formula_ids = sorted(key for key in node_properties(graph_directory) if key.startswith("formula:"))
    for formula_id in formula_ids:
        definition, result = monitor_formula_from_graph(trace, str(formula_id), graph_directory=graph_directory, contract=contract)
        yield str(formula_id).removeprefix("formula:"), definition, result


def replay_trace(
    trace: pd.DataFrame, formula_ids: list[str] | None = None,
    *, graph_directory: Path | str = OUT, contract=None,
) -> pd.DataFrame:
    rows = []
    for identifier, specification, result in _results(trace, formula_ids, graph_directory, contract):
        invariant = isinstance(specification, InvariantSpecification)
        rows.append({"formula_id": identifier,
                     "template_id": "invariant_upper" if invariant else "bounded_response",
                     "signal_id": specification.signal,
                     **{key: value for key, value in vars(specification).items() if key != "signal"},
                     "verdict": result.verdict.value, "sample_count": result.sampling_audit.sample_count,
                     "violating_sample_count": len(result.violating_sample_indices),
                     "created_obligation_count": len(result.created_obligations),
                     "recovered_obligation_count": len(result.recovered_obligation_ids),
                     "expired_obligation_count": len(result.expired_obligation_ids),
                     "pending_obligation_count": len(result.pending_obligation_ids),
                     "timestamp_input_mode": result.time_mapping.mode,
                     "time_origin_seconds_decimal": result.time_mapping.origin_seconds_decimal})
    return pd.DataFrame(rows).sort_values("formula_id").reset_index(drop=True)


def replay_event_ledger(
    trace: pd.DataFrame, formula_ids: list[str] | None = None,
    *, graph_directory: Path | str = OUT, contract=None,
) -> pd.DataFrame:
    rows = []
    for identifier, specification, result in _results(trace, formula_ids, graph_directory, contract):
        for event in result.absolute_event_records:
            rows.append({"formula_id": identifier,
                         "template_id": "invariant_upper" if isinstance(specification, InvariantSpecification) else "bounded_response",
                         "signal_id": specification.signal,
                         "runtime_specification": json.dumps(vars(specification), sort_keys=True),
                         "final_verdict": result.verdict.value, **event,
                         "timestamp_input_mode": result.time_mapping.mode})
    if not rows:
        return pd.DataFrame(columns=["formula_id", "observed_time_seconds", "observed_index", "event_type"])
    return pd.DataFrame(rows).sort_values(
        ["formula_id", "observed_time_seconds", "observed_index", "event_type"], kind="stable",
    ).reset_index(drop=True)
