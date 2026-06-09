from fastapi import APIRouter
from pydantic import BaseModel

from agent_tools.tools import invoke_tool

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class AgentInvokeRequest(BaseModel):
    tool: str
    params: dict = {}


@router.post("/invoke")
async def invoke_agent_tool(req: AgentInvokeRequest):
    """Unified endpoint for direct tool invocation."""
    response = await invoke_tool(req.tool, req.params)
    return response.model_dump()


class ChatRequest(BaseModel):
    messages: list


SYSTEM_PROMPT = (
    "你是一个智能学术助手。回答论文内容、方法、结论、证据时，"
    "优先调用 search_chunks 检索本地全文片段；如果本地全文不足，"
    "再调用 search_papers 查论文摘要/元数据，必要时建议用户导入 PDF 或触发爬虫。"
    "回答要简洁、专业，并说明依据来自全文片段还是摘要元数据。"
)


@router.post("/chat")
async def chat_with_deepseek(req: ChatRequest):
    """Chat endpoint that lets the model call local academic tools."""
    from agent.deepseek_client import chat_with_agent

    messages = req.messages
    if not any(msg.get("role") == "system" for msg in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    updated_messages = await chat_with_agent(messages)
    return {"messages": updated_messages}
