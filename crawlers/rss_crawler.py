"""
RSS 爬虫 —— 定期检查学术期刊的 RSS Feed
"""
import logging
from typing import Optional
from datetime import datetime

import feedparser
from dateutil import parser as date_parser

from config import CRAWLER_CONFIG
from crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class RSSCrawler(BaseCrawler):
    """期刊 RSS 订阅爬虫"""

    source_name = "rss"

    def __init__(self):
        super().__init__()
        cfg = CRAWLER_CONFIG.get("rss", {})
        self.default_feeds = cfg.get("feeds", [])
        self.rate_limit_seconds = 2

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """RSS 不支持直接搜索，此方法返回空或过滤后的最新论文"""
        latest = await self.fetch_latest(max_results=max_results * 5)
        if not query:
            return latest[:max_results]
            
        # 本地简单关键词过滤
        query_lower = query.lower()
        filtered = []
        for p in latest:
            if query_lower in p["title"].lower() or query_lower in p["abstract"].lower():
                filtered.append(p)
                if len(filtered) >= max_results:
                    break
        return filtered

    async def fetch_latest(self, max_results: int = 50) -> list[dict]:
        """抓取所有配置 RSS 源的最新文章"""
        all_papers = []
        for feed_url in self.default_feeds:
            papers = await self.fetch_feed(feed_url, max_results=max_results // len(self.default_feeds) + 1)
            all_papers.extend(papers)
            
        return sorted(all_papers, key=lambda x: x.get("publish_date", ""), reverse=True)[:max_results]

    async def fetch_feed(self, feed_url: str, max_results: int = 10) -> list[dict]:
        """抓取指定的 RSS 源"""
        try:
            response = await self._safe_get(feed_url)
            if not response:
                return []
                
            feed = feedparser.parse(response.content)
            papers = []
            
            journal_name = feed.feed.get("title", "Unknown Journal")
            
            for entry in feed.entries[:max_results]:
                paper = self._parse_entry(entry, journal_name)
                if paper:
                    papers.append(self._normalize_paper(paper))
                    
            logger.info(f"RSS: 从 {feed_url} 解析到 {len(papers)} 篇文章")
            return papers
            
        except Exception as e:
            logger.error(f"RSS 抓取失败 ({feed_url}): {e}")
            return []

    def _parse_entry(self, entry, journal_name: str) -> Optional[dict]:
        try:
            title = entry.get("title", "")
            if not title:
                return None

            link = entry.get("link", "")
            abstract = entry.get("summary", "") or entry.get("description", "")
            
            # 清理 HTML 标签
            if abstract:
                from bs4 import BeautifulSoup
                abstract = BeautifulSoup(abstract, "lxml").get_text(separator=" ").strip()

            authors = ""
            if "author" in entry:
                authors = entry.author
            elif "authors" in entry:
                authors = ", ".join([a.get("name", "") for a in entry.authors if "name" in a])

            publish_date = ""
            if "published" in entry:
                try:
                    dt = date_parser.parse(entry.published)
                    publish_date = dt.strftime("%Y-%m-%d")
                except:
                    pass

            return {
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "url": link,
                "publish_date": publish_date,
                "journal": journal_name,
                "language": "en" if "".isascii() else "zh", # 简单判断
            }
        except Exception as e:
            logger.error(f"RSS 条目解析失败: {e}")
            return None
