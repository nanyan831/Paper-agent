"""
爬虫基类 —— 定义统一接口
"""
import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """所有爬虫的抽象基类"""

    # 子类必须设置
    source_name: str = "unknown"
    rate_limit_seconds: float = 1.0

    def __init__(self):
        self._last_request_time = 0
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "PaperMemoryAgent/1.0 (Academic Research Tool; mailto:user@example.com)"
                },
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limit(self):
        """速率限制"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            await asyncio.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _safe_get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """带速率限制和错误处理的 GET 请求"""
        await self._rate_limit()
        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"[{self.source_name}] HTTP {e.response.status_code}: {url}")
            return None
        except httpx.RequestError as e:
            logger.error(f"[{self.source_name}] 请求失败: {url} - {e}")
            return None

    @abstractmethod
    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """
        搜索论文

        Args:
            query: 搜索关键词
            max_results: 最大返回数量

        Returns:
            标准化的论文列表
        """
        ...

    @abstractmethod
    async def fetch_latest(self, max_results: int = 20) -> list[dict]:
        """
        抓取最新论文

        Returns:
            标准化的论文列表
        """
        ...

    def _normalize_paper(self, raw: dict) -> dict:
        """标准化论文数据格式"""
        return {
            "id": raw.get("id") or str(uuid.uuid4()),
            "title": (raw.get("title") or "").strip(),
            "authors": (raw.get("authors") or "").strip(),
            "abstract": (raw.get("abstract") or "").strip(),
            "keywords": (raw.get("keywords") or "").strip(),
            "url": (raw.get("url") or "").strip(),
            "doi": (raw.get("doi") or "").strip() or None,
            "source": self.source_name,
            "publish_date": raw.get("publish_date"),
            "journal": (raw.get("journal") or "").strip(),
            "full_text": (raw.get("full_text") or "").strip(),
            "language": raw.get("language", "en"),
            "citation_count": raw.get("citation_count", 0),
        }

    def __repr__(self):
        return f"<{self.__class__.__name__} source={self.source_name}>"
