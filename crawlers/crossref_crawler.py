"""
CrossRef 爬虫 —— 根据关键词或 DOI 查询论文元数据
"""
import logging
from typing import Optional
from datetime import datetime

from config import CRAWLER_CONFIG
from crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class CrossRefCrawler(BaseCrawler):
    """CrossRef 论文爬虫"""

    source_name = "crossref"

    def __init__(self):
        super().__init__()
        cfg = CRAWLER_CONFIG.get("crossref", {})
        self.base_url = cfg.get("base_url", "https://api.crossref.org/works")
        self.mailto = cfg.get("mailto", "user@example.com")
        self.max_results = cfg.get("max_results_per_query", 50)
        self.rate_limit_seconds = cfg.get("rate_limit_seconds", 1)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": f"PaperMemoryAgent/1.0 (mailto:{self.mailto})"
        }

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """搜索 CrossRef"""
        params = {
            "query": query,
            "select": "DOI,title,author,abstract,URL,published-print,published-online,container-title,subject",
            "rows": min(max_results, self.max_results),
            "sort": "relevance",
            "order": "desc",
        }

        response = await self._safe_get(self.base_url, params=params, headers=self._get_headers())
        if not response:
            return []

        try:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            papers = []
            for item in items:
                paper = self._parse_item(item)
                if paper:
                    papers.append(self._normalize_paper(paper))
            return papers
        except Exception as e:
            logger.error(f"CrossRef 解析失败: {e}")
            return []

    async def fetch_latest(self, max_results: int = 20) -> list[dict]:
        """抓取最新的相关论文（按社会科学等类别过滤）"""
        # CrossRef 暂不支持直接搜 "最新"，我们通过指定 filter
        current_year = datetime.now().year
        params = {
            "query.container-title": "sociology,education,philosophy,history",
            "filter": f"from-pub-date:{current_year}-01-01",
            "select": "DOI,title,author,abstract,URL,published-print,published-online,container-title,subject",
            "rows": min(max_results, self.max_results),
            "sort": "published",
            "order": "desc",
        }

        response = await self._safe_get(self.base_url, params=params, headers=self._get_headers())
        if not response:
            return []

        try:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            papers = []
            for item in items:
                paper = self._parse_item(item)
                if paper:
                    papers.append(self._normalize_paper(paper))
            return papers
        except Exception as e:
            logger.error(f"CrossRef 获取最新失败: {e}")
            return []

    async def get_by_doi(self, doi: str) -> Optional[dict]:
        """通过 DOI 精确获取"""
        url = f"{self.base_url}/{doi}"
        response = await self._safe_get(url, headers=self._get_headers())
        if not response:
            return None

        try:
            data = response.json()
            item = data.get("message", {})
            paper = self._parse_item(item)
            if paper:
                return self._normalize_paper(paper)
        except Exception as e:
            logger.error(f"CrossRef DOI 解析失败: {e}")
        return None

    def _parse_item(self, item: dict) -> Optional[dict]:
        try:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""
            if not title:
                return None

            authors = []
            for a in item.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                if family:
                    authors.append(f"{given} {family}".strip())

            journal_list = item.get("container-title", [])
            journal = journal_list[0] if journal_list else ""

            doi = item.get("DOI", "")
            url = item.get("URL", "")

            # 摘要（CrossRef 中的摘要有时是 XML 或带 jats 标签）
            abstract = item.get("abstract", "")
            if abstract:
                import re
                abstract = re.sub(r'<[^>]+>', '', abstract) # 移除标签

            # 日期
            pub_date_parts = item.get("published-print", {}).get("date-parts", [])
            if not pub_date_parts:
                pub_date_parts = item.get("published-online", {}).get("date-parts", [])

            pub_date = ""
            if pub_date_parts and pub_date_parts[0]:
                parts = pub_date_parts[0]
                if len(parts) >= 3:
                    pub_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
                elif len(parts) == 2:
                    pub_date = f"{parts[0]}-{parts[1]:02d}-01"
                elif len(parts) == 1:
                    pub_date = f"{parts[0]}-01-01"

            subjects = item.get("subject", [])

            return {
                "title": title,
                "authors": ", ".join(authors),
                "abstract": abstract,
                "keywords": ", ".join(subjects),
                "url": url,
                "doi": doi,
                "publish_date": pub_date,
                "journal": journal,
                "language": "en",
            }
        except Exception as e:
            logger.error(f"CrossRef 条目解析错误: {e}")
            return None
