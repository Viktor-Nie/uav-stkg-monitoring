from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sampled_data_contract import (
    EventTimeObservationContract,
    SamplingContract,
    audit_event_time_trace,
    audit_sampled_trace,
)


def trace(times: list[float], values: list[float] | None = None) -> pd.DataFrame:
    return pd.DataFrame({"time_seconds": times, "signal": values if values is not None else np.zeros(len(times))})


def test_regular_trace_is_eligible() -> None:
    result = audit_sampled_trace(trace([0.0, 0.05, 0.10]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert result.eligible_for_sampled_point_semantics
    assert result.reasons == ()


def test_duplicate_timestamp_is_rejected() -> None:
    result = audit_sampled_trace(trace([0.0, 0.05, 0.05]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert not result.eligible_for_sampled_point_semantics
    assert "non_increasing_timestamp" in result.reasons


def test_gap_is_not_silently_interpolated() -> None:
    result = audit_sampled_trace(trace([0.0, 0.05, 0.20]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert not result.eligible_for_sampled_point_semantics
    assert result.gap_violation_count == 1
    assert "sampling_gap_exceeds_declared_maximum" in result.reasons


def test_non_finite_observable_is_rejected() -> None:
    result = audit_sampled_trace(trace([0.0, 0.05], [0.0, float("nan")]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert not result.eligible_for_sampled_point_semantics
    assert result.non_finite_signal_value_count == 1


def test_single_sample_is_rejected_because_no_sampling_interval_is_observed() -> None:
    result = audit_sampled_trace(trace([0.0]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert not result.eligible_for_sampled_point_semantics
    assert result.reasons == ("insufficient_sample_count_for_timing_contract",)


def test_single_sample_still_reports_missing_values() -> None:
    result = audit_sampled_trace(trace([float("nan")], [float("nan")]), ["signal"], SamplingContract(0.05, 0.05, 0.10))
    assert not result.eligible_for_sampled_point_semantics
    assert "insufficient_sample_count_for_timing_contract" in result.reasons
    assert result.non_finite_timestamp_count == 1
    assert result.non_finite_signal_value_count == 1


def test_irregular_native_event_times_are_eligible_under_the_separate_event_time_contract() -> None:
    result = audit_event_time_trace(
        trace([0.0, 0.005, 0.055, 0.110]),
        ["signal"],
        EventTimeObservationContract(maximum_observation_gap_seconds=0.06),
    )
    assert result.eligible_for_event_time_observation_semantics
    assert result.gap_violation_count == 0
    assert result.reasons == ()


def test_event_time_contract_rejects_an_observation_gap_without_filling_it() -> None:
    result = audit_event_time_trace(
        trace([0.0, 0.005, 0.080]),
        ["signal"],
        EventTimeObservationContract(maximum_observation_gap_seconds=0.06),
    )
    assert not result.eligible_for_event_time_observation_semantics
    assert result.reasons == ("observation_gap_exceeds_declared_maximum",)


def main() -> None:
    """Allow this small contract suite to run without an extra test runner."""
    test_regular_trace_is_eligible()
    test_duplicate_timestamp_is_rejected()
    test_gap_is_not_silently_interpolated()
    test_non_finite_observable_is_rejected()
    test_single_sample_is_rejected_because_no_sampling_interval_is_observed()
    test_single_sample_still_reports_missing_values()
    test_irregular_native_event_times_are_eligible_under_the_separate_event_time_contract()
    test_event_time_contract_rejects_an_observation_gap_without_filling_it()
    print("sampled-data contract tests: PASS")


if __name__ == "__main__":
    main()
