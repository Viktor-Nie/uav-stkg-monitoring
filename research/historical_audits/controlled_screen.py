"""Frozen finite-lexicon screening functions with portable imports only."""
from __future__ import annotations
import re
import pandas as pd
from uav_stkg.graph_constraints import parameterized_formula_skeleton,canonical_formula_serialization

ANGULAR_RATE_CUES = ("角速度范数", "角速度大小", "姿态角速度", "角速度")


ROLL_CUES = ("姿态横滚", "横滚")


PITCH_CUES = ("姿态俯仰", "俯仰")


HEIGHT_CUES = ("相对高度", "高度")


RECOVERY_ACTION_CUES = ("回落到", "回复到", "回到", "降回")


STRICT_TRIGGER_CUES = ("超过", "越过", "过大", "超限")


MODALITY_CUES = ("必须", "需要", "不得", "不能", "不应", "不可", "应", "要", "需")


INCLUSIVE_UPPER_CUES = (
    "必须不超过",
    "始终不超过",
    "不得超过",
    "不能高于",
    "不应大于",
    "不应超过",
    "不可超过",
    "不应高于",
    "不能超过",
    "小于等于",
    "保持低于",
)


CONTROLLED_SCREEN_NEGATIVE_PROBES = (
    (
        "P01_missing_signal",
        "飞行期间不得超过监测上界",
        "ambiguous_or_unobservable_signal",
    ),
    (
        "P02_multiple_signals",
        "三维速度和高度不得超过各自监测上界",
        "ambiguous_or_unobservable_signal",
    ),
    (
        "P03_missing_modality",
        "飞行期间三维速度超过速度监测上界",
        "missing_normative_modality_cue",
    ),
    (
        "P04_incomplete_response",
        "三维速度超过上界时应回到参考范围",
        "incomplete_bounded_response_cues",
    ),
    (
        "P05_conflicting_comparators",
        "当三维速度超过上界时应在规定恢复时限内回到不得超过的速度参考范围",
        "conflicting_strict_and_inclusive_comparator_cues",
    ),
    (
        "P06_unsupported_pattern",
        "飞行期间三维速度应保持稳定",
        "unsupported_temporal_or_comparator_cue",
    ),
)


def longest_present(text: str, cues: tuple[str, ...]) -> str:
    present = [cue for cue in cues if cue in text]
    return max(present, key=len) if present else ""


def screen_controlled_chinese(text: str) -> dict[str, str]:
    """Map only the frozen Chinese requirement text to a signal/template pair.

    This finite catalog rule is intentionally narrower than the separately
    evaluated language models.  It never reads formula text, template labels,
    numerical values, graph edges, or adjudication fields.
    """

    def rejection(
        reason: str,
        *,
        signal_id: str = "",
        signal_cue: str = "",
        modality_cue: str = "",
        comparator_cue: str = "",
    ) -> dict[str, str]:
        return {
            "screen_status": "rejected",
            "screen_reason": reason,
            "matched_signal_cue": signal_cue,
            "screened_signal_id": signal_id,
            "matched_modality_cue": modality_cue,
            "screened_modality": "obligation" if modality_cue else "",
            "matched_comparator_cue": comparator_cue,
            "matched_template_cue": "",
            "screened_template_id": "",
            "screened_trigger_comparator": "",
            "screened_recovery_comparator": "",
            "normalization_note": "",
        }

    signal_matches: list[tuple[str, str]] = []
    cue = longest_present(text, ANGULAR_RATE_CUES)
    if cue:
        signal_matches.append(("ang_rate_norm_rps", cue))
    cue = longest_present(text, ROLL_CUES)
    if cue:
        signal_matches.append(("abs_roll_rad", cue))
    cue = longest_present(text, PITCH_CUES)
    if cue:
        signal_matches.append(("abs_pitch_rad", cue))
    cue = longest_present(text, HEIGHT_CUES)
    if cue:
        signal_matches.append(("height_m", cue))
    if "三维速度" in text:
        signal_matches.append(("speed_3d_mps", "三维速度"))
    elif "速度" in text and "角速度" not in text:
        signal_matches.append(("speed_3d_mps", "速度"))

    if len(signal_matches) != 1:
        return rejection(
            "ambiguous_or_unobservable_signal",
            signal_cue="|".join(cue for _, cue in signal_matches),
        )

    signal_id, signal_cue = signal_matches[0]
    modality_cue = longest_present(text, MODALITY_CUES)
    if not modality_cue:
        return rejection(
            "missing_normative_modality_cue",
            signal_id=signal_id,
            signal_cue=signal_cue,
        )

    recovery_time_cue = "规定恢复时限内" if "规定恢复时限内" in text else ""
    recovery_action_cue = longest_present(text, RECOVERY_ACTION_CUES)
    strict_trigger_cue = longest_present(text, STRICT_TRIGGER_CUES)
    upper_cue = longest_present(text, INCLUSIVE_UPPER_CUES)
    if recovery_time_cue or recovery_action_cue:
        if not (recovery_time_cue and recovery_action_cue and strict_trigger_cue):
            return rejection(
                "incomplete_bounded_response_cues",
                signal_id=signal_id,
                signal_cue=signal_cue,
                modality_cue=modality_cue,
                comparator_cue=strict_trigger_cue,
            )
        if upper_cue:
            return rejection(
                "conflicting_strict_and_inclusive_comparator_cues",
                signal_id=signal_id,
                signal_cue=signal_cue,
                modality_cue=modality_cue,
                comparator_cue=f"{strict_trigger_cue}|{upper_cue}",
            )
        template_id = "bounded_response"
        template_cue = (
            f"{strict_trigger_cue}+{recovery_time_cue}+{recovery_action_cue}"
        )
        comparator_cue = strict_trigger_cue
        trigger_comparator = ">"
        recovery_comparator = "<="
        normalization_note = ""
    elif upper_cue:
        template_id = "invariant_upper"
        template_cue = upper_cue
        comparator_cue = upper_cue
        trigger_comparator = "<="
        recovery_comparator = ""
        normalization_note = (
            "finite-lexicon inclusive normalization; no general strict-to-inclusive rewrite outside this catalog"
            if upper_cue == "保持低于"
            else ""
        )
    else:
        return rejection(
            "unsupported_temporal_or_comparator_cue",
            signal_id=signal_id,
            signal_cue=signal_cue,
            modality_cue=modality_cue,
        )

    return {
        "screen_status": "accepted",
        "screen_reason": "",
        "matched_signal_cue": signal_cue,
        "screened_signal_id": signal_id,
        "matched_modality_cue": modality_cue,
        "screened_modality": "obligation",
        "matched_comparator_cue": comparator_cue,
        "matched_template_cue": template_cue,
        "screened_template_id": template_id,
        "screened_trigger_comparator": trigger_comparator,
        "screened_recovery_comparator": recovery_comparator,
        "normalization_note": normalization_note,
    }


def controlled_screen_negative_probe_audit() -> pd.DataFrame:
    """Exercise narrowly targeted refusal branches of the finite screen.

    These probes are executable regression cases, not an estimate of rejection
    accuracy on an open or independently sampled language distribution.
    """

    rows: list[dict[str, str]] = []
    for probe_id, source_text, expected_reason in CONTROLLED_SCREEN_NEGATIVE_PROBES:
        screened = screen_controlled_chinese(source_text)
        passed = (
            screened["screen_status"] == "rejected"
            and screened["screen_reason"] == expected_reason
        )
        rows.append(
            {
                "probe_id": probe_id,
                "source_text_zh": source_text,
                "expected_status": "rejected",
                "expected_reason": expected_reason,
                "observed_status": screened["screen_status"],
                "observed_reason": screened["screen_reason"],
                "probe_status": "passed" if passed else "failed",
                "evaluation_boundary": (
                    "targeted regression probe; not open-domain rejection accuracy"
                ),
            }
        )
    audit = pd.DataFrame(rows)
    failed = audit[~audit["probe_status"].eq("passed")]
    if not failed.empty:
        raise AssertionError(
            "controlled-screen refusal probes failed:\n"
            + failed.to_string(index=False)
        )
    return audit


def controlled_conversion_audit(
    pairs: pd.DataFrame, catalog: pd.DataFrame
) -> pd.DataFrame:
    """Audit the 24 finite-lexicon outputs against graph targets after screening."""

    graph_rows = catalog.set_index("formula_id")
    rows: list[dict[str, object]] = []
    for pair in pairs.itertuples(index=False):
        screened = screen_controlled_chinese(str(pair.nl))
        graph = graph_rows.loc[str(pair.id)]
        screened_skeleton = (
            parameterized_formula_skeleton(
                screened["screened_template_id"], screened["screened_signal_id"]
            )
            if screened["screen_status"] == "accepted"
            else ""
        )
        skeleton_match = canonical_formula_serialization(
            screened_skeleton
        ) == canonical_formula_serialization(
            str(graph["stored_parameterized_formula"])
        )
        comparator_match = (
            screened["screened_trigger_comparator"] == ">"
            and screened["screened_recovery_comparator"] == "<="
            if str(graph["template_id"]) == "bounded_response"
            else screened["screened_trigger_comparator"] == "<="
            and screened["screened_recovery_comparator"] == ""
        )
        passed = (
            screened["screen_status"] == "accepted"
            and screened["screened_signal_id"] == str(graph["signal_id"])
            and screened["screened_template_id"] == str(graph["template_id"])
            and screened["screened_modality"] == "obligation"
            and bool(screened["matched_modality_cue"])
            and bool(screened["matched_comparator_cue"])
            and comparator_match
            and skeleton_match
        )
        rows.append(
            {
                "requirement_id": str(pair.id),
                "screen_input_field": "nl",
                "source_text_zh": str(pair.nl),
                **screened,
                "graph_signal_id": str(graph["signal_id"]),
                "graph_template_id": str(graph["template_id"]),
                "screen_reconstructed_parameterized_formula": screened_skeleton,
                "stored_graph_parameterized_formula": str(
                    graph["stored_parameterized_formula"]
                ),
                "post_screen_formula_skeleton_status": (
                    "passed" if skeleton_match else "failed"
                ),
                "post_screen_comparison_status": "passed" if passed else "failed",
                "evaluation_boundary": (
                    "same-catalog deterministic consistency audit; not held-out language accuracy"
                ),
                "numeric_values_read_from_text": False,
            }
        )
    audit = pd.DataFrame(rows)
    failed = audit[~audit["post_screen_comparison_status"].eq("passed")]
    if not failed.empty:
        raise AssertionError(
            "controlled Chinese screening disagrees with frozen graph targets:\n"
            + failed[
                [
                    "requirement_id",
                    "source_text_zh",
                    "screened_signal_id",
                    "screened_template_id",
                    "graph_signal_id",
                    "graph_template_id",
                ]
            ].to_string(index=False)
        )
    return audit
