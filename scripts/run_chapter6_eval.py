#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chapter 6 evaluation runner for RAG parsing and question generation.

This script intentionally drives the public backend API instead of importing
internal pipeline classes. That keeps the measurement close to the frontend
workflow: upload a document, wait until the KB is ready, then generate
questions through the websocket endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import requests
import websockets


PROVIDERS = ["llamaindex", "lightrag"]
OBJECTIVE_TYPES = {"choice", "multiple_choice", "true_false"}
QUESTION_TYPES = {"choice", "multiple_choice", "true_false", "fill_blank", "written"}


@dataclass(frozen=True)
class MaterialFile:
    course: str
    path: Path
    file_type: str
    size_bytes: int

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1024 / 1024


QUESTION_CASES: list[dict[str, Any]] = [
    {"id": "Q01", "type": "choice", "label": "单选题", "count": 1, "difficulty": "easy"},
    {"id": "Q02", "type": "choice", "label": "单选题", "count": 3, "difficulty": "medium"},
    {"id": "Q03", "type": "choice", "label": "单选题", "count": 5, "difficulty": "hard"},
    {
        "id": "Q04",
        "type": "multiple_choice",
        "label": "多选题",
        "count": 3,
        "difficulty": "medium",
    },
    {
        "id": "Q05",
        "type": "multiple_choice",
        "label": "多选题",
        "count": 5,
        "difficulty": "hard",
    },
    {"id": "Q06", "type": "true_false", "label": "判断题", "count": 5, "difficulty": "easy"},
    {"id": "Q07", "type": "true_false", "label": "判断题", "count": 10, "difficulty": "medium"},
    {"id": "Q08", "type": "fill_blank", "label": "填空题", "count": 3, "difficulty": "medium"},
    {"id": "Q09", "type": "fill_blank", "label": "填空题", "count": 5, "difficulty": "hard"},
    {"id": "Q10", "type": "written", "label": "问答题", "count": 2, "difficulty": "medium"},
    {"id": "Q11", "type": "written", "label": "问答题", "count": 3, "difficulty": "hard"},
    {"id": "Q12", "type": "mixed", "label": "混合题", "count": 6, "difficulty": "medium"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Chapter 6 evaluation.")
    parser.add_argument(
        "--materials-root",
        default=r"D:\XMU\毕设\工作区\素材",
        help="Course material root directory.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument(
        "--mode",
        choices=["all", "rag", "questions", "metadata", "rag-retry"],
        default="all",
        help="Evaluation section to run.",
    )
    parser.add_argument("--providers", nargs="+", default=PROVIDERS, choices=PROVIDERS)
    parser.add_argument("--topic", default="课程核心知识点", help="Fixed knowledge point for generation.")
    parser.add_argument("--repeats", type=int, default=3, help="Question generation repeats.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Progress poll interval.")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Per operation timeout in seconds.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to data/evaluation/chapter6/<timestamp>.",
    )
    parser.add_argument(
        "--kb-prefix",
        default=None,
        help="Knowledge base name prefix. Defaults to ch6_eval_<timestamp>.",
    )
    parser.add_argument(
        "--question-kb",
        action="append",
        default=[],
        help="Provider to KB mapping for question-only mode, e.g. llamaindex=my_kb.",
    )
    parser.add_argument(
        "--rag-one-kb-per-file",
        action="store_true",
        help="Use an isolated KB for every file to avoid duplicate skipping and cumulative index effects.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Limit material files for smoke tests. 0 means all files.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing question_json files in the output directory and continue missing cases.",
    )
    parser.add_argument(
        "--case-ids",
        nargs="+",
        default=None,
        help="Limit question evaluation to specific case IDs, e.g. Q04 Q05.",
    )
    parser.add_argument(
        "--retry-source-dir",
        default=None,
        help="Existing evaluation output directory whose failed RAG rows should be retried and replaced.",
    )
    parser.add_argument(
        "--start-backend",
        action="store_true",
        help="Start a local uvicorn backend for the duration of this run.",
    )
    parser.add_argument(
        "--backend-log",
        default=None,
        help="Backend log path when --start-backend is used.",
    )
    return parser.parse_args()


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_name(value: str, max_len: int = 60) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-]+", "_", value).strip("_")
    return (cleaned or "item")[:max_len]


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def ws_url(base_url: str, path: str) -> str:
    if base_url.startswith("https://"):
        root = "wss://" + base_url[len("https://") :]
    elif base_url.startswith("http://"):
        root = "ws://" + base_url[len("http://") :]
    else:
        root = base_url
    return f"{root.rstrip('/')}{path}"


def collect_materials(root: Path) -> list[MaterialFile]:
    if not root.exists():
        raise FileNotFoundError(f"Materials root does not exist: {root}")

    rows: list[MaterialFile] = []
    for file_path in sorted(p for p in root.rglob("*") if p.is_file()):
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            rel = file_path
        course = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        stat = file_path.stat()
        rows.append(
            MaterialFile(
                course=course,
                path=file_path,
                file_type=file_path.suffix.lower().lstrip(".") or "unknown",
                size_bytes=stat.st_size,
            )
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        target = path
        f = target.open("w", newline="", encoding="utf-8-sig")
    except PermissionError:
        target = path.with_name(f"{path.stem}_{now_stamp()}{path.suffix}")
        f = target.open("w", newline="", encoding="utf-8-sig")
        print(f"[warn] {path.name} is locked; wrote {target.name} instead")
    with f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_material_metadata(output_dir: Path, materials: list[MaterialFile]) -> None:
    rows = [
        {
            "course": item.course,
            "file_name": item.path.name,
            "file_type": item.file_type,
            "file_size_mb": round(item.size_mb, 4),
            "path": str(item.path),
        }
        for item in materials
    ]
    write_csv(
        output_dir / "dataset_files.csv",
        rows,
        ["course", "file_name", "file_type", "file_size_mb", "path"],
    )

    by_course: dict[str, dict[str, Any]] = {}
    for item in materials:
        row = by_course.setdefault(
            item.course, {"course": item.course, "file_count": 0, "total_size_mb": 0.0}
        )
        row["file_count"] += 1
        row["total_size_mb"] += item.size_mb
    summary = [
        {
            "course": row["course"],
            "file_count": row["file_count"],
            "total_size_mb": round(row["total_size_mb"], 4),
        }
        for row in sorted(by_course.values(), key=lambda x: x["course"])
    ]
    write_csv(output_dir / "dataset_summary.csv", summary, ["course", "file_count", "total_size_mb"])


def check_backend(base_url: str) -> None:
    response = requests.get(api_url(base_url, "/api/v1/knowledge/health"), timeout=10)
    response.raise_for_status()


def wait_for_backend(base_url: str, timeout: float = 90.0) -> None:
    deadline = time.perf_counter() + timeout
    last_error = ""
    while time.perf_counter() < deadline:
        try:
            check_backend(base_url)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Backend did not become ready: {last_error}")


def start_backend_process(output_dir: Path, backend_log: str | None) -> subprocess.Popen:
    log_path = Path(backend_log) if backend_log else output_dir / "backend.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab", buffering=0)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    process = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    # Keep the handle alive on the process object so Windows does not close it
    # before uvicorn has finished writing.
    process._chapter6_log_file = log_file  # type: ignore[attr-defined]
    return process


def post_file(endpoint: str, file_path: Path, data: dict[str, Any]) -> requests.Response:
    with file_path.open("rb") as f:
        files = {"files": (file_path.name, f, "application/octet-stream")}
        response = requests.post(endpoint, data=data, files=files, timeout=120)
    response.raise_for_status()
    return response


def clear_progress(base_url: str, kb_name: str) -> None:
    try:
        requests.post(api_url(base_url, f"/api/v1/knowledge/{kb_name}/progress/clear"), timeout=20)
    except requests.RequestException:
        pass


def poll_until_ready(
    base_url: str,
    kb_name: str,
    start_time: float,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    progress_url = api_url(base_url, f"/api/v1/knowledge/{kb_name}/progress")
    info_url = api_url(base_url, f"/api/v1/knowledge/{kb_name}")
    deadline = start_time + timeout
    last_progress: dict[str, Any] = {}

    while time.perf_counter() < deadline:
        try:
            progress_response = requests.get(progress_url, timeout=20)
            if progress_response.ok:
                progress = progress_response.json()
                if isinstance(progress, dict):
                    last_progress = progress
                    stage = str(progress.get("stage") or progress.get("status") or "").lower()
                    if stage in {"completed", "error"}:
                        return progress
        except requests.RequestException:
            pass

        try:
            info_response = requests.get(info_url, timeout=20)
            if info_response.ok:
                info = info_response.json()
                status = str(info.get("status", "")).lower()
                stats = info.get("statistics") if isinstance(info.get("statistics"), dict) else {}
                rag_ready = bool(stats.get("rag_initialized"))
                if status == "ready" and rag_ready:
                    return {"stage": "completed", "message": "KB ready", "info": info}
                if status == "error":
                    return {"stage": "error", "message": "KB status error", "info": info}
        except requests.RequestException:
            pass

        time.sleep(poll_interval)

    raise TimeoutError(f"Timed out waiting for KB {kb_name}. Last progress: {last_progress}")


def upload_and_measure(
    base_url: str,
    provider: str,
    kb_name: str,
    material: MaterialFile,
    is_create: bool,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    clear_progress(base_url, kb_name)
    start = time.perf_counter()

    if is_create:
        endpoint = api_url(base_url, "/api/v1/knowledge/create")
        payload = {"name": kb_name, "rag_provider": provider}
    else:
        endpoint = api_url(base_url, f"/api/v1/knowledge/{kb_name}/upload")
        payload = {"rag_provider": provider}

    status = "success"
    error = ""
    progress: dict[str, Any] = {}
    try:
        post_file(endpoint, material.path, payload)
        progress = poll_until_ready(base_url, kb_name, start, timeout, poll_interval)
        if str(progress.get("stage", "")).lower() == "error":
            status = "error"
            error = str(progress.get("error") or progress.get("message") or "")
    except Exception as exc:  # noqa: BLE001 - keep raw CSV useful for troubleshooting
        status = "error"
        error = str(exc)

    elapsed = time.perf_counter() - start
    return {
        "provider": provider,
        "kb_name": kb_name,
        "course": material.course,
        "file_name": material.path.name,
        "file_type": material.file_type,
        "file_size_mb": round(material.size_mb, 4),
        "elapsed_sec": round(elapsed, 4),
        "sec_per_mb": round(elapsed / material.size_mb, 4) if material.size_mb > 0 else "",
        "status": status,
        "error": error,
        "progress_stage": progress.get("stage", ""),
        "progress_message": progress.get("message", ""),
    }


def summarize_rag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for provider in sorted({str(row["provider"]) for row in rows}):
        provider_rows = [
            row
            for row in rows
            if row.get("provider") == provider and row.get("status") == "success"
        ]
        if not provider_rows:
            out.append(
                {
                    "RAG provider": provider,
                    "平均解析耗时/s": "",
                    "最短耗时/s / 文件大小": "",
                    "最长耗时/s / 文件大小": "",
                    "单位耗时/s·MB^-1": "",
                }
            )
            continue

        avg_elapsed = sum(float(row["elapsed_sec"]) for row in provider_rows) / len(provider_rows)
        avg_unit = sum(float(row["sec_per_mb"]) for row in provider_rows) / len(provider_rows)
        min_row = min(provider_rows, key=lambda row: float(row["elapsed_sec"]))
        max_row = max(provider_rows, key=lambda row: float(row["elapsed_sec"]))
        out.append(
            {
                "RAG provider": provider,
                "平均解析耗时/s": round(avg_elapsed, 4),
                "最短耗时/s / 文件大小": (
                    f"{float(min_row['elapsed_sec']):.4f} / {float(min_row['file_size_mb']):.4f} MB"
                ),
                "最长耗时/s / 文件大小": (
                    f"{float(max_row['elapsed_sec']):.4f} / {float(max_row['file_size_mb']):.4f} MB"
                ),
                "单位耗时/s·MB^-1": round(avg_unit, 4),
            }
        )
    return out


def rewrite_rag_outputs(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    write_csv(
        output_dir / "rag_parse_raw.csv",
        rows,
        [
            "provider",
            "kb_name",
            "course",
            "file_name",
            "file_type",
            "file_size_mb",
            "elapsed_sec",
            "sec_per_mb",
            "status",
            "error",
            "progress_stage",
            "progress_message",
        ],
    )
    summary = summarize_rag(rows)
    write_csv(
        output_dir / "rag_parse_summary.csv",
        summary,
        ["RAG provider", "平均解析耗时/s", "最短耗时/s / 文件大小", "最长耗时/s / 文件大小", "单位耗时/s·MB^-1"],
    )
    (output_dir / "rag_parse_table.md").write_text(
        table_to_md(
            ["RAG provider", "平均解析耗时/s", "最短耗时/s / 文件大小", "最长耗时/s / 文件大小", "单位耗时/s·MB^-1"],
            summary,
        ),
        encoding="utf-8",
    )


def table_to_md(headers: list[str], rows: list[dict[str, Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines) + "\n"


def difficulty_to_bloom(difficulty: str) -> str:
    if difficulty == "hard":
        return "analyze"
    if difficulty == "easy":
        return "understand"
    return "apply"


async def generate_questions_once(
    base_url: str,
    kb_name: str,
    topic: str,
    case: dict[str, Any],
    timeout: float,
) -> tuple[float, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    url = ws_url(base_url, "/api/v1/question/generate")
    payload = {
        "requirement": {
            "knowledge_point": topic,
            "difficulty": case["difficulty"],
            "question_type": case["type"],
            "cognitive_level": difficulty_to_bloom(case["difficulty"]),
            "additional_requirements": "Ensure clarity and academic rigor.",
        },
        "count": case["count"],
        "kb_name": kb_name,
    }
    messages: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    start = time.perf_counter()

    async with websockets.connect(url, open_timeout=30, ping_timeout=None) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            messages.append(msg)
            msg_type = msg.get("type")
            if msg_type == "result":
                question = msg.get("question")
                if isinstance(question, dict):
                    questions.append(question)
            elif msg_type == "batch_summary":
                summary = msg
            elif msg_type == "error":
                raise RuntimeError(str(msg.get("content") or msg))
            elif msg_type == "complete":
                break

    return time.perf_counter() - start, questions, summary, messages


def parse_answer_labels(answer: Any) -> list[str]:
    if isinstance(answer, list):
        tokens = [str(item).strip().upper() for item in answer]
    else:
        raw = str(answer or "").strip().upper()
        tokens = re.findall(r"[A-H]", raw)
    seen: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.append(token)
    return seen


def canonical_stem(text: str) -> str:
    value = re.sub(r"\s+", "", str(text or "")).lower()
    value = re.sub(r"[，。！？,.!?;；:：\"'“”‘’（）()\[\]【】]", "", value)
    return value


def validate_question(question: dict[str, Any], requested_type: str) -> dict[str, Any]:
    qtype = str(question.get("question_type", "")).strip().lower()
    stem = str(question.get("question", "")).strip()
    answer = question.get("correct_answer", "")
    explanation = str(question.get("explanation", "")).strip()
    options = question.get("options") if isinstance(question.get("options"), dict) else {}

    type_ok = qtype in QUESTION_TYPES
    if requested_type != "mixed":
        type_ok = type_ok and qtype == requested_type

    has_stem = bool(stem)
    has_answer = bool(str(answer).strip())
    has_explanation = bool(explanation)
    option_ok: bool | None = None
    answer_format_ok: bool | None = None

    if qtype == "choice":
        labels = parse_answer_labels(answer)
        option_ok = all(key in options and str(options.get(key, "")).strip() for key in "ABCD")
        answer_format_ok = len(labels) == 1 and labels[0] in options
    elif qtype == "multiple_choice":
        labels = parse_answer_labels(answer)
        option_ok = all(key in options and str(options.get(key, "")).strip() for key in "ABCD")
        answer_format_ok = len(labels) >= 2 and all(label in options for label in labels)
    elif qtype == "true_false":
        labels = parse_answer_labels(answer)
        option_ok = all(key in options and str(options.get(key, "")).strip() for key in "AB")
        normalized = str(answer or "").strip().lower()
        answer_format_ok = (
            (len(labels) == 1 and labels[0] in {"A", "B"})
            or normalized in {"true", "false", "t", "f", "正确", "错误", "对", "错"}
        )
    elif qtype == "fill_blank":
        blanks = question.get("blanks") if isinstance(question.get("blanks"), list) else []
        has_answer = has_answer or any(str(blank).strip() for blank in blanks)
        markers = ["__", "___", "____", "（ ）", "( )", "()", "[]", "【】", "{blank}"]
        option_ok = True
        answer_format_ok = any(marker in stem for marker in markers) and has_answer
    elif qtype == "written":
        option_ok = None
        answer_format_ok = None

    field_complete = has_stem and has_answer and (has_explanation or qtype == "written")
    if qtype in OBJECTIVE_TYPES:
        field_complete = field_complete and bool(options)
    if qtype == "fill_blank":
        field_complete = field_complete and bool(answer_format_ok)

    return {
        "actual_type": qtype,
        "field_complete": bool(field_complete),
        "type_ok": bool(type_ok),
        "answer_format_ok": answer_format_ok,
        "option_ok": option_ok,
        "explanation_exists": has_explanation,
        "stem": stem,
    }


def percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "不适用"
    return f"{numerator / denominator * 100:.2f}%"


def summarize_question_speed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in sorted({(r["provider"], r["case_id"]) for r in rows}):
        provider, case_id = key
        items = [r for r in rows if r["provider"] == provider and r["case_id"] == case_id]
        if not items:
            continue
        avg_elapsed = sum(float(r["elapsed_sec"]) for r in items) / len(items)
        count = int(items[0]["count"])
        out.append(
            {
                "provider": provider,
                "编号": case_id,
                "题型": items[0]["question_label"],
                "题量": count,
                "难度": items[0]["difficulty"],
                "平均耗时/s": round(avg_elapsed, 4),
                "单题耗时/s": round(avg_elapsed / count, 4) if count else "",
            }
        )
    return out


def summarize_question_structure(question_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    labels = {
        "choice": "单选题",
        "multiple_choice": "多选题",
        "true_false": "判断题",
        "fill_blank": "填空题",
        "written": "问答题",
        "mixed": "混合题",
    }
    for provider in sorted({row["provider"] for row in question_rows}):
        provider_rows = [row for row in question_rows if row["provider"] == provider]
        for requested_type in ["choice", "multiple_choice", "true_false", "fill_blank", "written", "mixed"]:
            items = [row for row in provider_rows if row["requested_type"] == requested_type]
            if not items:
                continue
            sample_count = len(items)
            answer_items = [row for row in items if row["answer_format_ok"] != "NA"]
            option_items = [row for row in items if row["option_ok"] != "NA"]
            stems = [canonical_stem(row["stem"]) for row in items if canonical_stem(row["stem"])]
            duplicate_count = len(stems) - len(set(stems))
            mixed_batches = {
                (row["case_id"], row["repeat"]): set()
                for row in items
                if requested_type == "mixed"
            }
            for row in items:
                if requested_type == "mixed":
                    mixed_batches[(row["case_id"], row["repeat"])].add(row["actual_type"])
            mixed_ok = sum(1 for types in mixed_batches.values() if len(types) >= 2)
            mixed_total = len(mixed_batches)

            out.append(
                {
                    "provider": provider,
                    "题型": labels[requested_type],
                    "样本数": sample_count,
                    "字段完整率": percent(sum(row["field_complete"] == "1" for row in items), sample_count),
                    "题型合法率": percent(sum(row["type_ok"] == "1" for row in items), sample_count),
                    "答案格式合法率": percent(
                        sum(row["answer_format_ok"] == "1" for row in answer_items),
                        len(answer_items),
                    ),
                    "选项合法率": percent(
                        sum(row["option_ok"] == "1" for row in option_items),
                        len(option_items),
                    ),
                    "解析存在率": percent(
                        sum(row["explanation_exists"] == "1" for row in items), sample_count
                    ),
                    "混合覆盖率": percent(mixed_ok, mixed_total) if requested_type == "mixed" else "不适用",
                    "重复题数": duplicate_count,
                }
            )
    return out


def parse_kb_mapping(raw_items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in raw_items:
        if "=" not in item:
            raise ValueError(f"Invalid --question-kb value: {item}")
        provider, kb_name = item.split("=", 1)
        mapping[provider.strip()] = kb_name.strip()
    return mapping


async def run_question_eval(
    base_url: str,
    output_dir: Path,
    kb_by_provider: dict[str, str],
    topic: str,
    repeats: int,
    timeout: float,
    resume: bool = False,
    case_ids: set[str] | None = None,
) -> None:
    speed_rows: list[dict[str, Any]] = []
    question_rows: list[dict[str, Any]] = []
    raw_dir = output_dir / "question_json"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cases = [case for case in QUESTION_CASES if not case_ids or case["id"] in case_ids]
    for provider, kb_name in kb_by_provider.items():
        for case in cases:
            for repeat in range(1, repeats + 1):
                raw_path = raw_dir / f"{provider}_{case['id']}_r{repeat}.json"
                print(f"[question] {provider} {case['id']} repeat {repeat}/{repeats}")
                started = datetime.now().isoformat()
                status = "success"
                error = ""
                questions: list[dict[str, Any]] = []
                summary: dict[str, Any] = {}
                messages: list[dict[str, Any]] = []
                elapsed = 0.0
                if resume and raw_path.exists():
                    try:
                        existing = json.loads(raw_path.read_text(encoding="utf-8"))
                        elapsed = float(existing.get("elapsed_sec") or 0)
                        status = str(existing.get("status") or "success")
                        error = str(existing.get("error") or "")
                        questions = existing.get("questions") if isinstance(existing.get("questions"), list) else []
                        summary = existing.get("summary") if isinstance(existing.get("summary"), dict) else {}
                        messages = existing.get("messages") if isinstance(existing.get("messages"), list) else []
                        print(f"[question] reuse {raw_path.name}")
                    except Exception as exc:  # noqa: BLE001
                        status = "error"
                        error = f"Failed to reuse existing JSON: {exc}"
                else:
                    try:
                        elapsed, questions, summary, messages = await generate_questions_once(
                            base_url=base_url,
                            kb_name=kb_name,
                            topic=topic,
                            case=case,
                            timeout=timeout,
                        )
                    except Exception as exc:  # noqa: BLE001
                        status = "error"
                        error = str(exc)

                raw_payload = {
                    "provider": provider,
                    "kb_name": kb_name,
                    "case": case,
                    "repeat": repeat,
                    "started_at": started,
                    "elapsed_sec": elapsed,
                    "status": status,
                    "error": error,
                    "summary": summary,
                    "questions": questions,
                    "messages": messages,
                }
                if not (resume and raw_path.exists() and status != "error"):
                    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

                speed_rows.append(
                    {
                        "provider": provider,
                        "case_id": case["id"],
                        "question_label": case["label"],
                        "question_type": case["type"],
                        "count": case["count"],
                        "difficulty": case["difficulty"],
                        "repeat": repeat,
                        "elapsed_sec": round(elapsed, 4),
                        "completed": len(questions),
                        "status": status,
                        "error": error,
                        "raw_json": str(raw_path),
                    }
                )

                for index, question in enumerate(questions, start=1):
                    check = validate_question(question, case["type"])
                    question_rows.append(
                        {
                            "provider": provider,
                            "case_id": case["id"],
                            "repeat": repeat,
                            "index": index,
                            "requested_type": case["type"],
                            "actual_type": check["actual_type"],
                            "field_complete": "1" if check["field_complete"] else "0",
                            "type_ok": "1" if check["type_ok"] else "0",
                            "answer_format_ok": (
                                "NA"
                                if check["answer_format_ok"] is None
                                else "1"
                                if check["answer_format_ok"]
                                else "0"
                            ),
                            "option_ok": (
                                "NA"
                                if check["option_ok"] is None
                                else "1"
                                if check["option_ok"]
                                else "0"
                            ),
                            "explanation_exists": "1" if check["explanation_exists"] else "0",
                            "stem": check["stem"],
                            "raw_json": str(raw_path),
                        }
                    )

    write_csv(
        output_dir / "question_generation_raw.csv",
        speed_rows,
        [
            "provider",
            "case_id",
            "question_label",
            "question_type",
            "count",
            "difficulty",
            "repeat",
            "elapsed_sec",
            "completed",
            "status",
            "error",
            "raw_json",
        ],
    )
    write_csv(
        output_dir / "question_structure_raw.csv",
        question_rows,
        [
            "provider",
            "case_id",
            "repeat",
            "index",
            "requested_type",
            "actual_type",
            "field_complete",
            "type_ok",
            "answer_format_ok",
            "option_ok",
            "explanation_exists",
            "stem",
            "raw_json",
        ],
    )

    speed_summary = summarize_question_speed([row for row in speed_rows if row["status"] == "success"])
    structure_summary = summarize_question_structure(question_rows)

    write_csv(
        output_dir / "question_generation_summary.csv",
        speed_summary,
        ["provider", "编号", "题型", "题量", "难度", "平均耗时/s", "单题耗时/s"],
    )
    write_csv(
        output_dir / "question_structure_summary.csv",
        structure_summary,
        [
            "provider",
            "题型",
            "样本数",
            "字段完整率",
            "题型合法率",
            "答案格式合法率",
            "选项合法率",
            "解析存在率",
            "混合覆盖率",
            "重复题数",
        ],
    )

    sections: list[str] = []
    for provider in kb_by_provider:
        speed_items = [row for row in speed_summary if row["provider"] == provider]
        structure_items = [row for row in structure_summary if row["provider"] == provider]
        sections.append(f"## {provider} 题目生成效率\n")
        sections.append(
            table_to_md(["编号", "题型", "题量", "难度", "平均耗时/s", "单题耗时/s"], speed_items)
        )
        sections.append(f"\n## {provider} 题目结构合法性\n")
        sections.append(
            table_to_md(
                [
                    "题型",
                    "样本数",
                    "字段完整率",
                    "题型合法率",
                    "答案格式合法率",
                    "选项合法率",
                    "解析存在率",
                    "混合覆盖率",
                    "重复题数",
                ],
                structure_items,
            )
        )
    (output_dir / "question_tables.md").write_text("\n".join(sections), encoding="utf-8")


def run_rag_eval(
    base_url: str,
    output_dir: Path,
    materials: list[MaterialFile],
    providers: list[str],
    kb_prefix: str,
    timeout: float,
    poll_interval: float,
    one_kb_per_file: bool,
) -> dict[str, str]:
    rows: list[dict[str, Any]] = []
    kb_by_provider: dict[str, str] = {}

    for provider in providers:
        if one_kb_per_file:
            kb_by_provider[provider] = f"{kb_prefix}_{provider}_last"
        else:
            kb_by_provider[provider] = f"{kb_prefix}_{provider}"

        for index, material in enumerate(materials, start=1):
            if one_kb_per_file:
                kb_name = f"{kb_prefix}_{provider}_{index:03d}_{safe_name(material.path.stem, 24)}"
                is_create = True
            else:
                kb_name = kb_by_provider[provider]
                is_create = index == 1
            print(
                f"[rag] {provider} {index}/{len(materials)} "
                f"{material.course}/{material.path.name} ({material.size_mb:.2f} MB)"
            )
            row = upload_and_measure(
                base_url=base_url,
                provider=provider,
                kb_name=kb_name,
                material=material,
                is_create=is_create,
                timeout=timeout,
                poll_interval=poll_interval,
            )
            rows.append(row)

    write_csv(
        output_dir / "rag_parse_raw.csv",
        rows,
        [
            "provider",
            "kb_name",
            "course",
            "file_name",
            "file_type",
            "file_size_mb",
            "elapsed_sec",
            "sec_per_mb",
            "status",
            "error",
            "progress_stage",
            "progress_message",
        ],
    )
    summary = summarize_rag(rows)
    write_csv(
        output_dir / "rag_parse_summary.csv",
        summary,
        ["RAG provider", "平均解析耗时/s", "最短耗时/s / 文件大小", "最长耗时/s / 文件大小", "单位耗时/s·MB^-1"],
    )
    (output_dir / "rag_parse_table.md").write_text(
        table_to_md(
            ["RAG provider", "平均解析耗时/s", "最短耗时/s / 文件大小", "最长耗时/s / 文件大小", "单位耗时/s·MB^-1"],
            summary,
        ),
        encoding="utf-8",
    )
    (output_dir / "kb_mapping.json").write_text(
        json.dumps(kb_by_provider, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return kb_by_provider


def retry_failed_rag_rows(
    base_url: str,
    output_dir: Path,
    materials: list[MaterialFile],
    providers: list[str],
    kb_prefix: str,
    timeout: float,
    poll_interval: float,
) -> None:
    raw_path = output_dir / "rag_parse_raw.csv"
    rows = read_csv(raw_path)
    if not rows:
        raise FileNotFoundError(f"No RAG raw CSV found: {raw_path}")

    material_by_key = {(item.course, item.path.name): item for item in materials}
    retry_rows: list[dict[str, Any]] = []
    failed_indices = [
        idx
        for idx, row in enumerate(rows)
        if row.get("provider") in providers and row.get("status") != "success"
    ]
    print(f"[rag-retry] failed rows to retry: {len(failed_indices)}")

    for retry_no, idx in enumerate(failed_indices, start=1):
        row = rows[idx]
        material = material_by_key.get((row.get("course", ""), row.get("file_name", "")))
        if material is None:
            # Fallback for console/codepage mojibake in old CSV rows: file size
            # and basename are enough for the generated dataset here.
            candidates = [
                item
                for item in materials
                if item.path.name == row.get("file_name")
                or math.isclose(item.size_mb, float(row.get("file_size_mb") or 0), rel_tol=0, abs_tol=0.0002)
            ]
            material = candidates[0] if candidates else None
        if material is None:
            print(f"[rag-retry] skip unmatched row: {row.get('course')} / {row.get('file_name')}")
            continue

        provider = str(row["provider"])
        kb_name = f"{kb_prefix}_{provider}_retry_{retry_no:02d}_{safe_name(material.path.stem, 24)}"
        print(f"[rag-retry] {retry_no}/{len(failed_indices)} {provider} {material.path.name}")
        new_row = upload_and_measure(
            base_url=base_url,
            provider=provider,
            kb_name=kb_name,
            material=material,
            is_create=True,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        new_row["retry_replaces_kb_name"] = row.get("kb_name", "")
        new_row["retry_replaces_file_name"] = row.get("file_name", "")
        retry_rows.append(new_row)
        if new_row.get("status") == "success":
            rows[idx] = {k: str(v) for k, v in new_row.items()}
        else:
            print(f"[rag-retry] still failed: {new_row.get('error')}")

    write_csv(
        output_dir / "rag_retry_raw.csv",
        retry_rows,
        [
            "provider",
            "kb_name",
            "course",
            "file_name",
            "file_type",
            "file_size_mb",
            "elapsed_sec",
            "sec_per_mb",
            "status",
            "error",
            "progress_stage",
            "progress_message",
            "retry_replaces_kb_name",
            "retry_replaces_file_name",
        ],
    )
    rewrite_rag_outputs(output_dir, rows)


async def async_main() -> None:
    args = parse_args()
    stamp = now_stamp()
    output_dir = Path(args.output_dir) if args.output_dir else Path("data/evaluation/chapter6") / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    kb_prefix = args.kb_prefix or f"ch6_eval_{stamp}"

    config_payload = {
        "materials_root": args.materials_root,
        "base_url": args.base_url,
        "mode": args.mode,
        "providers": args.providers,
        "topic": args.topic,
        "repeats": args.repeats,
        "kb_prefix": kb_prefix,
        "rag_one_kb_per_file": args.rag_one_kb_per_file,
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    materials = collect_materials(Path(args.materials_root))
    if args.max_files and args.max_files > 0:
        materials = materials[: args.max_files]
    write_material_metadata(output_dir, materials)
    print(f"[meta] {len(materials)} files found. Output: {output_dir}")

    if args.mode == "metadata":
        return

    backend_process: subprocess.Popen | None = None
    try:
        if args.start_backend:
            backend_process = start_backend_process(output_dir, args.backend_log)
            print(f"[backend] started pid={backend_process.pid}")
            wait_for_backend(args.base_url)
        else:
            check_backend(args.base_url)

        kb_by_provider = parse_kb_mapping(args.question_kb)

        if args.mode in {"all", "rag"}:
            kb_by_provider = run_rag_eval(
                base_url=args.base_url,
                output_dir=output_dir,
                materials=materials,
                providers=args.providers,
                kb_prefix=kb_prefix,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
                one_kb_per_file=args.rag_one_kb_per_file,
            )

        if args.mode == "rag-retry":
            retry_dir = Path(args.retry_source_dir) if args.retry_source_dir else output_dir
            retry_failed_rag_rows(
                base_url=args.base_url,
                output_dir=retry_dir,
                materials=materials,
                providers=args.providers,
                kb_prefix=f"{kb_prefix}_repair",
                timeout=args.timeout,
                poll_interval=args.poll_interval,
            )

        if args.mode in {"all", "questions"}:
            missing = [provider for provider in args.providers if provider not in kb_by_provider]
            if missing:
                raise ValueError(
                    "Question mode needs KB mappings. Add --question-kb provider=kb_name for: "
                    + ", ".join(missing)
                )
            await run_question_eval(
                base_url=args.base_url,
                output_dir=output_dir,
                kb_by_provider={provider: kb_by_provider[provider] for provider in args.providers},
                topic=args.topic,
                repeats=args.repeats,
                timeout=args.timeout,
                resume=args.resume,
                case_ids=set(args.case_ids) if args.case_ids else None,
            )

        print(f"[done] Results written to {output_dir}")
    finally:
        if backend_process is not None and backend_process.poll() is None:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                backend_process.kill()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
