#!/usr/bin/env python3
"""Author the compact, diagram-led two-ratio auxiliary-line explanation."""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any

from author_auxiliary_ratio_50_bank import (
    auxiliary_route,
    diagram_slot,
    ratio_values,
    write_yaml,
)


DEFAULT_OUTPUT = Path(
    "artifacts/专题/2026-07-12-比例辅助线两组比例-待审核/"
    "02-student-explanation.plan.assignment.yaml"
)


def explanation_slot(
    stage: str,
    *,
    stem: str,
    values: dict[str, Fraction],
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = diagram_slot(
        "Q900",
        stem,
        values,
        ("x", "w"),
        "y",
        stage=stage,
        ordered_models=models if stage != "prompt" else None,
    )
    slot = deepcopy(raw)
    suffix = stage
    slot_id = f"explanation.example.{suffix}"
    old_prompt = "question_bank.auxiliary50.q900.prompt"
    slot["slot_id"] = slot_id
    slot["diagram_ref"] = slot_id
    if stage == "prompt":
        slot["placement"] = "block_center"
        slot["layout_role"] = "center_block"
        slot["display_profile"] = "worksheet_geometry_center"
        slot["teaching_intent"] = "explanation_prompt"
    else:
        slot["reuse_geometry_from"] = "explanation.example.prompt"
        slot["placement"] = "step_diagram"
        slot["layout_role"] = "solution_annotation"
        slot["display_profile"] = "worksheet_geometry_center"
        slot["teaching_intent"] = "explanation_solution"
        constraints = slot["semantic_constraints"]["given_constraints"]
        slot["semantic_constraints"]["given_constraints"] = [
            item.replace(old_prompt, "explanation.example.prompt")
            if isinstance(item, str)
            else item
            for item in constraints
        ]
    return slot


def build_assignment() -> dict[str, Any]:
    values = ratio_values(Fraction(2, 3), Fraction(4, 5))
    route = auxiliary_route({"x", "w", "y"})
    models = list(route["models"])
    stem = (
        r"如图，点 $D$ 在线段 $BC$ 上，点 $E$ 在线段 $AC$ 上，"
        r"$AD$ 与 $BE$ 交于点 $P$。已知 $AE:EC=2:3$，"
        r"$BD:DC=4:5$，求 $AP:PD$。"
    )
    prompt = explanation_slot("prompt", stem=stem, values=values, models=models)
    helper = explanation_slot("helper", stem=stem, values=values, models=models)
    model1 = explanation_slot("model1", stem=stem, values=values, models=models)
    model2 = explanation_slot("model2", stem=stem, values=values, models=models)
    helper["caption"] = r"蓝字标出题目给出的两组比；过 $C$ 作 $CF\parallel AD$。"
    model1["caption"] = "第二步解 8 字：由蓝色 $2:3$ 标出红色 $AP:CF=2:3$。"
    model2["caption"] = "第三步解 A 字：第一组红字保持不变，只新增 $PD=4/3$ 份。"

    return {
        "meta": {
            "title": "比例辅助线两组整数比：两幅相似图逐步标份数",
            "grade": "八年级",
            "subject": "数学",
            "version": "student",
            "show_answers": True,
            "source_artifacts": {
                "review_draft": (
                    "artifacts/专题/2026-07-12-比例辅助线两组比例-待审核/"
                    "02-student-explanation.review.md"
                ),
                "structure_reference": (
                    "artifacts/专题/2026-07-09-比例辅助线边比/01-structure-analysis.md"
                ),
            },
        },
        "render": {
            "template": "exam-zh-explanation",
            "paper_size": "a4paper",
            "show_step_numbers": True,
        },
        "sections": [
            {
                "id": "two-similar-share-labels",
                "title": "比例辅助线：解两组 A/8 字，把目标边标成份数",
                "show_title": True,
                "type": "explanation",
                "visibility": "student",
                "blocks": [
                    {
                        "type": "problemcard",
                        "id": "example-card",
                        "label": "例题",
                        "stem_latex": stem,
                        "diagram_slot": prompt,
                    },
                    {
                        "type": "route",
                        "id": "example-route",
                        "show_navigation": False,
                        "steps": [
                            {
                                "id": "step-helper",
                                "latex": "作辅助线",
                                "content_latex": (
                                    r"过 $C$ 作 $CF\parallel AD$，交直线 $BE$ 于 $F$。"
                                ),
                                "diagram_slot": helper,
                            },
                            {
                                "id": "step-eight",
                                "latex": "解第一组 8 字",
                                "content_latex": (
                                    r"$\because CF\parallel AP$。\\ "
                                    r"$\therefore \triangle EAP\sim\triangle ECF$。\\ "
                                    r"$AE:EC=2:3$，故 $AP:CF=2:3$。"
                                ),
                                "diagram_slot": model1,
                            },
                            {
                                "id": "step-a",
                                "latex": "解第二组 A 字",
                                "content_latex": (
                                    r"$BD:BC=4:(4+5)=4:9$。\\ "
                                    r"$\because CF\parallel DP$。\\ "
                                    r"$\therefore \triangle BDP\sim\triangle BCF$。沿用 $CF=3$ 份，故只标 $PD=\frac{4}{3}$ 份。"
                                ),
                                "diagram_slot": model2,
                            },
                            {
                                "id": "step-unify",
                                "latex": "比较两条边的份数",
                                "content_latex": (
                                    r"图中已有 $AP=2$ 份、$PD=\frac{4}{3}$ 份。\\ "
                                    r"$\therefore AP:PD=2:\frac{4}{3}=3:2$。"
                                ),
                            },
                        ],
                    },
                    {
                        "type": "dual_explanation",
                        "id": "example-solution",
                        "side_title": "看图提醒",
                        "side_items": [
                            {
                                "kind": "hint",
                                "title": "颜色怎么读",
                                "content_latex": "蓝字只表示题目给出的比；红字表示本步由相似得到的对应边份数。",
                            },
                            {
                                "kind": "mistake",
                                "title": "第二组先补整段",
                                "content_latex": "$BD:DC=4:5$，所以 $BD:BC=4:9$。",
                            },
                        ],
                        "solution_title": "解答",
                        "solution_step_ids": [
                            "step-helper",
                            "step-eight",
                            "step-a",
                            "step-unify",
                        ],
                    },
                ],
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    write_yaml(output, build_assignment())
    print(f"authored compact explanation at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
