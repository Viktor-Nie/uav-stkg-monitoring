"""Reference monitor for the declared finite sampled-point STL fragment.

This implementation deliberately separates input-contract rejection from an
STL verdict. It never fills missing samples or interpolates a physical
trajectory. The supported fragment and finite-trace semantics are specified in
``docs/重构工作台/01_采样数据STL语义与监测契约.md``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

from sampled_data_contract import (
    EventTimeObservationAudit,
    EventTimeObservationContract,
    SamplingAudit,
    SamplingContract,
    audit_event_time_trace,
    audit_sampled_trace,
)


class Verdict(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    INCONCLUSIVE = "inconclusive_end_of_trace"
    REJECTED_INPUT = "rejected_input_contract"


@dataclass(frozen=True)
class InvariantSpecification:
    signal: str
    upper_bound: float
    value_epsilon: float = 0.0


@dataclass(frozen=True)
class BoundedResponseSpecification:
    """Level-triggered sampled-point response specification.

    Each sample with ``value > trigger_upper + value_epsilon`` creates an
    obligation. A recovery segment must remain below ``recovery_upper`` for at
    least ``dwell_seconds`` and complete no later than the obligation deadline.
    """

    signal: str
    trigger_upper: float
    recovery_upper: float
    deadline_seconds: float
    dwell_seconds: float = 0.0
    value_epsilon: float = 0.0

    def __post_init__(self) -> None:
        if self.deadline_seconds < 0:
            raise ValueError("deadline_seconds must be non-negative")
        if self.dwell_seconds < 0:
            raise ValueError("dwell_seconds must be non-negative")
        if self.recovery_upper > self.trigger_upper:
            raise ValueError("recovery_upper must not exceed trigger_upper")
        if self.value_epsilon < 0:
            raise ValueError("value_epsilon must be non-negative")


@dataclass(frozen=True)
class Obligation:
    identifier: int
    trigger_index: int
    trigger_time_seconds: float
    deadline_time_seconds: float


@dataclass(frozen=True)
class MonitorEvent:
    """One observable monitor-state transition for audit and replay evidence.

    ``observed_time_seconds`` is the timestamp at which the monitor consumed a
    sample and made the transition.  For expiration, ``deadline_time_seconds``
    records the logical deadline; expiration is detected at the first later
    observed sample rather than interpolated at the deadline.
    """

    event_type: str
    observed_index: int
    observed_time_seconds: float
    observed_value: float
    obligation_id: int | None = None
    trigger_index: int | None = None
    trigger_time_seconds: float | None = None
    deadline_time_seconds: float | None = None
    recovery_segment_start_seconds: float | None = None


@dataclass
class MonitorResult:
    verdict: Verdict
    sampling_audit: SamplingAudit | EventTimeObservationAudit
    violating_sample_indices: list[int] = field(default_factory=list)
    created_obligations: list[Obligation] = field(default_factory=list)
    recovered_obligation_ids: list[int] = field(default_factory=list)
    expired_obligation_ids: list[int] = field(default_factory=list)
    pending_obligation_ids: list[int] = field(default_factory=list)
    events: list[MonitorEvent] = field(default_factory=list)


InputContract = SamplingContract | EventTimeObservationContract
InputAudit = SamplingAudit | EventTimeObservationAudit


def _audit(trace: pd.DataFrame, signal: str, contract: InputContract) -> InputAudit:
    if isinstance(contract, SamplingContract):
        return audit_sampled_trace(trace, signal_columns=[signal], contract=contract)
    return audit_event_time_trace(trace, signal_columns=[signal], contract=contract)


def _is_eligible(audit: InputAudit) -> bool:
    if isinstance(audit, SamplingAudit):
        return audit.eligible_for_sampled_point_semantics
    return audit.eligible_for_event_time_observation_semantics


def monitor_invariant(
    trace: pd.DataFrame,
    specification: InvariantSpecification,
    contract: InputContract,
) -> MonitorResult:
    """Evaluate ``G(signal <= upper_bound)`` on accepted sampled traces."""

    audit = _audit(trace, specification.signal, contract)
    if not _is_eligible(audit):
        return MonitorResult(Verdict.REJECTED_INPUT, audit)
    values = trace[specification.signal].astype(float).to_numpy()
    violating_indices = [
        int(index)
        for index, value in enumerate(values)
        if value > specification.upper_bound + specification.value_epsilon
    ]
    events = [
        MonitorEvent(
            event_type="invariant_violation",
            observed_index=index,
            observed_time_seconds=float(trace.iloc[index]["time_seconds"]),
            observed_value=float(trace.iloc[index][specification.signal]),
        )
        for index in violating_indices
    ]
    return MonitorResult(
        Verdict.VIOLATED if violating_indices else Verdict.SATISFIED,
        audit,
        violating_sample_indices=violating_indices,
        events=events,
    )


def monitor_bounded_response(
    trace: pd.DataFrame,
    specification: BoundedResponseSpecification,
    contract: InputContract,
) -> MonitorResult:
    """Evaluate the documented level-triggered bounded-response semantics.

    The monitor state is the pending obligation map and the start time of the
    current all-recovery sampled segment. Per sample, it (1) advances or resets
    that segment, (2) expires overdue obligations, (3) resolves eligible live
    obligations, and (4) creates the new level-triggered obligation.
    """

    audit = _audit(trace, specification.signal, contract)
    if not _is_eligible(audit):
        return MonitorResult(Verdict.REJECTED_INPUT, audit)

    # Trigger times and hence deadlines are nondecreasing. Because a recovery
    # sample cannot also be a strict trigger when recovery_upper <=
    # trigger_upper, pending obligations can be maintained as a FIFO queue.
    # Each obligation enters and leaves the queue once, yielding amortized O(1)
    # work per sample rather than scanning all pending obligations every time.
    pending: deque[Obligation] = deque()
    created: list[Obligation] = []
    recovered: list[int] = []
    expired: list[int] = []
    events: list[MonitorEvent] = []
    recovery_segment_start: float | None = None
    next_identifier = 0

    for index, row in trace.reset_index(drop=True).iterrows():
        now = float(row["time_seconds"])
        value = float(row[specification.signal])
        is_recovery_sample = value <= specification.recovery_upper + specification.value_epsilon
        if is_recovery_sample:
            if recovery_segment_start is None:
                recovery_segment_start = now
        else:
            recovery_segment_start = None

        while pending and now > pending[0].deadline_time_seconds + contract.timestamp_epsilon_seconds:
            obligation = pending.popleft()
            expired.append(obligation.identifier)
            events.append(MonitorEvent(
                event_type="obligation_expired",
                observed_index=int(index),
                observed_time_seconds=now,
                observed_value=value,
                obligation_id=obligation.identifier,
                trigger_index=obligation.trigger_index,
                trigger_time_seconds=obligation.trigger_time_seconds,
                deadline_time_seconds=obligation.deadline_time_seconds,
            ))

        if recovery_segment_start is not None:
            completed_dwell = now - recovery_segment_start >= specification.dwell_seconds - contract.timestamp_epsilon_seconds
            # Every unexpired pending obligation was triggered before this
            # recovery segment began: strict trigger and recovery predicates
            # are mutually exclusive by construction. Thus one completed
            # recovery segment resolves all remaining unexpired obligations.
            if completed_dwell:
                while pending:
                    obligation = pending.popleft()
                    recovered.append(obligation.identifier)
                    events.append(MonitorEvent(
                        event_type="obligation_recovered",
                        observed_index=int(index),
                        observed_time_seconds=now,
                        observed_value=value,
                        obligation_id=obligation.identifier,
                        trigger_index=obligation.trigger_index,
                        trigger_time_seconds=obligation.trigger_time_seconds,
                        deadline_time_seconds=obligation.deadline_time_seconds,
                        recovery_segment_start_seconds=recovery_segment_start,
                    ))

        if value > specification.trigger_upper + specification.value_epsilon:
            obligation = Obligation(
                identifier=next_identifier,
                trigger_index=int(index),
                trigger_time_seconds=now,
                deadline_time_seconds=now + specification.deadline_seconds,
            )
            pending.append(obligation)
            created.append(obligation)
            events.append(MonitorEvent(
                event_type="obligation_triggered",
                observed_index=int(index),
                observed_time_seconds=now,
                observed_value=value,
                obligation_id=obligation.identifier,
                trigger_index=obligation.trigger_index,
                trigger_time_seconds=obligation.trigger_time_seconds,
                deadline_time_seconds=obligation.deadline_time_seconds,
            ))
            next_identifier += 1

    if expired:
        verdict = Verdict.VIOLATED
    elif pending:
        verdict = Verdict.INCONCLUSIVE
    else:
        verdict = Verdict.SATISFIED
    if pending:
        last_index = len(trace) - 1
        last_time = float(trace.iloc[last_index]["time_seconds"])
        last_value = float(trace.iloc[last_index][specification.signal])
        for obligation in pending:
            events.append(MonitorEvent(
                event_type="obligation_pending_at_end",
                observed_index=last_index,
                observed_time_seconds=last_time,
                observed_value=last_value,
                obligation_id=obligation.identifier,
                trigger_index=obligation.trigger_index,
                trigger_time_seconds=obligation.trigger_time_seconds,
                deadline_time_seconds=obligation.deadline_time_seconds,
            ))
    return MonitorResult(
        verdict,
        audit,
        created_obligations=created,
        recovered_obligation_ids=recovered,
        expired_obligation_ids=expired,
        pending_obligation_ids=[obligation.identifier for obligation in pending],
        events=events,
    )
