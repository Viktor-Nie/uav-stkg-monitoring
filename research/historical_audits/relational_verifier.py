"""Frozen information-equivalent relational predicates, with portable imports."""
from __future__ import annotations
import json,math,re
from collections import defaultdict
import pandas as pd

CONTEXT_FIELDS = (
    "source_type", "source_reference", "source_version", "adoption_status",
    "platform_context", "vehicle_context", "flight_mode_context",
    "firmware_context", "applicability_status", "binding_version",
)


REQUIRED_ROLES = {
    "invariant_upper": {"upper_bound", "value_epsilon"},
    "bounded_response": {
        "trigger_upper", "recovery_upper", "deadline_seconds",
        "dwell_seconds", "value_epsilon",
    },
}


def project_tables(nodes: pd.DataFrame, edges: pd.DataFrame) -> dict[str, dict[str, dict]]:
    """Materialize typed relational rows with explicit foreign-key columns."""
    if nodes["id"].duplicated().any() or edges.duplicated().any():
        raise ValueError("duplicate source records")
    tables: dict[str, dict[str, dict]] = {
        name: {} for name in ("requirement", "formula", "signal", "template", "monitor", "parameter", "binding")
    }
    for row in nodes.itertuples(index=False):
        kind, _, identifier = str(row.id).partition(":")
        if kind not in tables or not identifier or identifier in tables[kind]:
            raise ValueError("unknown or duplicate typed row")
        tables[kind][identifier] = json.loads(str(row.properties_json))
    foreign_keys = {
        ("requirement", "FORMALIZED_AS"): ("formula_id", "formula"),
        ("formula", "USES_TEMPLATE"): ("template_fk", "template"),
        ("formula", "READS_SIGNAL"): ("signal_fk", "signal"),
        ("formula", "EXECUTED_BY"): ("monitor_fk", "monitor"),
        ("template", "IMPLEMENTED_BY"): ("monitor_fk", "monitor"),
        ("formula", "HAS_PARAMETER_BINDING"): ("owner_formula_fk", "binding"),
        ("binding", "BINDS_PARAMETER"): ("parameter_fk", "parameter"),
        ("binding", "APPLIES_TO_SIGNAL"): ("signal_fk", "signal"),
    }
    for row in edges.itertuples(index=False):
        source_kind, _, source_id = str(row.source).partition(":")
        target_kind, _, target_id = str(row.target).partition(":")
        rule = foreign_keys.get((source_kind, str(row.relation)))
        if rule is None or source_id not in tables[source_kind]:
            raise ValueError("unknown relation or source foreign key")
        column, expected_kind = rule
        if target_kind != expected_kind or target_id not in tables[target_kind]:
            raise ValueError("dangling or mis-typed foreign key")
        if str(row.relation) == "HAS_PARAMETER_BINDING":
            owner = tables["binding"][target_id]
            if column in owner:
                raise ValueError("binding has multiple formula owners")
            owner[column] = source_id
        else:
            source = tables[source_kind][source_id]
            if column in source:
                raise ValueError("duplicate foreign key")
            source[column] = target_id
    return tables


def validate_relational(tables: dict[str, dict[str, dict]]) -> None:
    """Check the same declared predicates using typed rows, not edge traversal."""
    requirements = tables["requirement"]
    formulas = tables["formula"]
    signals = tables["signal"]
    templates = tables["template"]
    monitors = tables["monitor"]
    parameters = tables["parameter"]
    bindings = tables["binding"]
    by_formula: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for binding_id, binding in bindings.items():
        if "owner_formula_fk" in binding:
            by_formula[binding["owner_formula_fk"]].append((binding_id, binding))

    for formula_id, formula in formulas.items():
        template_id = str(formula["template_id"])
        if template_id not in REQUIRED_ROLES:
            raise ValueError("unsupported template")
        if formula_id not in requirements or requirements[formula_id].get("formula_id") != formula_id:
            raise ValueError("missing requirement foreign key")
        if formula.get("template_fk") != template_id:
            raise ValueError("template foreign key mismatch")
        template = templates[template_id]
        expected_monitor = f"sampled_point_{template_id}_v2"
        if template.get("monitor_fk") != expected_monitor or formula.get("monitor_fk") != expected_monitor:
            raise ValueError("monitor foreign key mismatch")
        profiles = str(monitors[expected_monitor].get("supported_input_profiles", ""))
        if not all(item in profiles for item in ("fixed_rate_sampled_point_v2", "native_event_time_single_signal_v1")):
            raise ValueError("monitor profile missing")
        signal_id = formula.get("signal_fk")
        if signal_id not in signals:
            raise ValueError("missing signal foreign key")
        if template_id == "invariant_upper":
            skeleton = f"G[0,T]({signal_id} <= upper_bound)"
        else:
            skeleton = f"G[0,T](({signal_id} > trigger_upper) -> F[0,deadline_seconds]({signal_id} <= recovery_upper))"
        if re.sub(r"\s+", "", str(formula.get("parameterized_formula", ""))) != re.sub(r"\s+", "", skeleton):
            raise ValueError("formula serialization mismatch")

        owned = by_formula.get(formula_id, [])
        roles = [str(binding.get("role", "")) for _, binding in owned]
        if len(roles) != len(REQUIRED_ROLES[template_id]) or set(roles) != REQUIRED_ROLES[template_id]:
            raise ValueError("role cardinality mismatch")
        values: dict[str, float] = {}
        signal_unit = str(signals[signal_id]["unit"])
        for binding_id, binding in owned:
            parameter_id = binding.get("parameter_fk")
            if parameter_id not in parameters:
                raise ValueError("missing parameter foreign key")
            if (
                binding.get("formula_id") != f"formula:{formula_id}"
                or binding.get("signal_id") != signal_id
                or binding.get("parameter_id") != f"parameter:{parameter_id}"
                or binding.get("signal_fk") != signal_id
            ):
                raise ValueError(f"binding identity mismatch: {binding_id}")
            parameter = parameters[parameter_id]
            if any(not str(parameter.get(field, "")).strip() for field in CONTEXT_FIELDS):
                raise ValueError("parameter context missing")
            role = str(binding["role"])
            unit = str(parameter.get("unit", ""))
            if unit != ("s" if role in {"deadline_seconds", "dwell_seconds"} else signal_unit):
                raise ValueError("parameter unit mismatch")
            try:
                value = float(parameter["value"])
            except (TypeError, ValueError) as exc:
                raise ValueError("non-numeric parameter") from exc
            if not math.isfinite(value):
                raise ValueError("non-finite parameter")
            values[role] = value
            if role in {"upper_bound", "trigger_upper", "recovery_upper"}:
                policy = "HIL_train_quantile_95" if role == "recovery_upper" else "HIL_train_quantile_99"
                if (parameter.get("parameter_kind") != "threshold" or parameter.get("signal_scope") != signal_id
                        or parameter.get("policy") != policy):
                    raise ValueError("threshold kind, scope, or policy mismatch")
            elif role in {"deadline_seconds", "dwell_seconds"}:
                if parameter.get("parameter_role") != role:
                    raise ValueError("runtime parameter role mismatch")
            elif role == "value_epsilon":
                if parameter.get("parameter_kind") != "numeric_tolerance" or parameter.get("signal_scope") != signal_id:
                    raise ValueError("numeric-tolerance scope mismatch")
        if values["value_epsilon"] != 0:
            raise ValueError("value tolerance is not zero")
        if template_id == "bounded_response":
            if (values["recovery_upper"] > values["trigger_upper"] or values["deadline_seconds"] <= 0
                    or values["dwell_seconds"] < 0 or values["dwell_seconds"] >= values["deadline_seconds"]):
                raise ValueError("bounded-response parameter domain mismatch")
