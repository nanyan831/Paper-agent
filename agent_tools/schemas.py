"""
Agent 工具的请求/响应模型定义
"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """标准的工具响应格式"""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None


class SearchPapersParams(BaseModel):
    query: str = Field(..., description="搜索关键词或自然语言查询")
    top_k: int = Field(5, description="返回的最大结果数")
    filters: Optional[Dict[str, str]] = Field(None, description="过滤条件，如 {'source': 'arxiv'}")
    search_type: str = Field("hybrid", description="搜索类型: hybrid, semantic, keyword")


class SearchChunksParams(BaseModel):
    query: str = Field(..., description="用于检索全文片段的自然语言问题或关键词")
    top_k: int = Field(5, description="返回的最大片段数")
    filters: Optional[Dict[str, str]] = Field(None, description="过滤条件，如 {'paper_id': '...'}")
    search_type: str = Field("hybrid", description="检索类型: hybrid, semantic, keyword")


class CrawlPapersParams(BaseModel):
    topic: Optional[str] = Field(None, description="要爬取的主题/关键词")
    source: str = Field("arxiv", description="爬虫数据源: arxiv, semantic_scholar, crossref, cnki, rss")
    max_results: int = Field(20, description="最多爬取数量")


class AddPaperParams(BaseModel):
    title: str = Field(..., description="论文标题")
    authors: str = Field(..., description="作者列表")
    abstract: Optional[str] = Field(None, description="摘要")
    keywords: Optional[str] = Field(None, description="关键词，逗号分隔")
    url: Optional[str] = Field(None, description="论文链接")
    doi: Optional[str] = Field(None, description="DOI")
    publish_date: Optional[str] = Field(None, description="发布日期 (YYYY-MM-DD)")


class GetPaperDetailParams(BaseModel):
    paper_id: str = Field(..., description="论文的内部 ID")


class GetRelatedPapersParams(BaseModel):
    paper_id: str = Field(..., description="论文的内部 ID")
    top_k: int = Field(5, description="返回的相关论文数量")
