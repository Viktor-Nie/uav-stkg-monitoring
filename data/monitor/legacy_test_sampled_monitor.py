from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sampled_data_contract import EventTimeObservationContract, SamplingContract
from sampled_monitor import (
    BoundedResponseSpecification,
    InvariantSpecification,
    Verdict,
    monitor_bounded_response,
    monitor_invariant,
)


CONTRACT = SamplingContract(0.05, 0.05, 0.10)


def trace(values: list[float], times: list[float] | None = None) -> pd.DataFrame:
    if times is None:
        times = [0.05 * index for index in range(len(values))]
    return pd.DataFrame({"time_seconds": times, "signal": values})


def test_invariant_uses_explicit_value_tolerance() -> None:
    result = monitor_invariant(trace([1.0, 1.0005]), InvariantSpecification("signal", 1.0, 0.001), CONTRACT)
    assert result.verdict is Verdict.SATISFIED
    result = monitor_invariant(trace([1.0, 1.0011]), InvariantSpecification("signal", 1.0, 0.001), CONTRACT)
    assert result.verdict is Verdict.VIOLATED
    assert result.violating_sample_indices == [1]
    assert [(event.event_type, event.observed_index) for event in result.events] == [("invariant_violation", 1)]


def test_level_trigger_creates_one_obligation_per_exceeding_sample() -> None:
    result = monitor_bounded_response(
        trace([0.0, 2.0, 2.0, 2.0, 0.0]),
        BoundedResponseSpecification("signal", 1.0, 0.5, 0.25),
        CONTRACT,
    )
    assert result.verdict is Verdict.SATISFIED
    assert len(result.created_obligations) == 3
    assert result.recovered_obligation_ids == [0, 1, 2]
    assert [event.event_type for event in result.events] == [
        "obligation_triggered", "obligation_triggered", "obligation_triggered",
        "obligation_recovered", "obligation_recovered", "obligation_recovered",
    ]
    assert {event.obligation_id for event in result.events if event.event_type == "obligation_recovered"} == {0, 1, 2}


def test_recovery_at_exact_deadline_is_accepted() -> None:
    result = monitor_bounded_response(
        trace([2.0, 2.0, 0.0]),
        BoundedResponseSpecification("signal", 1.0, 0.5, 0.10),
        CONTRACT,
    )
    assert result.verdict is Verdict.SATISFIED


def test_unexpired_obligation_is_inconclusive_at_end() -> None:
    result = monitor_bounded_response(
        trace([2.0, 2.0]),
        BoundedResponseSpecification("signal", 1.0, 0.5, 0.20),
        CONTRACT,
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.pending_obligation_ids == [0, 1]
    assert [event.event_type for event in result.events[-2:]] == ["obligation_pending_at_end", "obligation_pending_at_end"]


def test_expired_obligation_is_violated() -> None:
    result = monitor_bounded_response(
        trace([2.0, 2.0, 2.0, 2.0]),
        BoundedResponseSpecification("signal", 1.0, 0.5, 0.10),
        CONTRACT,
    )
    assert result.verdict is Verdict.VIOLATED
    assert result.expired_obligation_ids == [0]
    expiry = next(event for event in result.events if event.event_type == "obligation_expired")
    assert expiry.deadline_time_seconds == 0.10
    assert abs(expiry.observed_time_seconds - 0.15) <= CONTRACT.timestamp_epsilon_seconds


def test_dwell_must_complete_by_deadline() -> None:
    result = monitor_bounded_response(
        trace([2.0, 0.0, 0.0, 0.0]),
        BoundedResponseSpecification("signal", 1.0, 0.5, 0.10, dwell_seconds=0.10),
        CONTRACT,
    )
    assert result.verdict is Verdict.VIOLATED


def test_input_contract_failure_is_not_an_stl_violation() -> None:
    result = monitor_invariant(
        trace([0.0, 0.0, 0.0], times=[0.0, 0.05, 0.25]),
        InvariantSpecification("signal", 1.0),
        CONTRACT,
    )
    assert result.verdict is Verdict.REJECTED_INPUT


def test_one_sample_cannot_establish_the_declared_sampling_contract() -> None:
    result = monitor_invariant(trace([0.0]), InvariantSpecification("signal", 1.0), CONTRACT)
    assert result.verdict is Verdict.REJECTED_INPUT
    assert result.sampling_audit.reasons == ("insufficient_sample_count_for_timing_contract",)


def test_event_time_contract_changes_only_input_timing_eligibility_not_formula_logic() -> None:
    irregular = trace([0.0, 2.0, 0.0], times=[0.0, 0.005, 0.055])
    specification = BoundedResponseSpecification("signal", 1.0, 0.5, 0.10)
    strict = monitor_bounded_response(irregular, specification, CONTRACT)
    event_time = monitor_bounded_response(
        irregular,
        specification,
        EventTimeObservationContract(maximum_observation_gap_seconds=0.06),
    )
    assert strict.verdict is Verdict.REJECTED_INPUT
    assert event_time.verdict is Verdict.SATISFIED
    assert len(event_time.created_obligations) == 1
    assert event_time.recovered_obligation_ids == [0]


def main() -> None:
    test_invariant_uses_explicit_value_tolerance()
    test_level_trigger_creates_one_obligation_per_exceeding_sample()
    test_recovery_at_exact_deadline_is_accepted()
    test_unexpired_obligation_is_inconclusive_at_end()
    test_expired_obligation_is_violated()
    test_dwell_must_complete_by_deadline()
    test_input_contract_failure_is_not_an_stl_violation()
    test_one_sample_cannot_establish_the_declared_sampling_contract()
    test_event_time_contract_changes_only_input_timing_eligibility_not_formula_logic()
    print("sampled monitor tests: PASS")


if __name__ == "__main__":
    main()
