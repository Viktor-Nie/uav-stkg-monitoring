"""Native ULog adapter; caller must supply the original file."""
from pathlib import Path
import numpy as np
import pandas as pd
from pyulog import ULog
from flight_attitude import to_abs_roll_pitch

def _topic(ulog: ULog, name: str) -> dict[str, np.ndarray]:
    matches = [dataset for dataset in ulog.data_list if dataset.name == name and dataset.multi_id == 0]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {name} instance, found {len(matches)}")
    return matches[0].data


def _finite_timestamp(data: dict[str, np.ndarray], topic: str) -> np.ndarray:
    if "timestamp_sample" not in data:
        raise RuntimeError(f"{topic} is missing timestamp_sample")
    timestamp_us = np.asarray(data["timestamp_sample"], dtype=float)
    if not np.isfinite(timestamp_us).all():
        raise RuntimeError(f"{topic} has a non-finite timestamp_sample")
    return timestamp_us


def extract_observations(path: Path) -> pd.DataFrame:
    """Return native roll, pitch and angular-rate observations in long format."""

    ulog = ULog(str(path))
    attitude = _topic(ulog, "vehicle_attitude")
    angular_velocity = _topic(ulog, "vehicle_angular_velocity")
    attitude_required = ["q[0]", "q[1]", "q[2]", "q[3]"]
    rate_required = ["xyz[0]", "xyz[1]", "xyz[2]"]
    if missing := [field for field in attitude_required if field not in attitude]:
        raise RuntimeError(f"vehicle_attitude is missing fields: {missing}")
    if missing := [field for field in rate_required if field not in angular_velocity]:
        raise RuntimeError(f"vehicle_angular_velocity is missing fields: {missing}")

    attitude_time_us = _finite_timestamp(attitude, "vehicle_attitude")
    rate_time_us = _finite_timestamp(angular_velocity, "vehicle_angular_velocity")
    origin_us = float(attitude_time_us[0])
    roll, pitch = to_abs_roll_pitch(np.column_stack([attitude[field] for field in attitude_required]))
    angular_rate = np.linalg.norm(
        np.column_stack([angular_velocity[field] for field in rate_required]).astype(float),
        axis=1,
    )
    if not np.isfinite(angular_rate).all():
        raise RuntimeError("vehicle_angular_velocity contains a non-finite component")

    frames = [
        pd.DataFrame({
            "signal_id": "abs_roll_rad",
            "time_seconds": (attitude_time_us - origin_us) / 1e6,
            "value": roll,
            "source_topic": "vehicle_attitude",
            "source_timestamp_sample_us": attitude_time_us.astype(np.int64),
            "unit": "rad",
            "coordinate_frame_status": "attitude reference frame is not independently established",
        }),
        pd.DataFrame({
            "signal_id": "abs_pitch_rad",
            "time_seconds": (attitude_time_us - origin_us) / 1e6,
            "value": pitch,
            "source_topic": "vehicle_attitude",
            "source_timestamp_sample_us": attitude_time_us.astype(np.int64),
            "unit": "rad",
            "coordinate_frame_status": "attitude reference frame is not independently established",
        }),
        pd.DataFrame({
            "signal_id": "ang_rate_norm_rps",
            "time_seconds": (rate_time_us - origin_us) / 1e6,
            "value": angular_rate,
            "source_topic": "vehicle_angular_velocity",
            "source_timestamp_sample_us": rate_time_us.astype(np.int64),
            "unit": "rad/s",
            "coordinate_frame_status": "component reference frame is not independently established",
        }),
    ]
    return pd.concat(frames, ignore_index=True).sort_values(
        ["signal_id", "time_seconds"], kind="stable"
    ).reset_index(drop=True)
