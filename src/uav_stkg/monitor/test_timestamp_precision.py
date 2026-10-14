"""Regression tests for exact admission, deadline order and event coordinates."""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

from . import _legacy_sampled_monitor as core
from .monitor_from_traceability_graph import instantiate_formula, replay_trace
from .sampled_data_contract import EventTimeObservationContract, SamplingContract
from .sampled_monitor import BoundedResponseSpecification, InvariantSpecification, monitor_bounded_response, monitor_invariant
from .timestamp_precision import decimal_add, prepare_timestamped_trace


class TimestampPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.contract = EventTimeObservationContract(0.1, 1e-9)
        self.response = BoundedResponseSpecification("x", 1, 0, 0.1)

    def trace(self, times, values=None):
        return pd.DataFrame({"time_seconds": pd.Series(times, dtype=object), "x": values or [2, 1, 0]})

    def test_closed_deadline_at_large_origin(self):
        result = monitor_bounded_response(self.trace(["1000000000", "1000000000.05", "1000000000.1"]), self.response, self.contract)
        self.assertEqual(result.recovered_obligation_ids, [0])
        self.assertEqual(result.expired_obligation_ids, [])
        self.assertEqual(result.time_mapping.origin_seconds_decimal, "1000000000")
        self.assertEqual(result.relative_events[-1].observed_time_seconds, 0.1)
        self.assertEqual(result.absolute_event_records[-1]["absolute_deadline_time_seconds_decimal"], "1000000000.1")

    def test_expiry_before_recovery_after_deadline_plus_two_epsilon(self):
        result = monitor_bounded_response(self.trace(["1000000000", "1000000000.05", "1000000000.100000002"]), self.response, self.contract)
        self.assertEqual(result.expired_obligation_ids, [0])
        self.assertEqual(result.recovered_obligation_ids, [])
        self.assertEqual(result.events[-1].event_type, "obligation_expired")

    def test_positive_dwell_uses_unchanged_recovery_segments(self):
        definition = BoundedResponseSpecification("x", 1, 0, 0.15, 0.1)
        frame = self.trace(["1000000000", "1000000000.05", "1000000000.1", "1000000000.15"], [2, 0, 0, 0])
        result = monitor_bounded_response(frame, definition, self.contract)
        self.assertEqual(result.recovered_obligation_ids, [0])
        self.assertEqual(result.absolute_event_records[-1]["absolute_recovery_segment_start_seconds_decimal"], "1000000000.05")

    def test_every_high_observation_triggers(self):
        result = monitor_bounded_response(self.trace(["9", "9.05", "9.1"], [2, 2, 0]), self.response, self.contract)
        self.assertEqual([item.trigger_index for item in result.created_obligations], [0, 1])
        self.assertEqual(result.recovered_obligation_ids, [0, 1])

    def test_precise_integer_microseconds(self):
        frame = self.trace([10**15, 10**15 + 50000, 10**15 + 100000])
        result = monitor_bounded_response(frame, self.response, self.contract, timestamp_scale_seconds="0.000001")
        self.assertEqual(result.recovered_obligation_ids, [0])
        self.assertEqual(Decimal(result.time_mapping.origin_seconds_decimal), Decimal("1000000000"))
        self.assertEqual(Decimal(result.time_mapping.restore_relative("0.1")), Decimal("1000000000.1"))

    def test_decimal_context_does_not_erase_small_offset_at_1e100(self):
        times = ["1e100", decimal_add("1e100", "0.05"), decimal_add("1e100", "0.1")]
        result = monitor_bounded_response(self.trace(times), self.response, self.contract)
        self.assertEqual(result.recovered_obligation_ids, [0])
        self.assertEqual(result.time_mapping.relative_seconds_decimal[-1], "0.1")

    def test_float_callers_keep_original_results(self):
        frame = self.trace([0.0, 0.05, 0.1])
        old = core.monitor_bounded_response(frame, self.response, self.contract)
        new = monitor_bounded_response(frame, self.response, self.contract)
        for key, value in asdict(old).items():
            self.assertEqual(asdict(new)[key], value)
        self.assertEqual(new.time_mapping.mode, "legacy_absolute_float")
        self.assertFalse(new.time_mapping.source_precision_preserved)

    def test_already_lost_float_precision_is_not_recovered(self):
        frame = self.trace([float("1000000000"), float("1000000000.00000001"), float("1000000000.05")])
        result = monitor_bounded_response(frame, self.response, self.contract)
        self.assertEqual(result.verdict.value, "rejected_input_contract")
        self.assertFalse(result.time_mapping.source_precision_preserved)

    def test_nonfinite_or_invalid_timestamps_rejected(self):
        for token in ["NaN", "Infinity", "-Infinity", "sNaN", "bad", "", True]:
            with self.subTest(token=token):
                result = monitor_bounded_response(self.trace(["1", token, "1.1"]), self.response, self.contract)
                self.assertEqual(result.verdict.value, "rejected_input_contract")

    def test_nonfinite_signal_rejected(self):
        result = monitor_invariant(self.trace(["1", "1.05", "1.1"], [0, float("nan"), 0]), InvariantSpecification("x", 1), self.contract)
        self.assertEqual(result.verdict.value, "rejected_input_contract")

    def test_no_sorting_or_deduplication(self):
        for times in [["10", "10", "10.1"], ["10", "9.95", "10.1"], ["10", "10.000000001", "10.1"]]:
            with self.subTest(times=times):
                self.assertEqual(monitor_bounded_response(self.trace(times), self.response, self.contract).verdict.value, "rejected_input_contract")

    def test_fixed_rate_profile_remains_distinct(self):
        contract = SamplingContract(0.05, 0.05, 0.10)
        frame = self.trace(["1000000000", "1000000000.05", "1000000000.11"])
        self.assertEqual(monitor_bounded_response(frame, self.response, contract).verdict.value, "rejected_input_contract")
        self.assertEqual(monitor_bounded_response(frame, self.response, self.contract).verdict.value, "violated")

    def test_empty_and_single_observation_rejected(self):
        for frame in [pd.DataFrame({"time_seconds": [], "x": []}), self.trace(["5"], [0])]:
            self.assertEqual(monitor_invariant(frame, InvariantSpecification("x", 1), self.contract).verdict.value, "rejected_input_contract")

    def test_invalid_scale_rejected(self):
        for scale in ["0", "-1", "NaN", "Infinity", 0.000001]:
            with self.subTest(scale=scale):
                with self.assertRaises(ValueError):
                    prepare_timestamped_trace(self.trace([1, 2, 3]), timestamp_scale_seconds=scale)

    def test_graph_bound_entry_consumes_exact_timestamp_column(self):
        definition = instantiate_formula("N06")
        frame = pd.DataFrame({"time_seconds": ["1000000000", "1000000000.05", "1000000000.1"],
                              definition.signal: [definition.trigger_upper + 1, definition.recovery_upper, definition.recovery_upper]})
        result = replay_trace(frame, ["formula:N06"])
        self.assertEqual(result.iloc[0]["timestamp_input_mode"], "exact_origin_relative_float")
        self.assertEqual(result.iloc[0]["recovered_obligation_count"], 1)

    def test_cli_uses_exact_csv_input_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.trace(["1000000000", "1000000000.05", "1000000000.1"]).to_csv(base / "trace.csv", index=False)
            (base / "spec.json").write_text(json.dumps({"kind": "response", **vars(self.response)}), encoding="utf-8")
            (base / "contract.json").write_text(json.dumps({"profile": "event_time", "maximum_observation_gap_seconds": 0.1}), encoding="utf-8")
            command = [sys.executable, "-B", "-m", "uav_stkg.monitor.sampled_monitor", "--trace", str(base / "trace.csv"), "--specification", str(base / "spec.json"), "--contract", str(base / "contract.json"), "--output", str(base / "result.json")]
            cwd = Path(__file__).resolve().parents[3]
            import os
            environment = dict(os.environ, PYTHONPATH=str(cwd / "src"))
            first = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            result = json.loads((base / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["recovered_obligation_ids"], [0])
            content = (base / "result.json").read_bytes()
            second = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((base / "result.json").read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
