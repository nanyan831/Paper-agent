from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent_tools.tools import invoke_tool
from config import DEEPSEEK_MODEL
from database.db import DatabaseManager

router = APIRouter(prefix="/api/agent", tags=["Agent"])
db_manager = DatabaseManager()

RECENT_CONTEXT_MESSAGES = 10
DISPLAY_MESSAGE_LIMIT = 200
SUMMARY_MESSAGE_THRESHOLD = 16

SYSTEM_PROMPT = (
    "你是一个智能学术助手。回答论文内容、方法、结论、证据时，优先调用 search_chunks "
    "检索本地全文片段；如果本地全文不足，再调用 search_papers 查询论文摘要和元数据，"
    "必要时建议用户导入 PDF 或触发爬虫。回答要简洁、专业，并说明依据来自全文片段还是摘要元数据。"
)


class AgentInvokeRequest(BaseModel):
    tool: str
    params: dict = {}


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = None
    messages: Optional[list[dict[str, Any]]] = None


@router.post("/invoke")
async def invoke_agent_tool(req: AgentInvokeRequest):
    """Unified endpoint for direct tool invocation."""
    response = await invoke_tool(req.tool, req.params)
    return response.model_dump()


def _message_to_display(row: dict) -> dict:
    message = {
        "id": row.get("id"),
        "role": row.get("role"),
        "content": row.get("content") or "",
        "created_at": row.get("created_at"),
    }
    if row.get("tool_name"):
        message["name"] = row["tool_name"]
    return message


def _extract_user_text(req: ChatRequest) -> str:
    if req.message and req.message.strip():
        return req.message.strip()
    for msg in reversed(req.messages or []):
        if msg.get("role") == "user" and (msg.get("content") or "").strip():
            return msg["content"].strip()
    return ""


def _build_context_messages(session: dict, recent_messages: list[dict]) -> list[dict]:
    context = [{"role": "system", "content": SYSTEM_PROMPT}]
    summary = (session.get("summary") or "").strip()
    if summary:
        context.append(
            {
                "role": "system",
                "content": f"以下是更早聊天的压缩摘要，只用于保持连续性：\n{summary}",
            }
        )
    while recent_messages and recent_messages[0].get("role") != "user":
        recent_messages = recent_messages[1:]
    for msg in recent_messages:
        if msg.get("role") in {"user", "assistant"}:
            context.append({"role": msg["role"], "content": msg.get("content") or ""})
    return context


def _build_summary(messages: list[dict]) -> str:
    if len(messages) <= RECENT_CONTEXT_MESSAGES:
        return ""

    older = messages[:-RECENT_CONTEXT_MESSAGES]
    lines = []
    for msg in older:
        role = "用户" if msg.get("role") == "user" else "助手"
        content = " ".join((msg.get("content") or "").split())
        if not content:
            continue
        lines.append(f"{role}: {content[:300]}")

    summary = "\n".join(lines)
    if len(summary) > 3800:
        summary = summary[-3800:]
    return summary


def _assistant_tool_names(message: dict) -> list[str]:
    names = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name"):
            names.append(function["name"])
    return names


async def _persist_agent_result(session_id: str, result_messages: list[dict], context_len: int) -> None:
    new_messages = result_messages[context_len:]
    for msg in new_messages:
        role = msg.get("role")
        if role == "assistant":
            content = msg.get("content") or ""
            tool_names = _assistant_tool_names(msg)
            metadata = {"tool_calls": msg.get("tool_calls") or []}
            if content:
                await db_manager.add_chat_message(session_id, "assistant", content, metadata=metadata)
            elif tool_names:
                await db_manager.add_chat_message(
                    session_id,
                    "tool",
                    f"Agent called: {', '.join(tool_names)}",
                    tool_name=", ".join(tool_names),
                    metadata=metadata,
                )
        elif role == "tool":
            content = msg.get("content") or ""
            await db_manager.add_chat_message(
                session_id,
                "tool",
                content[:2000],
                tool_name=msg.get("name"),
                metadata={"tool_call_id": msg.get("tool_call_id")},
            )


async def _refresh_summary_if_needed(session_id: str) -> None:
    messages = [
        msg
        for msg in await db_manager.list_chat_messages(session_id, limit=1000)
        if msg.get("role") in {"user", "assistant"}
    ]
    if len(messages) < SUMMARY_MESSAGE_THRESHOLD:
        return
    await db_manager.update_chat_summary(session_id, _build_summary(messages))


@router.get("/chat/{session_id}")
async def get_chat_session(session_id: str):
    session = await db_manager.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    rows = await db_manager.list_chat_messages(session_id, limit=DISPLAY_MESSAGE_LIMIT)
    return {"session_id": session_id, "messages": [_message_to_display(row) for row in rows]}


@router.post("/chat")
async def chat_with_deepseek(req: ChatRequest):
    """Persist full chat history while sending a compact context to the model."""
    from agent.deepseek_client import chat_with_agent_result

    user_text = _extract_user_text(req)
    if not user_text:
        raise HTTPException(status_code=400, detail="message is required")

    session = None
    if req.session_id:
        session = await db_manager.get_chat_session(req.session_id)

    if session:
        session_id = req.session_id
    else:
        title = user_text[:40] or "New chat"
        session_id = await db_manager.create_chat_session(title=title)
        session = await db_manager.get_chat_session(session_id)

    await db_manager.add_chat_message(session_id, "user", user_text)

    recent_messages = await db_manager.get_recent_chat_messages(
        session_id,
        limit=RECENT_CONTEXT_MESSAGES,
    )
    compact_context = _build_context_messages(session or {}, recent_messages)
    context_len = len(compact_context)

    result = await chat_with_agent_result(compact_context)
    await _persist_agent_result(session_id, result["messages"], context_len)

    usage = result.get("usage") or {}
    await db_manager.record_model_usage(
        session_id=session_id,
        model=DEEPSEEK_MODEL,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        tool_calls=result.get("tool_calls", 0),
    )
    await _refresh_summary_if_needed(session_id)

    rows = await db_manager.list_chat_messages(session_id, limit=DISPLAY_MESSAGE_LIMIT)
    return {
        "session_id": session_id,
        "messages": [_message_to_display(row) for row in rows],
        "usage": usage,
    }
