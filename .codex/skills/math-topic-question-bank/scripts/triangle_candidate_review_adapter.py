"""Adapt generated triangle candidates to the existing question-bank review UI."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml


BANK_ID = "staging:generated:triangle-cosine-question-candidates"
REVIEW_SCHEMA = "math_triangle_cosine_review/v1"
TYPE_LABELS = {"sss": "三边已知", "sas": "两边夹角", "ssa": "两边一角", "aas": "两角不夹边", "asa": "两角夹边"}


class TriangleCandidateReviewStore:
    def __init__(self, candidates_path: Path, review_path: Path):
        self.candidates_path = candidates_path.resolve()
        self.review_path = review_path.resolve()
        self.lock = threading.Lock()

    def _candidates(self) -> dict[str, Any]:
        payload = yaml.safe_load(self.candidates_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != "math_triangle_cosine_candidates/v1":
            raise ValueError("三角形候选题 schema 不正确")
        return payload

    def _review(self) -> dict[str, Any]:
        if not self.review_path.is_file():
            return {"schema": REVIEW_SCHEMA, "candidate_database_id": "triangle-cosine-question-candidates", "entries": []}
        payload = yaml.safe_load(self.review_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != REVIEW_SCHEMA:
            raise ValueError("三角形候选题审核 schema 不正确")
        return payload

    @staticmethod
    def _save(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=140)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def _state(self, question: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        decision = decisions.get(str(question.get("id")))
        if not decision:
            return {"status": "pending", "note": "", "notes": [], "reviewer": "", "reviewed_at": None, "stale": False}
        stale = decision.get("content_hash") != question.get("content_hash")
        reason = str(decision.get("reason") or "")
        return {"status": decision.get("decision", "pending"), "note": reason, "notes": [reason] if reason else [], "reviewer": "question-bank-review-ui", "reviewed_at": None, "stale": stale}

    def _loaded(self) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        questions = self._candidates().get("questions") or []
        decisions = {str(entry.get("question_id")): entry for entry in self._review().get("entries") or [] if isinstance(entry, dict)}
        return questions, decisions

    def summary(self) -> dict[str, Any]:
        questions, decisions = self._loaded()
        states = [self._state(question, decisions) for question in questions]
        return {"id": BANK_ID, "kind": "staging_exam", "paper_id": "TRIANGLE-COSINE-GENERATED", "topic": "解三角形生成题候选库", "grade": "九年级", "subject": "数学", "status": "staging", "target_count": len(questions), "item_count": len(questions), "enabled_count": sum(state["status"] == "approved" and not state["stale"] for state in states), "approved_count": sum(state["status"] == "approved" and not state["stale"] for state in states), "rejected_count": sum(state["status"] == "rejected" and not state["stale"] for state in states), "stale_count": sum(state["stale"] for state in states), "exam_type": "", "year": "", "district": ""}

    def _item(self, question: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        answers = question.get("answers") or []
        audit = question.get("audit") or {}
        type_label = TYPE_LABELS.get(str(question.get("problem_type")), str(question.get("problem_type", "")).upper())
        target = "求边" if question.get("target_kind") == "side" else f"求 {question.get('target_trig_function')}"
        return {"id": question.get("id"), "title": f"{type_label} · {target}", "question_type": "short_answer", "difficulty": "", "skill_tags": [str(question.get("problem_type", "")).upper(), target, f"答案数 {audit.get('solution_count', len(answers))}"], "stem_latex": question.get("stem_latex", ""), "choices": {}, "answer": " 或 ".join(str(answer.get("latex", "")) for answer in answers), "clue": "", "solution_steps": [], "solution_notes": [], "source_question_previews": [], "prompt_previews": [], "official_solution_previews": [], "source_pages": [], "prompt_preview_url": None, "solution_preview_url": None, "solution_previews": [], "review_issues": [], "review": self._state(question, decisions)}

    def item(self, item_id: str) -> dict[str, Any]:
        questions, decisions = self._loaded()
        for question in questions:
            if question.get("id") == item_id:
                return self._item(question, decisions)
        raise KeyError(item_id)

    def directory(self) -> dict[str, Any]:
        questions, decisions = self._loaded()
        items = []
        for question in questions:
            state = self._state(question, decisions)
            type_label = TYPE_LABELS.get(str(question.get("problem_type")), str(question.get("problem_type", "")).upper())
            items.append({"id": question.get("id"), "title": type_label, "review_status": state["status"], "stale": state["stale"], "review_issue_count": 0, "unresolved_review_issue_count": 0})
        summary = self.summary()
        return {"id": BANK_ID, "kind": "staging_exam", "topic": summary["topic"], "grade": summary["grade"], "paper_id": summary["paper_id"], "year": "", "exam_type": "", "district": "", "item_count": len(items), "counts": {"approved": summary["approved_count"], "rejected": summary["rejected_count"], "stale": summary["stale_count"]}, "review_mode_active": False, "review_issue_count": 0, "unresolved_review_issue_count": 0, "items": items}

    def write_review(self, item_id: str, decision: str, note: str = "") -> dict[str, Any]:
        with self.lock:
            questions = {str(question.get("id")): question for question in self._candidates().get("questions") or []}
            if item_id not in questions:
                raise KeyError(item_id)
            review = self._review()
            entries = {str(entry.get("question_id")): entry for entry in review.get("entries") or [] if isinstance(entry, dict)}
            entries[item_id] = {"question_id": item_id, "content_hash": questions[item_id].get("content_hash"), "decision": decision, "reason": note or None}
            review["entries"] = [entries[key] for key in sorted(entries)]
            self._save(self.review_path, review)
            return self._state(questions[item_id], entries)

    def approve_all(self) -> dict[str, Any]:
        with self.lock:
            questions = self._candidates().get("questions") or []
            review = self._review()
            entries = {str(entry.get("question_id")): entry for entry in review.get("entries") or [] if isinstance(entry, dict)}
            for question in questions:
                item_id = str(question.get("id"))
                entries[item_id] = {"question_id": item_id, "content_hash": question.get("content_hash"), "decision": "approved", "reason": None}
            review["entries"] = [entries[key] for key in sorted(entries)]
            self._save(self.review_path, review)
            updated = {str(question.get("id")): self._state(question, entries) for question in questions}
        summary = self.summary()
        return {"counts": {"approved": summary["approved_count"], "rejected": summary["rejected_count"], "stale": summary["stale_count"]}, "updated_reviews": updated, "errors": []}
