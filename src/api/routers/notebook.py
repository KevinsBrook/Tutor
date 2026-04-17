"""
Notebook API Router
Provides notebook creation, querying, updating, deletion, and record management functions
"""

from pathlib import Path
import sys
from typing import Literal,Any

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
        tasks.append("1. 生成学习总结 summary")
    if generate_outline:
        tasks.append("2. 生成知识型大纲 outline")
    if generate_mindmap:
        tasks.append("3. 生成知识型思维导图 mindmap")

    task_text = "\n".join(tasks)

    return f"""
你是一个中文学习笔记整理助手。请根据给定对话内容，输出结构化学习笔记。
你的目标不是做空泛总结，而是把对话中的“知识问题、概念定义、区别比较、示例代码、应用场景”整理成适合学习和复习的笔记。
你必须严格返回 JSON，不要输出任何解释、前言、后记、Markdown 代码块标记。

【对话内容】
{conversation_text}

【任务】
{task_text}

【总体要求】
1. 必须返回合法 JSON
2. 顶层只允许包含以下字段：
   - summary
   - outline
   - mindmap
3. 不需要生成的字段可以省略
4. 所有内容必须使用中文
5. 内容必须具体，不能空泛，不能只写“主题”“问题”“说明”这种模板词
6. 必须严格基于对话真实内容整理，不要编造对话中没有出现的大段内容
7. 如果对话中包含多个问题，必须按知识主题拆开整理，而不是合并成一句笼统总结
8. 如果对话中出现“定义、区别、例子、代码、数据集、步骤、应用场景”，要尽量在结构中体现出来
9. 如果对话中同时包含“用户提问”和“助手寒暄/自我介绍”，必须优先整理“用户提问中涉及的知识主题”，不要把助手自我介绍作为主要内容
10. 如果用户一次提了多个学习问题，必须优先按这些问题拆分知识模块
11. 除非用户主要在询问系统功能，否则不要把“助手功能介绍、服务内容、交互方式”作为主大纲
12. 本次整理的重点应放在用户想学习的知识，而不是对话礼貌性内容

【知识提取优先级】
请优先提取“用户问题中真正要学习的知识点”，优先级高于助手的寒暄、自我介绍和功能说明。

例如：
- 如果用户提问包含概念定义，应优先整理概念定义
- 如果用户提问包含区别比较，应优先整理区别比较
- 如果用户提问包含示例代码，应优先整理示例代码
- 如果用户提问包含多个连续问题，应拆成多个知识模块
- 如果助手回答里有自我介绍，而用户问题是课程知识，则笔记主结构必须围绕课程知识展开

【summary 要求】
- summary 必须是对象
- 必须包含以下字段：
  - 学习主题
  - 核心问题
  - 关键知识点
  - 对比关系
  - 示例与实践
  - 适合复习的结论
- 每个字段都必须是完整中文内容
- “核心问题”要概括用户到底问了哪些知识点
- “关键知识点”要提炼 3 到 6 个核心知识
- “对比关系”要写出对话中涉及的区别、联系、比较
- “示例与实践”要体现数据集、代码、例子、应用等内容
- “适合复习的结论”要写成适合学生复习时直接阅读的总结

【outline 要求】
- outline 必须是数组
- 每个节点格式必须为：
  {{
    "title": "节点标题",
    "children": [子节点...]
  }}
- 大纲必须体现“知识结构”，不能只是把 summary 的字段名重复一遍
- 一级节点应该优先按“真实知识主题”划分，例如：
  - 机器学习的定义
  - 监督学习、无监督学习、强化学习
  - 分类与回归的区别
  - 逻辑回归与线性回归的区别
  - 鸢尾花数据集代码示例
- 大纲至少 3 层
- 一级节点至少 3 个
- 每个一级节点至少 2 个二级节点
- 如果对话内容足够，尽量扩展到三级节点
- title 必须具体，不能只写“主题1”“总结”“说明”
- 如果对话中本来就是连续多个问题，应尽量按“问题 -> 解释 -> 对比/例子”展开

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
- 思维导图必须和 outline 对应，但更适合图形化展示
- 中心主题应该是本次对话的总学习主题，而不是“对话内容总结”
- 一级节点优先使用真实知识主题，例如：
  - 机器学习基础
  - 学习范式分类
  - 分类与回归
  - 逻辑回归 vs 线性回归
  - 鸢尾花数据集示例
- 每个一级节点至少 2 个子节点
- 至少 3 层
- topic 必须具体，不能空泛
- 思维导图节点要尽量短，但要有知识含义，适合展示在节点框里

【特别要求】
- 如果对话里有多个连续提问，必须拆成多个知识模块
- 如果对话里有“区别/对比”，要单独形成比较节点
- 如果对话里有“代码/数据集/例子”，要单独形成示例节点
- 不要把结果写成“用户与助手对话总结”
- 不要把结果主要写成“助手做了什么”，而要写“知识内容是什么”

【示例结构】
{{
  "summary": {{
    "学习主题": "...",
    "核心问题": "...",
    "关键知识点": "...",
    "对比关系": "...",
    "示例与实践": "...",
    "适合复习的结论": "..."
  }},
  "outline": [
    {{
      "title": "一级知识主题",
      "children": [
        {{
          "title": "二级知识点",
          "children": [
            {{
              "title": "三级展开点",
              "children": []
            }}
          ]
        }}
      ]
    }}
  ],
  "mindmap": {{
    "topic": "总学习主题",
    "children": [
      {{
        "topic": "一级知识模块",
        "children": [
          {{
            "topic": "二级知识点",
            "children": []
          }}
        ]
      }}
    ]
  }}
}}
""".strip()
#xinzengjieshu
def build_kb_note_prompt(
    kb_name: str,
    kb_text: str,
    generate_summary: bool,
    generate_outline: bool,
    generate_mindmap: bool,
) -> str:
    tasks = []
    if generate_summary:
        tasks.append("1. 生成知识库学习总结 summary")
    if generate_outline:
        tasks.append("2. 生成知识库知识型大纲 outline")
    if generate_mindmap:
        tasks.append("3. 生成知识库知识型思维导图 mindmap")

    task_text = "\n".join(tasks)

    return f"""
你是一个中文学习笔记整理助手。请根据给定知识库内容，输出结构化学习笔记。
你的目标不是做空泛总结，而是把知识库中的“概念定义、章节主题、区别比较、关键知识点、示例与应用场景”整理成适合学习和复习的笔记。
你必须严格返回 JSON，不要输出任何解释、前言、后记、Markdown 代码块标记。

【知识库名称】
{kb_name}

【知识库内容】
{kb_text}

【任务】
{task_text}

【总体要求】
1. 必须返回合法 JSON
2. 顶层只允许包含以下字段：
   - summary
   - outline
   - mindmap
3. 不需要生成的字段可以省略
4. 所有内容必须使用中文
5. 内容必须具体，不能空泛，不能只写“主题”“问题”“说明”这种模板词
6. 必须严格基于给定知识库内容整理，不要编造知识库中没有出现的大段内容
7. 如果知识库内容覆盖多个主题，必须按知识主题拆开整理，而不是合并成一句笼统总结
8. 要优先提炼知识点、概念关系、章节层级、比较关系、示例与应用

【summary 要求】
- summary 必须是对象
- 必须包含以下字段：
  - 学习主题
  - 核心内容
  - 关键知识点
  - 对比关系
  - 示例与应用
  - 适合复习的结论

【outline 要求】
- outline 必须是数组
- 每个节点格式必须为：
  {{
    "title": "节点标题",
    "children": [子节点...]
  }}
- 大纲必须体现“知识结构”
- 一级节点优先按真实知识主题划分
- 大纲至少 3 层
- 一级节点至少 3 个
- 每个一级节点至少 2 个二级节点
- title 必须具体，不能只写“主题1”“总结”“说明”

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
- 思维导图必须和 outline 对应，但更适合图形化展示
- 中心主题应该是知识库总学习主题，而不是“知识库内容总结”
- 一级节点优先使用真实知识主题
- 每个一级节点至少 2 个子节点
- 至少 3 层
- topic 必须具体，不能空泛

【示例结构】
{{
  "summary": {{
    "学习主题": "...",
    "核心内容": "...",
    "关键知识点": "...",
    "对比关系": "...",
    "示例与应用": "...",
    "适合复习的结论": "..."
  }},
  "outline": [
    {{
      "title": "一级知识主题",
      "children": [
        {{
          "title": "二级知识点",
          "children": [
            {{
              "title": "三级展开点",
              "children": []
            }}
          ]
        }}
      ]
    }}
  ],
  "mindmap": {{
    "topic": "总学习主题",
    "children": [
      {{
        "topic": "一级知识模块",
        "children": [
          {{
            "topic": "二级知识点",
            "children": []
          }}
        ]
      }}
    ]
  }}
}}
""".strip()


def collect_kb_text(kb_name: str, max_chunks: int = 15) -> str:
    """
    Collect representative text from a KB for note generation.
    First version: read from rag_storage/kv_store_text_chunks.json
    """
    project_root = Path(__file__).parent.parent.parent.parent
    kb_dir = project_root / "data" / "knowledge_bases" / kb_name
    rag_storage_dir = kb_dir / "rag_storage"
    text_chunks_file = rag_storage_dir / "kv_store_text_chunks.json"

    if not text_chunks_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"知识库 {kb_name} 还没有可用的文本索引，请先完成知识库处理",
        )

    try:
        with open(text_chunks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取知识库文本块失败：{e}")

    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=400, detail="知识库中没有可用文本块")

    chunks: list[str] = []

    for _, value in data.items():
        if not isinstance(value, dict):
            continue
        content = str(value.get("content", "")).strip()
        if content:
            chunks.append(content)
        if len(chunks) >= max_chunks:
            break

    if not chunks:
        raise HTTPException(status_code=400, detail="知识库中没有可用于整理的文本内容")

    combined = "\n\n".join(chunks)
    if len(combined) > 15000:
        combined = combined[:15000] + "\n\n[知识库内容过长，已截断]"
    return combined
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
class GenerateFromKbRequest(BaseModel):
    """Generate notebook content from a knowledge base"""

    kb_name: str
    generate_summary: bool = False
    generate_outline: bool = False
    generate_mindmap: bool = False
    max_chunks: int = 15

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

        clean_text = result_text.strip()

        if clean_text.startswith("```json"):
            clean_text = clean_text[len("```json"):].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[len("```"):].strip()

        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        try:
            parsed = json.loads(clean_text)
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
@router.post("/generate-from-kb")
async def generate_from_kb(request: GenerateFromKbRequest):
    """
    Generate summary / outline / mindmap from a knowledge base.
    """
    if not (
        request.generate_summary
        or request.generate_outline
        or request.generate_mindmap
    ):
        raise HTTPException(status_code=400, detail="请至少选择一种生成内容")

    try:
        kb_text = collect_kb_text(
            kb_name=request.kb_name,
            max_chunks=request.max_chunks,
        )

        prompt = build_kb_note_prompt(
            kb_name=request.kb_name,
            kb_text=kb_text,
            generate_summary=request.generate_summary,
            generate_outline=request.generate_outline,
            generate_mindmap=request.generate_mindmap,
        )

        llm_client = get_llm_client()

        result_text = await llm_client.complete(
            prompt=prompt,
            system_prompt="你是一个帮助学生整理知识库学习内容的中文学习助手。请严格按照要求输出 JSON。",
        )

        clean_text = result_text.strip()

        if clean_text.startswith("```json"):
            clean_text = clean_text[len("```json"):].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[len("```"):].strip()

        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        try:
            parsed = json.loads(clean_text)
        except Exception:
            parsed = {
                "raw_result": result_text
            }

        return {
            "success": True,
            "kb_name": request.kb_name,
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

