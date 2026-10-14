"""Offline reproduction of the separately scoped 651 graph and 14 domain tests."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "research/neo4j"
DATA = ROOT / "data/graph"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/graph_extension")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or any(output.is_relative_to(ROOT / folder) for folder in ("data", "src", "research")):
        parser.error("Output must not overwrite release source or evidence.")
    protected = [path for folder in (SOURCE, DATA) for path in folder.rglob("*") if path.is_file()]
    before = {str(path.relative_to(ROOT)): sha(path) for path in protected}
    output.mkdir(parents=True, exist_ok=True)
    for script, directory in (("run_constraint_extension.py", "extension"), ("run_numeric_domain_controls.py", "numeric_domain_controls")):
        done = subprocess.run([sys.executable, "-B", str(SOURCE / script), "--output", str(output / directory)],
            capture_output=True, text=True, encoding="utf-8")
        (output / (script.removesuffix(".py") + ".log")).write_text(done.stdout + done.stderr, encoding="utf-8")
        if done.returncode:
            sys.stderr.write(done.stderr)
            raise SystemExit(done.returncode)
    extension = json.loads((output / "extension/v33_constraint_extension_receipt.json").read_text(encoding="utf-8"))
    numeric = json.loads((output / "numeric_domain_controls/numeric_domain_controls_receipt.json").read_text(encoding="utf-8"))
    comparisons = {}
    for directory, reference in (("extension", "reference_extension"), ("numeric_domain_controls", "reference_numeric_domains")):
        for original in (SOURCE / reference).glob("*.csv"):
            comparisons[directory + "/" + original.name] = (output / directory / original.name).read_bytes() == original.read_bytes()
    assert all(comparisons.values()), "Portable reproduction differs from frozen reference CSVs"
    after = {str(path.relative_to(ROOT)): sha(path) for path in protected}
    assert before == after, "Protected graph inputs or source evidence changed"
    receipt = {"status": "passed", "source_evidence_unchanged": True,
        "network_requests": 0, "database_writes": 0, "model_calls": 0,
        "graph_variants": extension["new_variant_count"], "graph_variants_rejected": extension["new_variant_rejected_count"],
        "historical_validator_rejected": extension["historical_validator_rejected"],
        "positive_controls": extension["positive_control_count"], "numeric_domain_cases": numeric["cases"],
        "invalid_numeric_cases_rejected": numeric["invalid_boundaries_rejected"],
        "valid_numeric_controls_accepted": numeric["valid_controls_accepted"],
        "reference_csv_byte_equal": comparisons, "input_sha256": before,
        "interpretation": "Constructed graph/configuration checks with separate denominators; neither new flights nor new independently labeled requirements."}
    (output / "reproduction_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("status", "graph_variants", "graph_variants_rejected", "positive_controls", "numeric_domain_cases", "invalid_numeric_cases_rejected", "valid_numeric_controls_accepted", "source_evidence_unchanged")}, indent=2))
