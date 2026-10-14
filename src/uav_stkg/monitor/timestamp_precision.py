"""Keep exact source timestamps until after subtracting a recorded origin.

Strings, Decimal values and integer ticks are exact inputs. Float timestamps
follow the old absolute-float path for compatibility; their lost source digits
cannot be recovered. Signal values, contracts and monitor predicates are not
changed by this adapter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, localcontext
from numbers import Integral
from typing import Iterable

import numpy as np
import pandas as pd


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        return Decimal("NaN")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Integral):
        return Decimal(int(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return Decimal("NaN")
    return Decimal("NaN")


def _precision(values: Iterable[Decimal]) -> int:
    finite = [value for value in values if value.is_finite()]
    if not finite:
        return 28
    # Align all decimal places before subtraction/multiplication. Decimal's
    # ambient default precision must not erase a small offset at a large origin.
    return max(28, max(value.adjusted() for value in finite)
               - min(value.as_tuple().exponent for value in finite) + 8,
               2 * max(len(value.as_tuple().digits) for value in finite) + 8)


def decimal_add(left: str | Decimal, right: str | Decimal) -> str:
    a, b = Decimal(left), Decimal(right)
    with localcontext() as context:
        context.prec = _precision((a, b))
        return str(a + b)


@dataclass(frozen=True)
class TimestampMapping:
    mode: str
    origin_seconds_decimal: str | None
    timestamp_scale_seconds_decimal: str
    source_timestamp_tokens: tuple[str, ...]
    absolute_seconds_decimal: tuple[str, ...]
    relative_seconds_decimal: tuple[str, ...]
    source_precision_preserved: bool
    note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def restore_relative(self, relative_seconds: str | Decimal) -> str:
        """Restore a relative coordinate; observation indices remain preferred."""
        if self.origin_seconds_decimal is None:
            raise ValueError("no finite origin is available")
        return decimal_add(self.origin_seconds_decimal, Decimal(relative_seconds))


def prepare_timestamped_trace(
    trace: pd.DataFrame,
    *,
    timestamp_scale_seconds: str | Decimal | int = "1",
) -> tuple[pd.DataFrame, TimestampMapping]:
    """Return a monitor input copy and an explicit mapping to source time.

    The existing ``time_seconds`` column may hold exact integer ticks when an
    exact seconds-per-tick scale is supplied. CSV callers should read this
    column as strings, and JSON callers should parse numbers with Decimal.
    Invalid/nonfinite tokens remain invalid so the original input audit rejects
    them. No sorting, deduplication, interpolation or tolerance widening occurs.
    """
    if "time_seconds" not in trace.columns:
        raise ValueError("trace is missing required columns: ['time_seconds']")
    scale = _decimal(timestamp_scale_seconds)
    if not scale.is_finite() or scale <= 0:
        raise ValueError("timestamp_scale_seconds must be an exact finite positive value")
    values = trace["time_seconds"].tolist()
    tokens = tuple(str(value) for value in values)
    if any(isinstance(value, (float, np.floating)) for value in values):
        if scale != 1:
            raise ValueError("scaled integer timestamps must reach the adapter before float conversion")
        # Deliberately preserve the original caller's absolute-float behaviour.
        # Subtracting an origin now would not restore already rounded samples.
        mapping = TimestampMapping(
            "legacy_absolute_float", None, str(scale), tokens, tokens, (), False,
            "Float input follows the legacy absolute-time path; source precision is unavailable.",
        )
        return trace.copy(), mapping
    parsed = [_decimal(value) for value in values]
    parsed = [Decimal("NaN") if value.is_snan() else value for value in parsed]
    with localcontext() as context:
        context.prec = _precision((*parsed, scale))
        absolute = [value * scale for value in parsed]
        origin = absolute[0] if absolute and absolute[0].is_finite() else None
        relative = [value - origin for value in absolute] if origin is not None else absolute
    frame = trace.copy()
    frame["time_seconds"] = [float(value) for value in relative]
    mapping = TimestampMapping(
        "exact_origin_relative_float" if origin is not None else "invalid_or_empty_exact_input",
        str(origin) if origin is not None else None, str(scale), tokens,
        tuple(str(value) for value in absolute), tuple(str(value) for value in relative),
        all(value.is_finite() for value in parsed),
        "Origin subtracted in Decimal before float conversion; finite-span float arithmetic remains.",
    )
    return frame, mapping
