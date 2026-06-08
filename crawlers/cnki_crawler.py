"""
知网爬虫（基础版） —— 仅抓取公开页面的摘要和元数据
注意：知网有严格反爬机制，此爬虫仅作为辅助，建议不要高频访问
"""
import logging
from bs4 import BeautifulSoup

from config import CRAWLER_CONFIG
from crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class CNKICrawler(BaseCrawler):
    """知网学术论文爬虫（基础搜索）"""

    source_name = "cnki"

    def __init__(self):
        super().__init__()
        cfg = CRAWLER_CONFIG.get("cnki", {})
        self.base_url = cfg.get("base_url", "https://kns.cnki.net")
        self.rate_limit_seconds = cfg.get("rate_limit_seconds", 5)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://kns.cnki.net/",
        }

    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """
        知网公开检索接口非常容易触发验证码。
        这里提供一个模拟接口，或者使用搜狗学术代理。
        （实际部署时建议使用专用的知网 API 账号或 Playwright/Selenium）
        这里为了演示，返回提示信息，如果真要爬取可以使用类似 scholar.chinaso.com 或百度学术作为中转。
        """
        logger.warning("知网官方搜索需要复杂过盾，这里使用百度学术/搜狗学术的中转方案(示例逻辑)")
        return await self._search_via_proxy(query, max_results)

    async def _search_via_proxy(self, query: str, max_results: int) -> list[dict]:
        """通过百度学术进行中文文献检索的示例"""
        url = "https://xueshu.baidu.com/s"
        params = {"wd": query, "tn": "SE_baiduxueshu_c1gjeupa", "ie": "utf-8"}

        response = await self._safe_get(url, params=params, headers=self._get_headers())
        if not response:
            return []

        papers = []
        try:
            soup = BeautifulSoup(response.text, 'lxml')
            results = soup.select('.sc_content')

            for res in results[:max_results]:
                title_tag = res.select_one('h3.t a')
                title = title_tag.text.strip() if title_tag else ""
                url = title_tag['href'] if title_tag and 'href' in title_tag.attrs else ""

                authors_tag = res.select('.sc_author a')
                authors = [a.text.strip() for a in authors_tag]

                journal_tag = res.select_one('.sc_time')
                journal_info = journal_tag.text.strip() if journal_tag else ""
                journal = journal_info.split('-')[0].strip() if journal_info else ""

                abstract_tag = res.select_one('.c_abstract')
                abstract = abstract_tag.text.strip() if abstract_tag else ""

                if title:
                    papers.append(self._normalize_paper({
                        "title": title,
                        "authors": ", ".join(authors),
                        "abstract": abstract,
                        "url": f"https://xueshu.baidu.com{url}" if url.startswith('/') else url,
                        "journal": journal,
                        "language": "zh",
                        "source": "cnki_proxy",
                    }))
            return papers
        except Exception as e:
            logger.error(f"中文文献解析失败: {e}")
            return []

    async def fetch_latest(self, max_results: int = 10) -> list[dict]:
        return await self.search("社会科学", max_results=max_results)
