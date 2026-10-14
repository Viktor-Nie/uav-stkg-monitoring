"""Offline monitor reproduction using only the candidate repository inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(output: Path) -> dict[str, object]:
    """Called by the repository's top-level entry; refuses existing outputs."""
    output = output.resolve()
    if output == ROOT or output.is_relative_to(ROOT / "src") or output.is_relative_to(ROOT / "data"):
        raise ValueError("output must not overwrite candidate sources or inputs")
    if output.exists():
        raise FileExistsError("monitor output must be a new directory")
    import os
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-B", "-m", "uav_stkg.monitor.run_precision_regression", "--fixtures", str(ROOT / "data/monitor"), "--output", str(output)]
    completed = subprocess.run(command, cwd=ROOT, env=environment, check=False, capture_output=True, text=True, encoding="utf-8")
    if not output.exists():
        raise RuntimeError("monitor regression did not start: " + completed.stderr)
    (output / "execution.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output / "execution.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError("monitor regression failed; discrepancies and logs are retained in " + str(output))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if summary["status"] != "passed":
        raise RuntimeError("monitor regression did not pass")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/monitor_reproduction")
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
