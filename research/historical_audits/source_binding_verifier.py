"""Frozen source-binding predicates with paths confined to supplied inputs."""
from __future__ import annotations
import ast,csv,hashlib,json,math,re
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE/'source_inputs'
THRESHOLDS=ROOT/'specification/results/research_monitor_thresholds.csv'
RUNTIME=ROOT/'specification/v2/data/monitor_runtime_parameters_v2.csv'
SIGNALS=ROOT/'specification/v2/data/signal_context_v2.csv'
GENERATOR=ROOT/'specification/v2/build_traceability_graph.py'

THRESHOLD_REF = "specification/results/research_monitor_thresholds.csv"


SEMANTIC_REF = "docs/重构工作台/01_采样数据STL语义与监测契约.md"


RUNTIME_REF = "specification/run_all.py:build_monitor_specs"


REQUIRED_FIELDS = (
    "binding_id", "formula_id", "template_id", "monitor_id", "signal_id",
    "role", "parameter_id", "value", "unit", "source_type",
    "source_reference", "source_version", "adoption_status",
    "applicability_status", "binding_version",
)


DECLARED_SOURCE_FIELDS = (
    "source_type", "source_reference", "source_version", "adoption_status",
    "platform_context", "vehicle_context", "flight_mode_context",
    "firmware_context", "applicability_status", "binding_version",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def input_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def same_number(left: str, right: str) -> bool:
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and math.isclose(
        a, b, rel_tol=1e-12, abs_tol=1e-12
    )


def unique_index(rows: list[dict[str, str]], key: str, errors: list[str], name: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        identifier = row.get(key, "").strip()
        if not identifier or identifier in result:
            errors.append(f"{name}: missing or duplicate {key}: {identifier!r}")
        else:
            result[identifier] = row
    return result


def generator_source_declarations(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Read literal source declarations without importing or running the generator."""
    tree = ast.parse(text)
    functions = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "build_export"
    ]
    if len(functions) != 1:
        raise ValueError("expected one build_export declaration")
    statements = list(ast.walk(functions[0]))
    contexts = [
        item.value for item in statements
        if isinstance(item, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "threshold_context" for target in item.targets)
    ]
    if len(contexts) != 1:
        raise ValueError("expected one literal threshold_context declaration")
    threshold_context = ast.literal_eval(contexts[0])
    if not isinstance(threshold_context, dict):
        raise ValueError("threshold_context is not a literal mapping")

    epsilon_calls = []
    for item in statements:
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.func.id != "node":
            continue
        keywords = {keyword.arg: keyword.value for keyword in item.keywords if keyword.arg is not None}
        kind = keywords.get("parameter_kind")
        if isinstance(kind, ast.Constant) and kind.value == "numeric_tolerance":
            epsilon_calls.append(keywords)
    if len(epsilon_calls) != 1:
        raise ValueError("expected one literal numeric-tolerance node declaration")
    epsilon_context = {
        field: ast.literal_eval(epsilon_calls[0][field])
        for field in DECLARED_SOURCE_FIELDS
    }
    declarations = []
    for name, context in (("threshold", threshold_context), ("epsilon", epsilon_context)):
        values = {field: context[field] for field in DECLARED_SOURCE_FIELDS}
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError(f"{name} source declaration requires nonempty literal strings")
        declarations.append(values)
    return declarations[0], declarations[1]


def run(bindings_path: Path) -> dict[str, object]:
    inputs = [bindings_path, THRESHOLDS, RUNTIME, SIGNALS, GENERATOR, ROOT / SEMANTIC_REF, ROOT / "specification/run_all.py"]
    missing_inputs = [str(path) for path in inputs if not path.is_file()]
    if missing_inputs:
        return {"status": "failed", "errors": [f"missing input: {item}" for item in missing_inputs]}

    errors: list[str] = []
    bindings = read_csv(bindings_path)
    thresholds = unique_index(read_csv(THRESHOLDS), "threshold_id", errors, "threshold catalog")
    runtime = unique_index(read_csv(RUNTIME), "parameter_id", errors, "runtime catalog")
    signals = unique_index(read_csv(SIGNALS), "signal_id", errors, "signal context")
    unique_index(bindings, "binding_id", errors, "binding export")
    generator_text = GENERATOR.read_text(encoding="utf-8")
    runtime_text = (ROOT / "specification/run_all.py").read_text(encoding="utf-8")
    if not re.search(r'def\s+build_monitor_specs\s*\(', runtime_text):
        errors.append("runtime source pointer does not resolve to build_monitor_specs")
    if 'epsilon_id = f"zero_epsilon_{signal.signal_id}"' not in generator_text or 'value=0.0' not in generator_text:
        errors.append("semantic zero-epsilon generation rule not found")
    try:
        threshold_source, epsilon_source = generator_source_declarations(generator_text)
    except (SyntaxError, ValueError, TypeError, KeyError) as error:
        return {
            "status": "failed", "binding_count": len(bindings),
            "errors": [*errors, f"cannot statically resolve generator source declarations: {error}"],
        }

    by_source: Counter[str] = Counter()
    by_role: Counter[str] = Counter()
    for row in bindings:
        identifier = row.get("binding_id", "<missing>")
        absent = [field for field in REQUIRED_FIELDS if not row.get(field, "").strip()]
        if absent:
            errors.append(f"{identifier}: missing fields {','.join(absent)}")
            continue
        source_type = row["source_type"]
        by_source[source_type] += 1
        by_role[row["role"]] += 1
        parameter_id = row["parameter_id"]
        signal_id = row["signal_id"]
        if row["source_reference"] not in {THRESHOLD_REF, SEMANTIC_REF, RUNTIME_REF}:
            errors.append(f"{identifier}: unrecognized source pointer {row['source_reference']!r}")
            continue
        if source_type == "derived_statistical_reference":
            upstream = thresholds.get(parameter_id)
            if upstream is None:
                errors.append(f"{identifier}: threshold ID absent upstream: {parameter_id}")
                continue
            if row["source_reference"] != THRESHOLD_REF:
                errors.append(f"{identifier}: threshold source pointer mismatch")
            for field, declared in threshold_source.items():
                if row.get(field) != declared:
                    errors.append(f"{identifier}: {field} differs from declared threshold source")
            for field, upstream_field in (("signal_id", "signal_id"), ("unit", "unit")):
                if row[field] != upstream[upstream_field]:
                    errors.append(f"{identifier}: {field} differs from threshold catalog")
            if not same_number(row["value"], upstream["value"]):
                errors.append(f"{identifier}: value differs from threshold catalog")
        elif parameter_id in runtime:
            upstream = runtime[parameter_id]
            for field, upstream_field in (
                ("role", "parameter_role"), ("unit", "unit"),
                ("source_type", "source_type"), ("source_reference", "source_reference"),
                ("source_version", "source_version"), ("adoption_status", "adoption_status"),
                ("applicability_status", "applicability_status"), ("binding_version", "binding_version"),
            ):
                if row[field] != upstream[upstream_field]:
                    errors.append(f"{identifier}: {field} differs from runtime catalog")
            if not same_number(row["value"], upstream["value"]):
                errors.append(f"{identifier}: value differs from runtime catalog")
        elif source_type == "semantic_default" and parameter_id.startswith("zero_epsilon_"):
            signal = signals.get(signal_id)
            if signal is None:
                errors.append(f"{identifier}: signal absent from context: {signal_id}")
                continue
            if parameter_id != f"zero_epsilon_{signal_id}" or row["role"] != "value_epsilon":
                errors.append(f"{identifier}: epsilon ID or role differs from declared generation rule")
            if row["source_reference"] != SEMANTIC_REF or row["unit"] != signal["unit"]:
                errors.append(f"{identifier}: epsilon source or unit differs from signal context")
            for field, declared in epsilon_source.items():
                if row.get(field) != declared:
                    errors.append(f"{identifier}: {field} differs from declared epsilon source")
            if not same_number(row["value"], "0"):
                errors.append(f"{identifier}: epsilon value is not zero")
        else:
            errors.append(f"{identifier}: no independent catalog or declared generation rule for {parameter_id}")

    if len(bindings) != 84:
        errors.append(f"binding count changed: expected 84, found {len(bindings)}")
    expected_sources = {
        "derived_statistical_reference": 36,
        "semantic_default": 36,
        "prototype_runtime_configuration": 12,
    }
    if dict(by_source) != expected_sources:
        errors.append(f"source-type counts changed: {dict(by_source)}")
    return {
        "schema": "uav_stkg_source_binding_audit_v1",
        "status": "passed" if not errors else "failed",
        "binding_count": len(bindings),
        "source_type_counts": dict(sorted(by_source.items())),
        "role_counts": dict(sorted(by_role.items())),
        "input_sha256": {input_label(path): sha256(path) for path in inputs},
        "errors": errors,
        "interpretation": (
            "This audit checks local source-pointer completeness and exact frozen-value consistency. "
            "It does not evaluate automated extraction from original documents, requirement semantics, "
            "physical threshold validity, reduced human effort, or general ICPS transfer."
        ),
    }
