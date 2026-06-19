from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts" / "model_rules"
sys.path.insert(0, str(SCRIPT_DIR))

from model_rule_lib import (  # noqa: E402
    read_yaml,
    validate_registry,
    validate_relation,
    validate_relations_file,
)


def copy_model_rule_files(tmp_path: Path) -> tuple[Path, Path]:
    registry = tmp_path / "type_registry.yaml"
    relations = tmp_path / "relations.yaml"
    shutil.copy(ROOT / "model_rules" / "type_registry.yaml", registry)
    shutil.copy(ROOT / "model_rules" / "relations.yaml", relations)
    return registry, relations


def load_first_relation() -> dict:
    data = read_yaml(ROOT / "model_rules" / "relations.yaml")
    return data["relations"][0].copy()


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_bootstrap_model_rule_files_validate() -> None:
    registry = read_yaml(ROOT / "model_rules" / "type_registry.yaml")
    relations = read_yaml(ROOT / "model_rules" / "relations.yaml")

    registry_result = validate_registry(registry)
    relation_result = validate_relations_file(relations, registry)

    assert registry_result.errors == []
    assert relation_result.errors == []


def test_search_by_output_type_finds_area_inverse_relation() -> None:
    result = run_script(
        "scripts/model_rules/search_model_rules.py",
        "--output-type",
        "CandidateSet<Point2D>",
    )

    assert result.returncode == 0
    assert "vertical_area_inverse_on_linear_locus" in result.stdout


def test_search_by_input_type_finds_parallelogram_relation() -> None:
    result = run_script("scripts/model_rules/search_model_rules.py", "--input-type", "Point2D")

    assert result.returncode == 0
    assert "parallelogram_fourth_point_fixed_order" in result.stdout


def test_apply_patch_adds_alias_and_relation(tmp_path: Path) -> None:
    registry, relations = copy_model_rule_files(tmp_path)
    relation = load_first_relation()
    relation["relation_id"] = "two_points_determine_linear_function_test"
    relation["name"] = "两点确定一次函数测试"
    patch = tmp_path / "patch.yaml"
    patch.write_text(
        yaml.safe_dump(
            {
                "source_analysis_path": "artifacts/demo/01-structure-analysis.md",
                "model_family": {"model_family_id": "linear_function_determination"},
                "type_registry_patch": {
                    "aliases_to_add": [{"type_id": "Point2D", "aliases": ["测试点别名"]}],
                    "new_type_candidates": [],
                },
                "relations": [relation],
                "review_status": "ready",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run_script(
        "scripts/model_rules/apply_model_rule_patch.py",
        str(patch),
        "--registry",
        str(registry),
        "--relations",
        str(relations),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "applied" in result.stdout
    new_registry = read_yaml(registry)
    new_relations = read_yaml(relations)
    new_patch = read_yaml(patch)
    assert "测试点别名" in new_registry["types"]["Point2D"]["aliases"]
    assert any(r["relation_id"] == "two_points_determine_linear_function_test" for r in new_relations["relations"])
    assert new_patch["review_status"] == "applied"


def test_apply_patch_blocks_alias_conflict(tmp_path: Path) -> None:
    registry, relations = copy_model_rule_files(tmp_path)
    patch = tmp_path / "conflict.yaml"
    patch.write_text(
        yaml.safe_dump(
            {
                "source_analysis_path": "artifacts/demo/01-structure-analysis.md",
                "model_family": {"model_family_id": "bad"},
                "type_registry_patch": {
                    "aliases_to_add": [{"type_id": "Area", "aliases": ["点"]}],
                    "new_type_candidates": [],
                },
                "relations": [load_first_relation()],
                "review_status": "ready",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run_script(
        "scripts/model_rules/apply_model_rule_patch.py",
        str(patch),
        "--registry",
        str(registry),
        "--relations",
        str(relations),
    )

    assert result.returncode == 2
    assert read_yaml(patch)["review_status"] == "needs_review"
    assert "already belongs" in "\n".join(read_yaml(patch)["review_notes"])


def test_candidate_set_relation_requires_selector_or_branching() -> None:
    registry = read_yaml(ROOT / "model_rules" / "type_registry.yaml")
    relation = {
        "relation_id": "bad_candidate_set",
        "model_family_id": "bad",
        "topic_tags": ["一次函数"],
        "propositions": {"P1": {"statement": "bad", "ports": {"points": "CandidateSet<Point2D>"}}},
        "constraints": {"C1": "候选点很多"},
        "relation": {"given": ["P1"], "derive": ["P2"], "constraints": ["C1"]},
        "ports": {"inputs": {"A": "Point2D"}, "outputs": {"points": "CandidateSet<Point2D>"}},
        "generation_notes": ["bad"],
        "non_examples": ["bad"],
    }

    result = validate_relation(relation, registry)

    assert any("CandidateSet" in error for error in result.errors)

