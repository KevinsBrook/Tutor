"""
Knowledge Base API Router
=========================

Handles knowledge base CRUD operations, file uploads, and initialization.
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
from typing import Any, Iterable

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from src.api.utils.progress_broadcaster import ProgressBroadcaster
from src.api.utils.task_id_manager import TaskIDManager
from src.knowledge.add_documents import DocumentAdder
from src.knowledge.initializer import KnowledgeBaseInitializer
from src.knowledge.manager import KnowledgeBaseManager
from src.knowledge.progress_tracker import ProgressStage, ProgressTracker
from src.services.rag.components.routing import FileTypeRouter
from src.services.rag.factory import SELECTABLE_PIPELINE_IDS
from src.utils.document_validator import DocumentValidator
from src.utils.error_utils import format_exception_message

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))
from src.logging import get_logger
from src.services.config import load_config_with_main
from src.services.llm import get_llm_config

# Initialize logger with config
project_root = Path(__file__).parent.parent.parent.parent
config = load_config_with_main("solve_config.yaml", project_root)  # Use any config to get main.yaml
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = get_logger("Knowledge", level="INFO", log_dir=log_dir)

router = APIRouter()

# Constants for byte conversions
BYTES_PER_GB = 1024**3
BYTES_PER_MB = 1024**2
DEFAULT_RAG_PROVIDER = "raganything"
NODE_EXPLANATION_CACHE_FILE = "node_explanations.json"


def normalize_rag_provider(provider: str | None, *, allow_default: bool = True) -> str:
    """Return a stable, user-facing RAG provider id or raise a clear API error."""
    normalized = (provider or "").strip()
    if not normalized and allow_default:
        normalized = DEFAULT_RAG_PROVIDER
    if not normalized:
        raise HTTPException(status_code=400, detail="RAG provider is required")
    if normalized not in SELECTABLE_PIPELINE_IDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"RAG provider '{normalized}' is not available. "
                "Please choose one of: "
                + ", ".join(sorted(SELECTABLE_PIPELINE_IDS))
            ),
        )
    return normalized


def get_provider_supported_extensions(provider: str) -> list[str]:
    """Get stable provider extension list for API responses and validation."""
    normalized = normalize_rag_provider(provider)
    return sorted(FileTypeRouter.get_extensions_for_provider(normalized))


def validate_rag_provider_files(provider: str, filenames: Iterable[str]) -> None:
    """Reject files that the selected provider cannot actually parse."""
    normalized = normalize_rag_provider(provider)
    supported = set(get_provider_supported_extensions(normalized))
    unsupported = []
    for filename in filenames:
        suffix = Path(filename).suffix.lower()
        if suffix not in supported:
            unsupported.append(filename)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{normalized}' does not support: {', '.join(unsupported)}. "
                f"Supported extensions: {', '.join(sorted(supported))}"
            ),
        )


def enrich_rag_provider_info(provider: dict[str, str]) -> dict[str, Any]:
    """Attach parse capability metadata used by Course Center UI."""
    provider_id = normalize_rag_provider(provider.get("id"))
    supported_extensions = get_provider_supported_extensions(provider_id)
    return {
        **provider,
        "supported_extensions": supported_extensions,
        "graph_capable": provider_id in {"raganything", "raganything_docling"}
        or provider_id.startswith("lightrag"),
    }


def is_knowledge_base_initialized(kb_name: str) -> bool:
    """True only when index files exist, not merely when the KB is listed in config."""
    try:
        manager = get_kb_manager()
        info = manager.get_info(kb_name)
        statistics = info.get("statistics", {})
        return bool(statistics.get("rag_initialized"))
    except Exception:
        return False


def format_bytes_human_readable(size_bytes: int) -> str:
    """Format bytes into human-readable string (GB, MB, or bytes)."""
    if size_bytes >= BYTES_PER_GB:
        return f"{size_bytes / BYTES_PER_GB:.1f} GB"
    elif size_bytes >= BYTES_PER_MB:
        return f"{size_bytes / BYTES_PER_MB:.1f} MB"
    else:
        return f"{size_bytes} bytes"


def _safe_read_json(file_path: Path) -> dict[str, Any] | list[Any]:
    """Read JSON file safely and return parsed object."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, (dict, list)):
        raise ValueError(f"Invalid JSON structure in {file_path.name}: expected dict or list")
    return data


def _pick_first_str(source: dict[str, Any], keys: list[str]) -> str | None:
    """Pick first non-empty string value from dict by key priority."""
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_relation_endpoints_from_key(key: str) -> tuple[str | None, str | None]:
    """Best-effort parse relation endpoints from relation key."""
    text = key.strip()
    if not text:
        return None, None

    # Pattern 1: "A -> B"
    if "->" in text:
        left, right = text.split("->", 1)
        left = left.strip(" ()[]{}\"'")
        right = right.strip(" ()[]{}\"'")
        return (left or None, right or None)

    # Pattern 2: "(A, B)"
    tuple_match = re.match(r"^\(?\s*(.+?)\s*,\s*(.+?)\s*\)?$", text)
    if tuple_match:
        left = tuple_match.group(1).strip(" ()[]{}\"'")
        right = tuple_match.group(2).strip(" ()[]{}\"'")
        return (left or None, right or None)

    # Pattern 3: "A|B" / "A::B"
    for sep in ["|", "::", "\t"]:
        if sep in text:
            left, right = text.split(sep, 1)
            left = left.strip(" ()[]{}\"'")
            right = right.strip(" ()[]{}\"'")
            return (left or None, right or None)

    return None, None


def _infer_node_type(label: str) -> str:
    """Infer coarse node type from label text for coloring and filtering."""
    text = label.strip()
    if not text:
        return "entity"
    lower = text.lower()

    if re.search(r"(figure|fig\.?|图\d+|chapter|章节|第\d+章|ch\d+|eq\.?|equation|公式)", lower):
        return "meta"
    if re.search(r"(dataset|数据集|mnist|cifar|imagenet|语料|corpus)", lower):
        return "dataset"
    if re.search(
        r"(function|函数|layer|网络|network|loss|optimizer|梯度|激活|卷积|softmax|relu|sigmoid|norm)",
        lower,
    ):
        return "concept"
    if re.search(
        r"(university|conference|ieee|inc\.|co\.|media|press|出版社|大学|研究所|实验室|arxiv)",
        lower,
    ):
        return "organization"
    if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text):
        return "person"
    if re.fullmatch(r"[a-zA-Z]{1,2}\d{0,2}", text):
        return "symbol"
    return "entity"


def _is_probably_noisy_label(label: str) -> bool:
    """Heuristic filter for low-value nodes frequently produced by OCR/LLM extraction."""
    text = label.strip()
    if not text:
        return True
    if text.lower().startswith("doc-"):
        return True
    if len(text) <= 1:
        return True
    if re.fullmatch(r"[\W_]+", text):
        return True
    if re.search(r"[�]", text):
        return True
    if "?" in text and re.search(r"[\u4e00-\u9fff]", text):
        return True
    if "/" in text and "." in text:
        return True
    if re.fullmatch(r"[a-zA-Z]{1,2}\d{1,2}", text):
        return True
    if re.fullmatch(r"[-+*/=<>~^%|&:.;,()\[\]{}\d\s]+", text):
        return True
    return False


def _build_graph_payload(
    entities_raw: dict[str, Any] | list[Any],
    relations_raw: dict[str, Any] | list[Any],
    max_nodes: int,
    max_edges: int,
    min_degree: int = 1,
    filter_noise: bool = False,
) -> dict[str, Any]:
    """Convert raw entity/relation stores to frontend-friendly graph payload."""
    node_map: dict[str, dict[str, Any]] = {}
    edge_list: list[dict[str, Any]] = []
    edge_seen: set[tuple[str, str, str]] = set()

    def upsert_node(node_id: str, label: str | None = None, node_type: str | None = None):
        nid = node_id.strip()
        if not nid:
            return
        node_label = (label or nid).strip()
        if filter_noise and _is_probably_noisy_label(node_label):
            return
        inferred_type = node_type or _infer_node_type(node_label)
        if nid not in node_map:
            node_map[nid] = {
                "id": nid,
                "label": node_label,
                "type": inferred_type,
            }
        else:
            if node_label and node_map[nid].get("label") == nid:
                node_map[nid]["label"] = node_label
            if inferred_type and node_map[nid].get("type") == "entity":
                node_map[nid]["type"] = inferred_type

    def append_edge(source: str, target: str, relation_label: str, weight: float = 1.0):
        src = source.strip()
        tgt = target.strip()
        if not src or not tgt:
            return
        dedupe_key = (src, tgt, relation_label)
        if dedupe_key in edge_seen:
            return
        edge_seen.add(dedupe_key)

        upsert_node(src)
        upsert_node(tgt)
        if src not in node_map or tgt not in node_map:
            return
        edge_list.append(
            {
                "id": f"e_{len(edge_list)}",
                "source": src,
                "target": tgt,
                "label": relation_label,
                "weight": weight,
            }
        )

    # Parse entities (supports both flat entity stores and LightRAG's doc->entity_names format)
    if isinstance(entities_raw, dict):
        entity_items = entities_raw.items()
    else:
        entity_items = [(str(i), item) for i, item in enumerate(entities_raw)]

    for key, value in entity_items:
        if isinstance(value, dict):
            entity_names = value.get("entity_names")
            if isinstance(entity_names, list):
                for name in entity_names:
                    if isinstance(name, str) and name.strip():
                        upsert_node(name, label=name, node_type="entity")
                continue

        payload = value if isinstance(value, dict) else {}
        entity_id = _pick_first_str(payload, ["id", "entity_id", "entity_name", "name", "entity"])

        # For LightRAG doc-level wrapper keys like "doc-xxxx", don't treat as entity node
        if not entity_id:
            key_text = key.strip()
            if key_text and not key_text.startswith("doc-"):
                entity_id = key_text

        if not entity_id:
            continue

        label = _pick_first_str(payload, ["label", "entity_name", "name", "entity"])
        node_type = _pick_first_str(payload, ["entity_type", "type", "category"])
        description = _pick_first_str(payload, ["description", "summary", "content"])
        upsert_node(entity_id, label=label, node_type=node_type)
        if description:
            node_map[entity_id]["description"] = description

    # Parse relations (supports both flat relation stores and LightRAG's doc->relation_pairs format)
    if isinstance(relations_raw, dict):
        relation_items = relations_raw.items()
    else:
        relation_items = [(str(i), item) for i, item in enumerate(relations_raw)]

    for key, value in relation_items:
        if isinstance(value, dict):
            relation_pairs = value.get("relation_pairs")
            if isinstance(relation_pairs, list):
                for pair in relation_pairs:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        source = str(pair[0]).strip()
                        target = str(pair[1]).strip()
                        if source and target:
                            append_edge(source, target, "related_to", 1.0)
                continue

        payload = value if isinstance(value, dict) else {}
        source = _pick_first_str(
            payload,
            ["source", "source_id", "src_id", "from", "head", "subject", "src"],
        )
        target = _pick_first_str(
            payload,
            ["target", "target_id", "tgt_id", "to", "tail", "object", "dst"],
        )
        if not source or not target:
            parsed_source, parsed_target = _parse_relation_endpoints_from_key(str(key))
            source = source or parsed_source
            target = target or parsed_target
        if not source or not target:
            continue

        relation_label = _pick_first_str(
            payload,
            ["relation", "relation_type", "predicate", "label", "keyword"],
        ) or "related_to"
        weight_raw = payload.get("weight", payload.get("score", 1.0))
        try:
            weight = float(weight_raw)
        except (TypeError, ValueError):
            weight = 1.0
        append_edge(source, target, relation_label, weight)

    # Compute degree for filtering/ranking.
    degree_map: dict[str, int] = {nid: 0 for nid in node_map}
    for edge in edge_list:
        source = edge["source"]
        target = edge["target"]
        if source in degree_map:
            degree_map[source] += 1
        if target in degree_map:
            degree_map[target] += 1

    effective_min_degree = max(0, min_degree)
    candidate_node_ids = [
        nid for nid in node_map if degree_map.get(nid, 0) >= effective_min_degree
    ]
    if not candidate_node_ids and effective_min_degree > 0:
        candidate_node_ids = [nid for nid in node_map if degree_map.get(nid, 0) > 0]
    if not candidate_node_ids:
        candidate_node_ids = list(node_map.keys())

    connected_ids = [nid for nid in candidate_node_ids if degree_map.get(nid, 0) > 0]
    connected_ids.sort(key=lambda nid: (-degree_map.get(nid, 0), node_map[nid]["label"]))
    isolated_ids = [nid for nid in candidate_node_ids if degree_map.get(nid, 0) == 0]
    isolated_ids.sort(key=lambda nid: node_map[nid]["label"])
    ordered_node_ids = connected_ids + isolated_ids

    limited_node_ids = ordered_node_ids[:max_nodes]
    limited_nodes = []
    for nid in limited_node_ids:
        node = node_map[nid]
        degree = degree_map.get(nid, 0)
        node["degree"] = degree
        node["size"] = min(56, 18 + degree * 1.6)
        limited_nodes.append(node)

    allowed_node_ids = {node["id"] for node in limited_nodes}
    limited_edges = [
        edge
        for edge in edge_list
        if edge["source"] in allowed_node_ids and edge["target"] in allowed_node_ids
    ][:max_edges]

    return {
        "nodes": limited_nodes,
        "edges": limited_edges,
        "stats": {
            "raw_nodes": len(node_map),
            "raw_edges": len(edge_list),
            "filtered_nodes": len(candidate_node_ids),
            "returned_nodes": len(limited_nodes),
            "returned_edges": len(limited_edges),
            "truncated": len(node_map) > len(limited_nodes) or len(edge_list) > len(limited_edges),
        },
    }


def _normalize_text(text: str) -> str:
    """Normalize text for compact display."""
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate_text(text: str, max_len: int = 420) -> str:
    """Truncate text safely for UI payloads."""
    normalized = _normalize_text(text)
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3].rstrip() + "..."


def _looks_english_text(text: str) -> bool:
    """Heuristic: determine if text is predominantly English."""
    if not text:
        return False
    letters = re.findall(r"[A-Za-z]", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    # Mostly Latin letters and very little Chinese characters
    return len(letters) >= 30 and len(cjk) * 2 < len(letters)


def _get_dict_value_case_insensitive(data: dict[str, Any], key: str) -> Any | None:
    """Get dict value by case-insensitive key matching."""
    if key in data:
        return data[key]
    lower_key = key.lower()
    for k, v in data.items():
        if isinstance(k, str) and k.lower() == lower_key:
            return v
    return None


def _node_explanation_cache_path(kb_dir: Path) -> Path:
    return kb_dir / "rag_storage" / NODE_EXPLANATION_CACHE_FILE


def _read_node_explanation_cache(kb_dir: Path) -> dict[str, Any]:
    cache_file = _node_explanation_cache_path(kb_dir)
    if not cache_file.exists():
        return {"version": 1, "nodes": {}}
    try:
        data = _safe_read_json(cache_file)
        if isinstance(data, dict):
            nodes = data.get("nodes")
            if isinstance(nodes, dict):
                return data
    except Exception:
        pass
    return {"version": 1, "nodes": {}}


def _write_node_explanation_cache(kb_dir: Path, cache: dict[str, Any]) -> None:
    cache_file = _node_explanation_cache_path(kb_dir)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as fp:
        json.dump(cache, fp, indent=2, ensure_ascii=False)


def _estimate_node_explanation_confidence(explanation: str, source: str) -> int:
    if not explanation:
        return 0
    if source.startswith("llm_generated"):
        return 86
    if source.endswith("_zh"):
        return 82
    if source == "vdb_entities":
        return 72
    if source == "graph_description":
        return 68
    if source == "snippet_heuristic":
        return 58
    return 50


_kb_base_dir = _project_root / "data" / "knowledge_bases"

# Lazy initialization
kb_manager = None


def get_kb_manager():
    """Get KnowledgeBaseManager instance (lazy init)"""
    global kb_manager
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(base_dir=str(_kb_base_dir))
    return kb_manager


class KnowledgeBaseInfo(BaseModel):
    name: str
    is_default: bool
    statistics: dict


class LinkFolderRequest(BaseModel):
    """Request model for linking a local folder to a KB."""

    folder_path: str


class LinkedFolderInfo(BaseModel):
    """Response model for linked folder information."""

    id: str
    path: str
    added_at: str
    file_count: int


async def run_initialization_task(initializer: KnowledgeBaseInitializer):
    """Background task for knowledge base initialization"""
    task_manager = TaskIDManager.get_instance()
    task_id = task_manager.generate_task_id("kb_init", initializer.kb_name)

    try:
        if not initializer.progress_tracker:
            initializer.progress_tracker = ProgressTracker(
                initializer.kb_name, initializer.base_dir
            )

        initializer.progress_tracker.task_id = task_id

        logger.info(f"[{task_id}] Initializing KB: {initializer.kb_name}")

        init_success = await initializer.process_documents()
        if not init_success:
            error_msg = "Knowledge base initialization failed during document processing"
            logger.error(f"[{task_id}] KB '{initializer.kb_name}' init failed: {error_msg}")
            task_manager.update_task_status(task_id, "error", error=error_msg)
            if initializer.progress_tracker:
                initializer.progress_tracker.update(
                    ProgressStage.ERROR,
                    "Initialization failed during document processing",
                    error=error_msg,
                )
            return

        initializer.extract_numbered_items()

        initializer.progress_tracker.update(
            ProgressStage.COMPLETED, "Knowledge base initialization complete!", current=1, total=1
        )

        logger.success(f"[{task_id}] KB '{initializer.kb_name}' initialized")
        try:
            get_kb_manager().update_kb_status(initializer.kb_name, "ready")
        except Exception as status_err:
            logger.warning(f"[{task_id}] Failed to mark KB ready: {status_err}")
        task_manager.update_task_status(task_id, "completed")
    except Exception as e:
        error_msg = str(e)

        logger.error(f"[{task_id}] KB '{initializer.kb_name}' init failed: {error_msg}")

        task_manager.update_task_status(task_id, "error", error=error_msg)

        if initializer.progress_tracker:
            initializer.progress_tracker.update(
                ProgressStage.ERROR, f"Initialization failed: {error_msg}", error=error_msg
            )
        try:
            get_kb_manager().update_kb_status(
                initializer.kb_name,
                "error",
                progress={
                    "stage": "error",
                    "message": f"Initialization failed: {error_msg}",
                    "percent": 100,
                    "error": error_msg,
                },
            )
        except Exception as status_err:
            logger.warning(f"[{task_id}] Failed to mark KB error: {status_err}")


async def run_upload_processing_task(
    kb_name: str,
    base_dir: str,
    api_key: str,
    base_url: str,
    uploaded_file_paths: list[str],
    rag_provider: str = None,
    folder_id: str = None,
):
    """Background task for processing uploaded files.

    Args:
        kb_name: Knowledge base name
        base_dir: Base directory for knowledge bases
        api_key: LLM API key
        base_url: LLM API base URL
        uploaded_file_paths: List of file paths to process
        rag_provider: RAG provider (ignored - we use the one from KB metadata)
        folder_id: Optional folder ID for sync state update
    """
    task_manager = TaskIDManager.get_instance()
    task_key = f"{kb_name}_upload_{len(uploaded_file_paths)}"
    task_id = task_manager.generate_task_id("kb_upload", task_key)

    progress_tracker = ProgressTracker(kb_name, Path(base_dir))
    progress_tracker.task_id = task_id

    try:
        logger.info(f"[{task_id}] Processing {len(uploaded_file_paths)} files to KB '{kb_name}'")
        progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Processing {len(uploaded_file_paths)} files...",
            current=0,
            total=len(uploaded_file_paths),
        )

        adder = DocumentAdder(
            kb_name=kb_name,
            base_dir=base_dir,
            api_key=api_key,
            base_url=base_url,
            progress_tracker=progress_tracker,
            rag_provider=rag_provider,
        )

        # Stage files and check for duplicates
        staged_files = adder.add_documents(uploaded_file_paths, allow_duplicates=False)

        if not staged_files:
            logger.info(f"[{task_id}] No new files to process (all duplicates or invalid)")
            progress_tracker.update(
                ProgressStage.COMPLETED,
                "No new files to process (all duplicates or invalid)",
                current=0,
                total=0,
            )
            task_manager.update_task_status(task_id, "completed")
            return

        # Process staged files
        processed_files = await adder.process_new_documents(staged_files)

        if processed_files:
            progress_tracker.update(
                ProgressStage.EXTRACTING_ITEMS,
                "Extracting numbered items...",
                current=0,
                total=len(processed_files),
            )
            adder.extract_numbered_items_for_new_docs(processed_files, batch_size=20)

        adder.update_metadata(len(processed_files) if processed_files else 0)

        # Update folder sync state if this was a folder sync
        if folder_id and processed_files:
            try:
                manager = get_kb_manager()
                manager.update_folder_sync_state(
                    kb_name, folder_id, [str(f) for f in processed_files]
                )
                logger.info(f"[{task_id}] Updated folder sync state for folder '{folder_id}'")
            except Exception as sync_err:
                logger.warning(f"[{task_id}] Failed to update folder sync state: {sync_err}")

        num_processed = len(processed_files) if processed_files else 0
        progress_tracker.update(
            ProgressStage.COMPLETED,
            f"Successfully processed {num_processed} files!",
            current=num_processed,
            total=num_processed,
        )

        logger.success(f"[{task_id}] Processed {num_processed} files to KB '{kb_name}'")
        try:
            get_kb_manager().update_kb_status(kb_name, "ready")
        except Exception as status_err:
            logger.warning(f"[{task_id}] Failed to mark KB ready: {status_err}")
        task_manager.update_task_status(task_id, "completed")
    except Exception as e:
        error_msg = f"Upload processing failed (KB '{kb_name}'): {e}"
        logger.error(f"[{task_id}] {error_msg}")

        task_manager.update_task_status(task_id, "error", error=error_msg)

        progress_tracker.update(
            ProgressStage.ERROR, f"Processing failed: {error_msg}", error=error_msg
        )
        try:
            get_kb_manager().update_kb_status(
                kb_name,
                "error",
                progress={
                    "stage": "error",
                    "message": f"Processing failed: {error_msg}",
                    "percent": 100,
                    "error": error_msg,
                },
            )
        except Exception as status_err:
            logger.warning(f"[{task_id}] Failed to mark KB error: {status_err}")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        manager = get_kb_manager()
        config_exists = manager.config_file.exists()
        kb_count = len(manager.list_knowledge_bases())
        return {
            "status": "ok",
            "config_file": str(manager.config_file),
            "config_exists": config_exists,
            "base_dir": str(manager.base_dir),
            "base_dir_exists": manager.base_dir.exists(),
            "knowledge_bases_count": kb_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@router.get("/rag-providers")
async def get_rag_providers():
    """Get list of available RAG providers."""
    try:
        from src.services.rag.service import RAGService

        providers = [
            enrich_rag_provider_info(provider)
            for provider in RAGService.list_providers(include_experimental=True)
        ]
        return {"providers": providers}
    except Exception as e:
        logger.error(f"Error getting RAG providers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs")
async def get_all_kb_configs():
    """Get all knowledge base configurations from centralized config file."""
    try:
        from src.services.config import get_kb_config_service

        service = get_kb_config_service()
        return service.get_all_configs()
    except Exception as e:
        logger.error(f"Error getting KB configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_name}/config")
async def get_kb_config(kb_name: str):
    """Get configuration for a specific knowledge base."""
    try:
        from src.services.config import get_kb_config_service

        service = get_kb_config_service()
        config = service.get_kb_config(kb_name)
        return {"kb_name": kb_name, "config": config}
    except Exception as e:
        logger.error(f"Error getting config for KB '{kb_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_name}/config")
async def update_kb_config(kb_name: str, config: dict):
    """Update configuration for a specific knowledge base."""
    try:
        from src.services.config import get_kb_config_service

        service = get_kb_config_service()
        service.set_kb_config(kb_name, config)
        return {"status": "success", "kb_name": kb_name, "config": service.get_kb_config(kb_name)}
    except Exception as e:
        logger.error(f"Error updating config for KB '{kb_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/sync")
async def sync_configs_from_metadata():
    """Sync all KB configurations from their metadata.json files to centralized config."""
    try:
        from src.services.config import get_kb_config_service

        service = get_kb_config_service()
        service.sync_all_from_metadata(_kb_base_dir)
        return {"status": "success", "message": "Configurations synced from metadata files"}
    except Exception as e:
        logger.error(f"Error syncing configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/default")
async def get_default_kb():
    """Get the default knowledge base."""
    try:
        manager = get_kb_manager()
        default_kb = manager.get_default()
        return {"default_kb": default_kb}
    except Exception as e:
        logger.error(f"Error getting default KB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/default/{kb_name}")
async def set_default_kb(kb_name: str):
    """Set the default knowledge base."""
    try:
        manager = get_kb_manager()

        # Verify KB exists
        if kb_name not in manager.list_knowledge_bases():
            raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")

        manager.set_default(kb_name)
        return {"status": "success", "default_kb": kb_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default KB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=list[KnowledgeBaseInfo])
async def list_knowledge_bases():
    """List all available knowledge bases with their details."""
    try:
        manager = get_kb_manager()
        kb_names = manager.list_knowledge_bases()

        logger.info(f"Found {len(kb_names)} knowledge bases: {kb_names}")

        if not kb_names:
            logger.info("No knowledge bases found, returning empty list")
            return []

        result = []
        errors = []

        for name in kb_names:
            try:
                kb_config = manager.config.get("knowledge_bases", {}).get(name, {})
                metadata = {}
                try:
                    metadata = manager.get_metadata(name)
                except Exception:
                    metadata = {}
                if (
                    kb_config.get("scope") == "course_material"
                    or metadata.get("scope") == "course_material"
                    or name.startswith("course_")
                ):
                    logger.debug("Skipping course-scoped KB from public list: %s", name)
                    continue
                info = manager.get_info(name)
                logger.debug(f"Successfully got info for KB '{name}': {info.get('statistics', {})}")
                result.append(
                    KnowledgeBaseInfo(
                        name=info["name"],
                        is_default=info["is_default"],
                        statistics=info.get("statistics", {}),
                    )
                )
            except Exception as e:
                error_msg = f"Error getting info for KB '{name}': {e}"
                errors.append(error_msg)
                logger.warning(f"{error_msg}\n{traceback.format_exc()}")
                try:
                    kb_dir = manager.base_dir / name
                    if kb_dir.exists():
                        logger.info(f"KB '{name}' directory exists, creating fallback info")
                        result.append(
                            KnowledgeBaseInfo(
                                name=name,
                                is_default=name == manager.get_default(),
                                statistics={
                                    "raw_documents": 0,
                                    "images": 0,
                                    "content_lists": 0,
                                    "rag_initialized": False,
                                },
                            )
                        )
                except Exception as fallback_err:
                    logger.error(f"Fallback also failed for KB '{name}': {fallback_err}")

        if errors and not result:
            error_detail = f"Failed to load knowledge bases. Errors: {'; '.join(errors)}"
            logger.error(error_detail)
            raise HTTPException(status_code=500, detail=error_detail)

        if errors:
            logger.warning(
                f"Some KBs had errors, returning {len(result)} results. Errors: {errors}"
            )

        logger.info(f"Returning {len(result)} knowledge bases")
        return result
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error listing knowledge bases: {e}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to list knowledge bases: {e!s}")


@router.get("/{kb_name}")
async def get_knowledge_base_details(kb_name: str):
    """Get detailed info for a specific KB."""
    try:
        manager = get_kb_manager()
        return manager.get_info(kb_name)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_name}/graph")
async def get_knowledge_graph_data(
    kb_name: str,
    max_nodes: int = 300,
    max_edges: int = 800,
    min_degree: int = 1,
    filter_noise: bool = True,
):
    """Get knowledge graph data (nodes and edges) for visualization."""
    if max_nodes < 10 or max_nodes > 5000:
        raise HTTPException(status_code=400, detail="max_nodes must be between 10 and 5000")
    if max_edges < 10 or max_edges > 20000:
        raise HTTPException(status_code=400, detail="max_edges must be between 10 and 20000")
    if min_degree < 0 or min_degree > 20:
        raise HTTPException(status_code=400, detail="min_degree must be between 0 and 20")

    try:
        manager = get_kb_manager()
        kb_info = manager.get_info(kb_name)
        rag_provider = kb_info.get("statistics", {}).get("rag_provider")

        if rag_provider == "llamaindex":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Knowledge base '{kb_name}' uses provider 'llamaindex' "
                    "which does not build a graph store."
                ),
            )

        kb_dir = manager.get_knowledge_base_path(kb_name)
        rag_storage_dir = kb_dir / "rag_storage"
        entities_file = rag_storage_dir / "kv_store_full_entities.json"
        relations_file = rag_storage_dir / "kv_store_full_relations.json"

        if not rag_storage_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Graph storage not found for knowledge base '{kb_name}'",
            )

        if not entities_file.exists() or not relations_file.exists():
            diagnostic_msg = (
                "Graph data files are not available yet. "
                "Please reprocess documents or use a graph-capable provider."
            )
            doc_status_file = rag_storage_dir / "kv_store_doc_status.json"
            if doc_status_file.exists():
                try:
                    status_data = _safe_read_json(doc_status_file)
                    if isinstance(status_data, dict):
                        failed_messages = []
                        for _, item in status_data.items():
                            if not isinstance(item, dict):
                                continue
                            if str(item.get("status", "")).lower() == "failed":
                                error_msg = _pick_first_str(item, ["error_msg", "error", "message"])
                                if error_msg:
                                    failed_messages.append(error_msg)
                        if failed_messages:
                            diagnostic_msg = (
                                "Graph building failed in document pipeline. "
                                f"Last error: {failed_messages[0]}"
                            )
                except Exception:
                    pass

            return {
                "kb_name": kb_name,
                "rag_provider": rag_provider,
                "nodes": [],
                "edges": [],
                "stats": {
                    "raw_nodes": 0,
                    "raw_edges": 0,
                    "returned_nodes": 0,
                    "returned_edges": 0,
                    "truncated": False,
                },
                "message": diagnostic_msg,
            }

        entities_raw = _safe_read_json(entities_file)
        relations_raw = _safe_read_json(relations_file)
        graph_payload = _build_graph_payload(
            entities_raw=entities_raw,
            relations_raw=relations_raw,
            max_nodes=max_nodes,
            max_edges=max_edges,
            min_degree=min_degree,
            filter_noise=filter_noise,
        )

        return {
            "kb_name": kb_name,
            "rag_provider": rag_provider,
            **graph_payload,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        logger.error(f"Error loading graph data for KB '{kb_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_name}/graph/node-detail")
async def get_graph_node_detail(
    kb_name: str,
    node_id: str,
    use_llm: bool = True,
    force_chinese: bool = True,
    max_neighbors: int = 20,
):
    """Get detailed information for a graph node."""
    if not node_id.strip():
        raise HTTPException(status_code=400, detail="node_id is required")
    if max_neighbors < 1 or max_neighbors > 100:
        raise HTTPException(status_code=400, detail="max_neighbors must be between 1 and 100")

    try:
        manager = get_kb_manager()
        kb_dir = manager.get_knowledge_base_path(kb_name)
        rag_storage_dir = kb_dir / "rag_storage"
        entities_file = rag_storage_dir / "kv_store_full_entities.json"
        relations_file = rag_storage_dir / "kv_store_full_relations.json"
        entity_chunks_file = rag_storage_dir / "kv_store_entity_chunks.json"
        text_chunks_file = rag_storage_dir / "kv_store_text_chunks.json"
        vdb_entities_file = rag_storage_dir / "vdb_entities.json"

        if not entities_file.exists() or not relations_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Graph data not found for knowledge base '{kb_name}'",
            )

        entities_raw = _safe_read_json(entities_file)
        relations_raw = _safe_read_json(relations_file)
        graph_payload = _build_graph_payload(
            entities_raw=entities_raw,
            relations_raw=relations_raw,
            max_nodes=5000,
            max_edges=20000,
            min_degree=0,
            filter_noise=False,
        )

        node_id_input = node_id.strip()
        target_node = None
        for node in graph_payload["nodes"]:
            nid = str(node.get("id", ""))
            if nid == node_id_input or nid.lower() == node_id_input.lower():
                target_node = node
                break
        if not target_node:
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id_input}' not found in knowledge graph",
            )

        canonical_id = str(target_node["id"])
        node_label = str(target_node.get("label") or canonical_id)

        outgoing = [e for e in graph_payload["edges"] if e["source"] == canonical_id]
        incoming = [e for e in graph_payload["edges"] if e["target"] == canonical_id]

        neighbor_counts: dict[str, int] = {}
        for edge in outgoing:
            nid = edge["target"]
            neighbor_counts[nid] = neighbor_counts.get(nid, 0) + 1
        for edge in incoming:
            nid = edge["source"]
            neighbor_counts[nid] = neighbor_counts.get(nid, 0) + 1

        node_lookup = {str(n["id"]): n for n in graph_payload["nodes"]}
        related_nodes = []
        for nid, cnt in sorted(neighbor_counts.items(), key=lambda x: x[1], reverse=True)[
            :max_neighbors
        ]:
            n = node_lookup.get(nid, {})
            related_nodes.append(
                {
                    "id": nid,
                    "label": str(n.get("label") or nid),
                    "type": str(n.get("type") or "entity"),
                    "relation_count": cnt,
                    "degree": int(n.get("degree") or 0),
                }
            )

        explanation = ""
        explanation_source = "none"

        # 1) Prefer description in node payload if already available
        raw_description = str(target_node.get("description") or "").strip()
        if raw_description:
            explanation = _truncate_text(raw_description, 700)
            explanation_source = "graph_description"

        # 2) Fallback to vdb_entities content (often high quality extracted definition)
        if not explanation and vdb_entities_file.exists():
            try:
                vdb_data = _safe_read_json(vdb_entities_file)
                if isinstance(vdb_data, dict):
                    candidates = vdb_data.get("data")
                    if isinstance(candidates, list):
                        best_content = ""
                        for item in candidates:
                            if not isinstance(item, dict):
                                continue
                            entity_name = str(item.get("entity_name") or "").strip()
                            if entity_name and entity_name.lower() == canonical_id.lower():
                                content = _normalize_text(str(item.get("content") or ""))
                                if len(content) > len(best_content):
                                    best_content = content
                        if best_content:
                            explanation = _truncate_text(best_content, 700)
                            explanation_source = "vdb_entities"
            except Exception:
                pass

        chunk_snippets = []
        chunk_ids: list[str] = []

        if entity_chunks_file.exists():
            try:
                entity_chunk_data = _safe_read_json(entity_chunks_file)
                if isinstance(entity_chunk_data, dict):
                    rec = _get_dict_value_case_insensitive(entity_chunk_data, canonical_id)
                    if isinstance(rec, dict):
                        raw_chunk_ids = rec.get("chunk_ids")
                        if isinstance(raw_chunk_ids, list):
                            chunk_ids = [str(cid) for cid in raw_chunk_ids if str(cid).strip()]
            except Exception:
                pass

        if chunk_ids and text_chunks_file.exists():
            try:
                text_chunks_data = _safe_read_json(text_chunks_file)
                if isinstance(text_chunks_data, dict):
                    for cid in chunk_ids[:6]:
                        chunk_payload = text_chunks_data.get(cid)
                        if not isinstance(chunk_payload, dict):
                            continue
                        content = _normalize_text(str(chunk_payload.get("content") or ""))
                        if not content:
                            continue
                        chunk_snippets.append(
                            {
                                "chunk_id": cid,
                                "excerpt": _truncate_text(content, 240),
                            }
                        )
            except Exception:
                pass

        # 3) If still no explanation, build heuristic summary from snippets
        if not explanation and chunk_snippets:
            first = chunk_snippets[0]["excerpt"]
            explanation = _truncate_text(
                f"{node_label} appears in multiple knowledge chunks. Relevant excerpt: {first}",
                700,
            )
            explanation_source = "snippet_heuristic"

        # 4) Optional LLM augmentation as final fallback
        llm_error = None
        if use_llm and (not explanation or len(explanation) < 80):
            try:
                from src.services.llm import complete as llm_complete

                context_text = "\n".join(
                    [f"- {s['excerpt']}" for s in chunk_snippets[:4] if s.get("excerpt")]
                )
                llm_prompt = (
                    f"请用中文简明解释术语“{node_label}”。\n"
                    "要求：\n"
                    "1) 先给一句定义；2) 再说明它在机器学习/深度学习中的作用；\n"
                    "3) 不确定时明确说“可能”而不要编造；4) 总长度120-220字。\n"
                )
                if context_text:
                    llm_prompt += f"\n可参考上下文：\n{context_text}\n"
                llm_answer = await llm_complete(
                    prompt=llm_prompt,
                    system_prompt="你是严谨的知识图谱术语解释助手。",
                    temperature=0.2,
                    max_tokens=260,
                )
                llm_answer = _normalize_text(str(llm_answer))
                if llm_answer:
                    explanation = _truncate_text(llm_answer, 700)
                    explanation_source = "llm_generated"
            except Exception as e:
                llm_error = str(e)

        # 5) Optional Chinese normalization for explanation text
        if use_llm and force_chinese and explanation and _looks_english_text(explanation):
            try:
                from src.services.llm import complete as llm_complete

                translate_prompt = (
                    f"请把下面这段术语解释翻译并改写为简洁中文（120-260字），"
                    "保留术语含义，不要新增原文没有的结论。\n"
                    f"术语：{node_label}\n"
                    f"原文：{explanation}"
                )
                zh_explanation = await llm_complete(
                    prompt=translate_prompt,
                    system_prompt="你是严谨的技术术语中文解释助手。",
                    temperature=0.2,
                    max_tokens=320,
                )
                zh_explanation = _normalize_text(str(zh_explanation))
                if zh_explanation:
                    explanation = _truncate_text(zh_explanation, 700)
                    explanation_source = f"{explanation_source}_zh"
            except Exception as e:
                if not llm_error:
                    llm_error = str(e)

        return {
            "kb_name": kb_name,
            "node": {
                "id": canonical_id,
                "label": node_label,
                "type": str(target_node.get("type") or "entity"),
                "degree": int(target_node.get("degree") or 0),
            },
            "explanation": explanation,
            "explanation_source": explanation_source,
            "snippet_count": len(chunk_snippets),
            "chunk_snippets": chunk_snippets,
            "stats": {
                "outgoing": len(outgoing),
                "incoming": len(incoming),
                "neighbor_count": len(neighbor_counts),
            },
            "related_nodes": related_nodes,
            "llm_error": llm_error,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        logger.error(f"Error loading node detail for KB '{kb_name}', node '{node_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def generate_node_explanation_cache(
    kb_name: str,
    *,
    use_llm: bool = True,
    force_chinese: bool = True,
    refresh: bool = False,
    max_nodes: int = 5000,
) -> dict[str, Any]:
    """Precompute graph node explanations using the same path as node-detail."""
    manager = get_kb_manager()
    kb_dir = manager.get_knowledge_base_path(kb_name)
    rag_storage_dir = kb_dir / "rag_storage"
    entities_file = rag_storage_dir / "kv_store_full_entities.json"
    relations_file = rag_storage_dir / "kv_store_full_relations.json"

    if not entities_file.exists() or not relations_file.exists():
        return {"success": False, "cached_count": 0, "message": "Graph data not found"}

    graph_payload = _build_graph_payload(
        entities_raw=_safe_read_json(entities_file),
        relations_raw=_safe_read_json(relations_file),
        max_nodes=max_nodes,
        max_edges=20000,
        min_degree=0,
        filter_noise=True,
    )
    cache = _read_node_explanation_cache(kb_dir)
    cache_nodes = cache.setdefault("nodes", {})
    if not isinstance(cache_nodes, dict):
        cache_nodes = {}
        cache["nodes"] = cache_nodes

    cached_count = 0
    skipped_count = 0
    failed_count = 0
    for node in graph_payload.get("nodes", []):
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        if not refresh and isinstance(cache_nodes.get(node_id), dict):
            existing = cache_nodes[node_id]
            if str(existing.get("explanation") or "").strip():
                skipped_count += 1
                continue
        try:
            detail = await get_graph_node_detail(
                kb_name=kb_name,
                node_id=node_id,
                use_llm=use_llm,
                force_chinese=force_chinese,
                max_neighbors=20,
            )
            explanation = _truncate_text(str(detail.get("explanation") or ""), 900)
            source = str(detail.get("explanation_source") or "none")
            cache_nodes[node_id] = {
                "id": node_id,
                "label": str(detail.get("node", {}).get("label") or node.get("label") or node_id),
                "type": str(detail.get("node", {}).get("type") or node.get("type") or "entity"),
                "degree": int(detail.get("node", {}).get("degree") or node.get("degree") or 0),
                "explanation": explanation,
                "explanation_source": source,
                "confidence": _estimate_node_explanation_confidence(explanation, source),
                "snippet_count": int(detail.get("snippet_count") or 0),
                "updated_at": datetime.utcnow().isoformat(),
            }
            cached_count += 1
        except Exception as exc:
            cache_nodes[node_id] = {
                "id": node_id,
                "label": str(node.get("label") or node_id),
                "type": str(node.get("type") or "entity"),
                "degree": int(node.get("degree") or 0),
                "explanation": "",
                "explanation_source": "error",
                "confidence": 0,
                "error": str(exc),
                "updated_at": datetime.utcnow().isoformat(),
            }
            failed_count += 1

    cache.update(
        {
            "version": 1,
            "kb_name": kb_name,
            "generated_at": datetime.utcnow().isoformat(),
            "use_llm": use_llm,
            "force_chinese": force_chinese,
            "max_nodes": max_nodes,
            "stats": {
                "graph_nodes": len(graph_payload.get("nodes", [])),
                "cached_count": cached_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
            },
        }
    )
    _write_node_explanation_cache(kb_dir, cache)
    return {"success": True, **cache["stats"]}


@router.delete("/{kb_name}")
async def delete_knowledge_base(kb_name: str):
    """Delete a knowledge base."""
    try:
        manager = get_kb_manager()
        success = manager.delete_knowledge_base(kb_name, confirm=True)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete knowledge base")
        logger.info(f"KB '{kb_name}' deleted")
        return {"message": f"Knowledge base '{kb_name}' deleted successfully"}
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/upload")
async def upload_files(
    kb_name: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    rag_provider: str = Form(None),
):
    """Upload files to a knowledge base and process them in background."""
    try:
        manager = get_kb_manager()
        kb_path = manager.get_knowledge_base_path(kb_name)
        raw_dir = kb_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        metadata = manager.get_metadata(kb_name)
        existing_provider = metadata.get("rag_provider") if isinstance(metadata, dict) else None
        provider = normalize_rag_provider(existing_provider or rag_provider)
        validate_rag_provider_files(provider, [file.filename or "" for file in files])

        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"LLM config error: {e!s}")

        uploaded_files = []
        uploaded_file_paths = []

        # 1. Save files and validate size during streaming
        for file in files:
            file_path = None
            try:
                # Sanitize filename first (without size validation)
                sanitized_filename = DocumentValidator.validate_upload_safety(
                    file.filename,
                    None,
                    set(get_provider_supported_extensions(provider)),
                )
                file.filename = sanitized_filename

                # Save file to disk with size checking during streaming
                file_path = raw_dir / file.filename
                max_size = DocumentValidator.MAX_FILE_SIZE
                written_bytes = 0
                with open(file_path, "wb") as buffer:
                    for chunk in iter(lambda: file.file.read(8192), b""):
                        written_bytes += len(chunk)
                        if written_bytes > max_size:
                            # Format size in human-readable format
                            size_str = format_bytes_human_readable(max_size)
                            raise HTTPException(
                                status_code=400,
                                detail=f"File '{file.filename}' exceeds maximum size limit of {size_str}",
                            )
                        buffer.write(chunk)

                # Validate with actual size (additional checks)
                DocumentValidator.validate_upload_safety(
                    file.filename,
                    written_bytes,
                    set(get_provider_supported_extensions(provider)),
                )

                uploaded_files.append(file.filename)
                uploaded_file_paths.append(str(file_path))

            except Exception as e:
                # Clean up partially saved file
                if file_path and file_path.exists():
                    try:
                        os.unlink(file_path)
                    except OSError:
                        pass

                error_message = (
                    f"Validation failed for file '{file.filename}': {format_exception_message(e)}"
                )
                logger.error(error_message, exc_info=True)
                raise HTTPException(status_code=400, detail=error_message) from e

        logger.info(f"Uploading {len(uploaded_files)} files to KB '{kb_name}'")

        if is_knowledge_base_initialized(kb_name):
            background_tasks.add_task(
                run_upload_processing_task,
                kb_name=kb_name,
                base_dir=str(_kb_base_dir),
                api_key=api_key,
                base_url=base_url,
                uploaded_file_paths=uploaded_file_paths,
                rag_provider=provider,
            )
        else:
            progress_tracker = ProgressTracker(kb_name, _kb_base_dir)
            initializer = KnowledgeBaseInitializer(
                kb_name=kb_name,
                base_dir=str(_kb_base_dir),
                api_key=api_key,
                base_url=base_url,
                progress_tracker=progress_tracker,
                rag_provider=provider,
            )
            initializer.create_directory_structure()
            progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Saved {len(uploaded_files)} files, preparing to initialize...",
                current=0,
                total=len(uploaded_files),
            )
            manager.update_kb_status(
                kb_name,
                "initializing",
                progress={
                    "stage": "processing_documents",
                    "message": "Initializing knowledge base with uploaded files...",
                    "percent": 0,
                    "current": 0,
                    "total": len(uploaded_files),
                },
            )
            manager.config = manager._load_config()
            if kb_name in manager.config.get("knowledge_bases", {}):
                manager.config["knowledge_bases"][kb_name]["rag_provider"] = provider
                manager._save_config()
            background_tasks.add_task(run_initialization_task, initializer)

        return {
            "message": f"Uploaded {len(uploaded_files)} files. Processing in background.",
            "files": uploaded_files,
            "rag_provider": provider,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        # Unexpected failure (Server error)
        formatted_error = format_exception_message(e)
        raise HTTPException(status_code=500, detail=formatted_error) from e


@router.post("/create")
async def create_knowledge_base(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    rag_provider: str = Form("raganything"),
):
    """Create a new knowledge base and initialize it with files."""
    try:
        provider = normalize_rag_provider(rag_provider)
        validate_rag_provider_files(provider, [file.filename or "" for file in files])
        manager = get_kb_manager()
        if name in manager.list_knowledge_bases():
            raise HTTPException(status_code=400, detail=f"Knowledge base '{name}' already exists")

        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"LLM config error: {e!s}")

        logger.info(f"Creating KB: {name}")

        # Register KB to kb_config.json immediately with "initializing" status
        # This ensures the KB appears in the list right away
        manager.update_kb_status(
            name=name,
            status="initializing",
            progress={
                "stage": "initializing",
                "message": "Initializing knowledge base...",
                "percent": 0,
                "current": 0,
                "total": len(files),
            },
        )
        # Also store rag_provider in config (reload and update)
        manager.config = manager._load_config()
        if name in manager.config.get("knowledge_bases", {}):
            manager.config["knowledge_bases"][name]["rag_provider"] = provider
            manager._save_config()

        progress_tracker = ProgressTracker(name, _kb_base_dir)

        initializer = KnowledgeBaseInitializer(
            kb_name=name,
            base_dir=str(_kb_base_dir),
            api_key=api_key,
            base_url=base_url,
            progress_tracker=progress_tracker,
            rag_provider=provider,
        )

        initializer.create_directory_structure()

        manager = get_kb_manager()
        if name not in manager.list_knowledge_bases():
            logger.warning(f"KB {name} not found in config, registering manually")
            initializer._register_to_config()

        uploaded_files = []
        for file in files:
            sanitized_filename = DocumentValidator.validate_upload_safety(
                file.filename,
                None,
                set(get_provider_supported_extensions(provider)),
            )
            file_path = initializer.raw_dir / sanitized_filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            DocumentValidator.validate_upload_safety(
                sanitized_filename,
                file_path.stat().st_size,
                set(get_provider_supported_extensions(provider)),
            )
            uploaded_files.append(sanitized_filename)

        progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Saved {len(uploaded_files)} files, preparing to process...",
            current=0,
            total=len(uploaded_files),
        )

        background_tasks.add_task(run_initialization_task, initializer)

        logger.success(f"KB '{name}' created, processing {len(uploaded_files)} files in background")

        return {
            "message": f"Knowledge base '{name}' created. Processing {len(uploaded_files)} files in background.",
            "name": name,
            "files": uploaded_files,
            "rag_provider": provider,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create KB: {e}")
        logger.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_name}/progress")
async def get_progress(kb_name: str):
    """Get initialization progress for a knowledge base"""
    try:
        progress_tracker = ProgressTracker(kb_name, _kb_base_dir)
        progress = progress_tracker.get_progress()

        if progress is None:
            return {"status": "not_started", "message": "Initialization not started"}

        return progress
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/progress/clear")
async def clear_progress(kb_name: str):
    """Clear progress file for a knowledge base (useful for stuck states)"""
    try:
        progress_tracker = ProgressTracker(kb_name, _kb_base_dir)
        progress_tracker.clear()
        return {"status": "success", "message": f"Progress cleared for {kb_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/{kb_name}/progress/ws")
async def websocket_progress(websocket: WebSocket, kb_name: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()

    broadcaster = ProgressBroadcaster.get_instance()

    try:
        await broadcaster.connect(kb_name, websocket)

        progress_tracker = ProgressTracker(kb_name, _kb_base_dir)
        initial_progress = progress_tracker.get_progress()

        # Check if KB is already ready (has rag_storage)
        kb_dir = _kb_base_dir / kb_name
        rag_storage_dir = kb_dir / "rag_storage"
        kb_is_ready = rag_storage_dir.exists() and rag_storage_dir.is_dir()

        # Only send non-completed progress if KB is not ready
        # or if progress is recent (within 5 minutes)
        if initial_progress:
            stage = initial_progress.get("stage")
            timestamp = initial_progress.get("timestamp")

            should_send = False
            if stage in ["completed", "error"] or not kb_is_ready:
                should_send = True
            elif timestamp:
                # Check if progress is recent
                try:
                    progress_time = datetime.fromisoformat(timestamp)
                    now = datetime.now()
                    age_seconds = (now - progress_time).total_seconds()
                    if age_seconds < 300:  # 5 minutes
                        should_send = True
                except:
                    pass

            if should_send:
                await websocket.send_json({"type": "progress", "data": initial_progress})

        last_progress = initial_progress
        last_timestamp = initial_progress.get("timestamp") if initial_progress else None

        while True:
            try:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                except asyncio.TimeoutError:
                    current_progress = progress_tracker.get_progress()
                    if current_progress:
                        current_timestamp = current_progress.get("timestamp")
                        if current_timestamp != last_timestamp:
                            await websocket.send_json(
                                {"type": "progress", "data": current_progress}
                            )
                            last_progress = current_progress
                            last_timestamp = current_timestamp

                            if current_progress.get("stage") in ["completed", "error"]:
                                await asyncio.sleep(3)
                                break
                    continue

            except WebSocketDisconnect:
                break
            except Exception:
                break

    except Exception as e:
        logger.debug(f"Progress WS error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        await broadcaster.disconnect(kb_name, websocket)
        try:
            await websocket.close()
        except:
            pass


@router.post("/{kb_name}/link-folder", response_model=LinkedFolderInfo)
async def link_folder(kb_name: str, request: LinkFolderRequest):
    """
    Link a local folder to a knowledge base.

    This allows syncing documents from a local folder (which can be
    synced with SharePoint, Google Drive, OneLake, etc.) to the KB.

    The folder path supports:
    - Absolute paths: /Users/name/Documents or C:\\Users\\name\\Documents
    - Home directory: ~/Documents
    - Relative paths (resolved from server working directory)
    """
    try:
        manager = get_kb_manager()
        folder_info = manager.link_folder(kb_name, request.folder_path)
        logger.info(f"Linked folder '{request.folder_path}' to KB '{kb_name}'")
        return LinkedFolderInfo(**folder_info)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_name}/linked-folders", response_model=list[LinkedFolderInfo])
async def get_linked_folders(kb_name: str):
    """Get list of linked folders for a knowledge base."""
    try:
        manager = get_kb_manager()
        folders = manager.get_linked_folders(kb_name)
        return [LinkedFolderInfo(**f) for f in folders]
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_name}/linked-folders/{folder_id}")
async def unlink_folder(kb_name: str, folder_id: str):
    """Unlink a folder from a knowledge base."""
    try:
        manager = get_kb_manager()
        success = manager.unlink_folder(kb_name, folder_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Folder '{folder_id}' not found")
        logger.info(f"Unlinked folder '{folder_id}' from KB '{kb_name}'")
        return {"message": "Folder unlinked successfully", "folder_id": folder_id}
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/sync-folder/{folder_id}")
async def sync_folder(kb_name: str, folder_id: str, background_tasks: BackgroundTasks):
    """
    Sync files from a linked folder to the knowledge base.

    This scans the linked folder for supported documents and processes
    any new files that haven't been added yet.
    """
    try:
        manager = get_kb_manager()

        # Get linked folders and find the one with matching ID
        folders = manager.get_linked_folders(kb_name)
        folder_info = next((f for f in folders if f["id"] == folder_id), None)

        if not folder_info:
            raise HTTPException(status_code=404, detail=f"Linked folder '{folder_id}' not found")

        folder_path = folder_info["path"]

        # Check for changes (new or modified files)
        changes = manager.detect_folder_changes(kb_name, folder_id)
        files_to_process = changes["new_files"] + changes["modified_files"]

        if not files_to_process:
            return {"message": "No new or modified files to sync", "files": [], "file_count": 0}

        # Get LLM config
        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"LLM config error: {e!s}")

        logger.info(
            f"Syncing {len(files_to_process)} files from folder '{folder_path}' to KB '{kb_name}'"
        )

        # NOTE: We DO NOT update sync state here anymore.
        # It is updated in run_upload_processing_task only after successful processing.
        # This prevents marking files as synced if processing fails (race condition fix).

        # Add background task to process files
        background_tasks.add_task(
            run_upload_processing_task,
            kb_name=kb_name,
            base_dir=str(_kb_base_dir),
            api_key=api_key,
            base_url=base_url,
            uploaded_file_paths=files_to_process,
            folder_id=folder_id,  # Pass folder_id to update state on success
        )

        return {
            "message": f"Syncing {len(files_to_process)} files from linked folder",
            "folder_path": folder_path,
            "new_files": changes["new_count"],
            "modified_files": changes["modified_count"],
            "file_count": len(files_to_process),
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
