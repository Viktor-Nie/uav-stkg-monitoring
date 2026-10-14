"""Independent exact witness checks for v34; no production files are changed.

The oracle enumerates pairs of indices using Fraction arithmetic. It neither
keeps a recovery-run state nor reproduces the FIFO transition procedure.
Finite exhaustive checks support implementation review; the TeX induction is
the correctness argument. Known floating-point disagreements are retained as
counterexamples to unconditional exact-source correctness, not hidden failures.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import platform
import sys
import time

import pandas as pd


HERE = Path(__file__).resolve().parent


def locate_sources() -> tuple[Path, Path]:
    for parent in (HERE, *HERE.parents):
        if (parent / "src/uav_stkg/monitor/sampled_monitor.py").is_file():
            return parent, parent / "src"
        source = parent / "deliverables/github/uav-stkg-monitoring-v34-candidate/src"
        if (source / "uav_stkg/monitor/sampled_monitor.py").is_file():
            return parent, source
    raise FileNotFoundError("run inside the workspace or the release package containing src/uav_stkg/monitor")


WORKSPACE, CANDIDATE_SRC = locate_sources()
V2_DIR = HERE / "frozen_v2" if (HERE / "frozen_v2/sampled_monitor.py").is_file() else WORKSPACE / "specification/v2"
sys.path.insert(0, str(CANDIDATE_SRC))
from uav_stkg.monitor import sampled_monitor as candidate
from uav_stkg.monitor.sampled_data_contract import EventTimeObservationContract as CandidateContract

sys.path.insert(0, str(V2_DIR))
from sampled_data_contract import EventTimeObservationContract as V2Contract

_v2_spec = importlib.util.spec_from_file_location("v34_reviewed_v2_core", V2_DIR / "sampled_monitor.py")
assert _v2_spec is not None and _v2_spec.loader is not None
v2 = importlib.util.module_from_spec(_v2_spec)
sys.modules[_v2_spec.name] = v2
_v2_spec.loader.exec_module(v2)


def rational(value: str | int | float | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


def exact_token(value: Fraction) -> str:
    """All generated test fractions have terminating decimal expansions."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    assert denominator == 1
    digits = max(twos, fives)
    integer = value.numerator * 2 ** (digits - twos) * 5 ** (digits - fives)
    if digits == 0:
        return str(integer)
    sign = "-" if integer < 0 else ""
    body = str(abs(integer)).zfill(digits + 1)
    return sign + body[:-digits] + "." + body[-digits:]


@dataclass(frozen=True)
class Definition:
    trigger: Fraction = Fraction(1)
    recovery: Fraction = Fraction(1, 2)
    deadline: Fraction = Fraction(1)
    dwell: Fraction = Fraction(0)
    value_epsilon: Fraction = Fraction(0)
    time_epsilon: Fraction = Fraction(0)

    def as_tokens(self) -> dict[str, str]:
        return {key: exact_token(value) for key, value in asdict(self).items()}


def exact_witness_oracle(times: tuple[Fraction, ...], values: tuple[Fraction, ...], definition: Definition) -> dict:
    """Enumerate the mathematical witness set, then classify each trigger."""
    assert all(left < right for left, right in zip(times, times[1:]))
    assert len(times) == len(values)
    assert definition.deadline > 0 and 0 <= definition.dwell < definition.deadline
    assert definition.recovery <= definition.trigger
    assert definition.time_epsilon >= 0 and definition.value_epsilon >= 0
    triggers = tuple(i for i, value in enumerate(values) if value > definition.trigger + definition.value_epsilon)
    recovered, expired, pending = [], [], []
    transition_indices = {}
    recovery_starts = {}
    for i in triggers:
        boundary = times[i] + definition.deadline + definition.time_epsilon
        witnesses = [
            (a, j)
            for a in range(i + 1, len(times))
            for j in range(a, len(times))
            if times[j] <= boundary
            and times[j] - times[a] >= definition.dwell - definition.time_epsilon
            and all(values[k] <= definition.recovery + definition.value_epsilon for k in range(a, j + 1))
        ]
        if witnesses:
            recovered.append(i)
            end = min(j for _, j in witnesses)
            transition_indices[i] = end
            recovery_starts[i] = min(a for a, j in witnesses if j == end)
        elif any(stamp > boundary for stamp in times):
            expired.append(i)
            transition_indices[i] = min(j for j, stamp in enumerate(times) if stamp > boundary)
        else:
            pending.append(i)
            transition_indices[i] = len(times) - 1
    verdict = "violated" if expired else "inconclusive_end_of_trace" if pending else "satisfied"
    return {
        "verdict": verdict, "triggers": triggers, "recovered": tuple(recovered),
        "expired": tuple(expired), "pending": tuple(pending),
        "transition_indices": transition_indices, "recovery_starts": recovery_starts,
    }


def pointwise_stl_response(times: tuple[Fraction, ...], values: tuple[Fraction, ...], definition: Definition) -> bool:
    """Nominal sampled G(trigger -> F_(0,d-tau] G_[0,tau] recovery).

    Temporal operators quantify only over retained timestamp indices. This is
    a stated comparison semantics, not a general finite-STL tool emulation.
    The counterexample horizon contains the full candidate dwell interval.
    """
    for i, value in enumerate(values):
        if value <= definition.trigger + definition.value_epsilon:
            continue
        candidates = [a for a in range(i + 1, len(times))
                      if 0 < times[a] - times[i] <= definition.deadline - definition.dwell]
        if not any(all(values[k] <= definition.recovery + definition.value_epsilon
                       for k in range(a, len(times)) if 0 <= times[k] - times[a] <= definition.dwell)
                   for a in candidates):
            return False
    return True


def run_monitor(module, contract_type, times: tuple[Fraction, ...], values: tuple[Fraction, ...], definition: Definition, exact_input: bool):
    frame = pd.DataFrame({
        "time_seconds": [exact_token(value) if exact_input else float(value) for value in times],
        "signal": [float(value) for value in values],
    })
    specification = module.BoundedResponseSpecification(
        "signal", float(definition.trigger), float(definition.recovery), float(definition.deadline),
        float(definition.dwell), float(definition.value_epsilon),
    )
    contract = contract_type(10.0, timestamp_epsilon_seconds=float(definition.time_epsilon))
    result = module.monitor_bounded_response(frame, specification, contract)
    assert result.verdict.value != "rejected_input_contract", result.sampling_audit
    by_id = {item.identifier: item.trigger_index for item in result.created_obligations}
    terminal_events = {by_id[event.obligation_id]: event for event in result.events
                       if event.event_type in {"obligation_recovered", "obligation_expired", "obligation_pending_at_end"}}
    actual = {
        "verdict": result.verdict.value,
        "triggers": tuple(item.trigger_index for item in result.created_obligations),
        "recovered": tuple(by_id[i] for i in result.recovered_obligation_ids),
        "expired": tuple(by_id[i] for i in result.expired_obligation_ids),
        "pending": tuple(by_id[i] for i in result.pending_obligation_ids),
        "transition_indices": {i: event.observed_index for i, event in terminal_events.items()},
        "recovery_starts": {
            i: times.index(rational(str(event.recovery_segment_start_seconds)))
            for i, event in terminal_events.items() if event.event_type == "obligation_recovered"
        },
    }
    return actual


def checked_case(name: str, time_tokens, value_tokens, definition: Definition, expected_verdict: str | None = None) -> dict:
    times = tuple(rational(value) for value in time_tokens)
    values = tuple(rational(value) for value in value_tokens)
    expected = exact_witness_oracle(times, values, definition)
    if expected_verdict is not None:
        assert expected["verdict"] == expected_verdict, (name, expected)
    for module, contract_type, exact_input in ((candidate, CandidateContract, True), (v2, V2Contract, False)):
        actual = run_monitor(module, contract_type, times, values, definition, exact_input)
        assert actual == expected, (name, module.__name__, expected, actual)
    return {"name": name, "times": [exact_token(value) for value in times],
            "values": [exact_token(value) for value in values], "definition": definition.as_tokens(),
            "expected": expected, "candidate_and_v2": "agree"}


def boundary_cases() -> list[dict]:
    return [
        checked_case("no_trigger_vacuity", [0, 1], [0, "0.75"], Definition(), "satisfied"),
        checked_case("new_terminal_trigger_pending", [0, 1], [0, 2], Definition(), "inconclusive_end_of_trace"),
        checked_case("exact_deadline_unresolved_pending", [0, 1], [2, "0.75"], Definition(), "inconclusive_end_of_trace"),
        checked_case("exact_deadline_recovery", [0, 1], [2, 0], Definition(), "satisfied"),
        checked_case("strictly_later_recovery_cannot_rescue", [0, "1.25"], [2, 0], Definition(), "violated"),
        checked_case("positive_time_tolerance_boundary_pending", [0, "1.125"], [2, "0.75"], Definition(time_epsilon=Fraction(1, 8)), "inconclusive_end_of_trace"),
        checked_case("positive_time_tolerance_boundary_recovery", [0, "1.125"], [2, 0], Definition(time_epsilon=Fraction(1, 8)), "satisfied"),
        checked_case("positive_time_tolerance_strict_expiry", [0, "1.25"], [2, 0], Definition(time_epsilon=Fraction(1, 8)), "violated"),
        checked_case("dwell_exactly_completed", [0, "0.25", "0.5"], [2, 0, 0], Definition(dwell=Fraction(1, 4)), "satisfied"),
        checked_case("dwell_short_at_deadline", [0, "0.75", 1], [2, 0, 0], Definition(dwell=Fraction(1, 2)), "inconclusive_end_of_trace"),
        checked_case("dwell_reset_by_middle_value", [0, "0.25", "0.5", "0.75", 1], [2, 0, "0.75", 0, 0], Definition(dwell=Fraction(1, 2)), "inconclusive_end_of_trace"),
        checked_case("dwell_reduced_by_time_tolerance", [0, "0.5", "0.875"], [2, 0, 0], Definition(dwell=Fraction(1, 2), time_epsilon=Fraction(1, 8)), "satisfied"),
        checked_case("positive_dwell_below_epsilon_single_recovery", [0, "0.25"], [2, 0], Definition(dwell=Fraction(1, 16), time_epsilon=Fraction(1, 8)), "satisfied"),
        checked_case("level_triggering_and_shared_recovery", [0, "0.25", "0.5"], [2, 2, 0], Definition(), "satisfied"),
        checked_case("queue_expired_prefix_recovered_suffix", [0, "0.25", "1.125"], [2, 2, 0], Definition(), "violated"),
        checked_case("expiry_stays_after_later_new_recovery", [0, "1.25", "1.5", "1.75"], [2, 0, 2, 0], Definition(), "violated"),
        checked_case("trigger_threshold_equality_no_trigger", [0, "0.25"], ["1.125", "0.75"], Definition(value_epsilon=Fraction(1, 8)), "satisfied"),
        checked_case("recovery_threshold_equality_inclusive", [0, "0.25"], ["1.25", "0.625"], Definition(value_epsilon=Fraction(1, 8)), "satisfied"),
        checked_case("equal_recovery_and_trigger_bounds", [0, "0.25"], [2, 1], Definition(recovery=Fraction(1)), "satisfied"),
    ]


def non_equivalence_cases() -> list[dict]:
    cases = [
        ("positive_dwell_stl_true_policy_violated", [0, "0.5", "2.25"], [2, 0, 0], Definition(deadline=Fraction(2), dwell=Fraction(1)), True, "violated"),
        ("positive_dwell_tolerance_policy_true_nominal_stl_false", [0, "0.625", 1], [2, 0, 0], Definition(dwell=Fraction(1, 2), time_epsilon=Fraction(1, 8)), False, "satisfied"),
        ("zero_dwell_tolerance_policy_true_nominal_stl_false", [0, "1.0625"], [2, 0], Definition(time_epsilon=Fraction(1, 8)), False, "satisfied"),
    ]
    output = []
    for name, times, values, definition, expected_stl, expected_policy in cases:
        record = checked_case(name, times, values, definition, expected_policy)
        stl = pointwise_stl_response(tuple(map(rational, times)), tuple(map(rational, values)), definition)
        assert stl is expected_stl
        record["nominal_sampled_stl_boolean"] = stl
        output.append(record)
    return output


def floating_point_counterexamples() -> list[dict]:
    times = tuple(map(rational, ["0", "0.1", "0.30000000000000004"]))
    values = tuple(map(rational, ["0.75", "2", "0"]))
    definition = Definition(deadline=Fraction(1, 5))
    exact = exact_witness_oracle(times, values, definition)
    candidate_result = run_monitor(candidate, CandidateContract, times, values, definition, True)
    v2_result = run_monitor(v2, V2Contract, times, values, definition, False)
    assert exact["verdict"] == "violated"
    assert candidate_result["verdict"] == v2_result["verdict"] == "satisfied"
    deadline_record = {
        "name": "relative_decimal_input_still_uses_rounded_float_deadline_addition",
        "times_exact_decimal": [exact_token(value) for value in times],
        "values": [exact_token(value) for value in values], "definition": definition.as_tokens(),
        "exact_source_deadline": "0.3", "float_deadline_repr": repr(0.1 + 0.2),
        "exact_source_result": exact, "candidate_result": candidate_result, "v2_result": v2_result,
        "meaning": "Exact-origin subtraction does not guarantee comparison fidelity on the retained relative span.",
    }
    frame = pd.DataFrame({"time_seconds": ["0", "1"], "signal": [0, float("0.30000000000000004")]})
    invariant = candidate.monitor_invariant(frame, candidate.InvariantSpecification("signal", 0.1, 0.2), CandidateContract(10, timestamp_epsilon_seconds=0))
    assert rational("0.30000000000000004") > rational("0.1") + rational("0.2")
    assert invariant.verdict.value == "satisfied"
    return [deadline_record, {
        "name": "rounded_value_threshold_addition", "exact_observed_value": "0.30000000000000004",
        "exact_bound": "0.1", "exact_value_epsilon": "0.2", "exact_effective_bound": "0.3",
        "float_effective_bound_repr": repr(0.1 + 0.2), "exact_source_verdict": "violated",
        "candidate_verdict": invariant.verdict.value,
        "meaning": "The implementation proof also needs fidelity of the value predicates, independently of timestamp normalization.",
    }]


def exhaustive_checks() -> dict:
    alphabet = (Fraction(0), Fraction(3, 4), Fraction(3, 2))
    definitions = [Definition(deadline=d, dwell=tau, time_epsilon=epsilon)
                   for d, tau, epsilon in product((Fraction(1, 2), Fraction(3, 4)),
                                                   (Fraction(0), Fraction(1, 4)),
                                                   (Fraction(0), Fraction(1, 16)))]
    trace_count = 0
    comparison_count = 0
    digest = hashlib.sha256()
    outcome_counts = {"satisfied": 0, "violated": 0, "inconclusive_end_of_trace": 0}
    for count in range(2, 6):
        regular = tuple(Fraction(i, 4) for i in range(count))
        irregular = tuple(Fraction(i, 4) + (Fraction(1, 8) if i % 2 else 0) for i in range(count))
        for times, values, definition in product((regular, irregular), product(alphabet, repeat=count), definitions):
            expected = exact_witness_oracle(times, values, definition)
            for module, contract_type, exact_input in ((candidate, CandidateContract, True), (v2, V2Contract, False)):
                actual = run_monitor(module, contract_type, times, values, definition, exact_input)
                assert actual == expected, (times, values, definition, module.__name__, expected, actual)
                comparison_count += 1
            # Zero-dwell, zero-time-tolerance decided outcomes agree with the
            # explicitly defined pointwise formula; pending is left separate.
            if definition.dwell == definition.time_epsilon == 0 and expected["verdict"] != "inconclusive_end_of_trace":
                assert pointwise_stl_response(times, values, definition) == (expected["verdict"] == "satisfied")
            outcome_counts[expected["verdict"]] += 1
            trace_count += 1
            digest.update(repr((times, values, definition, expected)).encode("utf-8"))
    return {
        "finite_scope": "all 3-symbol value words of length 2..5, two exact dyadic time profiles, eight valid parameter tuples",
        "unique_case_count": trace_count, "candidate_plus_v2_comparisons": comparison_count,
        "outcome_counts": outcome_counts, "mismatch_count": 0, "deterministic_cases_sha256": digest.hexdigest(),
        "exact_arithmetic": "fractions.Fraction; every tested core operation is exact on the dyadic grid",
        "compared_fields": ["verdict", "trigger indices", "recovered/expired/pending memberships", "transition observation indices", "recovery start indices"],
        "role": "bounded implementation validation, not a replacement for the written induction proof",
    }


def source_hashes() -> dict[str, str]:
    paths = [CANDIDATE_SRC / "uav_stkg/monitor/sampled_monitor.py",
             CANDIDATE_SRC / "uav_stkg/monitor/_legacy_sampled_monitor.py",
             CANDIDATE_SRC / "uav_stkg/monitor/timestamp_precision.py",
             V2_DIR / "sampled_monitor.py", Path(__file__)]
    return {path.relative_to(WORKSPACE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "semantics_validation.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a new output path; validation receipts are not overwritten")
    started = time.perf_counter()
    boundary = boundary_cases()
    non_equivalence = non_equivalence_cases()
    floating = floating_point_counterexamples()
    exhaustive = exhaustive_checks()
    receipt = {
        "status": "passed_with_explicit_characterized_float_counterexamples",
        "python": platform.python_version(), "pandas": pd.__version__,
        "boundary_case_count": len(boundary), "boundary_cases": boundary,
        "non_equivalence_case_count": len(non_equivalence), "non_equivalence_cases": non_equivalence,
        "float_counterexample_count": len(floating), "float_counterexamples": floating,
        "exhaustive": exhaustive, "source_sha256": source_hashes(),
        "elapsed_seconds": time.perf_counter() - started,
        "scope": "Frozen monitor cores are read-only. General STL or unconditional exact-source float correctness is not claimed.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"status": receipt["status"], "boundary_cases": len(boundary),
                      "non_equivalence_cases": len(non_equivalence), "float_counterexamples": len(floating),
                      "exhaustive": exhaustive, "output": str(args.output),
                      "elapsed_seconds": receipt["elapsed_seconds"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
