from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from automata import MonitorSpec, monitor
from build_neo4j_import import build_import
from build_controlled_nl_stl_benchmark import main as build_controlled_benchmark
from evaluate_monitor_semantics import evaluate as evaluate_monitor_semantics
from evaluate_monitor_semantics import write_report as write_monitor_semantics_report
from evaluate_controlled_nl_stl_benchmark import write_results as evaluate_controlled_benchmark
from kgst import evaluate_pairs
from verify_traceability_export import verify_export


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
RESULTS = ROOT / "results"
HIL_FEATURES = PROJECT_ROOT / "analysis" / "results" / "01_current_complete_hil" / "rflymad_hil_complete_window_features.pkl"
REAL_TRACE = PROJECT_ROOT / "analysis" / "results" / "15_rflymad_real_minimal_frozen_eval" / "real_motor_online_input.csv"
FORBIDDEN = {"fault_state", "fault_onset_time", "fault_injection_time", "official_11_class", "fault_type_label", "y_true"}


def load_pairs() -> pd.DataFrame:
    """Read the hand-curated, standards-compliant CSV seed file."""
    frame = pd.read_csv(ROOT / "data" / "nl_stl_pairs.csv", encoding="utf-8-sig")
    if len(frame) != 24 or frame["stl"].str.contains(r"G\[0,T\]", regex=True).sum() != len(frame):
        raise ValueError("NL-STL 种子对格式不完整")
    return frame


def derive_hil_thresholds() -> pd.DataFrame:
    features = pd.read_pickle(HIL_FEATURES)
    train = features[features["split"].eq("train")].copy()
    if FORBIDDEN & set(train.columns) != FORBIDDEN & set(train.columns):
        raise ValueError("正式 HIL 特征文件缺少边界审计所需字段")
    derived = pd.DataFrame({
        "speed_3d_mps": train["speed_3d__last"].abs(),
        "height_m": train["altitude_estimated__last"].abs(),
        "abs_roll_rad": train["roll__last"].abs(),
        "abs_pitch_rad": train["pitch__last"].abs(),
        "ang_rate_norm_rps": (train["ang_rate_x__last"] ** 2 + train["ang_rate_y__last"] ** 2 + train["ang_rate_z__last"] ** 2) ** 0.5,
    })
    rows = []
    units = {"speed_3d_mps": "m/s", "height_m": "m", "abs_roll_rad": "rad", "abs_pitch_rad": "rad", "ang_rate_norm_rps": "rad/s"}
    for signal in derived:
        stem = signal.removesuffix("_mps").removesuffix("_m").removesuffix("_rad").removesuffix("_rps")
        for percentile in (0.95, 0.99):
            rows.append({"threshold_id": f"{stem}_p{int(percentile * 100)}_train", "signal_id": signal, "value": float(derived[signal].quantile(percentile)), "unit": units[signal], "policy": f"HIL_train_quantile_{int(percentile * 100)}", "scope": "research_monitor_reference_not_engineering_safety_limit", "train_windows": len(train)})
    return pd.DataFrame(rows)


def derive_real_trace() -> pd.DataFrame:
    raw = pd.read_csv(REAL_TRACE, encoding="utf-8-sig")
    found = FORBIDDEN & set(raw.columns)
    if found:
        raise ValueError(f"真实回放输入含禁止标签字段：{sorted(found)}")
    required = {"pos_d", "vel_n", "vel_e", "vel_d", "roll", "pitch", "ang_rate_x", "ang_rate_y", "ang_rate_z", "time_seconds"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"真实回放输入缺少字段：{sorted(missing)}")
    return pd.DataFrame({
        "time_seconds": raw["time_seconds"],
        "speed_3d_mps": (raw["vel_n"] ** 2 + raw["vel_e"] ** 2 + raw["vel_d"] ** 2) ** 0.5,
        "height_m": raw["pos_d"].abs(),
        "abs_roll_rad": raw["roll"].abs(),
        "abs_pitch_rad": raw["pitch"].abs(),
        "ang_rate_norm_rps": (raw["ang_rate_x"] ** 2 + raw["ang_rate_y"] ** 2 + raw["ang_rate_z"] ** 2) ** 0.5,
    })


def threshold_value(frame: pd.DataFrame, signal: str, percentile: int) -> float:
    stem = signal.removesuffix("_mps").removesuffix("_m").removesuffix("_rad").removesuffix("_rps")
    return float(frame.loc[frame["threshold_id"].eq(f"{stem}_p{percentile}_train"), "value"].iloc[0])


def build_monitor_specs(thresholds: pd.DataFrame) -> list[MonitorSpec]:
    specs = []
    for signal in ("speed_3d_mps", "height_m", "abs_roll_rad", "abs_pitch_rad", "ang_rate_norm_rps"):
        stem = signal.removesuffix("_mps").removesuffix("_m").removesuffix("_rad").removesuffix("_rps")
        p99 = threshold_value(thresholds, signal, 99)
        p95 = threshold_value(thresholds, signal, 95)
        specs.append(MonitorSpec(f"INV_{stem.upper()}", "invariant_upper", f"G[0,T]({signal} <= {stem}_p99_train)", signal, p99))
        specs.append(MonitorSpec(f"RESP_{stem.upper()}", "bounded_response", f"G[0,T]({signal} > {stem}_p99_train -> F[0,d_recovery_s]({signal} <= {stem}_p95_train))", signal, p99, p95, 2.0))
    return specs


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "（无记录）"
    return frame.to_markdown(index=False)


def write_report(thresholds: pd.DataFrame, literature_candidates: pd.DataFrame, kg_summary: dict[str, int], nl_summary: pd.DataFrame, monitor_summary: pd.DataFrame) -> None:
    text = "\n".join([
        "# 无人机 NL→STL 规约复刻：可运行阶段结果",
        "",
        "## 已完成的四步",
        "",
        "1. 数据：24 条人工核验的 NL-STL 对（18 开发、6 留出评估）；另有 100 条作者构造的受控评测需求（不代表开放域语料）；HIL 训练集计算分位数参考；真实 PX4 无标签状态流回放。",
        "2. 知识图谱：生成 Neo4j 节点/关系 CSV 和非破坏性 Cypher 导入脚本。",
        "3. 自动机：实现上界不变式与限时恢复两种监控自动机。",
        "4. 规约：检索开发库、受可观测信号和模板约束生成候选 STL，并在真实状态流上运行监控。",
        "",
        "## NL→STL 留出集结果",
        "",
        markdown_table(nl_summary),
        "",
        "该结果是小样本、规则候选生成器的可复现结果，不能表述为大语言模型精度，也不能与原文 16k 数据集结果直接比较。",
        "",
        "## 图谱导出规模",
        "",
        f"- 节点：{kg_summary['nodes']}；关系：{kg_summary['relationships']}。",
        "- 已生成 Neo4j CSV 与非破坏性 Cypher。是否已实际写入数据库必须以 Neo4j 验证查询为准；本次流水线不宣称已入库。",
        "",
        "## HIL 训练集导出的研究监测参考",
        "",
        markdown_table(thresholds[["threshold_id", "signal_id", "value", "unit", "policy", "train_windows"]]),
        "",
        "这些是统计参考分位数，不是物理安全阈值；物理阈值和响应时限的候选依据见 `data/literature_parameter_candidates.csv`，且必须与实际 PX4 参数、飞行模式和信号定义匹配后才能采用。",
        "",
        "## 文献/飞控配置候选依据（尚未采用）",
        "",
        markdown_table(literature_candidates[["candidate_id", "signal_id", "source", "source_version", "parameter_or_rule", "reference_value", "unit", "adoption_status"]]),
        "",
        "这些条目是可追溯候选依据，不会自动改写公式或替代实际飞控参数。",
        "",
        "## 真实 PX4 无标签轨迹监控",
        "",
        markdown_table(monitor_summary[["spec_id", "template_id", "verdict", "sample_count", "trigger_count", "satisfied_obligations", "violated_obligations", "incomplete_obligations_at_trace_end"]].fillna(0)),
        "",
        "结论仅限于：真实状态流能进入所实现的规约监控链路；限时恢复自动机在本次回放使用 2 秒原型运行参数，正式公式仍保留 `d_recovery_s`，不得将该 2 秒解释为物理安全时限。它不代表 HIL 模型在真实飞行中可用，也不输出任何飞控动作。",
        "",
        "## 阈值与时限的下一步依据",
        "",
        "- 先依据 `data/literature_parameter_candidates.csv` 收集官方飞控/文献候选值，并读取实际 PX4 参数，核对机型、模式、单位和变量语义。",
        "- 对高度、三维速度、分离的横滚/俯仰和角速度范数，不能直接套用通用默认值；响应时限也不能无依据地固定为一个通用秒数。",
        "- 当前范围不要求接入 LLM。只有老师明确要求复现原论文的 LLM 环节时，才单独设计 LLM 对照实验。",
        "",
    ])
    (RESULTS / "report.md").write_text(text, encoding="utf-8")


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    pairs = load_pairs()
    build_controlled_benchmark()
    evaluate_controlled_benchmark()
    literature_candidates = pd.read_csv(ROOT / "data" / "literature_parameter_candidates.csv", encoding="utf-8-sig")
    thresholds = derive_hil_thresholds()
    trace = derive_real_trace()
    thresholds.to_csv(RESULTS / "research_monitor_thresholds.csv", index=False, encoding="utf-8-sig")
    trace.to_csv(RESULTS / "real_px4_observable_trace.csv", index=False, encoding="utf-8-sig")
    details, retrieval, nl_summary = evaluate_pairs(pairs)
    details.to_csv(RESULTS / "nl_stl_test_details.csv", index=False, encoding="utf-8-sig")
    retrieval.to_csv(RESULTS / "nl_stl_retrieval_evidence.csv", index=False, encoding="utf-8-sig")
    nl_summary.to_csv(RESULTS / "nl_stl_metrics.csv", index=False, encoding="utf-8-sig")
    nodes, relationships = build_import(thresholds, pairs, RESULTS / "neo4j_import")
    traceability = verify_export()
    if traceability["fully_traced_requirement_count"] != len(pairs):
        raise AssertionError("Not every requirement has an exported traceability path.")
    automata_rows = []
    monitor_rows = []
    for spec in build_monitor_specs(thresholds):
        events, summary = monitor(trace, spec)
        automata_rows.append(events)
        monitor_rows.append(summary)
    pd.concat(automata_rows, ignore_index=True).to_csv(RESULTS / "real_px4_automata_trace.csv", index=False, encoding="utf-8-sig")
    monitor_summary = pd.DataFrame(monitor_rows)
    monitor_summary.to_csv(RESULTS / "real_px4_monitor_summary.csv", index=False, encoding="utf-8-sig")
    # 验证两类受支持模板的实现语义；这不替代真实飞行安全验证。
    semantic_results = evaluate_monitor_semantics()
    write_monitor_semantics_report(semantic_results)
    if not semantic_results["passed"].eq(1).all():
        raise AssertionError("Monitor semantic-oracle evaluation did not fully pass.")
    write_report(thresholds, literature_candidates, {"nodes": len(nodes), "relationships": len(relationships)}, nl_summary, monitor_summary)
    (RESULTS / "run_manifest.json").write_text(json.dumps({"pipeline": "uav_nl_stl_specification", "input_pairs": len(pairs), "development_pairs": int((pairs.split == 'development').sum()), "test_pairs": int((pairs.split == 'test').sum()), "real_trace_has_labels": False, "control_actions_generated": False, "neo4j_database_written": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results written to {RESULTS}")


if __name__ == "__main__":
    main()
