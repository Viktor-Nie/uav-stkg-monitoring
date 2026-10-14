"""Deliberately simple reference evaluator for the v2 finite-trace fragment.

This module is intentionally independent of the FIFO implementation in
``sampled_monitor.py``.  It evaluates every trigger separately and rescans the
future trace for a qualifying recovery segment, which is O(n*q) in the worst
case.  It is therefore unsuitable as the production monitor but suitable as a
readable differential oracle for accepted finite traces.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ReferenceInvariantResult:
    verdict: str
    violating_sample_indices: tuple[int, ...]


@dataclass(frozen=True)
class ReferenceResponseResult:
    verdict: str
    trigger_indices: tuple[int, ...]
    recovered_obligation_ids: tuple[int, ...]
    expired_obligation_ids: tuple[int, ...]
    pending_obligation_ids: tuple[int, ...]


def evaluate_invariant(
    trace: pd.DataFrame,
    signal: str,
    upper_bound: float,
    value_epsilon: float,
) -> ReferenceInvariantResult:
    """Directly evaluate G(y <= upper_bound) on the provided finite points."""

    values = trace[signal].astype(float).to_numpy()
    violating = tuple(
        int(index)
        for index, value in enumerate(values)
        if value > upper_bound + value_epsilon
    )
    return ReferenceInvariantResult("violated" if violating else "satisfied", violating)


def _recovers_before_deadline(
    times: list[float],
    values: list[float],
    trigger_index: int,
    recovery_upper: float,
    deadline_seconds: float,
    dwell_seconds: float,
    value_epsilon: float,
    timestamp_epsilon_seconds: float,
) -> bool:
    """Scan one trigger's future observations for its first valid recovery.

    A recovery run is made only of *observed* points.  The run must complete by
    the logical deadline, and a value above recovery_upper resets the run.
    This direct search deliberately does not reuse monitor state or queues.
    """

    deadline = times[trigger_index] + deadline_seconds
    run_start: float | None = None
    for index in range(trigger_index + 1, len(times)):
        now = times[index]
        if now > deadline + timestamp_epsilon_seconds:
            return False
        if values[index] <= recovery_upper + value_epsilon:
            if run_start is None:
                run_start = now
            if now - run_start >= dwell_seconds - timestamp_epsilon_seconds:
                return True
        else:
            run_start = None
    return False


def evaluate_bounded_response(
    trace: pd.DataFrame,
    signal: str,
    trigger_upper: float,
    recovery_upper: float,
    deadline_seconds: float,
    dwell_seconds: float,
    value_epsilon: float,
    timestamp_epsilon_seconds: float,
) -> ReferenceResponseResult:
    """Naively evaluate the documented level-triggered response semantics."""

    times = trace["time_seconds"].astype(float).tolist()
    values = trace[signal].astype(float).tolist()
    triggers = tuple(
        index for index, value in enumerate(values) if value > trigger_upper + value_epsilon
    )
    recovered: list[int] = []
    expired: list[int] = []
    pending: list[int] = []
    final_time = times[-1]
    for obligation_id, trigger_index in enumerate(triggers):
        if _recovers_before_deadline(
            times,
            values,
            trigger_index,
            recovery_upper,
            deadline_seconds,
            dwell_seconds,
            value_epsilon,
            timestamp_epsilon_seconds,
        ):
            recovered.append(obligation_id)
        elif final_time > times[trigger_index] + deadline_seconds + timestamp_epsilon_seconds:
            expired.append(obligation_id)
        else:
            pending.append(obligation_id)
    verdict = "violated" if expired else "inconclusive_end_of_trace" if pending else "satisfied"
    return ReferenceResponseResult(verdict, triggers, tuple(recovered), tuple(expired), tuple(pending))
