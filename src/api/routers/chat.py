"""
Chat API Router
================

WebSocket endpoint for lightweight chat with session management.
REST endpoints for session operations.
"""

from pathlib import Path
import sys

from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Form,
)

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from src.agents.chat import ChatAgent, SessionManager
from src.logging import get_logger
from src.services.config import load_config_with_main
from src.services.llm.config import get_llm_config
from src.services.settings.interface_settings import get_ui_language

# Initialize logger
project_root = Path(__file__).parent.parent.parent.parent
config = load_config_with_main("solve_config.yaml", project_root)
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = get_logger("ChatAPI", level="INFO", log_dir=log_dir)

router = APIRouter()

# Initialize session manager
session_manager = SessionManager()
async def _read_uploaded_file_text(file: UploadFile) -> str:
    """
    Read uploaded file and extract plain text for direct QA.
    First version: support txt / md / csv / json / pdf.
    """
    filename = (file.filename or "").lower()

    data = await file.read()

    # text-like files
    if filename.endswith((".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css")):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                return ""

    # pdf files
    if filename.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            texts = []
            for page in reader.pages[:20]:  # first version: at most first 20 pages
                page_text = page.extract_text() or ""
                if page_text.strip():
                    texts.append(page_text)
            return "\n\n".join(texts)
        except Exception:
            return ""

    # unsupported files for direct QA
    return ""


def _truncate_context(text: str, max_chars: int = 12000) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[内容过长，已截断]"


# =============================================================================
# REST Endpoints for Session Management
# =============================================================================


@router.get("/chat/sessions")
async def list_sessions(limit: int = 20):
    """
    List recent chat sessions.

    Args:
        limit: Maximum number of sessions to return

    Returns:
        List of session summaries
    """
    return session_manager.list_sessions(limit=limit, include_messages=False)


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """
    Get a specific chat session with full message history.

    Args:
        session_id: Session identifier

    Returns:
        Complete session data including messages
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a chat session.

    Args:
        session_id: Session identifier

    Returns:
        Success message
    """
    if session_manager.delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


# =============================================================================
# WebSocket Endpoint for Chat
# =============================================================================


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for chat with session and context management.

    Message format:
    {
        "message": str,              # User message
        "session_id": str | null,    # Session ID (null for new session)
        "history": [...] | null,     # Optional: explicit history override
        "kb_name": str,              # Knowledge base name (for RAG)
        "enable_rag": bool,          # Enable RAG retrieval
        "enable_web_search": bool    # Enable Web Search
    }

    Response format:
    - {"type": "session", "session_id": str}           # Session ID (new or existing)
    - {"type": "status", "stage": str, "message": str} # Status updates
    - {"type": "stream", "content": str}               # Streaming response chunks
    - {"type": "sources", "rag": list, "web": list}    # Source citations
    - {"type": "result", "content": str}               # Final complete response
    - {"type": "error", "message": str}                # Error message
    """
    await websocket.accept()

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            # Use current UI language (fallback to config/main.yaml system.language)
            language = get_ui_language(default=config.get("system", {}).get("language", "en"))
            message = data.get("message", "").strip()
            session_id = data.get("session_id")
            explicit_history = data.get("history")  # Optional override
            kb_name = data.get("kb_name", "")
            enable_rag = data.get("enable_rag", False)
            enable_web_search = data.get("enable_web_search", False)

            if not message:
                await websocket.send_json({"type": "error", "message": "Message is required"})
                continue

            logger.info(
                f"Chat request: session={session_id}, "
                f"message={message[:50]}..., rag={enable_rag}, web={enable_web_search}"
            )

            try:
                # Get or create session
                if session_id:
                    session = session_manager.get_session(session_id)
                    if not session:
                        # Session not found, create new one
                        session = session_manager.create_session(
                            title=message[:50] + ("..." if len(message) > 50 else ""),
                            settings={
                                "kb_name": kb_name,
                                "enable_rag": enable_rag,
                                "enable_web_search": enable_web_search,
                            },
                        )
                        session_id = session["session_id"]
                else:
                    # Create new session
                    session = session_manager.create_session(
                        title=message[:50] + ("..." if len(message) > 50 else ""),
                        settings={
                            "kb_name": kb_name,
                            "enable_rag": enable_rag,
                            "enable_web_search": enable_web_search,
                        },
                    )
                    session_id = session["session_id"]

                # Send session ID to frontend
                await websocket.send_json(
                    {
                        "type": "session",
                        "session_id": session_id,
                    }
                )

                # Build history from session or explicit override
                if explicit_history is not None:
                    history = explicit_history
                else:
                    # Get history from session messages
                    history = [
                        {"role": msg["role"], "content": msg["content"]}
                        for msg in session.get("messages", [])
                    ]

                # Add user message to session
                session_manager.add_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                )

                # Initialize ChatAgent
                try:
                    llm_config = get_llm_config()
                    api_key = llm_config.api_key
                    base_url = llm_config.base_url
                    api_version = getattr(llm_config, "api_version", None)
                except Exception:
                    api_key = None
                    base_url = None
                    api_version = None

                agent = ChatAgent(
                    language=language,
                    config=config,
                    api_key=api_key,
                    base_url=base_url,
                    api_version=api_version,
                )

                # Send status updates
                if enable_rag and kb_name:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "stage": "rag",
                            "message": f"Searching knowledge base: {kb_name}...",
                        }
                    )

                if enable_web_search:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "stage": "web",
                            "message": "Searching the web...",
                        }
                    )

                await websocket.send_json(
                    {
                        "type": "status",
                        "stage": "generating",
                        "message": "Generating response...",
                    }
                )

                # Process with streaming
                full_response = ""
                sources = {"rag": [], "web": []}

                stream_generator = await agent.process(
                    message=message,
                    history=history,
                    kb_name=kb_name,
                    enable_rag=enable_rag,
                    enable_web_search=enable_web_search,
                    stream=True,
                )

                async for chunk_data in stream_generator:
                    if chunk_data["type"] == "chunk":
                        await websocket.send_json(
                            {
                                "type": "stream",
                                "content": chunk_data["content"],
                            }
                        )
                        full_response += chunk_data["content"]
                    elif chunk_data["type"] == "complete":
                        full_response = chunk_data["response"]
                        sources = chunk_data.get("sources", {"rag": [], "web": []})

                # Send sources if any
                if sources.get("rag") or sources.get("web"):
                    await websocket.send_json({"type": "sources", **sources})

                # Send final result
                await websocket.send_json(
                    {
                        "type": "result",
                        "content": full_response,
                    }
                )

                # Save assistant message to session
                session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    sources=sources if (sources.get("rag") or sources.get("web")) else None,
                )

                logger.info(f"Chat completed: session={session_id}, {len(full_response)} chars")

            except Exception as e:
                logger.error(f"Chat processing error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.debug("Client disconnected from chat")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
@router.post("/chat/with-files")
async def chat_with_files(
    message: str = Form(...),
    files: list[UploadFile] = File(...),
    session_id: str | None = Form(None),
):
    """
    Direct QA based on files uploaded in this request.
    This does NOT depend on KB indexing being finished.
    """
    try:
        message = message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required")

        # current UI language
        language = get_ui_language(default=config.get("system", {}).get("language", "en"))

        # read file contents
        extracted_parts = []
        file_names = []

        for file in files:
            file_names.append(file.filename or "unnamed_file")
            text = await _read_uploaded_file_text(file)
            text = _truncate_context(text, max_chars=8000)

            if text.strip():
                extracted_parts.append(
                    f"【文件名】{file.filename or 'unnamed_file'}\n【文件内容】\n{text}"
                )

        if not extracted_parts:
            raise HTTPException(
                status_code=400,
                detail="当前上传的文件暂时无法提取可用文本内容，请先尝试 txt / md / pdf 文件。",
            )

        combined_context = "\n\n".join(extracted_parts)

        # get or create session
        if session_id:
            session = session_manager.get_session(session_id)
            if not session:
                session = session_manager.create_session(
                    title=message[:50] + ("..." if len(message) > 50 else ""),
                    settings={
                        "mode": "direct_file_qa",
                        "file_names": file_names,
                    },
                )
                session_id = session["session_id"]
        else:
            session = session_manager.create_session(
                title=message[:50] + ("..." if len(message) > 50 else ""),
                settings={
                    "mode": "direct_file_qa",
                    "file_names": file_names,
                },
            )
            session_id = session["session_id"]

        # build history
        history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in session.get("messages", [])
        ]

        # save user message
        session_manager.add_message(
            session_id=session_id,
            role="user",
            content=message,
        )

        # init ChatAgent
        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
            api_version = getattr(llm_config, "api_version", None)
        except Exception:
            api_key = None
            base_url = None
            api_version = None

        agent = ChatAgent(
            language=language,
            config=config,
            api_key=api_key,
            base_url=base_url,
            api_version=api_version,
        )

        # build direct file QA prompt
        direct_context_prompt = (
            "你是一个中文学习助手。请严格依据用户本次上传文件的内容回答问题。\n"
            "要求：\n"
            "1. 优先依据文件内容回答，不要编造。\n"
            "2. 如果文件中找不到答案，要明确说“在本次上传文件中没有找到相关信息”。\n"
            "3. 如果有多个文件，必要时说明答案来自哪个文件。\n"
            "4. 回答尽量清晰、简洁、有条理。\n\n"
            f"【本次上传文件内容】\n{combined_context}\n\n"
            f"【用户问题】\n{message}"
        )

        response = await agent.generate(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个严谨的中文文件问答助手。",
                },
                {
                    "role": "user",
                    "content": direct_context_prompt,
                },
            ]
        )

        # save assistant message
        session_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=response,
            sources={
                "direct_files": [
                    {"name": name} for name in file_names
                ]
            },
        )

        return {
            "success": True,
            "mode": "direct_file_qa",
            "session_id": session_id,
            "answer": response,
            "sources": {
                "direct_files": [{"name": name} for name in file_names]
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Direct file QA error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
