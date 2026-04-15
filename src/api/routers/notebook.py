"""
Notebook API Router
Provides notebook creation, querying, updating, deletion, and record management functions
"""

from pathlib import Path
import sys
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
from src.services.llm import get_llm_client

# Ensure module can be imported
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.api.utils.notebook_manager import notebook_manager

router = APIRouter()
#xinzeng
def format_session_messages(messages: list[dict]) -> str:
    """Format session messages into readable conversation text."""
    lines = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if not content:
            continue

        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"助手：{content}")
        else:
            lines.append(f"{role}：{content}")

    return "\n\n".join(lines)
def build_note_prompt(
    conversation_text: str,
    generate_summary: bool,
    generate_outline: bool,
    generate_mindmap: bool,
) -> str:
    tasks = []
    if generate_summary:
        tasks.append("1. 生成详细总结 summary")
    if generate_outline:
        tasks.append("2. 生成详细大纲 outline")
    if generate_mindmap:
        tasks.append("3. 生成详细思维导图 mindmap")

    task_text = "\n".join(tasks)

    return f"""
你是一个中文学习笔记整理助手。请根据给定对话内容，输出结构化学习笔记。
你必须严格返回 JSON，不要输出任何解释、前言、后记、Markdown 代码块标记。

【对话内容】
{conversation_text}

【任务】
{task_text}

【输出要求】
1. 必须返回合法 JSON
2. 顶层只允许包含以下字段：
   - summary
   - outline
   - mindmap
3. 不需要生成的字段可以省略
4. 所有内容必须使用中文
5. 内容必须具体，不能只写笼统标题
6. 必须结合对话中的真实信息，不要凭空扩展无关内容

【summary 要求】
- summary 必须是一个对象
- 至少包含以下字段：
  - 主题
  - 核心问题
  - 关键结论
  - 重要知识点
  - 简要说明
- 每个字段都必须有具体内容，不能只写几个字

【outline 要求】
- outline 必须是数组
- 每个节点格式必须为：
  {{
    "title": "节点标题",
    "children": [子节点...]
  }}
- 大纲至少 3 层
- 一级节点至少 2 个
- 每个一级节点至少 2 个二级节点
- 如果内容允许，尽量扩展到三级节点
- title 必须具体，如“逻辑回归与线性回归的区别”，不要只写“区别”

【mindmap 要求】
- mindmap 必须是对象
- 格式必须为：
  {{
    "topic": "中心主题",
    "children": [
      {{
        "topic": "子主题",
        "children": [...]
      }}
    ]
  }}
- 思维导图至少 3 层
- 根节点至少 2 个子节点
- 每个一级子节点至少 2 个二级子节点
- topic 必须具体，不要空泛

【示例结构】
{{
  "summary": {{
    "主题": "...",
    "核心问题": "...",
    "关键结论": "...",
    "重要知识点": "...",
    "简要说明": "..."
  }},
  "outline": [
    {{
      "title": "一级主题",
      "children": [
        {{
          "title": "二级主题",
          "children": [
            {{
              "title": "三级主题",
              "children": []
            }}
          ]
        }}
      ]
    }}
  ],
  "mindmap": {{
    "topic": "中心主题",
    "children": [
      {{
        "topic": "一级节点",
        "children": [
          {{
            "topic": "二级节点",
            "children": []
          }}
        ]
      }}
    ]
  }}
}}
""".strip()
#xinzengjieshu
# === Request/Response Models ===


class CreateNotebookRequest(BaseModel):
    """Create notebook request"""

    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "book"


class UpdateNotebookRequest(BaseModel):
    """Update notebook request"""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddRecordRequest(BaseModel):
    """Add record request"""

    notebook_ids: list[str]
    record_type: Literal["solve", "question", "research", "co_writer", "chat"]
    title: str
    user_query: str
    output: str
    metadata: dict = {}
    kb_name: str | None = None


class RemoveRecordRequest(BaseModel):
    """Remove record request"""

    record_id: str
#xinzeng
class GenerateFromChatRequest(BaseModel):
    """Generate notebook content from chat session"""

    session_id: str
    generate_summary: bool = False
    generate_outline: bool = False
    generate_mindmap: bool = False
#xinzengjieshu


# === API Endpoints ===


@router.get("/list")
async def list_notebooks():
    """
    Get all notebook list

    Returns:
        Notebook list (includes summary information)
    """
    try:
        notebooks = notebook_manager.list_notebooks()
        return {"notebooks": notebooks, "total": len(notebooks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_statistics():
    """
    Get notebook statistics

    Returns:
        Statistics information
    """
    try:
        stats = notebook_manager.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_notebook(request: CreateNotebookRequest):
    """
    Create new notebook

    Args:
        request: Create request

    Returns:
        Created notebook information
    """
    try:
        notebook = notebook_manager.create_notebook(
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
        )
        return {"success": True, "notebook": notebook}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy", "service": "notebook"}

@router.get("/{notebook_id}")
async def get_notebook(notebook_id: str):
    """
    Get notebook details

    Args:
        notebook_id: Notebook ID

    Returns:
        Notebook details (includes all records)
    """
    try:
        notebook = notebook_manager.get_notebook(notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return notebook
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{notebook_id}")
async def update_notebook(notebook_id: str, request: UpdateNotebookRequest):
    """
    Update notebook information

    Args:
        notebook_id: Notebook ID
        request: Update request

    Returns:
        Updated notebook information
    """
    try:
        notebook = notebook_manager.update_notebook(
            notebook_id=notebook_id,
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
        )
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "notebook": notebook}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notebook_id}")
async def delete_notebook(notebook_id: str):
    """
    Delete notebook

    Args:
        notebook_id: Notebook ID

    Returns:
        Deletion result
    """
    try:
        success = notebook_manager.delete_notebook(notebook_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "message": "Notebook deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add_record")
async def add_record(request: AddRecordRequest):
    """
    Add record to notebook

    Args:
        request: Add record request

    Returns:
        Addition result
    """
    try:
        result = notebook_manager.add_record(
            notebook_ids=request.notebook_ids,
            record_type=request.record_type,
            title=request.title,
            user_query=request.user_query,
            output=request.output,
            metadata=request.metadata,
            kb_name=request.kb_name,
        )
        return {
            "success": True,
            "record": result["record"],
            "added_to_notebooks": result["added_to_notebooks"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notebook_id}/records/{record_id}")
async def remove_record(notebook_id: str, record_id: str):
    """
    Remove record from notebook

    Args:
        notebook_id: Notebook ID
        record_id: Record ID

    Returns:
        Deletion result
    """
    try:
        success = notebook_manager.remove_record(notebook_id, record_id)
        if not success:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"success": True, "message": "Record removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-from-chat")
async def generate_from_chat(request: GenerateFromChatRequest):
    """
    Generate summary / outline / mindmap from a chat session.
    """
    if not (
        request.generate_summary
        or request.generate_outline
        or request.generate_mindmap
    ):
        raise HTTPException(status_code=400, detail="请至少选择一种生成内容")

    try:
        from src.agents.chat.session_manager import SessionManager

        session_manager = SessionManager()
        session_data = session_manager.get_session(request.session_id)

        if not session_data:
            raise HTTPException(status_code=404, detail="找不到对应会话")

        messages = session_data.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="当前会话没有可整理内容")

        conversation_text = format_session_messages(messages)

        prompt = build_note_prompt(
            conversation_text=conversation_text,
            generate_summary=request.generate_summary,
            generate_outline=request.generate_outline,
            generate_mindmap=request.generate_mindmap,
        )

        llm_client = get_llm_client()

        result_text = await llm_client.complete(
            prompt=prompt,
            system_prompt="你是一个帮助学生整理学习内容的中文学习助手。请严格按照要求输出 JSON。",
        )

        try:
            parsed = json.loads(result_text)
        except Exception:
            parsed = {
                "raw_result": result_text
            }

        return {
            "success": True,
            "session_id": request.session_id,
            "generated": {
                "summary": request.generate_summary,
                "outline": request.generate_outline,
                "mindmap": request.generate_mindmap,
            },
            "result": parsed,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

