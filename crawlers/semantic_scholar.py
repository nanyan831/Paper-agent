"""
Semantic Scholar 爬虫 —— 通过官方 API 搜索论文
"""
import logging
from typing import Optional

from config import CRAWLER_CONFIG
from crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class SemanticScholarCrawler(BaseCrawler):
    """Semantic Scholar 论文爬虫"""

    source_name = "semantic_scholar"

    def __init__(self):
        super().__init__()
        cfg = CRAWLER_CONFIG.get("semantic_scholar", {})
        self.base_url = cfg.get("base_url", "https://api.semanticscholar.org/graph/v1")
        self.api_key = cfg.get("api_key", "")
        self.max_results = cfg.get("max_results_per_query", 100)
        self.rate_limit_seconds = cfg.get("rate_limit_seconds", 1)

    def _get_headers(self) -> dict:
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """搜索 Semantic Scholar"""
        url = f"{self.base_url}/paper/search"
        params = {
            "query": query,
            "limit": min(max_results, self.max_results),
            "fields": "title,authors,abstract,url,externalIds,year,citationCount,journal,publicationDate",
        }

        response = await self._safe_get(url, params=params, headers=self._get_headers())
        if not response:
            return []

        try:
            data = response.json()
            papers = []
            for item in data.get("data", []):
                paper = self._parse_paper(item)
                if paper:
                    papers.append(self._normalize_paper(paper))
            logger.info(f"Semantic Scholar 搜索 '{query}' 返回 {len(papers)} 篇论文")
            return papers
        except Exception as e:
            logger.error(f"Semantic Scholar 响应解析失败: {e}")
            return []

    async def fetch_latest(self, max_results: int = 20) -> list[dict]:
        """获取推荐/最新论文"""
        # Semantic Scholar 搜索默认按相关度排序
        # 使用文科相关关键词搜索最新论文
        keywords = [
            "social science research",
            "humanities digital",
            "education policy",
        ]
        all_papers = []
        for kw in keywords:
            papers = await self.search(kw, max_results=max_results // len(keywords))
            all_papers.extend(papers)
        return all_papers

    async def get_paper_details(self, paper_id: str) -> Optional[dict]:
        """获取论文详细信息"""
        url = f"{self.base_url}/paper/{paper_id}"
        params = {
            "fields": "title,authors,abstract,url,externalIds,year,citationCount,"
                      "journal,publicationDate,references,citations",
        }

        response = await self._safe_get(url, params=params, headers=self._get_headers())
        if not response:
            return None

        try:
            data = response.json()
            paper = self._parse_paper(data)
            if paper:
                return self._normalize_paper(paper)
        except Exception as e:
            logger.error(f"论文详情获取失败: {e}")
        return None

    def _parse_paper(self, item: dict) -> Optional[dict]:
        """解析 Semantic Scholar 论文数据"""
        try:
            # 作者
            authors = []
            for a in item.get("authors", []):
                name = a.get("name", "")
                if name:
                    authors.append(name)

            # DOI
            ext_ids = item.get("externalIds", {}) or {}
            doi = ext_ids.get("DOI")

            # 日期
            pub_date = item.get("publicationDate") or ""
            if not pub_date and item.get("year"):
                pub_date = f"{item['year']}-01-01"

            # 期刊
            journal = ""
            j = item.get("journal")
            if j:
                journal = j.get("name", "") if isinstance(j, dict) else str(j)

            s2_id = item.get("paperId", "")

            return {
                "id": f"s2_{s2_id}",
                "title": item.get("title", ""),
                "authors": ", ".join(authors),
                "abstract": item.get("abstract", "") or "",
                "keywords": "",
                "url": item.get("url", ""),
                "doi": doi,
                "publish_date": pub_date,
                "journal": journal,
                "language": "en",
                "citation_count": item.get("citationCount", 0) or 0,
            }
        except Exception as e:
            logger.error(f"S2 论文解析失败: {e}")
            return None
