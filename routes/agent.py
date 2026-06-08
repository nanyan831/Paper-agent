from fastapi import APIRouter, Request
from pydantic import BaseModel

from agent_tools.tools import invoke_tool

router = APIRouter(prefix="/api/agent", tags=["Agent"])

class AgentInvokeRequest(BaseModel):
    tool: str
    params: dict = {}

@router.post("/invoke")
async def invoke_agent_tool(req: AgentInvokeRequest):
    """供外部 Agent 调用的统一接口（旧版）"""
    response = await invoke_tool(req.tool, req.params)
    return response.model_dump()

class ChatRequest(BaseModel):
    messages: list

@router.post("/chat")
async def chat_with_deepseek(req: ChatRequest):
    """
    供前端调用的聊天接口
    接受标准的 messages 数组，返回包含模型回复和工具调用记录的最新 messages 数组
    """
    # 这里延迟导入以避免在应用启动前抛出依赖错误
    from agent.deepseek_client import chat_with_agent
    
    # 强制加上系统提示词
    messages = req.messages
    if not any(msg.get("role") == "system" for msg in messages):
        messages.insert(0, {
            "role": "system",
            "content": "你是一个智能学术助手。你可以帮用户检索本地数据库的文献，或者调用爬虫去抓取外部论文。回答请尽量精炼、专业。"
        })
        
    updated_messages = await chat_with_agent(messages)
    return {"messages": updated_messages}
