"""Unchanged independent Decimal enumeration from frozen round 33."""
from decimal import Decimal
SIGNAL = "synthetic_speed_mps"
D = lambda value: Decimal(str(value))

def direct(points, rule, contract, epsilon=None):
    """Independent raw-value enumeration; no FIFO state, helper import or interpolation."""
    times = [D(s["time_seconds"]) for s in points]
    values = [D(s[SIGNAL]) for s in points]
    eps = D(contract["timestamp_epsilon_seconds"] if epsilon is None else epsilon)
    if (len(points) < contract["minimum_samples"] or not all(v.is_finite() for v in times+values)
            or any(b-a <= D(contract["timestamp_epsilon_seconds"]) for a, b in zip(times, times[1:]))
            or any(b-a > D(contract["maximum_observation_gap_seconds"])+D(contract["timestamp_epsilon_seconds"]) for a, b in zip(times, times[1:]))):
        return {"verdict": "rejected_input_contract", "violations": [], "triggers": [], "recovered": [], "expired": [], "pending": []}
    upper = D(rule["upper"])+D(rule["value_epsilon"])
    base = {"violations": [], "triggers": [], "recovered": [], "expired": [], "pending": []}
    if rule["kind"] == "invariant":
        base["violations"] = [i for i, v in enumerate(values) if v > upper]
        base["verdict"] = "violated" if base["violations"] else "satisfied"
        return base
    for i, v in enumerate(values):
        if v <= upper:
            continue
        oid = len(base["triggers"])
        base["triggers"].append(i)
        deadline = times[i]+D(rule["deadline"])
        witnesses = [j for j in range(i, len(times)) if times[j] <= deadline+eps and values[j] <= D(rule["recovery"])+D(rule["value_epsilon"])]
        target = "recovered" if witnesses else "expired" if times[-1] > deadline+eps else "pending"
        base[target].append(oid)
    base["verdict"] = "violated" if base["expired"] else "inconclusive_end_of_trace" if base["pending"] else "satisfied"
    return base
