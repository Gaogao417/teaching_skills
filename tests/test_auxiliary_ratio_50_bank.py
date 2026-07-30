from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = REPO_ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from author_auxiliary_ratio_50_bank import (  # noqa: E402
    RATIO_SEGMENTS,
    ROUTES,
    auxiliary_route,
    author_item,
    select_cases,
    staged_model_share_additions,
)


def test_every_item_preserves_first_model_shares_and_adds_one_target_share() -> None:
    cases = select_cases()

    assert len(cases) == 50
    for index, values in enumerate(cases):
        block, _, _ = author_item(index, values)
        known, target = ROUTES[index]
        steps = block["solution_steps"]

        assert len(steps) == 4
        assert steps[0]["title"] == "作辅助线"
        assert steps[1]["title"].startswith("解第一组")
        assert steps[2]["title"].startswith("解第二组")
        assert steps[1]["title"].endswith(("A字", "8字"))
        assert steps[2]["title"].endswith(("A字", "8字"))
        assert "diagram_slot" not in steps[3]

        helper_texts = steps[0]["diagram_slot"]["visual_requirements"][
            "required_visible_annotations"
        ]["texts"]
        first_texts = steps[1]["diagram_slot"]["visual_requirements"][
            "required_visible_annotations"
        ]["texts"]
        second_texts = steps[2]["diagram_slot"]["visual_requirements"][
            "required_visible_annotations"
        ]["texts"]

        assert len(helper_texts) == 4
        models = list(auxiliary_route(set(known) | {target})["models"])
        if models[0]["anchor"] not in known:
            models.reverse()
        additions = staged_model_share_additions(models, values, known, target)

        assert len(first_texts) == len(helper_texts) + len(additions[0])
        assert len(second_texts) == len(first_texts) + len(additions[1])
        assert {item["color"] for item in helper_texts} == {"#2563eb"}
        assert {item["color"] for item in first_texts[4:]} <= {"#dc2626"}
        assert {item["color"] for item in second_texts[len(first_texts) :]} == {"#059669"}
        assert second_texts[: len(first_texts)] == first_texts
        for texts in (helper_texts, first_texts, second_texts):
            segment_keys = ["".join(sorted(item["target"])) for item in texts]
            assert len(segment_keys) == len(set(segment_keys))
            for item in texts:
                segment = "".join(item["target"])
                if segment in {"BE", "BC"}:
                    assert item["segment_position"] == "legend"

        if index in {3, 15, 27, 39}:
            ap_labels = [
                item
                for item in second_texts
                if item["target"] == ["A", "P"]
            ]
            assert len(ap_labels) == 1
            assert ap_labels[0]["segment_position"] == "auto"
            first_legend_segments = {
                "".join(item["target"])
                for item in first_texts
                if item.get("segment_position") == "legend"
            }
            second_legend_segments = {
                "".join(item["target"])
                for item in second_texts
                if item.get("segment_position") == "legend"
            }
            assert first_legend_segments == {"BE"}
            assert second_legend_segments == {"BE", "BP", "PE"}

        target_first, target_second = RATIO_SEGMENTS[target]
        final_segments = {"".join(sorted(item["target"])) for item in second_texts}
        assert "".join(sorted(target_first)) in final_segments
        assert "".join(sorted(target_second)) in final_segments

        expected = f"${target_first}:{target_second}={values[target].numerator}:{values[target].denominator}$。"
        assert block["answer"] == expected
        assert all(key in {"x", "w", "y", "z"} for key in known)


def test_q002_reuses_blue_dc_and_bd_then_marks_the_requested_pair() -> None:
    values = select_cases()[1]
    block, _, _ = author_item(1, values)
    first_texts = block["solution_steps"][1]["diagram_slot"]["visual_requirements"][
        "required_visible_annotations"
    ]["texts"]
    second_texts = block["solution_steps"][2]["diagram_slot"]["visual_requirements"][
        "required_visible_annotations"
    ]["texts"]

    assert first_texts[-1]["target"] == ["E", "F"]
    assert first_texts[-1]["text"] == "5/2份"
    assert all(item["id"] != "model-1-dc" for item in first_texts)
    assert second_texts[: len(first_texts)] == first_texts
    assert all(item["id"] != "model-2-bd" for item in second_texts)
    assert [(item["target"], item["text"]) for item in second_texts[-2:]] == [
        (["B", "P"], "8份"),
        (["P", "E"], "5份"),
    ]
