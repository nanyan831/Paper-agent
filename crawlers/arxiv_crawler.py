"""
arXiv 爬虫 —— 通过 arXiv API 搜索和抓取论文
"""
import logging
import xml.etree.ElementTree as ET
from typing import Optional

from config import CRAWLER_CONFIG
from crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)

# arXiv API 命名空间
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivCrawler(BaseCrawler):
    """arXiv 论文爬虫"""

    source_name = "arxiv"

    def __init__(self):
        super().__init__()
        cfg = CRAWLER_CONFIG.get("arxiv", {})
        self.base_url = cfg.get("base_url", "http://export.arxiv.org/api/query")
        self.max_results = cfg.get("max_results_per_query", 50)
        self.rate_limit_seconds = cfg.get("rate_limit_seconds", 3)
        self.default_categories = cfg.get("default_categories", [])

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """搜索 arXiv 论文"""
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(max_results, self.max_results),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        response = await self._safe_get(self.base_url, params=params)
        if not response:
            return []

        return self._parse_response(response.text)

    async def fetch_latest(self, max_results: int = 20) -> list[dict]:
        """抓取最新 arXiv 论文（按默认分类）"""
        all_papers = []
        for cat in self.default_categories:
            params = {
                "search_query": f"cat:{cat}",
                "start": 0,
                "max_results": min(max_results, 10),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            response = await self._safe_get(self.base_url, params=params)
            if response:
                papers = self._parse_response(response.text)
                all_papers.extend(papers)
                logger.info(f"arXiv [{cat}] 抓取到 {len(papers)} 篇论文")

        return all_papers

    async def search_by_category(
        self, category: str, query: Optional[str] = None, max_results: int = 20
    ) -> list[dict]:
        """按分类搜索"""
        search_query = f"cat:{category}"
        if query:
            search_query += f" AND all:{query}"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max_results, self.max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        response = await self._safe_get(self.base_url, params=params)
        if not response:
            return []

        return self._parse_response(response.text)

    def _parse_response(self, xml_text: str) -> list[dict]:
        """解析 arXiv Atom XML 响应"""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            entries = root.findall("atom:entry", ARXIV_NS)

            for entry in entries:
                paper = self._parse_entry(entry)
                if paper:
                    papers.append(self._normalize_paper(paper))
        except ET.ParseError as e:
            logger.error(f"arXiv XML 解析失败: {e}")

        return papers

    def _parse_entry(self, entry) -> Optional[dict]:
        """解析单条 arXiv 条目"""
        try:
            # 提取 arXiv ID
            arxiv_id_elem = entry.find("atom:id", ARXIV_NS)
            if arxiv_id_elem is None:
                return None
            arxiv_url = arxiv_id_elem.text.strip()
            arxiv_id = arxiv_url.split("/abs/")[-1]

            # 标题
            title_elem = entry.find("atom:title", ARXIV_NS)
            title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""

            # 摘要
            summary_elem = entry.find("atom:summary", ARXIV_NS)
            abstract = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None else ""

            # 作者
            authors = []
            for author in entry.findall("atom:author", ARXIV_NS):
                name = author.find("atom:name", ARXIV_NS)
                if name is not None:
                    authors.append(name.text.strip())

            # 发表日期
            published_elem = entry.find("atom:published", ARXIV_NS)
            publish_date = ""
            if published_elem is not None:
                publish_date = published_elem.text.strip()[:10]  # YYYY-MM-DD

            # 分类（作为关键词）
            categories = []
            for cat in entry.findall("atom:category", ARXIV_NS):
                term = cat.get("term")
                if term:
                    categories.append(term)

            # PDF 链接
            pdf_url = ""
            for link in entry.findall("atom:link", ARXIV_NS):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")

            # DOI
            doi_elem = entry.find("arxiv:doi", ARXIV_NS)
            doi = doi_elem.text.strip() if doi_elem is not None else None

            return {
                "id": f"arxiv_{arxiv_id.replace('/', '_')}",
                "title": title,
                "authors": ", ".join(authors),
                "abstract": abstract,
                "keywords": ", ".join(categories),
                "url": pdf_url or arxiv_url,
                "doi": doi,
                "publish_date": publish_date,
                "journal": "arXiv",
                "language": "en",
            }
        except Exception as e:
            logger.error(f"arXiv 条目解析失败: {e}")
            return None
