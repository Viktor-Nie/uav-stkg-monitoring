"""Original INSANE verified ZIP-member adapter; explicit source directory."""
from pathlib import Path
import hashlib
import io
import json
import struct
import zipfile
import zlib
import pandas as pd
SEGMENT_SHA256 = '7b5bbf40d4d1a004436b6c153d80ca1063363cce9c4449d8cc09279403f5464b'
CALIBRATION_ARCHIVE_SHA256 = 'cff4fbd099051cf0ff29838f7ab4bc67ff35d70cc6555029e537ca1036c215f2'
ENTRY_NAME = 'indoor_1_sensors/px4_imu.csv'
ENTRY_CRC32 = 0xECF2F396
ENTRY_COMPRESSED_SIZE = 3705983
ENTRY_UNCOMPRESSED_SIZE = 8860615
SOURCE_PAGE = 'https://www.aau.at/en/smart-systems-technologies/control-of-networked-systems/datasets/insane-dataset/'
SOURCE_ARCHIVE_URL = 'https://cns-data.aau.at/insane-dataset/indoor_1_sensors.zip'
CALIBRATION_ARCHIVE_URL = 'https://cns-data.aau.at/insane-dataset/insane_sensor_calib_preprocessed.zip'
SOURCE_LICENSE = 'BSD-2-Clause-License with no commercial use allowed (source page wording)'
SUPPORTED_SIGNALS = {'ang_rate_norm_rps': 'PX4 ICM20689 IMU: sqrt(w_x^2 + w_y^2 + w_z^2), rad/s'}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_px4_imu(segment_path: Path) -> pd.DataFrame:
    if not segment_path.is_file():
        raise FileNotFoundError(f"official INSANE ZIP member range is missing: {segment_path}")
    if _sha256(segment_path) != SEGMENT_SHA256:
        raise RuntimeError("INSANE PX4-IMU member range SHA-256 mismatch")
    raw = segment_path.read_bytes()
    header = struct.unpack_from("<4s5H3I2H", raw, 0)
    signature, _, flags, method, _, _, crc32, compressed_size, uncompressed_size, name_length, extra_length = header
    if signature != b"PK\x03\x04" or flags != 0 or method != 8:
        raise RuntimeError("INSANE PX4-IMU member is not the expected plain deflate ZIP entry")
    name_start = 30
    name = raw[name_start:name_start + name_length].decode("utf-8")
    if name != ENTRY_NAME:
        raise RuntimeError(f"unexpected INSANE ZIP member: {name}")
    if (crc32, compressed_size, uncompressed_size) != (ENTRY_CRC32, ENTRY_COMPRESSED_SIZE, ENTRY_UNCOMPRESSED_SIZE):
        raise RuntimeError("INSANE PX4-IMU ZIP member metadata mismatch")
    payload_start = name_start + name_length + extra_length
    payload = raw[payload_start:payload_start + compressed_size]
    if len(raw) != payload_start + compressed_size or len(payload) != compressed_size:
        raise RuntimeError("INSANE PX4-IMU member range is incomplete or contains trailing data")
    decoded = zlib.decompress(payload, -15)
    if len(decoded) != uncompressed_size or zlib.crc32(decoded) & 0xFFFFFFFF != crc32:
        raise RuntimeError("INSANE PX4-IMU member CRC/size verification failed")
    frame = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
    frame.columns = frame.columns.str.strip()
    required = ["t", "a_x", "a_y", "a_z", "w_x", "w_y", "w_z"]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise RuntimeError(f"INSANE PX4-IMU CSV columns missing: {missing}")
    if frame[required].isna().any().any():
        raise RuntimeError("INSANE PX4-IMU CSV has missing values in selected fields")
    if not frame["t"].is_monotonic_increasing or frame["t"].duplicated().any():
        raise RuntimeError("INSANE PX4-IMU timestamps must stay strictly increasing without collapsing samples")
    return frame


def _calibration_audit(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"INSANE calibration archive is missing: {path}")
    if _sha256(path) != CALIBRATION_ARCHIVE_SHA256:
        raise RuntimeError("INSANE calibration archive SHA-256 mismatch")
    name = "insane_sensor_calib_preprocessed/sensor_calibration.yaml"
    with zipfile.ZipFile(path) as archive:
        entries = sorted(info.filename for info in archive.infolist())
        content = archive.read(name).decode("utf-8")
    required_tokens = ["p_vc_pximu", "R_vc_pximu", "p_pximu_rtk1", "p_pximu_rtk2", "T_pximu_lsimu", "T_pximu_rsimu"]
    missing = [token for token in required_tokens if token not in content]
    if missing:
        raise RuntimeError(f"INSANE calibration YAML missing expected PX4-IMU fields: {missing}")
    return {
        "archive": path.name,
        "archive_sha256": _sha256(path),
        "sensor_calibration_yaml": name,
        "entries": entries,
        "verified_fields": required_tokens,
        "boundary": "The archive supplies sensor-frame transformations and calibration data. It does not turn this project's research-reference thresholds into engineering safety limits.",
    }


def extract_observations(input_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    segment = input_dir / "indoor_1_px4_imu_segment.bin"
    frame = _read_px4_imu(segment)
    origin = float(frame["t"].iloc[0])
    observations = pd.DataFrame({
        "signal_id": "ang_rate_norm_rps",
        "time_seconds": frame["t"].astype(float) - origin,
        "source_timestamp_seconds": frame["t"].astype(float),
        "value": (frame["w_x"].astype(float).pow(2) + frame["w_y"].astype(float).pow(2) + frame["w_z"].astype(float).pow(2)).pow(0.5),
        "unit": "rad/s",
        "signal_construction": SUPPORTED_SIGNALS["ang_rate_norm_rps"],
    })
    source = {
        "dataset": "INSANE indoor_1 real indoor multicopter flight",
        "source_page": SOURCE_PAGE,
        "source_sensor_archive_url": SOURCE_ARCHIVE_URL,
        "source_calibration_archive_url": CALIBRATION_ARCHIVE_URL,
        "source_license": SOURCE_LICENSE,
        "platform_scope": "3 kg extended carbon-frame quadcopter; PixHawk4 with ICM20689 PX4 IMU; two Raspberry Pi 4 companion boards, as documented by the source paper.",
        "member_range": {
            "path": segment.name,
            "sha256": _sha256(segment),
            "zip_member": ENTRY_NAME,
            "zip_member_crc32": f"{ENTRY_CRC32:08x}",
            "zip_member_compressed_size": ENTRY_COMPRESSED_SIZE,
            "zip_member_uncompressed_size": ENTRY_UNCOMPRESSED_SIZE,
        },
        "calibration": _calibration_audit(input_dir / "insane_sensor_calib_preprocessed.zip"),
        "time_origin": "first retained published t timestamp; absolute source epoch time is retained separately and not interpreted as transport latency",
        "source_time_clock": "published PX4-IMU observation timestamp in seconds; no cross-topic alignment, resampling, hold, interpolation or imputation",
    }
    return observations, source
