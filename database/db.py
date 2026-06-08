"""
数据库操作管理器 —— 封装所有 CRUD 操作
"""
import uuid
import aiosqlite
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from config import DB_PATH


class DatabaseManager:
    """异步数据库管理器"""

    def __init__(self):
        self.db_path = str(DB_PATH)

    @asynccontextmanager
    async def _get_conn(self):
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON;")
            yield conn

    # ==================== 论文 CRUD ====================

    async def add_paper(self, paper: dict) -> Optional[str]:
        """添加论文，返回 paper_id；如果 DOI 重复则跳过"""
        paper_id = paper.get("id") or str(uuid.uuid4())
        async with self._get_conn() as db:
            try:
                await db.execute(
                    """INSERT INTO papers 
                       (id, title, authors, abstract, keywords, url, doi, source,
                        publish_date, journal, full_text, language, citation_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        paper_id,
                        paper.get("title", ""),
                        paper.get("authors", ""),
                        paper.get("abstract", ""),
                        paper.get("keywords", ""),
                        paper.get("url", ""),
                        paper.get("doi"),
                        paper.get("source", "manual"),
                        paper.get("publish_date"),
                        paper.get("journal", ""),
                        paper.get("full_text", ""),
                        paper.get("language", "zh"),
                        paper.get("citation_count", 0),
                    ),
                )
                await db.commit()
                return paper_id
            except aiosqlite.IntegrityError:
                # DOI 重复，跳过
                return None

    async def add_papers_batch(self, papers: list[dict]) -> dict:
        """批量添加论文"""
        added = 0
        skipped = 0
        for paper in papers:
            result = await self.add_paper(paper)
            if result:
                added += 1
            else:
                skipped += 1
        return {"added": added, "skipped": skipped}

    async def get_paper(self, paper_id: str) -> Optional[dict]:
        """根据 ID 获取论文详情"""
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE id = ?", (paper_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def get_paper_by_doi(self, doi: str) -> Optional[dict]:
        """根据 DOI 获取论文"""
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT * FROM papers WHERE doi = ?", (doi,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def list_papers(
        self,
        offset: int = 0,
        limit: int = 20,
        source: Optional[str] = None,
        language: Optional[str] = None,
        favorited_only: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "DESC",
    ) -> dict:
        """分页列出论文"""
        conditions = []
        params = []

        if source:
            conditions.append("source = ?")
            params.append(source)
        if language:
            conditions.append("language = ?")
            params.append(language)
        if favorited_only:
            conditions.append("is_favorited = 1")

        where = " AND ".join(conditions) if conditions else "1=1"
        allowed_sort = {"created_at", "publish_date", "citation_count", "title"}
        sort_col = sort_by if sort_by in allowed_sort else "created_at"
        order = "ASC" if sort_order.upper() == "ASC" else "DESC"

        async with self._get_conn() as db:
            # 总数
            cursor = await db.execute(
                f"SELECT COUNT(*) as cnt FROM papers WHERE {where}", params
            )
            total = (await cursor.fetchone())["cnt"]

            # 分页数据
            cursor = await db.execute(
                f"""SELECT id, title, authors, abstract, keywords, url, doi, source,
                           publish_date, journal, language, citation_count,
                           is_favorited, created_at
                    FROM papers WHERE {where}
                    ORDER BY {sort_col} {order}
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            rows = await cursor.fetchall()
            return {
                "total": total,
                "papers": [dict(r) for r in rows],
                "offset": offset,
                "limit": limit,
            }

    async def update_paper(self, paper_id: str, updates: dict) -> bool:
        """更新论文字段"""
        if not updates:
            return False
        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [paper_id]

        async with self._get_conn() as db:
            cursor = await db.execute(
                f"UPDATE papers SET {set_clause} WHERE id = ?", values
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_paper(self, paper_id: str) -> bool:
        """删除论文"""
        async with self._get_conn() as db:
            cursor = await db.execute(
                "DELETE FROM papers WHERE id = ?", (paper_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def toggle_favorite(self, paper_id: str) -> Optional[bool]:
        """切换收藏状态"""
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT is_favorited FROM papers WHERE id = ?", (paper_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            new_val = 0 if row["is_favorited"] else 1
            await db.execute(
                "UPDATE papers SET is_favorited = ? WHERE id = ?",
                (new_val, paper_id),
            )
            await db.commit()
            return bool(new_val)

    # ==================== 全文搜索 ====================

    async def fts_search(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 全文搜索"""
        async with self._get_conn() as db:
            # 使用 BM25 排序
            cursor = await db.execute(
                """SELECT p.id, p.title, p.authors, p.abstract, p.keywords,
                          p.url, p.doi, p.source, p.publish_date, p.journal,
                          p.language, p.citation_count, p.is_favorited,
                          rank AS fts_score
                   FROM papers_fts fts
                   JOIN papers p ON p.rowid = fts.rowid
                   WHERE papers_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ==================== 标签 ====================

    async def add_tag(self, paper_id: str, tag: str) -> bool:
        async with self._get_conn() as db:
            try:
                await db.execute(
                    "INSERT INTO paper_tags (paper_id, tag) VALUES (?, ?)",
                    (paper_id, tag),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_tag(self, paper_id: str, tag: str) -> bool:
        async with self._get_conn() as db:
            cursor = await db.execute(
                "DELETE FROM paper_tags WHERE paper_id = ? AND tag = ?",
                (paper_id, tag),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_tags(self, paper_id: str) -> list[str]:
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT tag FROM paper_tags WHERE paper_id = ?", (paper_id,)
            )
            rows = await cursor.fetchall()
            return [r["tag"] for r in rows]

    # ==================== 爬取日志 ====================

    async def add_crawl_log(self, log: dict) -> int:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """INSERT INTO crawl_logs (source, query, status, papers_found,
                          papers_added, error_message, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    log.get("source"),
                    log.get("query"),
                    log.get("status", "running"),
                    log.get("papers_found", 0),
                    log.get("papers_added", 0),
                    log.get("error_message"),
                    log.get("completed_at"),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_crawl_logs(self, limit: int = 50) -> list[dict]:
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT * FROM crawl_logs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ==================== 统计 ====================

    async def get_stats(self) -> dict:
        """获取系统统计信息"""
        async with self._get_conn() as db:
            stats = {}

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM papers")
            stats["total_papers"] = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM papers WHERE is_favorited = 1"
            )
            stats["favorited_papers"] = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                "SELECT source, COUNT(*) as cnt FROM papers GROUP BY source"
            )
            stats["papers_by_source"] = {
                r["source"]: r["cnt"] for r in await cursor.fetchall()
            }

            cursor = await db.execute(
                "SELECT language, COUNT(*) as cnt FROM papers GROUP BY language"
            )
            stats["papers_by_language"] = {
                r["language"]: r["cnt"] for r in await cursor.fetchall()
            }

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM crawl_logs")
            stats["total_crawls"] = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                """SELECT * FROM crawl_logs 
                   ORDER BY started_at DESC LIMIT 1"""
            )
            last_crawl = await cursor.fetchone()
            stats["last_crawl"] = dict(last_crawl) if last_crawl else None

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM search_history")
            stats["total_searches"] = (await cursor.fetchone())["cnt"]

            return stats

    async def record_search(self, query: str, results_count: int, search_type: str = "hybrid"):
        """记录搜索历史"""
        async with self._get_conn() as db:
            await db.execute(
                "INSERT INTO search_history (query, results_count, search_type) VALUES (?, ?, ?)",
                (query, results_count, search_type),
            )
            await db.commit()

    # ==================== DOI 存在性检查 ====================

    async def doi_exists(self, doi: str) -> bool:
        """检查 DOI 是否已存在"""
        if not doi:
            return False
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT 1 FROM papers WHERE doi = ?", (doi,)
            )
            return (await cursor.fetchone()) is not None

    async def get_all_dois(self) -> set[str]:
        """获取所有已有的 DOI 集合（用于去重）"""
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT doi FROM papers WHERE doi IS NOT NULL"
            )
            rows = await cursor.fetchall()
            return {r["doi"] for r in rows}
