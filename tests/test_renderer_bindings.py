from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))

from diagram_contracts import DiagramJob, DiagramJobsManifest  # noqa: E402
from renderer_bindings import build_renderer_binding_manifest  # noqa: E402


class RendererBindingsTest(unittest.TestCase):
    def test_builds_bindable_tikz_binding_and_hashes_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            jobs_dir = artifact_dir / "build" / "diagram" / "jobs"
            job_dir = jobs_dir / "q1-prompt"
            rendered_dir = job_dir / "rendered"
            rendered_dir.mkdir(parents=True)
            fragment = rendered_dir / "prompt.fragment.tex"
            fragment.write_text(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}", encoding="utf-8")
            (job_dir / "renderer_result.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "tikz_fragment_path": "rendered/prompt.fragment.tex",
                        "renderer_audit": "renderer_audit.json",
                    }
                ),
                encoding="utf-8",
            )
            (job_dir / "workflow_result.json").write_text(
                json.dumps({"status": "ok", "model": {"text_model_used": "qwen-test"}}),
                encoding="utf-8",
            )
            manifest = DiagramJobsManifest(
                assignment_id="bindings",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                    )
                ],
            )

            bindings = build_renderer_binding_manifest(manifest, jobs_dir, artifact_dir)

            binding = bindings.bindings["q1.prompt"]
            self.assertTrue(binding.bindable)
            self.assertEqual(binding.tikz_fragment_path, "build/diagram/jobs/q1-prompt/rendered/prompt.fragment.tex")
            self.assertTrue(binding.artifact_hash.startswith("sha256:"))

    def test_missing_renderer_result_is_not_bindable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            jobs_dir = artifact_dir / "build" / "diagram" / "jobs"
            (jobs_dir / "q1-prompt").mkdir(parents=True)
            manifest = DiagramJobsManifest(
                assignment_id="bindings",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                    )
                ],
            )

            bindings = build_renderer_binding_manifest(manifest, jobs_dir, artifact_dir)

            binding = bindings.bindings["q1.prompt"]
            self.assertFalse(binding.bindable)
            self.assertIn("renderer_result.json missing or invalid", binding.warnings)

    def test_ok_renderer_result_without_tikz_payload_warns_and_is_not_bindable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            jobs_dir = artifact_dir / "build" / "diagram" / "jobs"
            job_dir = jobs_dir / "q1-prompt"
            job_dir.mkdir(parents=True)
            (job_dir / "renderer_result.json").write_text(
                json.dumps({"status": "ok"}),
                encoding="utf-8",
            )
            manifest = DiagramJobsManifest(
                assignment_id="bindings",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                    )
                ],
            )

            bindings = build_renderer_binding_manifest(manifest, jobs_dir, artifact_dir)

            binding = bindings.bindings["q1.prompt"]
            self.assertFalse(binding.bindable)
            self.assertIn("ok renderer_result missing TikZ payload", binding.warnings)

    def test_offline_constraint_fallback_is_not_bindable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            jobs_dir = artifact_dir / "build" / "diagram" / "jobs"
            job_dir = jobs_dir / "q1-prompt"
            rendered_dir = job_dir / "rendered"
            rendered_dir.mkdir(parents=True)
            fragment = rendered_dir / "prompt.fragment.tex"
            fragment.write_text(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}", encoding="utf-8")
            (job_dir / "renderer_result.json").write_text(
                json.dumps({"status": "ok", "tikz_fragment_path": "rendered/prompt.fragment.tex"}),
                encoding="utf-8",
            )
            (job_dir / "workflow_result.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "message": "Generated by deterministic constraint solve after model failure",
                        "model": {"text_model_used": "offline-constraint-solver"},
                    }
                ),
                encoding="utf-8",
            )
            (job_dir / "final_renderer_spec.json").write_text(
                json.dumps({"generator": "build/diagram/generate_constraint_specs.py"}),
                encoding="utf-8",
            )
            manifest = DiagramJobsManifest(
                assignment_id="bindings",
                source_assignment="assignment.plan.yaml",
                jobs=[
                    DiagramJob(
                        job_id="q1-prompt",
                        slot_id="q1.prompt",
                        diagram_ref="q1.prompt",
                        slot_path="/sections/0/blocks/0/diagram_slot",
                        request_path="build/diagram/jobs/q1-prompt/request.json",
                        out_dir="build/diagram/jobs/q1-prompt",
                        public_image_dir="diagram/jobs/q1-prompt/rendered",
                    )
                ],
            )

            bindings = build_renderer_binding_manifest(manifest, jobs_dir, artifact_dir)

            binding = bindings.bindings["q1.prompt"]
            self.assertFalse(binding.bindable)
            self.assertIn("fallback/offline constraint workflow is not bindable", binding.warnings)


if __name__ == "__main__":
    unittest.main()
