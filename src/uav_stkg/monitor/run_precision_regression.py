"""Execute frozen suites through the formal v33 entry, preserving old evidence.

The Decimal oracles are retained independent per-trigger witness enumerators.
They do not import the production predicates, input audit or FIFO monitor.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import pandas as pd

from .monitor_from_traceability_graph import monitor_formula_from_graph
from .sampled_data_contract import EventTimeObservationContract, SamplingContract
from .sampled_monitor import InvariantSpecification, BoundedResponseSpecification, monitor_invariant, monitor_bounded_response


HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[2] / "data" / "monitor"
COUNT_FIELDS = ["sample_count", "violating_sample_count", "created_obligation_count", "recovered_obligation_count", "expired_obligation_count", "pending_obligation_count"]
EVENT_NUMBER_FIELDS = {"observed_time_seconds", "observed_value", "trigger_time_seconds", "deadline_time_seconds", "recovery_segment_start_seconds"}
EVENT_ID_FIELDS = {"observed_index", "obligation_id", "trigger_index"}
EVENT_FIELDS = ["event_type", "observed_index", "observed_time_seconds", "observed_value", "obligation_id", "trigger_index", "trigger_time_seconds", "deadline_time_seconds", "recovery_segment_start_seconds"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def csv_write(path, rows, columns=None):
    with Path(path).open("x", encoding="utf-8-sig", newline="") as handle:
        fieldnames = columns or list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def oracle(name):
    spec = importlib.util.spec_from_file_location(name, FIXTURES / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def compact(result):
    return {"verdict": result.verdict.value, "violations": result.violating_sample_indices,
            "triggers": [item.trigger_index for item in result.created_obligations],
            "recovered": result.recovered_obligation_ids, "expired": result.expired_obligation_ids,
            "pending": result.pending_obligation_ids}


def observed_102(points, rule, contract):
    frame = pd.DataFrame({"time_seconds": [point["time_seconds"] for point in points],
                          "synthetic_speed_mps": [float(point["synthetic_speed_mps"]) for point in points]})
    if rule["kind"] == "invariant":
        result = monitor_invariant(frame, InvariantSpecification("synthetic_speed_mps", float(rule["upper"]), float(rule["value_epsilon"])), contract)
    else:
        result = monitor_bounded_response(frame, BoundedResponseSpecification(
            "synthetic_speed_mps", float(rule["upper"]), float(rule["recovery"]), float(rule["deadline"]),
            float(rule["dwell"]), float(rule["value_epsilon"])), contract)
    return compact(result), result


def run_102(output):
    protocol = load(FIXTURES / "e5_102_protocol.json")
    reference = oracle("e5_decimal_oracle")
    rules, raw_contract = protocol["rules"], protocol["contract"]
    contract = EventTimeObservationContract(float(raw_contract["maximum_observation_gap_seconds"]), float(raw_contract["timestamp_epsilon_seconds"]), raw_contract["minimum_samples"])
    rows, prefixes, details, differences, results = [], [], [], [], {}
    for case in protocol["cases"]:
        rule = {**rules[case["task_id"]], **(case["rule_override"] or {})}
        points = case["samples"]
        if "original_path" in case:
            original = FIXTURES / "original_12" / (case["case_id"] + ".json")
            if sha(original) != case["original_sha256"]:
                raise ValueError("original fixture hash changed: " + case["case_id"])
            raw = json.loads(original.read_text(encoding="utf-8-sig"), parse_float=Decimal, parse_int=Decimal)
            exact_points = [{"time_seconds": str(item["time_seconds"]), "synthetic_speed_mps": str(item["synthetic_speed_mps"])} for item in raw["samples"]]
            assert len(points) == len(exact_points)
            assert all(Decimal(a[key]) == Decimal(b[key]) for a, b in zip(points, exact_points) for key in ("time_seconds", "synthetic_speed_mps"))
            points = exact_points
        ref = reference.direct(points, rule, raw_contract)
        got, result = observed_102(points, rule, contract)
        bad = [key for key in ref if ref[key] != got[key]]
        item = {"case_id": case["case_id"], "reference": ref, "observed": got,
                "time_mapping": result.time_mapping.to_dict(), "absolute_events": result.absolute_event_records}
        details.append(item)
        results[case["case_id"]] = item
        rows.append({"case_id": case["case_id"], "task_id": case["task_id"],
                     "category": case["category"], "full_signature_agrees": not bad,
                     "differing_fields": ";".join(bad), "reference_verdict": ref["verdict"], "observed_verdict": got["verdict"],
                     "timestamp_mode": result.time_mapping.mode, "source_precision_preserved": result.time_mapping.source_precision_preserved})
        if bad:
            differences.append({**item, "prefix_length": None})
        for length in range(2, len(points) + 1):
            pr = reference.direct(points[:length], rule, raw_contract)
            pg, _ = observed_102(points[:length], rule, contract)
            pb = [key for key in pr if pr[key] != pg[key]]
            prefixes.append({"case_id": case["case_id"], "prefix_length": length, "agrees": not pb, "differing_fields": ";".join(pb)})
            if pb:
                differences.append({"case_id": case["case_id"], "prefix_length": length, "reference": pr, "observed": pg})
    relations = []
    for case in protocol["cases"]:
        if not case["relation_to"]:
            continue
        left, right = results[case["relation_to"]], results[case["case_id"]]
        fields = ("verdict", "violations", "recovered", "expired", "pending") if case["transform"] == "same_trigger_and_recovery_endpoints_different_neutral_observations" else tuple(left["observed"])
        preserved = lambda key: all(left[key][field] == right[key][field] for field in fields) and len(left[key]["triggers"]) == len(right[key]["triggers"])
        relations.append({"case_id": case["case_id"], "base_case_id": case["relation_to"], "transform": case["transform"], "decimal_property_preserved": preserved("reference"), "formal_entry_property_preserved": preserved("observed")})
    csv_write(output / "e5_102_cases.csv", rows)
    csv_write(output / "e5_553_prefixes.csv", prefixes)
    csv_write(output / "e5_24_transformations.csv", relations)
    write(output / "e5_full_signatures_and_mapping.json", details)
    write(output / "e5_discrepancies.json", differences)
    assert len(rows) == 102 and len(prefixes) == 553 and len(relations) == 24
    summary = {"cases": len(rows), "case_matches": sum(row["full_signature_agrees"] for row in rows),
               "prefixes": len(prefixes), "prefix_mismatches": sum(not row["agrees"] for row in prefixes),
               "transformations": len(relations), "transformation_failures": sum(not row["formal_entry_property_preserved"] for row in relations)}
    print(json.dumps({"suite102": summary}), flush=True)
    return summary


def observed_boundary(points, rule, contract):
    frame = pd.DataFrame({"time_seconds": [point["time"] for point in points], "signal": [float(point["value"]) for point in points]})
    inv = monitor_invariant(frame, InvariantSpecification("signal", float(rule["upper"]), float(rule["value_epsilon"])), contract)
    response = monitor_bounded_response(frame, BoundedResponseSpecification("signal", float(rule["upper"]), float(rule["recovery"]), float(rule["deadline"]), float(rule["dwell"]), float(rule["value_epsilon"])), contract)
    return {"invariant_verdict": inv.verdict.value, "invariant_violations": inv.violating_sample_indices,
            "response_verdict": response.verdict.value, "triggers": [item.trigger_index for item in response.created_obligations],
            "recovered": sorted(response.recovered_obligation_ids), "expired": sorted(response.expired_obligation_ids), "pending": sorted(response.pending_obligation_ids)}, response


def run_boundary(output):
    cases = load(FIXTURES / "boundary_648_cases.json")
    controls = load(FIXTURES / "boundary_12_contract_controls.json")
    raw_contract = load(FIXTURES / "boundary_contract.json")
    contract = EventTimeObservationContract(float(raw_contract["maximum_gap"]), float(raw_contract["timestamp_epsilon"]))
    reference = oracle("boundary_decimal_oracle")
    rows, prefixes, details, differences = [], [], [], []
    for case in cases + controls:
        points, rule = case["points"], case["rule"]
        group = "factorial" if case["case_id"].startswith("A") else "contract_control"
        ref = reference.evaluate(points, rule, raw_contract)
        got, result = observed_boundary(points, rule, contract)
        bad = [key for key in ref if ref[key] != got[key]]
        item = {"case_id": case["case_id"], "reference": ref, "observed": got,
                "time_mapping": result.time_mapping.to_dict(), "absolute_events": result.absolute_event_records}
        details.append(item)
        rows.append({"case_id": case["case_id"], "group": group, "pattern": case["pattern"], "origin": case["origin"],
                     "deadline": rule["deadline"], "dwell": rule["dwell"], "value_epsilon": rule["value_epsilon"],
                     "full_signature_agrees": not bad, "differing_fields": ";".join(bad),
                     "reference_verdict": ref["response_verdict"], "observed_verdict": got["response_verdict"],
                     "timestamp_mode": result.time_mapping.mode})
        if bad:
            differences.append({**item, "prefix_length": None})
        for length in range(2, len(points) + 1):
            pr = reference.evaluate(points[:length], rule, raw_contract)
            pg, _ = observed_boundary(points[:length], rule, contract)
            pb = [key for key in pr if pr[key] != pg[key]]
            prefixes.append({"case_id": case["case_id"], "group": group, "prefix_length": length, "agrees": not pb, "differing_fields": ";".join(pb)})
            if pb:
                differences.append({"case_id": case["case_id"], "prefix_length": length, "reference": pr, "observed": pg})
        if len(rows) % 108 == 0:
            print(json.dumps({"boundary_cases_processed": len(rows)}), flush=True)
    csv_write(output / "boundary_cases.csv", rows)
    csv_write(output / "boundary_prefixes.csv", prefixes)
    write(output / "boundary_full_signatures_and_mapping.json", details)
    write(output / "boundary_discrepancies.json", differences)
    factorial = [row for row in rows if row["group"] == "factorial"]
    factorial_prefixes = [row for row in prefixes if row["group"] == "factorial"]
    negatives = [row for row in rows if row["group"] == "contract_control"]
    assert len(factorial) == 648 and len(factorial_prefixes) == 16134 and len(negatives) == 12
    summary = {"cases": len(factorial), "case_matches": sum(row["full_signature_agrees"] for row in factorial),
               "prefixes": len(factorial_prefixes), "prefix_mismatches": sum(not row["agrees"] for row in factorial_prefixes),
               "controls": len(negatives), "controls_rejected": sum(row["observed_verdict"] == "rejected_input_contract" for row in negatives),
               "control_signature_matches": sum(row["full_signature_agrees"] for row in negatives),
               "all_discrepancies": len(differences)}
    print(json.dumps({"boundary": summary}), flush=True)
    return summary


def run_semantic_600(output):
    """Replay frozen valid-domain traces, independently rescanning each trigger."""
    source = FIXTURES / "semantic_differential_600.csv"
    rows = pd.read_csv(source, keep_default_na=False).to_dict("records")
    reference = oracle("independent_reference_semantics")
    results, differences = [], []
    for row in rows:
        # These retained inputs were originally float lists. Preserve their
        # exact serialized decimal spelling at this new entry; do not regenerate.
        times = json.loads(row["times_json"], parse_float=Decimal, parse_int=Decimal)
        frame = pd.DataFrame({"time_seconds": [str(value) for value in times], "signal": json.loads(row["values_json"])})
        contract = SamplingContract(0.05, 0.05, 0.10) if row["profile"] == "strict_fixed_rate" else EventTimeObservationContract(0.06)
        definition = BoundedResponseSpecification("signal", float(row["trigger_upper"]), float(row["recovery_upper"]), float(row["deadline_seconds"]), float(row["dwell_seconds"]), float(row["value_epsilon"]))
        invariant = InvariantSpecification("signal", definition.trigger_upper, definition.value_epsilon)
        if not definition.deadline_seconds > 0 or not 0 <= definition.dwell_seconds < definition.deadline_seconds:
            raise ValueError("retained semantic fixture outside declared parameter domain")
        fast_inv = monitor_invariant(frame, invariant, contract)
        fast_resp = monitor_bounded_response(frame, definition, contract)
        # This independent float oracle never imports the production monitor,
        # audit or adapter. It reads the retained zero-origin source coordinates.
        ref_inv = reference.evaluate_invariant(frame, "signal", definition.trigger_upper, definition.value_epsilon)
        ref_resp = reference.evaluate_bounded_response(frame, "signal", definition.trigger_upper, definition.recovery_upper, definition.deadline_seconds, definition.dwell_seconds, definition.value_epsilon, contract.timestamp_epsilon_seconds)
        observed = {"invariant_verdict": fast_inv.verdict.value, "invariant_violations": fast_inv.violating_sample_indices,
                    "response_verdict": fast_resp.verdict.value, "triggers": [item.trigger_index for item in fast_resp.created_obligations],
                    "recovered": fast_resp.recovered_obligation_ids, "expired": fast_resp.expired_obligation_ids, "pending": fast_resp.pending_obligation_ids}
        expected = {"invariant_verdict": ref_inv.verdict, "invariant_violations": list(ref_inv.violating_sample_indices),
                    "response_verdict": ref_resp.verdict, "triggers": list(ref_resp.trigger_indices),
                    "recovered": list(ref_resp.recovered_obligation_ids), "expired": list(ref_resp.expired_obligation_ids), "pending": list(ref_resp.pending_obligation_ids)}
        frozen = {"invariant_verdict": row["reference_invariant_verdict"], "invariant_violations": json.loads(row["reference_invariant_violations_json"]),
                  "response_verdict": row["reference_response_verdict"], "triggers": json.loads(row["reference_trigger_indices_json"]),
                  "recovered": json.loads(row["reference_recovered_ids_json"]), "expired": json.loads(row["reference_expired_ids_json"]), "pending": json.loads(row["reference_pending_ids_json"])}
        bad = [key for key in expected if expected[key] != observed[key]]
        frozen_bad = [key for key in frozen if frozen[key] != observed[key]]
        results.append({"trace_id": row["trace_id"], "profile": row["profile"], "deadline_seconds": definition.deadline_seconds,
                        "dwell_seconds": definition.dwell_seconds, "all_signature_fields_match": not bad,
                        "frozen_signature_matches": not frozen_bad, "differing_fields": ";".join(bad),
                        "timestamp_mode": fast_resp.time_mapping.mode, "observed_signature_json": json.dumps(observed, separators=(",", ":"))})
        if bad or frozen_bad:
            differences.append({"trace_id": row["trace_id"], "reference": expected, "observed": observed, "frozen_reference": frozen})
    assert len(results) == 600 and Counter(row["profile"] for row in results) == {"strict_fixed_rate": 300, "native_event_time": 300}
    csv_write(output / "semantic_600_results.csv", results)
    write(output / "semantic_600_discrepancies.json", differences)
    summary = {"cases": 600, "case_matches": sum(row["all_signature_fields_match"] for row in results),
               "frozen_signature_matches": sum(row["frozen_signature_matches"] for row in results),
               "positive_dwell_cases": sum(row["dwell_seconds"] > 0 for row in results), "profiles": dict(Counter(row["profile"] for row in results)),
               "reference": "unchanged independent per-trigger float future scan; separate from the two Decimal stress oracles"}
    print(json.dumps({"semantic600": summary}), flush=True)
    return summary


def ledger_key(row):
    def integer(key):
        value = row.get(key)
        return "" if value in (None, "") or pd.isna(value) else str(int(float(value)))
    return (str(row.get("case_id", "")), str(row["formula_id"]), str(row["event_type"]), integer("observed_index"), integer("obligation_id"), integer("trigger_index"))


def event_diff(old, new):
    differing = []
    for field in [*EVENT_FIELDS, "final_verdict", "signal_id", "template_id"]:
        left, right = old.get(field), new.get(field)
        empty_left = left in (None, "") or pd.isna(left)
        empty_right = right in (None, "") or pd.isna(right)
        if empty_left or empty_right:
            same = empty_left and empty_right
        elif field in EVENT_NUMBER_FIELDS:
            same = math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-12)
        elif field in EVENT_ID_FIELDS:
            same = int(float(left)) == int(float(right))
        else:
            same = str(left) == str(right)
        if not same:
            differing.append(field)
    if json.loads(old["runtime_specification"]) != json.loads(new["runtime_specification"]):
        differing.append("runtime_specification")
    return differing


def run_real(project, output):
    v2 = project / "specification/v2/results"
    graph = v2 / "traceability_graph"
    sources = [
        ("RflyMAD", v2 / "multi_real_motor_replay/canonical_formula_replay_by_log.csv", v2 / "multi_real_motor_replay/canonical_formula_monitor_events.csv", None, SamplingContract(0.05, 0.05, 0.10)),
        ("FlightReview", graph / "external_flight_review_event_time_graph_bound_replay.csv", graph / "external_flight_review_event_time_graph_bound_events.csv", v2 / "external_flight_review_event_time_signal_observations.csv", EventTimeObservationContract(0.10)),
        ("IDF_DS", v2 / "idf_ds_lap120_event_time/graph_bound_monitor_replay.csv", v2 / "idf_ds_lap120_event_time/graph_bound_monitor_events.csv", v2 / "idf_ds_lap120_event_time/native_signal_observations.csv", EventTimeObservationContract(0.11)),
        ("INSANE", v2 / "insane_indoor1_px4_imu_event_time/graph_bound_monitor_replay.csv", v2 / "insane_indoor1_px4_imu_event_time/graph_bound_monitor_events.csv", v2 / "insane_indoor1_px4_imu_event_time/native_signal_observations.csv", EventTimeObservationContract(0.06)),
    ]
    summaries, summary_rows, differences, mapping_rows = [], [], [], []
    for source, summary_path, event_path, observation_path, contract in sources:
        prior_summary = pd.read_csv(summary_path, dtype={"formula_id": str}, keep_default_na=False)
        prior_events = pd.read_csv(event_path, dtype=str, keep_default_na=False).to_dict("records")
        observations = None if observation_path is None else pd.read_csv(observation_path, dtype={"time_seconds": str}, keep_default_na=False)
        actual_events = []
        source_rows = prior_summary[prior_summary["verdict"] != "not_evaluated"]
        for original in source_rows.to_dict("records"):
            case = str(original.get("case_id", ""))
            signal = str(original["signal_id"])
            if source == "RflyMAD":
                frame = pd.read_csv(v2 / "multi_real_motor_replay" / (case + "_observable_trace.csv"), dtype={"time_seconds": str}, keep_default_na=False)
            else:
                frame = observations.loc[observations["signal_id"].eq(signal), ["time_seconds", "value"]].rename(columns={"value": signal}).reset_index(drop=True)
            definition, result = monitor_formula_from_graph(frame, str(original["formula_id"]), contract=contract)
            counts = {"sample_count": result.sampling_audit.sample_count,
                      "violating_sample_count": len(result.violating_sample_indices),
                      "created_obligation_count": len(result.created_obligations),
                      "recovered_obligation_count": len(result.recovered_obligation_ids),
                      "expired_obligation_count": len(result.expired_obligation_ids),
                      "pending_obligation_count": len(result.pending_obligation_ids)}
            bad = [key for key in COUNT_FIELDS if int(original[key]) != counts[key]]
            if str(original["verdict"]) != result.verdict.value:
                bad.append("verdict")
            common = {"formula_id": str(original["formula_id"]), "signal_id": signal,
                      "template_id": "invariant_upper" if isinstance(definition, InvariantSpecification) else "bounded_response",
                      "runtime_specification": json.dumps(vars(definition), sort_keys=True),
                      "final_verdict": result.verdict.value}
            if case:
                common["case_id"] = case
            for event in result.absolute_event_records:
                actual_events.append({**common, **event})
            row = {"source": source, "case_id": case, "formula_id": str(original["formula_id"]),
                   "legacy_verdict": original["verdict"], "new_verdict": result.verdict.value,
                   "summary_matches": not bad, "differing_fields": ";".join(bad), **counts}
            summary_rows.append(row)
            if bad:
                differences.append({"source": source, "type": "summary", "old": original, "new": row})
            mapping_rows.append({"source": source, "case_id": case, "formula_id": str(original["formula_id"]),
                                 "input_mode": result.time_mapping.mode, "origin_seconds_decimal": result.time_mapping.origin_seconds_decimal,
                                 "timestamp_source": "frozen derived CSV lexemes; earlier acquisition precision is not recovered",
                                 "source_precision_preserved_at_this_interface": result.time_mapping.source_precision_preserved})
        old_by_key = {ledger_key(row): row for row in prior_events}
        new_by_key = {ledger_key(row): row for row in actual_events}
        duplicate_keys = len(old_by_key) != len(prior_events) or len(new_by_key) != len(actual_events)
        if duplicate_keys:
            differences.append({"source": source, "type": "duplicate_event_key", "old_count": len(prior_events), "new_count": len(actual_events)})
        missing, extra = sorted(old_by_key.keys() - new_by_key.keys()), sorted(new_by_key.keys() - old_by_key.keys())
        for key in missing:
            differences.append({"source": source, "type": "missing_event", "key": key, "old": old_by_key[key]})
        for key in extra:
            differences.append({"source": source, "type": "extra_event", "key": key, "new": new_by_key[key]})
        changed = 0
        for key in sorted(old_by_key.keys() & new_by_key.keys()):
            bad = event_diff(old_by_key[key], new_by_key[key])
            if bad:
                changed += 1
                differences.append({"source": source, "type": "event_fields", "key": key, "differing_fields": bad, "old": old_by_key[key], "new": new_by_key[key]})
        csv_write(output / (source + "_formal_entry_event_ledger.csv"), actual_events)
        summary = {"source": source, "evaluated_configurations": len(source_rows), "legacy_event_rows": len(prior_events),
                   "new_event_rows": len(actual_events), "missing_events": len(missing), "extra_events": len(extra),
                   "changed_event_rows": changed, "duplicate_event_keys": duplicate_keys,
                   "summary_mismatches": sum(not row["summary_matches"] for row in summary_rows if row["source"] == source),
                   "numeric_comparison_absolute_tolerance": 1e-12}
        summaries.append(summary)
        print(json.dumps({"real_replay": summary}), flush=True)
    csv_write(output / "real_replay_summary_comparison.csv", summary_rows)
    csv_write(output / "real_replay_timestamp_mapping.csv", mapping_rows)
    write(output / "real_replay_discrepancies.json", differences)
    write(output / "real_replay_summary.json", summaries)
    return summaries


def main():
    global FIXTURES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--project-root", type=Path, help="Also replay the four retained source ledgers; never reparses raw archives.")
    args = parser.parse_args()
    FIXTURES = args.fixtures.resolve()
    fixture_manifest = FIXTURES / "input_manifest.json"
    if fixture_manifest.exists():
        expected = load(fixture_manifest)
        for relative, digest in expected["sha256"].items():
            target = (FIXTURES / relative).resolve()
            if not target.is_relative_to(FIXTURES) or sha(target) != digest:
                raise ValueError("frozen packaged monitor input changed: " + relative)
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    source_files = [path for path in HERE.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    source_files.extend(path for path in FIXTURES.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    immutable = {str(path): sha(path) for path in source_files}
    if args.project_root:
        for directory in ["analysis/results/33_computational_research_20261006/e5_computational", "analysis/results/77_monitor_scale_extension_20261011"]:
            immutable.update({str(path): sha(path) for path in (args.project_root / directory).rglob("*") if path.is_file()})
        paths = [args.project_root / "specification/v2/sampled_monitor.py", args.project_root / "specification/v2/sampled_data_contract.py"]
        results = args.project_root / "specification/v2/results"
        for directory in ["traceability_graph", "multi_real_motor_replay", "idf_ds_lap120_event_time", "insane_indoor1_px4_imu_event_time"]:
            paths.extend(path for path in (results / directory).rglob("*") if path.is_file())
        paths.append(results / "external_flight_review_event_time_signal_observations.csv")
        immutable.update({str(path): sha(path) for path in paths})
    def public_label(path):
        target = Path(path)
        if target.is_relative_to(FIXTURES):
            return "fixtures/" + target.relative_to(FIXTURES).as_posix()
        if target.is_relative_to(HERE):
            return "monitor/" + target.relative_to(HERE).as_posix()
        if args.project_root and target.is_relative_to(args.project_root):
            return "workspace/" + target.relative_to(args.project_root).as_posix()
        raise ValueError("unexpected protected input location")
    write(args.output / "protocol_before_runs.json", {"schema": "v33_formal_precision_regression_v1", "formal_entry": "uav_stkg.monitor.sampled_monitor",
          "contract_and_fifo_thresholds_unchanged": True, "exact_before_float_origin_adaptation": True,
          "float_legacy_compatibility_path": "no precision recovery claimed", "network": False,
          "independent_references": ["round33 raw Decimal enumeration", "round77 per-trigger Decimal full-witness enumeration"],
          "expected_denominators": {"e5_cases": 102, "e5_prefixes": 553, "transformations": 24, "boundary_cases": 648, "boundary_prefixes": 16134, "controls": 12, "semantic_traces": 600, "optional_retained_event_rows": 28210},
          "immutable_sha256_before": {public_label(path): digest for path, digest in immutable.items()}, "failure_policy": "Persist differences without relabelling or filtering."})
    e5 = run_102(args.output)
    boundary = run_boundary(args.output)
    semantic = run_semantic_600(args.output)
    real = run_real(args.project_root, args.output) if args.project_root else []
    changes = [public_label(path) for path, digest in immutable.items() if sha(path) != digest]
    clean = e5["case_matches"] == 102 and e5["prefix_mismatches"] == 0 and e5["transformation_failures"] == 0 and boundary["case_matches"] == 648 and boundary["prefix_mismatches"] == 0 and boundary["controls_rejected"] == 12 and boundary["all_discrepancies"] == 0 and semantic["case_matches"] == 600 and semantic["frozen_signature_matches"] == 600 and not changes and all(not row["missing_events"] and not row["extra_events"] and not row["changed_event_rows"] and not row["duplicate_event_keys"] and not row["summary_mismatches"] for row in real)
    summary = {"schema": "v33_formal_precision_regression_result_v1", "status": "passed" if clean else "differences_retained",
               "e5": e5, "boundary": boundary, "semantic600": semantic, "real_replay": real, "immutable_file_count": len(immutable),
               "changed_immutable_files": changes, "elapsed_seconds": time.perf_counter() - started,
               "historical_results_preserved": not changes, "new_flight_acquisition": False,
               "model_calls": 0, "training": 0,
               "limitations": ["Finite relative-span float arithmetic remains.", "Previously quantized source timestamps cannot be restored.", "Real replay uses retained derived CSV lexemes, without raw-log reparsing or new flight evidence."]}
    write(args.output / "summary.json", summary)
    write(args.output / "output_manifest.json", {path.name: sha(path) for path in args.output.iterdir() if path.is_file()})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    raise SystemExit(0 if clean else 1)


if __name__ == "__main__":
    main()
