"""
混合检索器 —— 融合语义搜索 + 全文关键词搜索
使用 Reciprocal Rank Fusion (RRF) 进行结果融合排序
"""
import logging
from typing import Optional

from config import SEARCH_CONFIG
from database.db import DatabaseManager
from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索器：语义 + 关键词"""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.db = db or DatabaseManager()
        self.vector_store = vector_store or VectorStore()
        self.semantic_weight = SEARCH_CONFIG["semantic_weight"]
        self.keyword_weight = SEARCH_CONFIG["keyword_weight"]

    async def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[dict] = None,
        search_type: str = "hybrid",
    ) -> list[dict]:
        """
        混合搜索论文

        Args:
            query: 搜索查询
            top_k: 返回条数
            filters: 过滤条件 {"source": "arxiv", "language": "zh"}
            search_type: "hybrid" | "semantic" | "keyword"

        Returns:
            融合排序后的论文列表
        """
        results = []

        if search_type in ("hybrid", "semantic"):
            # 语义搜索
            try:
                chroma_filters = self._build_chroma_filters(filters)
                semantic_results = self.vector_store.search(
                    query=query,
                    top_k=top_k * 2,
                    filters=chroma_filters,
                )
                logger.info(f"语义搜索返回 {len(semantic_results)} 条结果")
            except Exception as e:
                logger.error(f"语义搜索失败: {e}")
                semantic_results = []
        else:
            semantic_results = []

        if search_type in ("hybrid", "keyword"):
            # 关键词搜索 (FTS5)
            try:
                fts_query = self._build_fts_query(query)
                keyword_results = await self.db.fts_search(fts_query, limit=top_k * 2)
                logger.info(f"关键词搜索返回 {len(keyword_results)} 条结果")
            except Exception as e:
                logger.error(f"关键词搜索失败: {e}")
                keyword_results = []
        else:
            keyword_results = []

        if search_type == "hybrid" and semantic_results and keyword_results:
            # RRF 融合排序
            results = self._rrf_fusion(
                semantic_results, keyword_results, top_k
            )
        elif semantic_results:
            results = await self._enrich_semantic_results(semantic_results[:top_k])
        elif keyword_results:
            results = keyword_results[:top_k]
            for r in results:
                r["search_score"] = abs(r.get("fts_score", 0))
                r["search_type"] = "keyword"

        # 应用过滤条件（对关键词搜索结果额外过滤）
        if filters:
            results = self._apply_filters(results, filters)

        # 记录搜索历史
        await self.db.record_search(query, len(results), search_type)

        return results[:top_k]

    async def find_related(self, paper_id: str, top_k: int = 10) -> list[dict]:
        """查找与指定论文相关的论文"""
        paper = await self.db.get_paper(paper_id)
        if not paper:
            return []

        # 用论文的标题+摘要作为查询
        query_text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        results = self.vector_store.search(query=query_text, top_k=top_k + 1)

        # 排除自身
        results = [r for r in results if r["id"] != paper_id]

        return await self._enrich_semantic_results(results[:top_k])

    def _build_fts_query(self, query: str) -> str:
        """构建 FTS5 查询语句"""
        # 移除 FTS 特殊字符
        cleaned = query.replace('"', "").replace("'", "").replace("*", "")
        # 分词并用 OR 连接（宽泛匹配）
        tokens = cleaned.split()
        if len(tokens) <= 1:
            return cleaned
        # 使用 OR 连接所有词，提高召回率
        return " OR ".join(tokens)

    def _build_chroma_filters(self, filters: Optional[dict]) -> Optional[dict]:
        """构建 ChromaDB where 过滤条件"""
        if not filters:
            return None
        where = {}
        if "source" in filters:
            where["source"] = filters["source"]
        if "language" in filters:
            where["language"] = filters["language"]
        return where if where else None

    def _rrf_fusion(
        self,
        semantic_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion 融合排序

        RRF_score(d) = Σ 1 / (k + rank(d))
        """
        scores: dict[str, float] = {}
        paper_data: dict[str, dict] = {}

        # 语义搜索排名得分
        for rank, result in enumerate(semantic_results):
            pid = result["id"]
            rrf = self.semantic_weight / (k + rank + 1)
            scores[pid] = scores.get(pid, 0) + rrf
            if pid not in paper_data:
                paper_data[pid] = result

        # 关键词搜索排名得分
        for rank, result in enumerate(keyword_results):
            pid = result["id"]
            rrf = self.keyword_weight / (k + rank + 1)
            scores[pid] = scores.get(pid, 0) + rrf
            if pid not in paper_data:
                paper_data[pid] = result

        # 按 RRF 分数降序排列
        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

        results = []
        for pid in sorted_ids[:top_k]:
            data = paper_data[pid]
            data["search_score"] = scores[pid]
            data["search_type"] = "hybrid"
            results.append(data)

        return results

    async def _enrich_semantic_results(self, results: list[dict]) -> list[dict]:
        """用数据库中的完整信息丰富语义搜索结果"""
        enriched = []
        for r in results:
            paper = await self.db.get_paper(r["id"])
            if paper:
                paper["search_score"] = r.get("score", 0)
                paper["search_type"] = "semantic"
                enriched.append(paper)
            else:
                r["search_type"] = "semantic"
                r["search_score"] = r.get("score", 0)
                enriched.append(r)
        return enriched

    def _apply_filters(self, results: list[dict], filters: dict) -> list[dict]:
        """应用后过滤"""
        filtered = results
        if "source" in filters:
            filtered = [r for r in filtered if r.get("source") == filters["source"]]
        if "language" in filters:
            filtered = [r for r in filtered if r.get("language") == filters["language"]]
        if "min_citations" in filters:
            min_c = filters["min_citations"]
            filtered = [r for r in filtered if (r.get("citation_count") or 0) >= min_c]
        return filtered
