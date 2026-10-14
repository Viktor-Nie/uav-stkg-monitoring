"""Historical native PX4 topic adapter; explicit source directory."""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd
SUPPORTED_SIGNALS = {
 'speed_3d_mps': 'vehicle_local_position: sqrt(vx^2 + vy^2 + vz^2), m/s',
 'abs_roll_rad': 'vehicle_attitude quaternion: abs(roll), rad',
 'abs_pitch_rad': 'vehicle_attitude quaternion: abs(pitch), rad',
 'ang_rate_norm_rps': 'vehicle_angular_velocity: sqrt(xyz[0]^2 + xyz[1]^2 + xyz[2]^2), rad/s',
}

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _topic(path: Path, required: list[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = pd.read_csv(path)
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise RuntimeError(f"{path.name}: required columns missing: {missing}")
    if not pd.api.types.is_integer_dtype(frame["timestamp"]):
        raise RuntimeError(f"{path.name}: timestamp must remain an integer PX4 microsecond clock")
    if not frame["timestamp"].is_monotonic_increasing or frame["timestamp"].duplicated().any():
        raise RuntimeError(f"{path.name}: timestamp must be strictly increasing without duplicate collapse")
    complete = ~frame[required].isna().any(axis=1)
    if not complete.any():
        raise RuntimeError(f"{path.name}: no complete native observations exist")
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_complete in enumerate(complete.tolist()):
        if is_complete and start is None:
            start = index
        elif not is_complete and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(frame)))
    selected_start, selected_end = max(runs, key=lambda bounds: (bounds[1] - bounds[0], -bounds[0]))
    selected = frame.iloc[selected_start:selected_end].copy()
    audit = {
        "source_file": path.name,
        "source_row_count": len(frame),
        "rows_with_missing_selected_fields": int((~complete).sum()),
        "selection": "longest contiguous complete native-observation segment; no interpolation, imputation, or gap bridging",
        "selected_row_start_zero_based": selected_start,
        "selected_row_count": len(selected),
        "selected_first_timestamp_us": int(selected["timestamp"].iloc[0]),
        "selected_last_timestamp_us": int(selected["timestamp"].iloc[-1]),
    }
    return selected, audit


def _attitude_values(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    w, x, y, z = (frame[column].astype(float) for column in ("q[0]", "q[1]", "q[2]", "q[3]"))
    roll = pd.Series([math.atan2(2.0 * (wi * xi + yi * zi), 1.0 - 2.0 * (xi * xi + yi * yi)) for wi, xi, yi, zi in zip(w, x, y, z)], index=frame.index)
    pitch = pd.Series([math.asin(max(-1.0, min(1.0, 2.0 * (wi * yi - zi * xi)))) for wi, xi, yi, zi in zip(w, x, y, z)], index=frame.index)
    return roll.abs(), pitch.abs()


def extract_observations(input_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    files = {
        "position": input_dir / "vehicle_local_position_0.csv",
        "attitude": input_dir / "vehicle_attitude_0.csv",
        "angular_velocity": input_dir / "vehicle_angular_velocity_0.csv",
    }
    position, position_audit = _topic(files["position"], ["timestamp", "vx", "vy", "vz"])
    attitude, attitude_audit = _topic(files["attitude"], ["timestamp", "q[0]", "q[1]", "q[2]", "q[3]"])
    angular_velocity, angular_velocity_audit = _topic(files["angular_velocity"], ["timestamp", "xyz[0]", "xyz[1]", "xyz[2]"])
    roll, pitch = _attitude_values(attitude)
    rows: list[pd.DataFrame] = []
    rows.append(pd.DataFrame({"signal_id": "speed_3d_mps", "source_topic": "vehicle_local_position", "timestamp_us": position["timestamp"], "value": (position["vx"] ** 2 + position["vy"] ** 2 + position["vz"] ** 2).pow(0.5), "unit": "m/s"}))
    rows.append(pd.DataFrame({"signal_id": "abs_roll_rad", "source_topic": "vehicle_attitude", "timestamp_us": attitude["timestamp"], "value": roll, "unit": "rad"}))
    rows.append(pd.DataFrame({"signal_id": "abs_pitch_rad", "source_topic": "vehicle_attitude", "timestamp_us": attitude["timestamp"], "value": pitch, "unit": "rad"}))
    rows.append(pd.DataFrame({"signal_id": "ang_rate_norm_rps", "source_topic": "vehicle_angular_velocity", "timestamp_us": angular_velocity["timestamp"], "value": (angular_velocity["xyz[0]"] ** 2 + angular_velocity["xyz[1]"] ** 2 + angular_velocity["xyz[2]"] ** 2).pow(0.5), "unit": "rad/s"}))
    observations = pd.concat(rows, ignore_index=True)
    origin_us = int(observations["timestamp_us"].min())
    observations["time_seconds"] = (observations["timestamp_us"].astype(float) - origin_us) / 1_000_000.0
    observations["signal_construction"] = observations["signal_id"].map(SUPPORTED_SIGNALS)
    observations = observations.sort_values(["signal_id", "timestamp_us"], kind="stable").reset_index(drop=True)
    manifest = json.loads((input_dir / "source_acquisition_manifest.json").read_text(encoding="utf-8"))
    source = {
        "acquisition_manifest": "source_acquisition_manifest.json",
        "source_record_doi": manifest["source"]["record_doi"],
        "source_license": manifest["source"]["license"],
        "selected_platform": manifest["selection"]["platform"],
        "source_files_sha256": {path.name: _sha256(path) for path in files.values()},
        "topic_selection_audits": {"vehicle_local_position": position_audit, "vehicle_attitude": attitude_audit, "vehicle_angular_velocity": angular_velocity_audit},
        "time_origin": "minimum native PX4 microsecond timestamp among the selected topics",
        "source_time_clock": "PX4 boot-relative integer microseconds; not wall-clock, transport-latency, or hardware-I/O timing",
    }
    return observations, source
