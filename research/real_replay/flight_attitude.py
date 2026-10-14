"""Historical pure quaternion conversion, preserved verbatim."""
import numpy as np

def to_abs_roll_pitch(quaternion: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert PX4 Hamilton quaternion columns [w, x, y, z] to absolute angles."""

    q = np.asarray(quaternion, dtype=float)
    if q.ndim != 2 or q.shape[1] != 4 or not np.isfinite(q).all():
        raise ValueError("vehicle_attitude quaternion must be a finite n-by-4 array")
    norms = np.linalg.norm(q, axis=1)
    if np.any(norms <= 1e-12):
        raise ValueError("vehicle_attitude contains a zero-norm quaternion")
    w, x, y, z = (q / norms[:, None]).T
    roll = np.arctan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2.0 * (w * y - z * x), -1.0, 1.0))
    return np.abs(roll), np.abs(pitch)
