import json
import logging

from openai import AsyncOpenAI

from agent_tools.tools import invoke_tool
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Search paper metadata and abstracts in the local memory database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords or natural-language question."},
                    "top_k": {"type": "integer", "description": "Number of results to return. Default 10."},
                    "search_type": {
                        "type": "string",
                        "enum": ["hybrid", "semantic", "keyword"],
                        "description": "Search mode. Prefer hybrid.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_chunks",
            "description": (
                "Search local full-text paper chunks. Use this first for questions about "
                "paper methods, evidence, conclusions, details, or citations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question or full-text evidence topic."},
                    "top_k": {"type": "integer", "description": "Number of chunks to return. Usually <= 8."},
                    "search_type": {
                        "type": "string",
                        "enum": ["hybrid", "semantic", "keyword"],
                        "description": "Search mode. Prefer hybrid.",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters, for example {'paper_id': '...'}",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_papers",
            "description": "Trigger a background crawler to fetch papers from a given source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["arxiv", "semantic_scholar", "crossref", "cnki", "rss"],
                        "description": "Paper source.",
                    },
                    "topic": {"type": "string", "description": "Topic or keywords to crawl."},
                    "max_results": {"type": "integer", "description": "Maximum number of results. Default 50."},
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_stats",
            "description": "Get local paper memory statistics.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _add_usage(totals: dict, usage) -> None:
    if not usage:
        return
    totals["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    totals["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0
    totals["total_tokens"] += getattr(usage, "total_tokens", 0) or 0


async def chat_with_agent_result(messages: list) -> dict:
    """Run an agent chat turn and return messages plus usage totals."""
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    tool_call_count = 0

    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your_api_key_here":
        messages.append(
            {
                "role": "assistant",
                "content": "系统提示：请先在 .env 文件中配置真实的 DEEPSEEK_API_KEY，然后重启服务。",
            }
        )
        return {"messages": messages, "usage": usage_totals, "tool_calls": tool_call_count}

    max_loops = 5
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1
        try:
            response = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )
            _add_usage(usage_totals, getattr(response, "usage", None))

            message = response.choices[0].message
            msg_dict = message.model_dump(exclude_none=True)
            messages.append(msg_dict)

            if not message.tool_calls:
                break

            tool_call_count += len(message.tool_calls)
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                logger.info("Agent calling tool %s with args %s", func_name, args)
                tool_res = await invoke_tool(func_name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": json.dumps(tool_res.model_dump(), ensure_ascii=False),
                    }
                )

        except Exception as exc:
            logger.error("DeepSeek API request failed: %s", exc)
            messages.append({"role": "assistant", "content": f"遇到错误: {exc}"})
            break

    return {"messages": messages, "usage": usage_totals, "tool_calls": tool_call_count}


async def chat_with_agent(messages: list) -> list:
    result = await chat_with_agent_result(messages)
    return result["messages"]
