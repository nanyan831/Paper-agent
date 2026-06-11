"""
定义供 Agent 调用的工具函数
"""
import logging
from typing import Dict, Any, Callable

from database.db import DatabaseManager
from rag.vector_store import VectorStore
from rag.retriever import HybridRetriever
from crawlers.manager import CrawlerManager
from .schemas import (
    ToolResponse,
    SearchPapersParams,
    SearchChunksParams,
    CrawlPapersParams,
    AddPaperParams,
    GetPaperDetailParams,
    GetRelatedPapersParams
)

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 900


def _snippet(text: str, max_chars: int = SNIPPET_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def _slim_paper_result(paper: dict) -> dict:
    return {
        "paper_id": paper.get("id"),
        "title": paper.get("title"),
        "authors": paper.get("authors"),
        "source": paper.get("source"),
        "publish_date": paper.get("publish_date"),
        "journal": paper.get("journal"),
        "doi": paper.get("doi"),
        "url": paper.get("url"),
        "search_score": paper.get("search_score"),
        "search_type": paper.get("search_type"),
        "abstract_snippet": _snippet(paper.get("abstract", ""), 600),
    }


def _slim_chunk_result(chunk: dict) -> dict:
    return {
        "chunk_id": chunk.get("id"),
        "paper_id": chunk.get("paper_id"),
        "title": chunk.get("title"),
        "authors": chunk.get("authors"),
        "source": chunk.get("source"),
        "publish_date": chunk.get("publish_date"),
        "journal": chunk.get("journal"),
        "doi": chunk.get("doi"),
        "url": chunk.get("url"),
        "section": chunk.get("section"),
        "chunk_index": chunk.get("chunk_index"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "search_score": chunk.get("search_score"),
        "search_type": chunk.get("search_type"),
        "snippet": _snippet(chunk.get("content", "")),
    }

# 全局实例依赖（将在 main.py 初始化时注入）
_db: DatabaseManager = None
_vector_store: VectorStore = None
_retriever: HybridRetriever = None
_crawler_manager: CrawlerManager = None

def init_tools_dependencies(
    db: DatabaseManager,
    vs: VectorStore,
    retriever: HybridRetriever,
    crawler_manager: CrawlerManager
):
    global _db, _vector_store, _retriever, _crawler_manager
    _db = db
    _vector_store = vs
    _retriever = retriever
    _crawler_manager = crawler_manager


async def tool_search_papers(params: SearchPapersParams) -> ToolResponse:
    try:
        top_k = min(params.top_k, 8)
        results = await _retriever.search(
            query=params.query,
            top_k=top_k,
            filters=params.filters,
            search_type=params.search_type
        )
        return ToolResponse(success=True, data=[_slim_paper_result(r) for r in results])
    except Exception as e:
        logger.error(f"tool_search_papers err: {e}")
        return ToolResponse(success=False, message=str(e))


async def tool_search_chunks(params: SearchChunksParams) -> ToolResponse:
    try:
        top_k = min(params.top_k, 8)
        results = await _retriever.search_chunks(
            query=params.query,
            top_k=top_k,
            filters=params.filters,
            search_type=params.search_type
        )
        return ToolResponse(success=True, data=[_slim_chunk_result(r) for r in results])
    except Exception as e:
        logger.error(f"tool_search_chunks err: {e}")
        return ToolResponse(success=False, message=str(e))


async def tool_crawl_papers(params: CrawlPapersParams) -> ToolResponse:
    try:
        result = await _crawler_manager.run_crawl(
            source=params.source,
            query=params.topic,
            max_results=params.max_results
        )
        if result["status"] == "success":
            return ToolResponse(success=True, data=result)
        return ToolResponse(success=False, message=result.get("message"))
    except Exception as e:
        logger.error(f"tool_crawl_papers err: {e}")
        return ToolResponse(success=False, message=str(e))


async def tool_add_paper(params: AddPaperParams) -> ToolResponse:
    try:
        paper_dict = params.model_dump()
        paper_id = await _db.add_paper(paper_dict)
        if not paper_id:
            return ToolResponse(success=False, message="DOI 已存在或插入失败")
        
        # 添加到向量库
        paper_dict["id"] = paper_id
        _vector_store.add_paper(paper_id, paper_dict)
        
        return ToolResponse(success=True, data={"paper_id": paper_id})
    except Exception as e:
        logger.error(f"tool_add_paper err: {e}")
        return ToolResponse(success=False, message=str(e))


async def tool_get_paper_detail(params: GetPaperDetailParams) -> ToolResponse:
    try:
        paper = await _db.get_paper(params.paper_id)
        if not paper:
            return ToolResponse(success=False, message="论文未找到")
        return ToolResponse(success=True, data=paper)
    except Exception as e:
        return ToolResponse(success=False, message=str(e))


async def tool_get_related_papers(params: GetRelatedPapersParams) -> ToolResponse:
    try:
        results = await _retriever.find_related(params.paper_id, params.top_k)
        return ToolResponse(success=True, data=results)
    except Exception as e:
        return ToolResponse(success=False, message=str(e))


async def tool_get_memory_stats(params: Any = None) -> ToolResponse:
    try:
        stats = await _db.get_stats()
        return ToolResponse(success=True, data=stats)
    except Exception as e:
        return ToolResponse(success=False, message=str(e))


# 注册所有工具
agent_tools_registry: Dict[str, Callable] = {
    "search_papers": (tool_search_papers, SearchPapersParams),
    "search_chunks": (tool_search_chunks, SearchChunksParams),
    "crawl_papers": (tool_crawl_papers, CrawlPapersParams),
    "add_paper": (tool_add_paper, AddPaperParams),
    "get_paper_detail": (tool_get_paper_detail, GetPaperDetailParams),
    "get_related_papers": (tool_get_related_papers, GetRelatedPapersParams),
    "get_memory_stats": (tool_get_memory_stats, type(None)),
}


async def invoke_tool(tool_name: str, params_dict: dict) -> ToolResponse:
    """动态调用工具"""
    if tool_name not in agent_tools_registry:
        return ToolResponse(success=False, message=f"未知的工具: {tool_name}")
        
    func, param_model = agent_tools_registry[tool_name]
    
    try:
        if param_model is not type(None):
            params = param_model(**params_dict)
            return await func(params)
        else:
            return await func()
    except Exception as e:
        return ToolResponse(success=False, message=f"参数验证或执行失败: {e}")
