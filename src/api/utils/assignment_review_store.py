#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Assignment Review Store
=======================

JSON-backed persistence for assignment-review workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
import uuid
from typing import Any

from src.api.utils.assignment_review_repository import (
    AssignmentReviewRepository,
    JsonAssignmentReviewRepository,
)

@dataclass
class AssignmentReviewPaths:
    root: Path
    uploads_root: Path
    assignments_file: Path
    submissions_file: Path
    wrongbook_file: Path


class AssignmentReviewStore:
    """JSON-backed storage for assignment review workflows."""

    def __init__(self, root_dir: Path, repository: AssignmentReviewRepository | None = None):
        root = root_dir / "data" / "user" / "assignment_review"
        self.paths = AssignmentReviewPaths(
            root=root,
            uploads_root=root / "uploads",
            assignments_file=root / "assignments.json",
            submissions_file=root / "submissions.json",
            wrongbook_file=root / "wrongbook.json",
        )
        self.repository = repository or JsonAssignmentReviewRepository()
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self):
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.uploads_root.mkdir(parents=True, exist_ok=True)
        self._init_json_file(self.paths.assignments_file, {"assignments": []})
        self._init_json_file(self.paths.submissions_file, {"submissions": []})
        self._init_json_file(self.paths.wrongbook_file, {"items": []})

    def _init_json_file(self, path: Path, initial_payload: dict[str, Any]):
        self.repository.init_json_file(path, initial_payload)

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        return self.repository.read_json(path)

    def _write_json_file(self, path: Path, payload: dict[str, Any]):
        self.repository.write_json(path, payload)

    def create_assignment(
        self,
        teacher_username: str,
        title: str,
        description: str,
        rubric_items: list[dict[str, Any]],
        files: list[dict[str, Any]],
        assignment_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._read_json_file(self.paths.assignments_file)
            assignments = payload.get("assignments", [])

            assignment = {
                "id": assignment_id or str(uuid.uuid4())[:12],
                "teacher_username": teacher_username,
                "title": title,
                "description": description,
                "rubric_items": rubric_items,
                "files": files,
                "status": "draft",
                "confirmed": False,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            assignments.append(assignment)
            payload["assignments"] = assignments
            self._write_json_file(self.paths.assignments_file, payload)
            return assignment

    def get_assignment_by_id(self, assignment_id: str) -> dict[str, Any] | None:
        payload = self._read_json_file(self.paths.assignments_file)
        assignments = payload.get("assignments", [])
        for assignment in assignments:
            if assignment.get("id") == assignment_id:
                return assignment
        return None

    def list_teacher_assignments(self, teacher_username: str) -> list[dict[str, Any]]:
        payload = self._read_json_file(self.paths.assignments_file)
        assignments = payload.get("assignments", [])
        return [a for a in assignments if a.get("teacher_username") == teacher_username]

    def confirm_assignment(self, assignment_id: str, teacher_username: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._read_json_file(self.paths.assignments_file)
            assignments = payload.get("assignments", [])
            updated = None

            for assignment in assignments:
                if assignment.get("id") != assignment_id:
                    continue
                if assignment.get("teacher_username") != teacher_username:
                    continue
                assignment["confirmed"] = True
                assignment["status"] = "published"
                assignment["updated_at"] = time.time()
                updated = assignment
                break

            if updated:
                payload["assignments"] = assignments
                self._write_json_file(self.paths.assignments_file, payload)
            return updated

    def list_published_assignments(self) -> list[dict[str, Any]]:
        payload = self._read_json_file(self.paths.assignments_file)
        assignments = payload.get("assignments", [])
        return [a for a in assignments if a.get("confirmed") and a.get("status") == "published"]

    def create_submission(
        self,
        student_username: str,
        assignment_id: str,
        answer_text: str,
        files: list[dict[str, Any]],
        auto_review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._read_json_file(self.paths.submissions_file)
            submissions = payload.get("submissions", [])

            submission = {
                "id": str(uuid.uuid4())[:12],
                "student_username": student_username,
                "assignment_id": assignment_id,
                "answer_text": answer_text,
                "files": files,
                "status": "submitted",
                "created_at": time.time(),
                "updated_at": time.time(),
                "review": None,
                "auto_review": auto_review,
            }
            submissions.append(submission)
            payload["submissions"] = submissions
            self._write_json_file(self.paths.submissions_file, payload)
            return submission

    def list_student_submissions(self, student_username: str) -> list[dict[str, Any]]:
        payload = self._read_json_file(self.paths.submissions_file)
        submissions = payload.get("submissions", [])
        assignments_payload = self._read_json_file(self.paths.assignments_file)
        assignment_map = {a.get("id"): a for a in assignments_payload.get("assignments", [])}

        filtered: list[dict[str, Any]] = []
        for submission in submissions:
            if submission.get("student_username") != student_username:
                continue
            enriched = dict(submission)
            assignment = assignment_map.get(submission.get("assignment_id"), {})
            enriched["assignment_title"] = assignment.get("title", "")
            enriched["assignment_rubric_items"] = assignment.get("rubric_items", [])
            filtered.append(enriched)
        return filtered

    def list_teacher_submissions(self, teacher_username: str) -> list[dict[str, Any]]:
        assignments_payload = self._read_json_file(self.paths.assignments_file)
        assignments = assignments_payload.get("assignments", [])
        assignment_map = {a.get("id"): a for a in assignments}
        teacher_assignment_ids = {
            aid
            for aid, assignment in assignment_map.items()
            if assignment.get("teacher_username") == teacher_username
        }

        submissions_payload = self._read_json_file(self.paths.submissions_file)
        submissions = submissions_payload.get("submissions", [])
        filtered = []
        for submission in submissions:
            assignment_id = submission.get("assignment_id")
            if assignment_id not in teacher_assignment_ids:
                continue
            enriched = dict(submission)
            assignment = assignment_map.get(assignment_id, {})
            enriched["assignment_title"] = assignment.get("title", "")
            enriched["assignment_rubric_items"] = assignment.get("rubric_items", [])
            filtered.append(enriched)
        filtered.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return filtered

    def review_submission(
        self,
        submission_id: str,
        teacher_username: str,
        total_score: float,
        feedback: str,
        rubric_scores: list[dict[str, Any]] | None = None,
        wrongbook_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            assignments_payload = self._read_json_file(self.paths.assignments_file)
            assignments = assignments_payload.get("assignments", [])
            assignment_map = {a.get("id"): a for a in assignments}

            submissions_payload = self._read_json_file(self.paths.submissions_file)
            submissions = submissions_payload.get("submissions", [])
            target_submission = None

            for submission in submissions:
                if submission.get("id") != submission_id:
                    continue
                assignment = assignment_map.get(submission.get("assignment_id"))
                if not assignment:
                    continue
                if assignment.get("teacher_username") != teacher_username:
                    return None

                submission["status"] = "reviewed"
                submission["updated_at"] = time.time()
                submission["review"] = {
                    "teacher_username": teacher_username,
                    "total_score": total_score,
                    "feedback": feedback,
                    "rubric_scores": rubric_scores or [],
                    "reviewed_at": time.time(),
                }
                submission["assignment_title"] = assignment.get("title", "")
                target_submission = submission
                break

            if not target_submission:
                return None

            submissions_payload["submissions"] = submissions
            self._write_json_file(self.paths.submissions_file, submissions_payload)

            wrongbook_payload = self._read_json_file(self.paths.wrongbook_file)
            items = wrongbook_payload.get("items", [])
            items = [i for i in items if i.get("source_submission_id") != submission_id]

            base_items = wrongbook_items or []
            if not base_items and total_score < 60:
                base_items = [
                    {
                        "assignment_title": target_submission.get("assignment_title", ""),
                        "feedback": feedback or "本次作业得分偏低，建议重点复盘本次提交内容。",
                        "error_type": "综合能力不足",
                        "knowledge_point": "本次作业综合考点",
                        "suggestion": "建议按 rubric 维度逐项复盘并补充练习。",
                    }
                ]
            elif not base_items and rubric_scores:
                generated_items: list[dict[str, Any]] = []
                for rubric in rubric_scores:
                    score = float(rubric.get("score", 0))
                    max_score = float(rubric.get("max_score", 0) or 0)
                    if max_score <= 0:
                        continue
                    if score / max_score >= 0.65:
                        continue
                    name = rubric.get("name", "未命名维度")
                    generated_items.append(
                        {
                            "assignment_title": target_submission.get("assignment_title", ""),
                            "feedback": f"维度“{name}”得分较低（{score}/{max_score}）。",
                            "error_type": "维度薄弱",
                            "knowledge_point": name,
                            "suggestion": f"围绕“{name}”补充针对性练习并复盘错误原因。",
                        }
                    )
                base_items = generated_items

            for item in base_items:
                items.append(
                    {
                        "id": str(uuid.uuid4())[:12],
                        "student_username": target_submission.get("student_username"),
                        "assignment_id": target_submission.get("assignment_id"),
                        "assignment_title": item.get(
                            "assignment_title",
                            target_submission.get("assignment_title", ""),
                        ),
                        "feedback": item.get("feedback", feedback),
                        "error_type": item.get("error_type", ""),
                        "knowledge_point": item.get("knowledge_point", ""),
                        "suggestion": item.get("suggestion", ""),
                        "source_submission_id": submission_id,
                        "practice_history": [],
                        "created_at": time.time(),
                    }
                )

            wrongbook_payload["items"] = items
            self._write_json_file(self.paths.wrongbook_file, wrongbook_payload)
            return target_submission

    def list_wrongbook_items(self, student_username: str) -> list[dict[str, Any]]:
        payload = self._read_json_file(self.paths.wrongbook_file)
        items = payload.get("items", [])
        filtered = [i for i in items if i.get("student_username") == student_username]
        for item in filtered:
            if "practice_history" not in item:
                item["practice_history"] = []
        filtered.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return filtered

    def append_wrongbook_practice(
        self,
        student_username: str,
        item_id: str,
        practice: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
            payload = self._read_json_file(self.paths.wrongbook_file)
            items = payload.get("items", [])
            updated_item = None
            for item in items:
                if item.get("id") != item_id:
                    continue
                if item.get("student_username") != student_username:
                    return None
                history = item.get("practice_history", [])
                history.append(practice)
                item["practice_history"] = history
                updated_item = item
                break

            if updated_item:
                payload["items"] = items
                self._write_json_file(self.paths.wrongbook_file, payload)
            return updated_item

    def add_wrongbook_item(
        self,
        student_username: str,
        assignment_id: str,
        assignment_title: str,
        feedback: str,
        error_type: str = "",
        knowledge_point: str = "",
        suggestion: str = "",
        source_submission_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._read_json_file(self.paths.wrongbook_file)
            items = payload.get("items", [])
            item = {
                "id": str(uuid.uuid4())[:12],
                "student_username": student_username,
                "assignment_id": assignment_id,
                "assignment_title": assignment_title,
                "feedback": feedback,
                "error_type": error_type,
                "knowledge_point": knowledge_point,
                "suggestion": suggestion,
                "source_submission_id": source_submission_id,
                "practice_history": [],
                "created_at": time.time(),
            }
            items.append(item)
            payload["items"] = items
            self._write_json_file(self.paths.wrongbook_file, payload)
            return item


_store: AssignmentReviewStore | None = None


def get_assignment_review_store() -> AssignmentReviewStore:
    global _store
    if _store is None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        _store = AssignmentReviewStore(project_root)
    return _store
