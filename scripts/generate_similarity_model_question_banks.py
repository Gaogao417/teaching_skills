#!/usr/bin/env python3
"""Generate three 50-item similarity-model question-bank plans.

The script intentionally delegates number selection to the reviewed training-number
selector, freezes every selected entry in coverage-plan.yaml, and writes one teacher
plan assignment per item. Diagram resolution remains a separate workflow stage.
"""

from __future__ import annotations

import argparse
import math
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / ".codex/skills/math-topic-question-bank/scripts/select_training_numbers.py"
PYTHON = ROOT / ".venv/bin/python"
DATABASE_ID = "question-bank-training-numbers"


@dataclass(frozen=True)
class ExactValue:
    coefficient: Fraction
    radicand: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ExactValue":
        return cls(Fraction(str(payload["coefficient"])), int(payload["radicand"]))

    def scaled(self, multiplier: Fraction) -> "ExactValue":
        return ExactValue(self.coefficient * multiplier, self.radicand)

    def numeric(self) -> float:
        return float(self.coefficient) * math.sqrt(self.radicand)

    def latex(self) -> str:
        c = self.coefficient
        if self.radicand == 1:
            return fraction_latex(c)
        radical = rf"\sqrt{{{self.radicand}}}"
        if c == 1:
            return radical
        return f"{fraction_latex(c)}{radical}"

    def wl(self) -> str:
        c = fraction_plain(self.coefficient)
        if self.radicand == 1:
            return c
        if self.coefficient == 1:
            return f"Sqrt[{self.radicand}]"
        return f"({c}) Sqrt[{self.radicand}]"


def fraction_plain(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def fraction_latex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def run_selector(family: str, count: int, seed: int) -> dict[str, Any]:
    command = [
        str(PYTHON),
        str(SELECTOR),
        "--family",
        family,
        "--count",
        str(count),
        "--seed",
        str(seed),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    return yaml.safe_load(completed.stdout)


def select_pairs(seed: int) -> list[dict[str, Any]]:
    rational_payload = run_selector("rational_multiple_pairs", 25, seed)
    radical_payloads = (
        run_selector("radical_multiple_pairs", 50, seed + 1000),
        run_selector("radical_multiple_pairs", 50, seed + 2000),
    )
    radicals = []
    seen_ids: set[str] = set()
    for radical_payload in radical_payloads:
        for entry in radical_payload["entries"]:
            k = int(entry["parameters"]["k"])
            values = entry["values"]
            if entry["id"] in seen_ids or math.isqrt(k) ** 2 == k:
                continue
            if not all(int(value["radicand"]) > 1 for value in values):
                continue
            radicals.append(entry)
            seen_ids.add(entry["id"])
    if len(radicals) < 25:
        raise RuntimeError(f"seed {seed}: only {len(radicals)} reviewed fully-irrational pairs")
    rational = [{**entry, "selection_class": "fraction_pair"} for entry in rational_payload["entries"]]
    radical = [{**entry, "selection_class": "irrational_pair"} for entry in radicals[:25]]
    pairs: list[dict[str, Any]] = []
    for left, right in zip(rational, radical, strict=True):
        pairs.extend([left, right])
    return pairs


@dataclass(frozen=True)
class ModelSpec:
    key: str
    bank_dir: str
    topic: str
    source_explanation: str
    similarity_statement: str
    pairs: tuple[tuple[str, str], ...]
    allowed_pair_routes: tuple[tuple[int, int], ...]
    base_stem: str
    scene_points: tuple[str, ...]
    anchor_points: tuple[str, ...]
    constructed_points: tuple[str, ...]
    scene_constraints: tuple[str, ...]
    segments: tuple[tuple[str, str], ...]
    labels: dict[str, str]
    caption: str
    given_constraints: tuple[str, ...]


MODELS = (
    ModelSpec(
        key="reverse_a",
        bank_dir="2026-07-16-反A形相似",
        topic="反A形相似",
        source_explanation="../../专题/2026-07-14-反A形相似求第四边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle PAB\sim\triangle PDC",
        pairs=(("PA", "PD"), ("PB", "PC"), ("AB", "DC")),
        allowed_pair_routes=((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
        base_stem=r"如图，$\angle PAB=\angle PDC$。",
        scene_points=("P", "A", "B", "C", "D"),
        anchor_points=("P", "C", "D"),
        constructed_points=("A", "B"),
        scene_constraints=(
            "Element[A, Line[{P, C}]]",
            "Element[B, Line[{P, D}]]",
            "EuclideanDistance[P, A] > 0",
            "EuclideanDistance[A, C] > 0",
            "EuclideanDistance[P, B] > 0",
            "EuclideanDistance[B, D] > 0",
            "EuclideanDistance[P, C] == EuclideanDistance[P, A] + EuclideanDistance[A, C]",
            "EuclideanDistance[P, D] == EuclideanDistance[P, B] + EuclideanDistance[B, D]",
            "PlanarAngle[{P, A, B}] == PlanarAngle[{P, D, C}]",
            "TriangleMeasurement[{P, A, B}, {\"InteriorAngle\", P}] >= 8 Degree",
            "TriangleMeasurement[{P, A, B}, {\"InteriorAngle\", A}] >= 8 Degree",
            "TriangleMeasurement[{P, A, B}, {\"InteriorAngle\", B}] >= 8 Degree",
            'GeometricAssertion[Line[{P, D}], "Horizontal"]',
            'GeometricAssertion[Line[{P, D}], "Rightward"]',
            'GeometricAssertion[{P, D, C}, "Counterclockwise"]',
        ),
        segments=(("P", "C"), ("P", "D"), ("A", "B"), ("C", "D")),
        labels={"P": "below left", "A": "above left", "B": "below", "C": "above right", "D": "below right"},
        caption="沿题设等角的顶点顺序，找出两组三角形的对应边。",
        given_constraints=(
            "A lies strictly between P and C",
            "B lies strictly between P and D",
            "angle PAB equals angle PDC",
        ),
    ),
    ModelSpec(
        key="butterfly",
        bank_dir="2026-07-16-蝶形相似",
        topic="蝶形相似",
        source_explanation="../../专题/2026-07-14-蝶形相似求第四边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle AOC\sim\triangle DOB",
        pairs=(("AO", "OD"), ("OC", "OB"), ("AC", "DB")),
        allowed_pair_routes=((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
        base_stem=r"如图，$\angle OAC=\angle ODB$。",
        scene_points=("A", "O", "B", "C", "D"),
        anchor_points=("A", "B", "C", "D"),
        constructed_points=("O",),
        scene_constraints=(
            "Element[O, Line[{A, B}]]",
            "Element[O, Line[{C, D}]]",
            "EuclideanDistance[A, O] > 0",
            "EuclideanDistance[O, B] > 0",
            "EuclideanDistance[C, O] > 0",
            "EuclideanDistance[O, D] > 0",
            "EuclideanDistance[A, B] == EuclideanDistance[A, O] + EuclideanDistance[O, B]",
            "EuclideanDistance[C, D] == EuclideanDistance[C, O] + EuclideanDistance[O, D]",
            "PlanarAngle[{O, A, C}] == PlanarAngle[{O, D, B}]",
            "TriangleMeasurement[{A, O, C}, {\"InteriorAngle\", A}] >= 8 Degree",
            "TriangleMeasurement[{A, O, C}, {\"InteriorAngle\", O}] >= 8 Degree",
            "TriangleMeasurement[{A, O, C}, {\"InteriorAngle\", C}] >= 8 Degree",
            'GeometricAssertion[Line[{A, B}], "Horizontal"]',
            'GeometricAssertion[Line[{A, B}], "Rightward"]',
            'GeometricAssertion[{A, B, C}, "Counterclockwise"]',
        ),
        segments=(("A", "B"), ("C", "D"), ("A", "C"), ("D", "B")),
        labels={"A": "below left", "O": "below", "B": "below right", "C": "above right", "D": "below right"},
        caption="先用对顶角补齐第二组等角，再按顶点顺序配边。",
        given_constraints=(
            "A, O, B are collinear with O strictly between A and B",
            "C, O, D are collinear with O strictly between C and D",
            "angle OAC equals angle ODB",
        ),
    ),
    ModelSpec(
        key="nested",
        bank_dir="2026-07-16-子母型相似",
        topic="子母型相似",
        source_explanation="../../专题/2026-07-14-子母型相似比与对应边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle ABD\sim\triangle ACB",
        pairs=(("AB", "AC"), ("AD", "AB"), ("BD", "BC")),
        allowed_pair_routes=((0, 2), (2, 0)),
        base_stem=r"如图，在 $\triangle ABC$ 中，$\angle ABD=\angle ACB$。",
        scene_points=("A", "B", "C", "D"),
        anchor_points=("A", "B", "C"),
        constructed_points=("D",),
        scene_constraints=(
            "Element[D, Line[{A, C}]]",
            "EuclideanDistance[A, D] > 0",
            "EuclideanDistance[D, C] > 0",
            "EuclideanDistance[A, C] == EuclideanDistance[A, D] + EuclideanDistance[D, C]",
            "PlanarAngle[{A, B, D}] == PlanarAngle[{A, C, B}]",
            "TriangleMeasurement[{A, B, C}, {\"InteriorAngle\", A}] >= 8 Degree",
            "TriangleMeasurement[{A, B, C}, {\"InteriorAngle\", B}] >= 8 Degree",
            "TriangleMeasurement[{A, B, C}, {\"InteriorAngle\", C}] >= 8 Degree",
            'GeometricAssertion[Line[{A, C}], "Horizontal"]',
            'GeometricAssertion[Line[{A, C}], "Rightward"]',
            'GeometricAssertion[{A, C, B}, "Counterclockwise"]',
        ),
        segments=(("A", "B"), ("B", "C"), ("C", "A"), ("B", "D")),
        labels={"A": "below left", "B": "above", "C": "below right", "D": "below"},
        caption="先确认对应边，再判断题中的线段是否属于相似三角形。",
        given_constraints=(
            "D lies strictly between A and C",
            "angle ABD equals angle ACB",
        ),
    ),
)


STEM_MODES = (
    ("三边求第四边", "changed_question", "由三条已知边求第四条对应边"),
    ("先证相似再求边", "partially_hidden", "先补出第二组等角并证明相似，再求边"),
    ("先写对应关系再求边", "changed_representation", "先写三组对应边和相似比，再求边"),
    ("完整判定与计算", "packaged_condition", "完整写出相似判定、对应关系、比例计算和验算"),
)


def difficulty(index: int) -> str:
    if index < 16:
        return "foundation"
    if index < 36:
        return "standard"
    return "challenge"


def values_of(entry: dict[str, Any]) -> tuple[ExactValue, ExactValue]:
    first, second = entry["values"]
    return ExactValue.from_payload(first), ExactValue.from_payload(second)


def distance_constraint(segment: str, normalized_value: float) -> str:
    if len(segment) != 2:
        raise ValueError(f"expected a two-point segment name, got {segment!r}")
    return f"EuclideanDistance[{segment[0]}, {segment[1]}] == {normalized_value:.10g}"


def normalized_distance_constraints(known_lengths: dict[str, ExactValue]) -> list[str]:
    scale = 6.0 / max(value.numeric() for value in known_lengths.values())
    return [
        distance_constraint(segment, value.numeric() * scale)
        for segment, value in known_lengths.items()
    ]


def diagram_slot(
    model: ModelSpec,
    item_id: str,
    stem: str,
    geometry_lengths: dict[str, ExactValue],
    seed: int,
) -> dict[str, Any]:
    points = ", ".join(model.scene_points)
    constraints = list(model.scene_constraints) + normalized_distance_constraints(geometry_lengths)
    scene_code = f"GeometricScene[{{{points}}}, {{{', '.join(constraints)}}}]"
    return {
        "slot_id": f"question_bank.{model.key}.{item_id.lower()}.prompt",
        "diagram_ref": f"question_bank.{model.key}.{item_id.lower()}.prompt",
        "variant": "prompt",
        "disclosure_policy": "clean",
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "question_sidecar",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": model.caption,
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "engine_options": {
            "scene_payload": {
                "scene_code": scene_code,
                "points": list(model.scene_points),
                "point_roles": {
                    "anchors": list(model.anchor_points),
                    "constructed": list(model.constructed_points),
                    "auxiliary": [],
                },
                "diagram_spec": {
                    "type": "synthetic_geometry",
                    "segments": [{"from": a, "to": b} for a, b in model.segments],
                    "markers": [],
                    "labels": {point: {"text": point, "placement": placement} for point, placement in model.labels.items()},
                    "constraints": list(model.given_constraints),
                    "teaching_focus": ["identify equal angles", "match vertices before matching sides"],
                },
                "rationale": "先用一组完整对应边锁定相似比，再约束目标小边；题干中的目标大边由相似关系等价确定。所有距离统一缩放，图中不标边长数值。",
                "model_used": "deterministic-similarity-model-question-bank",
                "model_attempts": [],
            },
            "seed": seed,
        },
        "teaching_intent": "practice_prompt",
        "problem_context": {
            "stem_latex": stem,
            "source_problem_text": "逐题独立生成干净题图。边长比例与题干一致；图中只保留点名和必要标记，不标边长数值、相似结论、对应箭头、比例式、推导或答案。",
        },
        "semantic_constraints": {
            "given_objects": list(model.scene_points),
            "given_constraints": list(model.given_constraints)
            + ["one full corresponding-side pair fixes the scale and the target small side fixes the shape; the stated target large side is implied by similarity"],
            "clean_forbidden": [
                "do not show the final answer",
                "do not label the derived triangle similarity",
                "do not draw numeric side-length labels",
                "do not add auxiliary lines or solution annotations",
            ],
        },
    }


def make_problem(
    model: ModelSpec,
    item_id: str,
    entry: dict[str, Any],
    task_index: int,
    item_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    small, large = values_of(entry)
    combo_count = len(model.allowed_pair_routes) * 2
    combo_index = task_index % combo_count
    route = model.allowed_pair_routes[combo_index // 2]
    source_pair = model.pairs[route[0]]
    target_pair = model.pairs[route[1]]
    multiplier = (
        Fraction(1)
        if model.key in {"reverse_a", "nested"}
        else (Fraction(2), Fraction(3), Fraction(4), Fraction(1, 2), Fraction(3, 2))[task_index % 5]
    )
    target_small = small.scaled(multiplier)
    target_large = large.scaled(multiplier)
    ask_large = combo_index % 2 == 0
    known_target_name, known_target_value = (
        (target_pair[0], target_small) if ask_large else (target_pair[1], target_large)
    )
    unknown_target_name, answer_value = (
        (target_pair[1], target_large) if ask_large else (target_pair[0], target_small)
    )
    mode_index = (task_index // combo_count) % len(STEM_MODES)
    title, variation, training_action = STEM_MODES[mode_index]
    knowns = (
        rf"${source_pair[0]}={small.latex()}$，${source_pair[1]}={large.latex()}$，"
        rf"${known_target_name}={known_target_value.latex()}$"
    )
    endings = (
        rf"已知 {knowns}，求 ${unknown_target_name}$。",
        rf"已知 {knowns}。求证 ${model.similarity_statement}$，并求 ${unknown_target_name}$。",
        rf"已知 {knowns}。写出三组对应边及相似比，并求 ${unknown_target_name}$。",
        rf"已知 {knowns}。先证明 ${model.similarity_statement}$，再写出对应关系并求 ${unknown_target_name}$。",
    )
    stem = f"{model.base_stem}\n\n{endings[mode_index]}"
    geometry_lengths = {
        source_pair[0]: small,
        source_pair[1]: large,
        target_pair[0]: target_small,
    }
    direction = "小三角形边与大三角形对应边之比" if ask_large else "大三角形边与小三角形对应边之比"
    if ask_large:
        ratio_equation = (
            rf"\dfrac{{{source_pair[0]}}}{{{source_pair[1]}}}="
            rf"\dfrac{{{target_pair[0]}}}{{{target_pair[1]}}}"
        )
    else:
        ratio_equation = (
            rf"\dfrac{{{source_pair[1]}}}{{{source_pair[0]}}}="
            rf"\dfrac{{{target_pair[1]}}}{{{target_pair[0]}}}"
        )
    answer = rf"${unknown_target_name}={answer_value.latex()}$。"
    solution_steps = [
        {"title": "见等角，找相似", "content": f"由题设等角和构型自带的第二组等角，得 ${model.similarity_statement}$。"},
        {"title": "按顶点写对应边", "content": f"三组小边与大边依次为：" + "，".join(rf"${a}\leftrightarrow {b}$" for a, b in model.pairs) + "。"},
        {"title": "保持比例方向一致", "content": rf"取 {direction}，可列 ${ratio_equation}$。"},
        {"title": "代入并验算", "content": rf"代入已知量解得 ${unknown_target_name}={answer_value.latex()}$；两组对应边的比均等于同一相似比。"},
    ]
    block = {
        "type": "problem",
        "id": item_id,
        "points": 10,
        "label": title,
        "stem_latex": stem,
        "answer_space": {"type": "steps", "height": "48mm", "step_count": 4},
        "answer": answer,
        "explanation": f"先由等角判相似，再按同序顶点确定对应边；本题所用数值对来自 {entry['family']}。",
        "solution_steps": solution_steps,
        "teaching": {
            "teaching_goal": training_action,
            "source_relations": [f"explanation:{model.key}", "similar_triangles_corresponding_sides"],
            "expected_blocker": "没有先锁定等角顶点，或两组比例的大小方向不一致。",
            "entry_point": "equal_angles_to_similarity_to_correspondence",
            "scaffold_level": "medium" if difficulty(item_index) != "challenge" else "low",
            "variation_depth": variation,
            "complexity_note": "只训练 AA 判定、对应边和一层比例；不引入面积、周长或额外辅助线。",
            "upgrade_rule": "能独立写出同序相似式并用另一组对应边验算。",
            "fallback_move": "先标出两个相等角的顶点，再逐个写出对应点。",
            "number_selection": {
                "database_id": DATABASE_ID,
                "family_id": entry["family"],
                "entry_id": entry["id"],
                "selection_class": entry["selection_class"],
            },
        },
        "diagram_slot": diagram_slot(model, item_id, stem, geometry_lengths, 716000 + item_index),
    }
    slot = {
        "id": item_id,
        "difficulty": difficulty(item_index),
        "training_action": training_action,
        "question_type": "problem",
        "variation_dimension": variation,
        "diagram_requirement": "prompt_only",
        "number_selection": {
            "database_id": DATABASE_ID,
            "family_id": entry["family"],
            "entry_id": entry["id"],
            "selection_class": entry["selection_class"],
            "pair_latex": [small.latex(), large.latex()],
        },
        "source_pair": list(source_pair),
        "target_pair": list(target_pair),
        "title": title,
    }
    return block, slot


def assignment(model: ModelSpec, item_id: str, block: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {
            "title": f"{model.topic} · {item_id} · 教师版",
            "grade": "八年级",
            "subject": "数学",
            "total_points": 10,
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {
                "explanation": model.source_explanation,
                "diagram_policy": "一题一张独立 prompt 图；题图不泄露相似结论或答案",
            },
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "after_page_break",
        },
        "sections": [
            {
                "id": "question",
                "title": "专题题",
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


def generate_model(model: ModelSpec, output_root: Path, seed: int) -> None:
    bank_root = output_root / model.bank_dir
    pairs = select_pairs(seed)
    slots = []
    items = []
    for index, entry in enumerate(pairs):
        item_id = f"Q{index + 1:03d}"
        task_index = index // 2
        block, slot = make_problem(model, item_id, entry, task_index, index)
        slots.append(slot)
        item_root = bank_root / "items" / item_id
        write_yaml(item_root / "teacher.plan.assignment.yaml", assignment(model, item_id, block))
        items.append(
            {
                "id": item_id,
                "title": slot["title"],
                "question_type": "problem",
                "difficulty": difficulty(index),
                "skill_tags": ["等角找相似", "对应顶点", "对应边比例", entry["selection_class"]],
                "variation_dimension": slot["variation_dimension"],
                "diagram_requirement": "prompt_only",
                "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
                "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
                "weight": 1.0,
                "enabled": True,
            }
        )
    coverage = {
        "topic": model.topic,
        "source_explanation": model.source_explanation,
        "target_count": 50,
        "difficulty_distribution": {"foundation": 16, "standard": 20, "challenge": 14},
        "number_distribution": {"fraction_pair": 25, "irrational_pair": 25},
        "design_note": "每个教学动作各配一组分数对和一组比值为无理数、且两项本身均为无理数的根式对。",
        "slots": slots,
    }
    manifest = {
        "schema": "math_topic_question_bank/v1",
        "bank": {
            "id": f"{model.key}-similarity-2026-07-16",
            "topic": model.topic,
            "grade": "八年级",
            "subject": "数学",
            "source_explanation": model.source_explanation,
            "status": "plan",
            "target_count": 50,
        },
        "items": items,
    }
    write_yaml(bank_root / "coverage-plan.yaml", coverage)
    write_yaml(bank_root / "question-bank.yaml", manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/题库")
    args = parser.parse_args()
    for offset, model in enumerate(MODELS):
        generate_model(model, args.output_root.resolve(), 716 + 97 * offset)
        print(f"generated {model.topic}: 50 plans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
