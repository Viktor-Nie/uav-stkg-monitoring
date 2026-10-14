"""Formal v33 monitor entry: exact source time, unchanged FIFO semantics.

Existing DataFrame callers and specification/result fields remain supported.
For exact timestamps, the old time fields are restored to absolute float time;
``absolute_event_records`` additionally retains exact decimal source coordinates
and the actual relative coordinates consumed by the unchanged monitor core.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from decimal import Decimal
import json
from pathlib import Path

import pandas as pd

if __package__:
    from . import _legacy_sampled_monitor as core
    from .sampled_data_contract import EventTimeObservationContract, SamplingContract
    from .timestamp_precision import TimestampMapping, decimal_add, prepare_timestamped_trace
else:
    import _legacy_sampled_monitor as core
    from sampled_data_contract import EventTimeObservationContract, SamplingContract
    from timestamp_precision import TimestampMapping, decimal_add, prepare_timestamped_trace


Verdict = core.Verdict
InvariantSpecification = core.InvariantSpecification
BoundedResponseSpecification = core.BoundedResponseSpecification
Obligation = core.Obligation
MonitorEvent = core.MonitorEvent
InputContract = core.InputContract


@dataclass
class MonitorResult(core.MonitorResult):
    time_mapping: TimestampMapping | None = None
    relative_events: list[MonitorEvent] = field(default_factory=list)
    relative_created_obligations: list[Obligation] = field(default_factory=list)
    absolute_event_records: list[dict[str, object]] = field(default_factory=list)


def _mapped_result(
    result: core.MonitorResult,
    mapping: TimestampMapping,
    specification: InvariantSpecification | BoundedResponseSpecification,
) -> MonitorResult:
    output = MonitorResult(**vars(result), time_mapping=mapping)
    if mapping.mode != "exact_origin_relative_float":
        output.absolute_event_records = [vars(event).copy() for event in result.events]
        return output
    output.relative_events = result.events.copy()
    output.relative_created_obligations = result.created_obligations.copy()
    exact_times = mapping.absolute_seconds_decimal
    relative_index = {float(value): index for index, value in enumerate(mapping.relative_seconds_decimal)
                      if Decimal(value).is_finite()}
    deadline = str(specification.deadline_seconds) if hasattr(specification, "deadline_seconds") else None
    output.created_obligations = [replace(
        obligation,
        trigger_time_seconds=float(exact_times[obligation.trigger_index]),
        deadline_time_seconds=float(decimal_add(exact_times[obligation.trigger_index], deadline)),
    ) for obligation in result.created_obligations]
    restored_events = []
    for event in result.events:
        observed = exact_times[event.observed_index]
        trigger = None if event.trigger_index is None else exact_times[event.trigger_index]
        due = None if trigger is None or deadline is None else decimal_add(trigger, deadline)
        recovery = None
        if event.recovery_segment_start_seconds is not None:
            recovery = exact_times[relative_index[event.recovery_segment_start_seconds]]
        restored = replace(
            event, observed_time_seconds=float(observed),
            trigger_time_seconds=None if trigger is None else float(trigger),
            deadline_time_seconds=None if due is None else float(due),
            recovery_segment_start_seconds=None if recovery is None else float(recovery),
        )
        restored_events.append(restored)
        output.absolute_event_records.append({
            **vars(restored),
            "relative_observed_time_seconds": event.observed_time_seconds,
            "relative_trigger_time_seconds": event.trigger_time_seconds,
            "relative_deadline_time_seconds": event.deadline_time_seconds,
            "relative_recovery_segment_start_seconds": event.recovery_segment_start_seconds,
            "absolute_observed_time_seconds_decimal": observed,
            "absolute_trigger_time_seconds_decimal": trigger,
            "absolute_deadline_time_seconds_decimal": due,
            "absolute_recovery_segment_start_seconds_decimal": recovery,
            "time_origin_seconds_decimal": mapping.origin_seconds_decimal,
        })
    output.events = restored_events
    if exact_times:
        finite_first = Decimal(exact_times[0]).is_finite()
        finite_last = Decimal(exact_times[-1]).is_finite()
        output.sampling_audit = replace(
            result.sampling_audit,
            first_time_seconds=float(exact_times[0]) if finite_first else None,
            last_time_seconds=float(exact_times[-1]) if finite_last else None,
        )
    return output


def monitor_invariant(
    trace: pd.DataFrame, specification: InvariantSpecification, contract: InputContract,
    *, timestamp_scale_seconds: str | Decimal | int = "1",
) -> MonitorResult:
    prepared, mapping = prepare_timestamped_trace(trace, timestamp_scale_seconds=timestamp_scale_seconds)
    return _mapped_result(core.monitor_invariant(prepared, specification, contract), mapping, specification)


def monitor_bounded_response(
    trace: pd.DataFrame, specification: BoundedResponseSpecification, contract: InputContract,
    *, timestamp_scale_seconds: str | Decimal | int = "1",
) -> MonitorResult:
    prepared, mapping = prepare_timestamped_trace(trace, timestamp_scale_seconds=timestamp_scale_seconds)
    return _mapped_result(core.monitor_bounded_response(prepared, specification, contract), mapping, specification)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--specification", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timestamp-scale-seconds", default="1")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not exist; frozen results are never overwritten")
    spec = json.loads(args.specification.read_text(encoding="utf-8"))
    contract_data = json.loads(args.contract.read_text(encoding="utf-8"))
    profile = contract_data.pop("profile")
    contract_type = SamplingContract if profile == "fixed_rate" else EventTimeObservationContract if profile == "event_time" else None
    if contract_type is None:
        parser.error("contract profile must be fixed_rate or event_time")
    kind = spec.pop("kind")
    if kind not in ("invariant", "response"):
        parser.error("specification kind must be invariant or response")
    definition = InvariantSpecification(**spec) if kind == "invariant" else BoundedResponseSpecification(**spec)
    frame = pd.read_csv(args.trace, dtype={"time_seconds": str}, keep_default_na=False)
    function = monitor_invariant if kind == "invariant" else monitor_bounded_response
    result = function(frame, definition, contract_type(**contract_data), timestamp_scale_seconds=args.timestamp_scale_seconds)
    payload = {"verdict": result.verdict.value, "sampling_audit": result.sampling_audit.to_dict(),
               "time_mapping": result.time_mapping.to_dict(), "events": result.absolute_event_records,
               "violating_sample_indices": result.violating_sample_indices,
               "recovered_obligation_ids": result.recovered_obligation_ids,
               "expired_obligation_ids": result.expired_obligation_ids,
               "pending_obligation_ids": result.pending_obligation_ids}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
