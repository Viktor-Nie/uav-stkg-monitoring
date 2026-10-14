"""Validation contract for the reconstructed sampled-data STL study.

This module intentionally does not reinterpret sampled logs as continuous
physical trajectories.  It establishes when a timestamped trace is eligible
for the *sampled-point* semantics documented in
``docs/重构工作台/01_采样数据STL语义与监测契约.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SamplingContract:
    """Declared timing conditions for one sampled-data monitoring experiment."""

    nominal_period_seconds: float
    relative_jitter_tolerance: float
    maximum_gap_seconds: float
    timestamp_epsilon_seconds: float = 1e-9
    minimum_sample_count: int = 2

    def __post_init__(self) -> None:
        if self.nominal_period_seconds <= 0:
            raise ValueError("nominal_period_seconds must be positive")
        if not 0 <= self.relative_jitter_tolerance < 1:
            raise ValueError("relative_jitter_tolerance must be in [0, 1)")
        if self.maximum_gap_seconds < self.nominal_period_seconds:
            raise ValueError("maximum_gap_seconds must not be below the nominal period")
        if self.timestamp_epsilon_seconds < 0:
            raise ValueError("timestamp_epsilon_seconds must be non-negative")
        if self.minimum_sample_count < 2:
            raise ValueError("minimum_sample_count must be at least two to establish a sampling interval")


@dataclass(frozen=True)
class SamplingAudit:
    """Machine-readable result of checking a trace against a SamplingContract."""

    eligible_for_sampled_point_semantics: bool
    sample_count: int
    signal_columns: tuple[str, ...]
    first_time_seconds: float | None
    last_time_seconds: float | None
    minimum_interval_seconds: float | None
    median_interval_seconds: float | None
    p95_interval_seconds: float | None
    maximum_interval_seconds: float | None
    non_finite_timestamp_count: int
    non_finite_signal_value_count: int
    non_increasing_interval_count: int
    jitter_violation_count: int
    gap_violation_count: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EventTimeObservationContract:
    """Input contract for one signal observed at irregular original timestamps.

    This is deliberately a *different* semantics from ``SamplingContract``.
    It requires no nominal period and therefore does not reinterpret a
    multi-rate ULog as a fixed-rate trace.  A formula may be evaluated only on
    its own original signal observations.  It neither aligns distinct topics
    nor interpolates, imputes or holds a value across topics.
    """

    maximum_observation_gap_seconds: float
    timestamp_epsilon_seconds: float = 1e-9
    minimum_sample_count: int = 2

    def __post_init__(self) -> None:
        if self.maximum_observation_gap_seconds <= 0:
            raise ValueError("maximum_observation_gap_seconds must be positive")
        if self.timestamp_epsilon_seconds < 0:
            raise ValueError("timestamp_epsilon_seconds must be non-negative")
        if self.minimum_sample_count < 2:
            raise ValueError("minimum_sample_count must be at least two to establish an observation gap")


@dataclass(frozen=True)
class EventTimeObservationAudit:
    """Audit result for event-time, native-signal observation semantics."""

    eligible_for_event_time_observation_semantics: bool
    sample_count: int
    signal_columns: tuple[str, ...]
    first_time_seconds: float | None
    last_time_seconds: float | None
    minimum_interval_seconds: float | None
    median_interval_seconds: float | None
    p95_interval_seconds: float | None
    maximum_interval_seconds: float | None
    non_finite_timestamp_count: int
    non_finite_signal_value_count: int
    non_increasing_interval_count: int
    gap_violation_count: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_sampled_trace(
    trace: pd.DataFrame,
    signal_columns: Iterable[str],
    contract: SamplingContract,
) -> SamplingAudit:
    """Audit timestamps and observable values without interpolating the trace.

    A trace is eligible only when every declared signal and timestamp is finite,
    timestamps increase strictly, no interval exceeds the declared gap budget,
    and each interval is within the declared relative jitter tolerance of the
    nominal period.  Violations are reported rather than silently repaired.
    """

    signals = tuple(signal_columns)
    required = {"time_seconds", *signals}
    missing = required - set(trace.columns)
    if missing:
        raise ValueError(f"trace is missing required columns: {sorted(missing)}")
    if trace.empty:
        return SamplingAudit(
            eligible_for_sampled_point_semantics=False,
            sample_count=0,
            signal_columns=signals,
            first_time_seconds=None,
            last_time_seconds=None,
            minimum_interval_seconds=None,
            median_interval_seconds=None,
            p95_interval_seconds=None,
            maximum_interval_seconds=None,
            non_finite_timestamp_count=0,
            non_finite_signal_value_count=0,
            non_increasing_interval_count=0,
            jitter_violation_count=0,
            gap_violation_count=0,
            reasons=("empty_trace",),
        )

    if len(trace) < contract.minimum_sample_count:
        times = pd.to_numeric(trace["time_seconds"], errors="coerce").to_numpy(dtype=float)
        values = trace.loc[:, signals].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        non_finite_timestamps = int((~np.isfinite(times)).sum())
        non_finite_signals = int((~np.isfinite(values)).sum())
        reasons = ["insufficient_sample_count_for_timing_contract"]
        if non_finite_timestamps:
            reasons.append("non_finite_timestamp")
        if non_finite_signals:
            reasons.append("non_finite_signal_value")
        return SamplingAudit(
            eligible_for_sampled_point_semantics=False,
            sample_count=int(len(trace)),
            signal_columns=signals,
            first_time_seconds=float(times[0]) if np.isfinite(times[0]) else None,
            last_time_seconds=float(times[-1]) if np.isfinite(times[-1]) else None,
            minimum_interval_seconds=None,
            median_interval_seconds=None,
            p95_interval_seconds=None,
            maximum_interval_seconds=None,
            non_finite_timestamp_count=non_finite_timestamps,
            non_finite_signal_value_count=non_finite_signals,
            non_increasing_interval_count=0,
            jitter_violation_count=0,
            gap_violation_count=0,
            reasons=tuple(reasons),
        )

    times = pd.to_numeric(trace["time_seconds"], errors="coerce").to_numpy(dtype=float)
    values = trace.loc[:, signals].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    finite_times = np.isfinite(times)
    finite_values = np.isfinite(values)
    non_finite_timestamps = int((~finite_times).sum())
    non_finite_signals = int((~finite_values).sum())

    intervals = np.diff(times) if len(times) > 1 and finite_times.all() else np.array([], dtype=float)
    non_increasing = int((intervals <= contract.timestamp_epsilon_seconds).sum())
    lower = contract.nominal_period_seconds * (1.0 - contract.relative_jitter_tolerance)
    upper = contract.nominal_period_seconds * (1.0 + contract.relative_jitter_tolerance)
    jitter_violations = int(((intervals < lower - contract.timestamp_epsilon_seconds) | (intervals > upper + contract.timestamp_epsilon_seconds)).sum())
    gap_violations = int((intervals > contract.maximum_gap_seconds + contract.timestamp_epsilon_seconds).sum())

    reasons: list[str] = []
    if non_finite_timestamps:
        reasons.append("non_finite_timestamp")
    if non_finite_signals:
        reasons.append("non_finite_signal_value")
    if non_increasing:
        reasons.append("non_increasing_timestamp")
    if jitter_violations:
        reasons.append("sampling_jitter_outside_declared_tolerance")
    if gap_violations:
        reasons.append("sampling_gap_exceeds_declared_maximum")

    return SamplingAudit(
        eligible_for_sampled_point_semantics=not reasons,
        sample_count=int(len(trace)),
        signal_columns=signals,
        first_time_seconds=float(times[0]) if finite_times[0] else None,
        last_time_seconds=float(times[-1]) if finite_times[-1] else None,
        minimum_interval_seconds=float(intervals.min()) if len(intervals) else None,
        median_interval_seconds=float(np.median(intervals)) if len(intervals) else None,
        p95_interval_seconds=float(np.quantile(intervals, 0.95)) if len(intervals) else None,
        maximum_interval_seconds=float(intervals.max()) if len(intervals) else None,
        non_finite_timestamp_count=non_finite_timestamps,
        non_finite_signal_value_count=non_finite_signals,
        non_increasing_interval_count=non_increasing,
        jitter_violation_count=jitter_violations,
        gap_violation_count=gap_violations,
        reasons=tuple(reasons),
    )


def audit_event_time_trace(
    trace: pd.DataFrame,
    signal_columns: Iterable[str],
    contract: EventTimeObservationContract,
) -> EventTimeObservationAudit:
    """Audit one native signal stream without a fixed-rate assumption.

    The timestamp and value checks match the strict contract where applicable,
    but there is intentionally no jitter test: irregular timing is the stated
    observation model.  A maximum gap still makes a missing-observation period
    explicit and rejects it rather than filling it synthetically.
    """

    signals = tuple(signal_columns)
    required = {"time_seconds", *signals}
    missing = required - set(trace.columns)
    if missing:
        raise ValueError(f"trace is missing required columns: {sorted(missing)}")
    if trace.empty:
        return EventTimeObservationAudit(
            eligible_for_event_time_observation_semantics=False,
            sample_count=0,
            signal_columns=signals,
            first_time_seconds=None,
            last_time_seconds=None,
            minimum_interval_seconds=None,
            median_interval_seconds=None,
            p95_interval_seconds=None,
            maximum_interval_seconds=None,
            non_finite_timestamp_count=0,
            non_finite_signal_value_count=0,
            non_increasing_interval_count=0,
            gap_violation_count=0,
            reasons=("empty_trace",),
        )

    times = pd.to_numeric(trace["time_seconds"], errors="coerce").to_numpy(dtype=float)
    values = trace.loc[:, signals].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    non_finite_timestamps = int((~np.isfinite(times)).sum())
    non_finite_signals = int((~np.isfinite(values)).sum())
    if len(trace) < contract.minimum_sample_count:
        reasons = ["insufficient_sample_count_for_observation_gap_contract"]
        if non_finite_timestamps:
            reasons.append("non_finite_timestamp")
        if non_finite_signals:
            reasons.append("non_finite_signal_value")
        return EventTimeObservationAudit(
            eligible_for_event_time_observation_semantics=False,
            sample_count=int(len(trace)),
            signal_columns=signals,
            first_time_seconds=float(times[0]) if np.isfinite(times[0]) else None,
            last_time_seconds=float(times[-1]) if np.isfinite(times[-1]) else None,
            minimum_interval_seconds=None,
            median_interval_seconds=None,
            p95_interval_seconds=None,
            maximum_interval_seconds=None,
            non_finite_timestamp_count=non_finite_timestamps,
            non_finite_signal_value_count=non_finite_signals,
            non_increasing_interval_count=0,
            gap_violation_count=0,
            reasons=tuple(reasons),
        )

    intervals = np.diff(times) if len(times) > 1 and not non_finite_timestamps else np.array([], dtype=float)
    non_increasing = int((intervals <= contract.timestamp_epsilon_seconds).sum())
    gap_violations = int((intervals > contract.maximum_observation_gap_seconds + contract.timestamp_epsilon_seconds).sum())
    reasons: list[str] = []
    if non_finite_timestamps:
        reasons.append("non_finite_timestamp")
    if non_finite_signals:
        reasons.append("non_finite_signal_value")
    if non_increasing:
        reasons.append("non_increasing_timestamp")
    if gap_violations:
        reasons.append("observation_gap_exceeds_declared_maximum")
    return EventTimeObservationAudit(
        eligible_for_event_time_observation_semantics=not reasons,
        sample_count=int(len(trace)),
        signal_columns=signals,
        first_time_seconds=float(times[0]) if np.isfinite(times[0]) else None,
        last_time_seconds=float(times[-1]) if np.isfinite(times[-1]) else None,
        minimum_interval_seconds=float(intervals.min()) if len(intervals) else None,
        median_interval_seconds=float(np.median(intervals)) if len(intervals) else None,
        p95_interval_seconds=float(np.quantile(intervals, 0.95)) if len(intervals) else None,
        maximum_interval_seconds=float(intervals.max()) if len(intervals) else None,
        non_finite_timestamp_count=non_finite_timestamps,
        non_finite_signal_value_count=non_finite_signals,
        non_increasing_interval_count=non_increasing,
        gap_violation_count=gap_violations,
        reasons=tuple(reasons),
    )
