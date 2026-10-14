"""Historical case metadata interpretation, no project-relative reads."""
from pathlib import Path
import re
import pandas as pd

def number_list(value: object) -> list[float]:
    return [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", str(value))]


def read_test_info(path: Path) -> dict:
    table = pd.read_csv(path, header=None)
    values = {
        str(row.iloc[0]).strip(): str(row.iloc[1]).strip()
        for _, row in table.iterrows()
        if len(row) > 1
    }
    fault_id_values = number_list(values.get("Fault ID", ""))
    parameter_values = number_list(values.get("Fault Parameter", ""))
    return {
        "fault_id": int(fault_id_values[0]) if fault_id_values else None,
        "fault_parameter": values.get("Fault Parameter", ""),
        "fault_mode_or_first_parameter": parameter_values[0] if parameter_values else None,
        "fault_injection_time": number_list(values.get("Fault injection time", ""))[0]
        if number_list(values.get("Fault injection time", ""))
        else None,
        "test_end_time": number_list(values.get("Test end time", ""))[0]
        if number_list(values.get("Test end time", ""))
        else None,
        "data_frequency": number_list(values.get("Data collected Frequency", ""))[0]
        if number_list(values.get("Data collected Frequency", ""))
        else None,
        "data_num": number_list(values.get("Data num", ""))[0]
        if number_list(values.get("Data num", ""))
        else None,
    }


def infer_status(case_root: str) -> str:
    parts = case_root.split("/")
    if len(parts) >= 3 and parts[0] == "HIL-NoFault" and parts[1] == "HIL-NoFault":
        return parts[2]
    if len(parts) >= 2:
        return parts[1].split("-")[0]
    return "unknown"


def map_official_class(fault_id: int | None, first_parameter: float | None) -> str:
    if fault_id is None:
        return "normal"
    simple = {
        123450: "motor",
        123451: "propeller",
        # The HIL-Voltage archive uses four related voltage-control/fault IDs;
        # all belong to the official low-voltage data group.
        123540: "low_voltage",
        123541: "low_voltage",
        123542: "low_voltage",
        123543: "low_voltage",
        123544: "wind_affect",
        123545: "wind_affect",
        123546: "wind_affect",
        123457: "load_lose",
        123458: "load_lose",
        123459: "load_lose",
    }
    if fault_id in simple:
        return simple[fault_id]
    sensor_map = {
        123452: "accelerometer",
        123453: "gyroscope",
        123454: "barometer",
        123455: "magnetometer",
        123456: "gps",
    }
    if fault_id in sensor_map:
        return "sensor_noise" if first_parameter == 3 else sensor_map[fault_id]
    return "extra_or_unmapped"
