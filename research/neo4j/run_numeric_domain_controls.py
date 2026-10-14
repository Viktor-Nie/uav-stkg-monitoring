"""Independent N06 numerical-domain boundaries; no denominator change to 651."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import pandas as pd
from run_constraint_extension import change_property, digest_frame
from validation_extension import validate_extended

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data/graph"
DEFAULT_OUT = ROOT / "outputs/graph_extension/numeric_domain_controls"


def run(out: Path):
    nodes = pd.read_csv(DATA / "nodes.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    edges = pd.read_csv(DATA / "relationships.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    props = {row.id: json.loads(row.properties_json) for row in nodes.itertuples(index=False)}
    parameters = {role: props[f"binding:N06:{role}"]["parameter_id"] for role in
        ("trigger_upper", "recovery_upper", "deadline_seconds", "dwell_seconds", "value_epsilon")}
    trigger = float(props[parameters["trigger_upper"]]["value"])
    recovery = float(props[parameters["recovery_upper"]]["value"])
    deadline = float(props[parameters["deadline_seconds"]]["value"])
    tiny = math.nextafter(0.0, math.inf)
    probes = [
        ("clean_frozen_values", None, None, True, "Clean snapshot"),
        ("deadline_zero", "deadline_seconds", 0.0, False, "d > 0"),
        ("deadline_negative_adjacent", "deadline_seconds", -tiny, False, "d > 0"),
        ("deadline_positive_adjacent", "deadline_seconds", tiny, True, "d > 0; tau=0"),
        ("dwell_negative_adjacent", "dwell_seconds", -tiny, False, "tau >= 0"),
        ("dwell_below_deadline_adjacent", "dwell_seconds", math.nextafter(deadline, -math.inf), True, "tau < d"),
        ("dwell_equals_deadline", "dwell_seconds", deadline, False, "tau < d"),
        ("dwell_above_deadline_adjacent", "dwell_seconds", math.nextafter(deadline, math.inf), False, "tau < d"),
        ("recovery_equals_trigger", "recovery_upper", trigger, True, "r <= u"),
        ("recovery_above_trigger_adjacent", "recovery_upper", math.nextafter(trigger, math.inf), False, "r <= u"),
        ("trigger_equals_recovery", "trigger_upper", recovery, True, "r <= u"),
        ("trigger_below_recovery_adjacent", "trigger_upper", math.nextafter(recovery, -math.inf), False, "r <= u"),
        ("epsilon_positive_adjacent", "value_epsilon", tiny, False, "epsilon = 0 in frozen fragment"),
        ("epsilon_negative_adjacent", "value_epsilon", -tiny, False, "epsilon = 0 in frozen fragment"),
    ]
    records, seen = [], set()
    for name, role, value, expected, constraint in probes:
        parameter = parameters[role] if role else "none"
        changed = change_property(nodes, parameter, {"value": value}) if role else nodes
        digest = digest_frame(changed)
        assert digest not in seen, "Duplicate numerical graph fixture"
        seen.add(digest)
        result = validate_extended(changed, edges)
        assert result["accepted"] is expected, (name, result)
        records.append({"case": name, "formula_id": "formula:N06", "parameter_id": parameter,
            "role": role or "all", "test_value_repr": repr(value) if role else "frozen values",
            "constraint": constraint, "expected_accepted": expected, "actual_accepted": result["accepted"],
            "passed": True, "graph_nodes_sha256": digest, "rejection_details_json": json.dumps(result["errors"], sort_keys=True)})
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(out / "numeric_domain_controls.csv", index=False, encoding="utf-8-sig")
    result = {"status": "passed", "cases": len(records),
        "invalid_boundaries_rejected": sum(not row["expected_accepted"] for row in records),
        "valid_controls_accepted": sum(row["expected_accepted"] for row in records),
        "unique_graph_fixtures": len(seen), "tested_formula": "N06", "tested_parameter_roles": list(parameters),
        "adjacent_boundary_definition": "math.nextafter in IEEE-754 binary64; exact values preserved in repr/JSON",
        "frozen_fragment_domains": "d>0; 0<=tau<d; r<=u; epsilon=0",
        "input_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
            (DATA / "nodes.csv", DATA / "relationships.csv")},
        "interpretation": "Constructed numerical configuration boundary tests only. Independent of the historical 354 and new 651 variant denominators; not flight measurements or calibrated operating limits."}
    (out / "numeric_domain_controls_receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "cases", "invalid_boundaries_rejected", "valid_controls_accepted", "unique_graph_fixtures")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    run(parser.parse_args().output)
