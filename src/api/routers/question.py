import asyncio
import base64
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import traceback
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.question import AgentCoordinator
from src.api.utils.history import ActivityType, history_manager
from src.api.utils.log_interceptor import LogInterceptor
from src.api.utils.task_id_manager import TaskIDManager
from src.core.database import get_db
from src.core.models import KnowledgePoint, Student, User
from src.services.mastery import apply_mastery_event
from src.tools.question import mimic_exam_questions
from src.utils.document_validator import DocumentValidator
from src.utils.error_utils import format_exception_message

# Add project root for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logging import get_logger
from src.services.config import load_config_with_main
from src.services.llm import complete as llm_complete
from src.services.llm.config import get_llm_config
from src.services.settings.interface_settings import get_ui_language

# Setup module logger with unified logging system (from config)
project_root = Path(__file__).parent.parent.parent.parent
config = load_config_with_main("question_config.yaml", project_root)
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = get_logger("QuestionAPI", log_dir=log_dir)

router = APIRouter()

# Output directory for mimic mode - use data/user/question
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MIMIC_OUTPUT_DIR = PROJECT_ROOT / "data" / "user" / "question" / "mimic_papers"


class WrittenEvaluateRequest(BaseModel):
    question: dict[str, Any]
    answer: str
    student_username: str | None = None
    knowledge_point_id: int | None = None
    source_id: str | None = None
    difficulty: str = "medium"
    used_hint: bool = False
    attempt_count: int | None = Field(default=None, ge=1, le=20)


def _normalize_words(text: str) -> set[str]:
    zh_words = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    en_words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return set(zh_words + en_words)


def _evaluate_written_answer(question: dict[str, Any], answer: str) -> dict[str, Any]:
    answer = (answer or "").strip()
    if not answer:
        return {
            "status": "incorrect",
            "score_ratio": 0.0,
            "reason": "未检测到有效作答内容，请补充关键观点后再提交。",
        }

    reference = "\n".join(
        [
            str(question.get("correct_answer", "")),
            str(question.get("explanation", "")),
            str(question.get("question", "")),
        ]
    )
    ref_tokens = _normalize_words(reference)
    ans_tokens = _normalize_words(answer)
    overlap_ratio = len(ref_tokens & ans_tokens) / max(1, len(ref_tokens))
    len_factor = min(1.0, len(answer) / 180)
    score_ratio = max(0.0, min(1.0, 0.72 * overlap_ratio + 0.28 * len_factor))

    if score_ratio >= 0.75:
        status = "correct"
        reason = "答案与参考要点高度一致，覆盖面较完整。"
    elif score_ratio >= 0.45:
        status = "partial"
        reason = "答案覆盖了部分关键点，建议补充细节与依据。"
    else:
        status = "incorrect"
        reason = "答案与题目关键要点匹配度较低，请围绕核心概念重答。"

    return {"status": status, "score_ratio": round(score_ratio, 3), "reason": reason}


async def _evaluate_written_answer_with_llm(question: dict[str, Any], answer: str) -> dict[str, Any]:
    """LLM-first written grading. Falls back to heuristic grading when unavailable."""
    answer = (answer or "").strip()
    if not answer:
        return {
            "status": "incorrect",
            "score_ratio": 0.0,
            "reason": "未检测到有效作答内容，请补充关键观点后再提交。",
            "source": "rule",
        }

    try:
        llm_config = get_llm_config()
        system_prompt = (
            "你是一名严谨的助教，请根据题目、参考答案和学生作答进行评分。"
            "只输出 JSON，不要输出 markdown。"
            "字段必须包含 status(correct|partial|incorrect)、score_ratio(0-1)、reason(简短中文说明)。"
        )
        user_prompt = json.dumps(
            {
                "question": question.get("question", ""),
                "reference_answer": question.get("correct_answer", ""),
                "reference_explanation": question.get("explanation", ""),
                "student_answer": answer,
                "scoring_rule": "优先考察是否命中关键概念、论证是否完整、是否存在明显事实错误。",
            },
            ensure_ascii=False,
        )
        raw = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            api_version=getattr(llm_config, "api_version", None),
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        if isinstance(raw, dict):
            data = raw
        else:
            data = json.loads(raw)
        status = str(data.get("status", "partial")).lower()
        if status not in {"correct", "partial", "incorrect"}:
            status = "partial"
        score_ratio = float(data.get("score_ratio", 0.5))
        score_ratio = max(0.0, min(1.0, score_ratio))
        reason = str(data.get("reason", "")).strip() or "已完成评分，但模型未返回详细理由。"
        return {
            "status": status,
            "score_ratio": round(score_ratio, 3),
            "reason": reason,
            "source": "llm",
        }
    except Exception as exc:
        logger.warning("LLM written grading failed, fallback to rule grading: %s", format_exception_message(exc))
        fallback = _evaluate_written_answer(question, answer)
        fallback["source"] = "rule"
        return fallback


@router.post("/evaluate/written")
async def evaluate_written_submission(
    request: WrittenEvaluateRequest,
    db: Session = Depends(get_db),
):
    question_type = str(request.question.get("question_type", "")).lower()
    if question_type and question_type not in {"written", "essay", "subjective"}:
        raise HTTPException(status_code=400, detail="This endpoint is only for written questions")
    result = await _evaluate_written_answer_with_llm(request.question, request.answer)
    mastery_payload = None
    if request.student_username and request.knowledge_point_id:
        try:
            user = (
                db.query(User)
                .filter(User.username == request.student_username, User.role == "student")
                .first()
            )
            student = db.query(Student).filter(Student.user_id == user.id).first() if user else None
            point = (
                db.query(KnowledgePoint)
                .filter(KnowledgePoint.id == request.knowledge_point_id)
                .first()
            )
            if student and point:
                status = str(result.get("status", "")).lower()
                is_correct = True if status == "correct" else False if status == "incorrect" else None
                update = apply_mastery_event(
                    db,
                    student_id=student.id,
                    knowledge_point_id=point.id,
                    source_type="question_practice",
                    source_id=request.source_id or f"written:{point.id}",
                    difficulty=request.difficulty,
                    answer_quality="partial" if status == "partial" else None,
                    used_hint=request.used_hint,
                    attempt_count=request.attempt_count,
                    score=float(result.get("score_ratio", 0.0)),
                    max_score=1.0,
                    is_correct=is_correct,
                    note="题目模块主观题评分后自动更新掌握度",
                )
                db.commit()
                mastery_payload = {
                    "event_id": update.event.id,
                    "knowledge_point_id": point.id,
                    "mastery_level": update.mastery.mastery_level,
                    "mastery_delta": update.event.mastery_delta,
                    "strategy": update.details,
                }
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to update written-question mastery: %s", format_exception_message(exc))
            mastery_payload = {"error": "掌握度更新失败，评分结果已保留"}
    return {"success": True, **result, "mastery": mastery_payload}


@router.websocket("/mimic")
async def websocket_mimic_generate(websocket: WebSocket):
    """
    WebSocket endpoint for mimic exam paper question generation.

    Supports two modes:
    1. Upload PDF directly via WebSocket (base64 encoded)
    2. Use a pre-parsed paper directory path

    Message format for PDF upload:
    {
        "mode": "upload",
        "pdf_data": "base64_encoded_pdf_content",
        "pdf_name": "exam.pdf",
        "kb_name": "knowledge_base_name",
        "max_questions": 5  // optional
    }

    Message format for pre-parsed:
    {
        "mode": "parsed",
        "paper_path": "directory_name",
        "kb_name": "knowledge_base_name",
        "max_questions": 5  // optional
    }
    """
    await websocket.accept()

    pusher_task = None
    original_stdout = sys.stdout

    try:
        # 1. Wait for config
        data = await websocket.receive_json()
        mode = data.get("mode", "parsed")  # "upload" or "parsed"
        kb_name = data.get("kb_name", "ai_textbook")
        max_questions = data.get("max_questions")

        logger.info(f"Starting mimic generation (mode: {mode}, kb: {kb_name})")

        # 2. Setup Log Queue
        log_queue = asyncio.Queue()

        async def log_pusher():
            while True:
                entry = await log_queue.get()
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
                log_queue.task_done()

        pusher_task = asyncio.create_task(log_pusher())

        # 3. Stdout interceptor for capturing prints
        # ANSI escape sequence pattern for stripping color codes
        ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

        class StdoutInterceptor:
            def __init__(self, queue, original):
                self.queue = queue
                self.original_stdout = original
                self._closed = False

            def write(self, message):
                if self._closed:
                    return
                # Write to terminal first (with ANSI codes for color)
                try:
                    self.original_stdout.write(message)
                except Exception:
                    pass
                # Strip ANSI escape codes before sending to frontend
                clean_message = ANSI_ESCAPE_PATTERN.sub("", message).strip()
                # Then send to frontend (non-blocking)
                if clean_message:
                    try:
                        self.queue.put_nowait(
                            {
                                "type": "log",
                                "content": clean_message,
                                "timestamp": asyncio.get_event_loop().time(),
                            }
                        )
                    except (asyncio.QueueFull, RuntimeError):
                        pass

            def flush(self):
                if not self._closed:
                    try:
                        self.original_stdout.flush()
                    except Exception:
                        pass

            def close(self):
                """Mark interceptor as closed to prevent further writes."""
                self._closed = True

        interceptor = StdoutInterceptor(log_queue, original_stdout)
        sys.stdout = interceptor

        try:
            await websocket.send_json(
                {"type": "status", "stage": "init", "content": "Initializing..."}
            )

            pdf_path = None
            paper_dir = None

            # Handle PDF upload mode
            if mode == "upload":
                pdf_data = data.get("pdf_data")
                pdf_name = data.get("pdf_name", "exam.pdf")

                if not pdf_data:
                    await websocket.send_json(
                        {"type": "error", "content": "PDF data is required for upload mode"}
                    )
                    return

                # Decode PDF data first to check size
                try:
                    pdf_bytes = base64.b64decode(pdf_data)
                except Exception as e:
                    await websocket.send_json(
                        {"type": "error", "content": f"Invalid base64 PDF data: {e}"}
                    )
                    return

                # Pre-validate filename and file size before writing
                try:
                    safe_name = DocumentValidator.validate_upload_safety(
                        pdf_name, len(pdf_bytes), {".pdf"}
                    )
                except ValueError as e:
                    await websocket.send_json({"type": "error", "content": str(e)})
                    return

                # Create batch directory for this mimic session
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_stem = Path(safe_name).stem
                batch_dir = MIMIC_OUTPUT_DIR / f"mimic_{timestamp}_{pdf_stem}"
                batch_dir.mkdir(parents=True, exist_ok=True)

                # Save uploaded PDF in batch directory
                pdf_path = batch_dir / safe_name

                await websocket.send_json(
                    {"type": "status", "stage": "upload", "content": f"Saving PDF: {safe_name}"}
                )

                # Write the validated PDF bytes
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                # Additional validation (file readability, etc.)
                try:
                    DocumentValidator.validate_file(pdf_path)
                except (ValueError, FileNotFoundError, PermissionError) as e:
                    # Clean up invalid or inaccessible file
                    pdf_path.unlink(missing_ok=True)
                    await websocket.send_json({"type": "error", "content": str(e)})
                    return

                await websocket.send_json(
                    {
                        "type": "status",
                        "stage": "parsing",
                        "content": "Parsing PDF exam paper (MinerU)...",
                    }
                )
                logger.info(f"Saved and validated uploaded PDF to: {pdf_path}")

                # Pass batch_dir as output directory
                pdf_path = str(pdf_path)
                output_dir = str(batch_dir)

            elif mode == "parsed":
                paper_path = data.get("paper_path")
                if not paper_path:
                    await websocket.send_json(
                        {"type": "error", "content": "paper_path is required for parsed mode"}
                    )
                    return
                paper_dir = paper_path

                # Create batch directory for parsed mode too
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                batch_dir = MIMIC_OUTPUT_DIR / f"mimic_{timestamp}_{Path(paper_path).name}"
                batch_dir.mkdir(parents=True, exist_ok=True)
                output_dir = str(batch_dir)

            else:
                await websocket.send_json({"type": "error", "content": f"Unknown mode: {mode}"})
                return

            # Create WebSocket callback for real-time progress updates
            async def ws_callback(event_type: str, data: dict):
                """Send progress updates to the frontend via WebSocket."""
                try:
                    message = {"type": event_type, **data}
                    await websocket.send_json(message)
                except Exception as e:
                    logger.debug(f"WebSocket send failed: {e}")

            # Run the complete mimic workflow with callback
            await websocket.send_json(
                {
                    "type": "status",
                    "stage": "processing",
                    "content": "Executing question generation workflow...",
                }
            )

            result = await mimic_exam_questions(
                pdf_path=pdf_path,
                paper_dir=paper_dir,
                kb_name=kb_name,
                output_dir=output_dir,
                max_questions=max_questions,
                ws_callback=ws_callback,
            )

            if result.get("success"):
                # Results are already sent via ws_callback during generation
                # Just send the final complete signal
                total_ref = result.get("total_reference_questions", 0)
                generated = result.get("generated_questions", [])
                failed = result.get("failed_questions", [])

                logger.success(
                    f"Mimic generation complete: {len(generated)} succeeded, {len(failed)} failed"
                )

                try:
                    await websocket.send_json({"type": "complete"})
                except (RuntimeError, WebSocketDisconnect):
                    logger.debug("WebSocket closed before complete signal could be sent")
            else:
                error_msg = result.get("error", "Unknown error")
                try:
                    await websocket.send_json({"type": "error", "content": error_msg})
                except (RuntimeError, WebSocketDisconnect):
                    pass
                logger.error(f"Mimic generation failed: {error_msg}")

        finally:
            # Close interceptor and restore stdout
            if "interceptor" in locals():
                interceptor.close()
            sys.stdout = original_stdout

    except WebSocketDisconnect:
        logger.debug("Client disconnected during mimic generation")
    except Exception as e:
        logger.exception("Mimic generation error")
        error_msg = format_exception_message(e)
        try:
            await websocket.send_json({"type": "error", "content": error_msg})
        except Exception:
            pass
    finally:
        # Ensure stdout is always restored
        sys.stdout = original_stdout

        # Clean up pusher task
        if pusher_task:
            try:
                pusher_task.cancel()
                await pusher_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            except Exception:
                pass

        # Drain any remaining items in the queue
        try:
            while not log_queue.empty():
                log_queue.get_nowait()
        except Exception:
            pass

        # Close WebSocket
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/generate")
async def websocket_question_generate(websocket: WebSocket):
    await websocket.accept()

    # Get task ID manager
    task_manager = TaskIDManager.get_instance()

    try:
        # 1. Wait for config
        data = await websocket.receive_json()
        requirement = data.get("requirement")
        kb_name = data.get("kb_name", "ai_textbook")
        count = data.get("count", 1)

        if not requirement:
            try:
                await websocket.send_json({"type": "error", "content": "Requirement is required"})
            except (RuntimeError, WebSocketDisconnect):
                pass
            return

        # Generate task ID
        task_key = f"question_{kb_name}_{hash(str(requirement))}"
        task_id = task_manager.generate_task_id("question_gen", task_key)

        # Send task ID to frontend
        try:
            await websocket.send_json({"type": "task_id", "task_id": task_id})
        except (RuntimeError, WebSocketDisconnect):
            logger.debug("WebSocket closed, cannot send task_id")
            return

        logger.info(
            f"[{task_id}] Starting question generation: {requirement.get('knowledge_point', 'Unknown')}"
        )

        # 2. Initialize Coordinator
        # Define unified output directory (DeepTutor/data/user/question)
        root_dir = Path(__file__).parent.parent.parent.parent
        output_base = root_dir / "data" / "user" / "question"

        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
            api_version = getattr(llm_config, "api_version", None)
        except Exception:
            api_key = None
            base_url = None
            api_version = None

        coordinator = AgentCoordinator(
            api_key=api_key,
            base_url=base_url,
            api_version=api_version,
            kb_name=kb_name,
            language=get_ui_language(default=config.get("system", {}).get("language", "en")),
            max_rounds=10,
            output_dir=str(output_base),
        )

        # 3. Setup Log Queue for WebSocket streaming
        log_queue = asyncio.Queue()

        # WebSocket callback for coordinator to send structured updates
        async def ws_callback(data: dict):
            try:
                await log_queue.put(data)
            except Exception:
                pass

        coordinator.set_ws_callback(ws_callback)

        # 4. Define background pusher for logs
        async def log_pusher():
            while True:
                entry = await log_queue.get()
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
                log_queue.task_done()

        pusher_task = asyncio.create_task(log_pusher())

        # 5. Setup LogInterceptor for capturing logger output (same as solve.py)
        # Get the coordinator's logger to intercept
        target_logger = coordinator.logger.logger
        interceptor = LogInterceptor(target_logger, log_queue)

        # 6. Run Generation with LogInterceptor
        try:
            with interceptor:
                try:
                    await websocket.send_json({"type": "status", "content": "started"})
                except (RuntimeError, WebSocketDisconnect):
                    logger.debug("WebSocket closed, stopping question generation")
                    return

                # Use custom mode generation (new streamlined flow)
                logger.info(f"Starting custom mode generation for {count} question(s)")

                # Use the new custom generation method
                batch_result = await coordinator.generate_questions_custom(
                    requirement=requirement,
                    num_questions=count,
                )

                # Results are already sent via WebSocket callbacks in the coordinator
                # Just need to save to history for successful results
                for result in batch_result.get("results", []):
                    # Save to history
                    history_manager.add_entry(
                        activity_type=ActivityType.QUESTION,
                        title=f"{requirement.get('knowledge_point', 'Question')} ({requirement.get('question_type')})",
                        content={
                            "requirement": requirement,
                            "question": result.get("question", {}),
                            "validation": result.get("validation", {}),
                            "kb_name": kb_name,
                        },
                        summary=result.get("question", {}).get("question", "")[:100],
                    )

                # Send final token stats
                try:
                    await websocket.send_json(
                        {"type": "token_stats", "stats": coordinator.token_stats}
                    )
                except (RuntimeError, WebSocketDisconnect):
                    logger.debug("WebSocket closed, stopping question generation")

                # Send batch summary
                try:
                    await websocket.send_json(
                        {
                            "type": "batch_summary",
                            "requested": batch_result.get("requested", count),
                            "completed": batch_result.get("completed", 0),
                            "failed": batch_result.get("failed", 0),
                            "plan": batch_result.get("plan", {}),
                        }
                    )
                except (RuntimeError, WebSocketDisconnect):
                    pass

                if not batch_result.get("success"):
                    logger.warning(
                        f"Question generation had failures: {batch_result.get('failed', 0)} failed"
                    )

                # Wait for any pending messages in the queue to be sent
                # Give the pusher a moment to process remaining messages
                await asyncio.sleep(0.1)
                while not log_queue.empty():
                    await asyncio.sleep(0.05)

                # Send complete signal
                try:
                    await websocket.send_json({"type": "complete"})
                    logger.info(f"[{task_id}] Question generation completed")
                    task_manager.update_task_status(task_id, "completed")
                except (RuntimeError, WebSocketDisconnect):
                    logger.debug("WebSocket closed, cannot send complete signal")

        except Exception as e:
            error_msg = format_exception_message(e)
            error_traceback = traceback.format_exc()
            logger.error(f"Question generation error: {error_msg}")
            logger.error(f"Error traceback:\n{error_traceback}")

            # Log additional context if available
            try:
                if "result" in locals():
                    logger.error(
                        f"Result type: {type(result)}, result keys: {result.keys() if isinstance(result, dict) else 'N/A'}"
                    )
                    if isinstance(result, dict) and "validation" in result:
                        validation = result["validation"]
                        logger.error(f"Validation type: {type(validation)}")
                        if isinstance(validation, dict):
                            logger.error(f"Validation keys: {validation.keys()}")
                            logger.error(
                                f"Issues type: {type(validation.get('issues'))}, value: {validation.get('issues')}"
                            )
                            logger.error(
                                f"Suggestions type: {type(validation.get('suggestions'))}, value: {validation.get('suggestions')}"
                            )
            except Exception as context_error:
                logger.warning(f"Failed to log error context: {context_error}")

            try:
                await websocket.send_json({"type": "error", "content": error_msg})
            except (RuntimeError, WebSocketDisconnect):
                logger.debug("WebSocket closed, cannot send error message")
            task_manager.update_task_status(task_id, "error", error=error_msg)

        finally:
            pusher_task.cancel()
            try:
                await pusher_task
            except asyncio.CancelledError:
                pass
            await websocket.close()

    except WebSocketDisconnect:
        logger.debug("Client disconnected")
    except Exception as e:
        error_msg = format_exception_message(e)
        logger.error(f"WebSocket error: {error_msg}")
