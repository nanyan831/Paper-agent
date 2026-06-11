import json
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
    "你是一个智能学术助手。回答论文内容、方法、结论、证据时，必须优先调用 search_chunks "
    "检索本地全文片段；如果本地全文不足，再调用 search_papers 查询论文摘要和元数据。"
    "使用 search_chunks 后，最终回答必须尽量附上可追溯来源，至少包含论文名、页码范围和原文片段。"
    "如果本地论文库没有检索到相关全文证据，要明确说明“本地论文库没有找到可引用依据”，不要编造来源。"
    "回答要简洁、专业，并区分依据来自全文片段还是摘要元数据。"
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
    metadata = _parse_metadata(row.get("metadata"))
    if metadata.get("sources"):
        message["sources"] = metadata["sources"]
    return message


def _parse_metadata(raw_metadata: Optional[str]) -> dict:
    if not raw_metadata:
        return {}
    try:
        return json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}


def _latest_assistant_sources(display_messages: list[dict]) -> list[dict]:
    for message in reversed(display_messages):
        if message.get("role") == "assistant":
            return message.get("sources") or []
    return []


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


def _tool_message_metadata(msg: dict) -> dict:
    metadata = {"tool_call_id": msg.get("tool_call_id")}
    if msg.get("name") != "search_chunks":
        return metadata

    try:
        payload = json.loads(msg.get("content") or "{}")
    except json.JSONDecodeError:
        return metadata

    if payload.get("success") and isinstance(payload.get("data"), list):
        metadata["rag_hits"] = payload["data"][:8]
    return metadata


def _short_snippet(text: str, max_chars: int = 220) -> str:
    snippet = " ".join((text or "").split())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[:max_chars].rstrip() + "..."


def _normalize_source(hit: dict) -> dict:
    return {
        "paper_id": hit.get("paper_id"),
        "title": hit.get("title") or "未知论文",
        "page_start": hit.get("page_start"),
        "page_end": hit.get("page_end"),
        "snippet": _short_snippet(hit.get("snippet") or hit.get("content") or ""),
        "chunk_id": hit.get("chunk_id") or hit.get("id"),
    }


def _format_page_range(hit: dict) -> str:
    start = hit.get("page_start")
    end = hit.get("page_end")
    if start and end and start != end:
        return f"第 {start}-{end} 页"
    if start:
        return f"第 {start} 页"
    if end:
        return f"第 {end} 页"
    return "页码未知"


def _extract_rag_hits(messages: list[dict]) -> tuple[bool, list[dict]]:
    searched_chunks = False
    hits: list[dict] = []
    seen = set()

    for msg in messages:
        if msg.get("role") != "tool" or msg.get("name") != "search_chunks":
            continue
        searched_chunks = True
        try:
            payload = json.loads(msg.get("content") or "{}")
        except json.JSONDecodeError:
            continue

        if not payload.get("success") or not isinstance(payload.get("data"), list):
            continue

        for hit in payload["data"]:
            chunk_id = hit.get("chunk_id") or hit.get("id")
            dedupe_key = chunk_id or (
                hit.get("paper_id"),
                hit.get("page_start"),
                hit.get("page_end"),
                hit.get("snippet"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            hits.append(hit)

    return searched_chunks, hits


def _build_sources_block(sources: list[dict], max_sources: int = 4) -> str:
    lines = ["", "", "本地引用来源："]
    for index, source in enumerate(sources[:max_sources], start=1):
        title = source.get("title") or "未知论文"
        page_range = _format_page_range(source)
        snippet = source.get("snippet") or ""
        if snippet:
            lines.append(f"{index}. 《{title}》，{page_range}：{snippet}")
        else:
            lines.append(f"{index}. 《{title}》，{page_range}")
    return "\n".join(lines)


def _apply_evidence_policy(messages: list[dict]) -> list[dict]:
    searched_chunks, rag_hits = _extract_rag_hits(messages)
    if not searched_chunks:
        return []

    final_answer = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and (msg.get("content") or "").strip():
            final_answer = msg
            break
    if final_answer is None:
        return []

    content = final_answer.get("content") or ""
    sources = [_normalize_source(hit) for hit in rag_hits]
    if rag_hits:
        if "本地引用来源：" not in content:
            final_answer["content"] = content.rstrip() + _build_sources_block(sources)
        final_answer["sources"] = sources[:4]
    elif "本地论文库没有找到可引用依据" not in content:
        final_answer["content"] = (
            "本地论文库没有找到可引用依据，因此我不能给出确定结论。"
            "请先导入相关 PDF，或换一个更贴近本地论文内容的问题。"
        )
        final_answer["sources"] = []
    return sources[:4]


async def _persist_agent_result(session_id: str, result_messages: list[dict], context_len: int) -> None:
    new_messages = result_messages[context_len:]
    _apply_evidence_policy(new_messages)
    for msg in new_messages:
        role = msg.get("role")
        if role == "assistant":
            content = msg.get("content") or ""
            tool_names = _assistant_tool_names(msg)
            metadata = {"tool_calls": msg.get("tool_calls") or []}
            if "sources" in msg:
                metadata["sources"] = msg["sources"]
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
                metadata=_tool_message_metadata(msg),
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
    display_messages = [_message_to_display(row) for row in rows]
    return {
        "session_id": session_id,
        "messages": display_messages,
        "sources": _latest_assistant_sources(display_messages),
    }


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
    display_messages = [_message_to_display(row) for row in rows]
    return {
        "session_id": session_id,
        "messages": display_messages,
        "sources": _latest_assistant_sources(display_messages),
        "usage": usage,
    }
