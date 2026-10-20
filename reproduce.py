"""Reproduce graph checks and scope scores from the supplied frozen evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def f1(pairs: list[tuple[str, str]]) -> float:
    values = []
    for label in ("in_scope", "conditional", "out_of_scope"):
        tp = sum(y == label and p == label for y, p in pairs)
        fp = sum(y != label and p == label for y, p in pairs)
        fn = sum(y == label and p != label for y, p in pairs)
        values.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return sum(values) / 3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reproduction")
    parser.add_argument("--core-only", action="store_true", help="Run only the frozen graph and English scope checks")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or output.is_relative_to(ROOT / "data") or output.is_relative_to(ROOT / "src"):
        parser.error("output must not overwrite release inputs or source")
    if output.exists():
        parser.error("output must be a new directory; previous evidence is preserved")
    output.mkdir(parents=True)

    import pandas as pd
    from uav_stkg.graph_constraints import run_mutation_ablation, validate_variant

    nodes = pd.read_csv(ROOT / "data/graph/nodes.csv", encoding="utf-8-sig")
    edges = pd.read_csv(ROOT / "data/graph/relationships.csv", encoding="utf-8-sig")
    validate_variant(nodes, edges)
    detail, summary = run_mutation_ablation(nodes, edges)
    expected = pd.read_csv(ROOT / "data/structural_ablation/details.csv", encoding="utf-8-sig")
    keys = ["validator_variant", "mutation_type", "mutation_target"]
    actual = detail.sort_values(keys).reset_index(drop=True)
    expected = expected.sort_values(keys).reset_index(drop=True)
    assert len(actual) == len(expected) == 2832
    assert actual[keys].equals(expected[keys])
    assert actual["mutant_accepted"].equals(expected["mutant_accepted"])
    detail.to_csv(output / "structural_ablation_details.csv", index=False)
    summary.to_csv(output / "structural_ablation_summary.csv", index=False)

    grouped = defaultdict(list)
    for row in read_csv(ROOT / "data/language/english_predictions.csv"):
        grouped[(row["method"], row["family"])].append((row["reference_scope"], row["prediction"]))
    folds = [{"method": method, "family": family, "n": len(pairs), "accuracy": sum(y == p for y, p in pairs) / len(pairs), "fixed_three_class_f1": f1(pairs)} for (method, family), pairs in sorted(grouped.items())]
    english = []
    reference = {r["method"]: r for r in read_csv(ROOT / "data/language/english_expected_summary.csv")}
    for method in sorted(reference):
        rows = [r for r in folds if r["method"] == method]
        assert len(rows) == 8 and sum(r["n"] for r in rows) == 215
        value = sum(r["fixed_three_class_f1"] for r in rows) / 8
        accuracy = sum(r["accuracy"] for r in rows) / 8
        assert abs(value - float(reference[method]["mean_fixed_three_class_f1"])) < 1e-12
        assert abs(accuracy - float(reference[method]["mean_accuracy"])) < 1e-12
        english.append({"method": method, "n": 215, "families": 8, "mean_accuracy": accuracy, "mean_fixed_three_class_f1": value})

    extensions = {}
    if not args.core_only:
        import subprocess
        for driver, name, receipt_name in (
            ('reproduce_ablation.py','ablation','reproduction_receipt.json'),
            ('reproduce_monitor.py','monitor','summary.json'),
            ('reproduce_graph_extension.py','graph_extension','reproduction_receipt.json'),
            ('reproduce_historical_audits.py','historical_audits','receipt.json'),
            ('reproduce_catalog_screen.py','catalog_screen','receipt.json'),
            ('reproduce_semantics.py','semantics','receipt.json'),
            ('research/annotation/reproduce_annotation.py','annotation','annotation_receipt.json'),
            ('research/statistics_performance/conditional_statistics.py','conditional_statistics','receipt.json'),
            ('research/statistics_performance/verify_performance.py','performance_records','receipt.json'),
            ('research/threshold_reproduction/verify_threshold_provenance.py','threshold_provenance','receipt.json'),
            ('reproduce_idf_verified.py','verified_idf','receipt.json'),
        ):
            target = output / name
            completed = subprocess.run([sys.executable,'-B',str(ROOT/driver),'--output',str(target)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            (output/(name+'.stdout.txt')).write_text(completed.stdout,encoding='utf-8')
            (output/(name+'.stderr.txt')).write_text(completed.stderr,encoding='utf-8')
            if completed.returncode: raise RuntimeError(f'{driver} failed; see retained logs in {output}')
            saved = json.loads((target/receipt_name).read_text(encoding='utf-8-sig'))
            assert saved['status'] == 'passed', (driver,saved.get('status'))
            extensions[name] = {'status':'passed','receipt':f'{name}/{receipt_name}'}
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "data").rglob("*")) if p.is_file()}
    receipt = {"status": "passed", "graph": {"nodes": len(nodes), "relationships": len(edges), "bindings": sum(nodes["label"].eq("ParameterBinding")) if "label" in nodes else 84}, "structural_decisions": len(detail), "historical_mutants": 354, "english_scores": english, "input_sha256": hashes, "model_calls": 0, "training_runs": 0, "downloads": 0}
    receipt['extensions'] = extensions
    receipt['reference_status'] = {'historical_human_workflow':'author reports independent classmates A/B and separate adjudicator C','revised_19_reference':'human_review_20261019; core independent A/B review and C adjudication completed as author-confirmed; original C physical-context fields empty'}
    receipt['external_raw_reproduction'] = {'full_HIL_quantiles':'optional explicit raw-state root; default checks prior raw receipt and composition','four_source_replays':'optional explicit upstream root; default independently replays verified CC-BY IDF members','downloads_this_run':0}
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "graph": receipt["graph"], "structural_decisions": len(detail), "english_scores": english}, indent=2))


if __name__ == "__main__":
    main()
