"""
爬虫管理器 —— 统一调度各类爬虫，去重，入库
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from database.db import DatabaseManager
from rag.vector_store import VectorStore
from crawlers.arxiv_crawler import ArxivCrawler
from crawlers.semantic_scholar import SemanticScholarCrawler
from crawlers.crossref_crawler import CrossRefCrawler
from crawlers.cnki_crawler import CNKICrawler
from crawlers.rss_crawler import RSSCrawler

logger = logging.getLogger(__name__)


class CrawlerManager:
    def __init__(self, db: DatabaseManager, vector_store: VectorStore):
        self.db = db
        self.vector_store = vector_store
        
        # 初始化所有启用的爬虫
        self.crawlers = {
            "arxiv": ArxivCrawler(),
            "semantic_scholar": SemanticScholarCrawler(),
            "crossref": CrossRefCrawler(),
            "cnki": CNKICrawler(),
            "rss": RSSCrawler(),
        }

    async def get_crawler(self, source: str):
        """获取指定的爬虫"""
        return self.crawlers.get(source)

    async def run_crawl(
        self, 
        source: str, 
        query: Optional[str] = None, 
        max_results: int = 20,
        is_scheduled: bool = False
    ) -> dict:
        """
        执行一次爬取任务，并处理结果入库
        """
        crawler = await self.get_crawler(source)
        if not crawler:
            return {"status": "error", "message": f"未知的爬虫源: {source}"}

        # 记录日志 - 开始
        log_id = await self.db.add_crawl_log({
            "source": source,
            "query": query,
            "status": "running" if not is_scheduled else "scheduled",
        })

        try:
            # 1. 抓取数据
            if query:
                papers = await crawler.search(query, max_results=max_results)
            else:
                papers = await crawler.fetch_latest(max_results=max_results)

            if not papers:
                logger.info(f"爬虫 [{source}] 没有找到新论文")
                await self._update_log(log_id, "completed", 0, 0)
                return {"status": "success", "found": 0, "added": 0}

            # 2. 去重处理
            new_papers = await self._deduplicate(papers)
            
            if not new_papers:
                logger.info(f"爬虫 [{source}] 找到 {len(papers)} 篇论文，但都已存在于库中")
                await self._update_log(log_id, "completed", len(papers), 0)
                return {"status": "success", "found": len(papers), "added": 0}

            # 3. 入库 (关系型数据库 + 向量数据库)
            added_count = 0
            # 批量写入 SQLite
            db_result = await self.db.add_papers_batch(new_papers)
            added_count = db_result.get("added", 0)

            # 写入 ChromaDB (向量化)
            if new_papers:
                # 在后台执行向量化，避免阻塞太久
                asyncio.create_task(self._add_to_vector_store(new_papers))

            # 更新日志
            await self._update_log(log_id, "completed", len(papers), added_count)
            logger.info(f"爬虫 [{source}] 完成: 找到 {len(papers)}, 新增 {added_count}")
            
            return {
                "status": "success", 
                "found": len(papers), 
                "added": added_count,
                "papers": [p["title"] for p in new_papers[:5]] # 返回部分标题供预览
            }

        except Exception as e:
            err_msg = str(e)
            logger.error(f"爬虫 [{source}] 运行失败: {err_msg}")
            await self._update_log(log_id, "failed", 0, 0, err_msg)
            return {"status": "error", "message": err_msg}

    async def run_all_latest(self) -> dict:
        """运行所有启用的爬虫，抓取最新论文"""
        results = {}
        for source, crawler in self.crawlers.items():
            if crawler:
                res = await self.run_crawl(source, max_results=20, is_scheduled=True)
                results[source] = res
        return results

    async def _deduplicate(self, papers: list[dict]) -> list[dict]:
        """论文去重（基于 DOI 和标题精确匹配）"""
        # 获取库中所有的 DOI
        existing_dois = await self.db.get_all_dois()
        
        new_papers = []
        seen_titles = set()
        
        for p in papers:
            # 1. 批次内标题去重
            title_lower = p.get("title", "").lower().strip()
            if not title_lower or title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
                
            # 2. DOI 去重
            doi = p.get("doi")
            if doi and doi in existing_dois:
                continue
                
            # 3. 标题精确查库去重 (避免没有DOI的文章重复)
            # FTS 查询做精确匹配不够准，这里直接用简单判断或者假设没有DOI的文章只要标题不同就是新的
            # 实际生产中可以计算标题的 Levenshtein 距离
            
            new_papers.append(p)
            
        return new_papers

    async def _add_to_vector_store(self, papers: list[dict]):
        """异步加入向量库"""
        try:
            self.vector_store.add_papers_batch(papers)
            logger.info(f"成功将 {len(papers)} 篇论文加入向量库")
        except Exception as e:
            logger.error(f"加入向量库失败: {e}")

    async def _update_log(self, log_id: int, status: str, found: int, added: int, err: str = None):
        """更新爬取日志"""
        # 复用 DatabaseManager 的连接更新
        async with self.db._get_conn() as conn:
            await conn.execute(
                """UPDATE crawl_logs 
                   SET status = ?, papers_found = ?, papers_added = ?, 
                       error_message = ?, completed_at = ?
                   WHERE id = ?""",
                (status, found, added, err, datetime.utcnow().isoformat(), log_id)
            )
            await conn.commit()

    async def close_all(self):
        """关闭所有爬虫客户端"""
        for crawler in self.crawlers.values():
            await crawler.close()
