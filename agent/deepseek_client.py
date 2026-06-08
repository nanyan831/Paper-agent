import json
import logging
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from agent_tools.tools import invoke_tool

logger = logging.getLogger(__name__)

# DeepSeek 兼容 OpenAI 格式
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# 将本地 Agent 工具转换为 OpenAI Function Calling Schema
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "自然语言或关键词搜索记忆库中的论文文献",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                    "top_k": {"type": "integer", "description": "返回条数，默认20"},
                    "search_type": {"type": "string", "enum": ["hybrid", "semantic", "keyword"], "description": "检索方式，推荐使用hybrid"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_papers",
            "description": "触发后台爬虫去指定平台抓取最新论文",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["arxiv", "semantic_scholar", "crossref", "cnki", "rss"], "description": "数据源"},
                    "topic": {"type": "string", "description": "搜索的主题或关键词"},
                    "max_results": {"type": "integer", "description": "最大抓取数，默认20"}
                },
                "required": ["source"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_stats",
            "description": "获取当前论文记忆库的总体统计信息（文献数、收藏数、爬虫执行次数等）",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

async def chat_with_agent(messages: list) -> list:
    """
    处理多轮对话并执行必要的工具调用
    返回更新后的 messages 列表（包含助手的回复及中间的 tool_calls）
    """
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your_api_key_here":
        messages.append({"role": "assistant", "content": "系统提示：请先在 .env 文件中配置真实的 DEEPSEEK_API_KEY，然后重启服务。"})
        return messages

    max_loops = 5
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1
        try:
            response = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            # 记录模型的回复或函数调用请求
            msg_dict = message.model_dump(exclude_none=True)
            messages.append(msg_dict)
            
            # 如果模型没有调用工具，说明对话结束
            if not message.tool_calls:
                break
                
            # 执行所有工具调用
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                logger.info(f"Agent 调用工具: {func_name}, 参数: {args}")
                
                # 调用本地工具函数
                tool_res = await invoke_tool(func_name, args)
                
                # 将工具执行结果添加进上下文
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": json.dumps(tool_res.model_dump(), ensure_ascii=False)
                })
                
        except Exception as e:
            logger.error(f"DeepSeek API 请求失败: {e}")
            messages.append({"role": "assistant", "content": f"遇到错误: {str(e)}"})
            break

    return messages
