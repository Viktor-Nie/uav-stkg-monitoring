"""Property and metamorphic tests for the declared sampled-point monitor.

These tests do not claim a proof beyond the two supported templates. They
exercise semantic invariants on many generated *accepted* sampled traces so a
future code change cannot silently reverse the documented threshold, tolerance
or obligation behaviour. They complement, rather than replace, the RTAMT
shared-subset differential tests.
"""

from __future__ import annotations

from pathlib import Path
import random
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sampled_data_contract import SamplingContract
from sampled_monitor import (
    BoundedResponseSpecification,
    InvariantSpecification,
    Verdict,
    monitor_bounded_response,
    monitor_invariant,
)


CONTRACT = SamplingContract(0.05, 0.0, 0.05)
SEED = 20260810
INVARIANT_CASES = 256
RESPONSE_CASES = 64


def trace(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "time_seconds": [0.05 * index for index in range(len(values))],
        "signal": values,
    })


def test_invariant_threshold_and_tolerance_are_monotone() -> None:
    """A more permissive upper bound/tolerance cannot add a violation."""

    generator = random.Random(SEED)
    for _ in range(INVARIANT_CASES):
        values = [generator.uniform(-2.0, 3.0) for _ in range(generator.randrange(3, 17))]
        strict = monitor_invariant(trace(values), InvariantSpecification("signal", 0.5, 0.0), CONTRACT)
        relaxed_bound = monitor_invariant(trace(values), InvariantSpecification("signal", 1.0, 0.0), CONTRACT)
        relaxed_epsilon = monitor_invariant(trace(values), InvariantSpecification("signal", 0.5, 0.5), CONTRACT)

        assert strict.verdict is not Verdict.REJECTED_INPUT
        assert relaxed_bound.verdict is not Verdict.REJECTED_INPUT
        assert relaxed_epsilon.verdict is not Verdict.REJECTED_INPUT
        assert set(relaxed_bound.violating_sample_indices).issubset(strict.violating_sample_indices)
        assert set(relaxed_epsilon.violating_sample_indices).issubset(strict.violating_sample_indices)
        if strict.verdict is Verdict.SATISFIED:
            assert relaxed_bound.verdict is Verdict.SATISFIED
            assert relaxed_epsilon.verdict is Verdict.SATISFIED


def test_invariant_violation_cannot_be_erased_by_an_accepted_suffix() -> None:
    """Appending samples to an already violated invariant cannot satisfy it."""

    generator = random.Random(SEED + 1)
    for _ in range(INVARIANT_CASES):
        prefix = [generator.uniform(-1.0, 0.5) for _ in range(generator.randrange(2, 10))]
        prefix.append(2.0)
        suffix = [generator.uniform(-1.0, 0.5) for _ in range(generator.randrange(1, 10))]
        before = monitor_invariant(trace(prefix), InvariantSpecification("signal", 1.0), CONTRACT)
        after = monitor_invariant(trace(prefix + suffix), InvariantSpecification("signal", 1.0), CONTRACT)
        assert before.verdict is Verdict.VIOLATED
        assert after.verdict is Verdict.VIOLATED
        assert before.violating_sample_indices == [len(prefix) - 1]
        assert set(before.violating_sample_indices).issubset(after.violating_sample_indices)


def test_recovery_segment_resolves_all_unexpired_level_triggered_obligations() -> None:
    """One completed recovery segment clears every eligible FIFO obligation."""

    generator = random.Random(SEED + 2)
    specification = BoundedResponseSpecification(
        "signal", trigger_upper=1.0, recovery_upper=0.0, deadline_seconds=0.40, dwell_seconds=0.10
    )
    for _ in range(RESPONSE_CASES):
        trigger_count = generator.randrange(1, 4)
        # The final four samples form a 0.15-s recovery segment. It completes
        # before the earliest possible 0.40-s deadline in this construction.
        values = [2.0] * trigger_count + [0.0, 0.0, 0.0, 0.0]
        result = monitor_bounded_response(trace(values), specification, CONTRACT)
        assert result.verdict is Verdict.SATISFIED
        assert len(result.created_obligations) == trigger_count
        assert result.recovered_obligation_ids == list(range(trigger_count))
        assert not result.expired_obligation_ids
        assert not result.pending_obligation_ids


def test_expired_obligation_is_not_erased_by_a_later_recovery_suffix() -> None:
    """The terminal violated verdict remains irreversible after expiry."""

    specification = BoundedResponseSpecification(
        "signal", trigger_upper=1.0, recovery_upper=0.0, deadline_seconds=0.10, dwell_seconds=0.0
    )
    before = monitor_bounded_response(trace([2.0, 2.0, 2.0, 2.0]), specification, CONTRACT)
    after = monitor_bounded_response(trace([2.0, 2.0, 2.0, 2.0, 0.0, 0.0]), specification, CONTRACT)
    assert before.verdict is Verdict.VIOLATED
    assert after.verdict is Verdict.VIOLATED
    assert before.expired_obligation_ids
    assert set(before.expired_obligation_ids).issubset(after.expired_obligation_ids)


def main() -> None:
    test_invariant_threshold_and_tolerance_are_monotone()
    test_invariant_violation_cannot_be_erased_by_an_accepted_suffix()
    test_recovery_segment_resolves_all_unexpired_level_triggered_obligations()
    test_expired_obligation_is_not_erased_by_a_later_recovery_suffix()
    print(
        "monitor metamorphic tests: PASS "
        f"(seed={SEED}, invariant_cases={INVARIANT_CASES}, response_cases={RESPONSE_CASES})"
    )


if __name__ == "__main__":
    main()
