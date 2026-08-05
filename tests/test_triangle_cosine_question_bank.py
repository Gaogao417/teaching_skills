from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
DATA = ROOT / ".codex/skills/math-topic-question-bank/data"
ASSIGNMENT_VALIDATOR = ROOT / ".codex/skills/math-assignment-latex/scripts/validate_assignment.py"
sys.path.insert(0, str(SCRIPTS))

from generate_triangle_cosine_database import generate as generate_triangles  # noqa: E402
from generate_triangle_cosine_questions import generate as generate_questions  # noqa: E402
from generate_triangle_trig_ratio_database import generate as generate_trig_ratios  # noqa: E402
from triangle_cosine_contracts import (  # noqa: E402
    PublishedQuestionBank,
    QuestionReview,
)


def dump_model(path: Path, model) -> None:
    path.write_text(
        yaml.safe_dump(
            model.model_dump(by_alias=True, mode="json"),
            allow_unicode=True,
            sort_keys=False,
            width=140,
        ),
        encoding="utf-8",
    )


def build_pipeline(tmp_path: Path):
    trig = generate_trig_ratios(
        DATA / "training-number-database.yaml",
        DATA / "training-number-review.yaml",
    )
    trig_path = tmp_path / "trig.yaml"
    dump_model(trig_path, trig)
    triangles = generate_triangles(trig_path)
    triangle_path = tmp_path / "triangles.yaml"
    dump_model(triangle_path, triangles)
    candidates = generate_questions(triangles, triangle_path, max_per_type=100)
    candidate_path = tmp_path / "candidates.yaml"
    dump_model(candidate_path, candidates)
    return trig, triangles, candidates, candidate_path


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory):
    tmp_path = tmp_path_factory.mktemp("triangle-trig-pipeline")
    return tmp_path, *build_pipeline(tmp_path)


def test_pipeline_materializes_three_strict_layers(pipeline) -> None:
    _, trig, triangles, candidates, _ = pipeline

    assert len(trig.entries) > 9
    assert any(
        value.radicand not in {1, 2, 3}
        for entry in trig.entries
        for value in (
            entry.ratios.sin,
            entry.ratios.cos,
            entry.ratios.tan,
            entry.ratios.cot,
        )
        if value is not None
    )
    assert len(triangles.triangles) >= 20
    assert {len(case.triangle_ids) for case in triangles.ssa_cases} == {1, 2}
    assert {question.problem_type for question in candidates.questions} == {
        "sss",
        "sas",
        "ssa",
        "aas",
        "asa",
    }

    trig_ids = {entry.id for entry in trig.entries}
    triangle_ids = {triangle.id for triangle in triangles.triangles}
    assert all(
        set(triangle.source_trig_ratio_ids).issubset(trig_ids)
        for triangle in triangles.triangles
    )
    assert all(
        set(question.source_triangle_ids).issubset(triangle_ids)
        for question in candidates.questions
    )

    triangle_payload = triangles.model_dump(by_alias=True, mode="json")
    candidate_payload = candidates.model_dump(by_alias=True, mode="json")
    assert "acute_angles" not in triangle_payload
    assert "source_number_entry_ids" not in str(candidate_payload)


def test_assignments_cover_four_ratios_without_obtuse_arguments(pipeline) -> None:
    _, _, _, candidates, _ = pipeline

    covered_functions = set()
    for question in candidates.questions:
        assert not any(character in question.stem_latex for character in ("\a", "\b", "\t", "\v", "\f", "\r"))
        assert r"\triangle ABC" in question.stem_latex
        assert "分别为" not in question.stem_latex
        assert "为锐角" not in question.stem_latex
        assert "为直角" not in question.stem_latex
        assert not any(f"${name}=" in question.stem_latex for name in ("a", "b", "c"))
        assert not any(f"求 ${name}$" in question.stem_latex for name in ("a", "b", "c"))
        assert question.audit.no_obtuse_trig_in_assignment
        assert len(question.answers) in {1, 2}
        if question.target_trig_function:
            covered_functions.add(question.target_trig_function)
        for fact in question.visible_angle_facts:
            covered_functions.add(fact.function)
            assert fact.value.coefficient_fraction >= 0
            if fact.display == "supplement_ratio":
                assert rf"\{fact.function}(180^\circ-{fact.angle_name})" in question.stem_latex
    assert covered_functions == {"sin", "cos", "tan", "cot"}


def test_review_publish_sample_is_seeded_and_answer_only(pipeline) -> None:
    tmp_path, _, _, candidates, candidate_path = pipeline
    selected = []
    for problem_type in ("sss", "sas", "ssa", "aas", "asa"):
        selected.append(next(q for q in candidates.questions if q.problem_type == problem_type))
    review = QuestionReview.model_validate(
        {
            "schema": "math_triangle_cosine_review/v1",
            "candidate_database_id": "triangle-cosine-question-candidates",
            "entries": [
                {
                    "question_id": question.id,
                    "content_hash": question.content_hash,
                    "decision": "approved",
                }
                for question in selected
            ],
        }
    )
    review_path = tmp_path / "review.yaml"
    dump_model(review_path, review)
    bank_path = tmp_path / "bank.yaml"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "publish_triangle_cosine_question_bank.py"),
            "--candidates",
            str(candidate_path),
            "--review",
            str(review_path),
            "--out",
            str(bank_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    bank = PublishedQuestionBank.model_validate(yaml.safe_load(bank_path.read_text(encoding="utf-8")))
    assert len(bank.questions) == 5

    first = tmp_path / "first.assignment.yaml"
    second = tmp_path / "second.assignment.yaml"
    for output in (first, second):
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sample_triangle_cosine_question_bank.py"),
                str(bank_path),
                "--output",
                str(output),
                "--count-per-type",
                "1",
                "--seed",
                "42",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assignment_text = first.read_text(encoding="utf-8")
    assert "difficulty:" not in assignment_text
    assert "explanation:" not in assignment_text
    assert "solution_steps:" not in assignment_text
    subprocess.run(
        [sys.executable, str(ASSIGNMENT_VALIDATOR), str(first)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
