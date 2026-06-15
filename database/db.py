"""
数据库操作管理器 —— 封装所有 CRUD 操作
"""
import json
import uuid
import aiosqlite
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from config import DB_PATH, DEEPSEEK_API_KEY, DAILY_TOKEN_BUDGET

PLACEHOLDER_KEYS = {"", "your-api-key-here", "sk-xxx", "sk-placeholder", "insert_your_key_here"}


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
                        publish_date, journal, full_text, file_path, parse_status,
                        language, citation_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        paper.get("file_path", ""),
                        paper.get("parse_status", "metadata_only"),
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
            conditions.append("p.source = ?")
            params.append(source)
        if language:
            conditions.append("p.language = ?")
            params.append(language)
        if favorited_only:
            conditions.append("p.is_favorited = 1")

        where = " AND ".join(conditions) if conditions else "1=1"
        allowed_sort = {
            "created_at": "p.created_at",
            "publish_date": "p.publish_date",
            "citation_count": "p.citation_count",
            "title": "p.title",
        }
        sort_col = allowed_sort.get(sort_by, "p.created_at")
        order = "ASC" if sort_order.upper() == "ASC" else "DESC"

        async with self._get_conn() as db:
            # 总数
            cursor = await db.execute(
                f"SELECT COUNT(*) as cnt FROM papers p WHERE {where}", params
            )
            total = (await cursor.fetchone())["cnt"]

            # 分页数据
            cursor = await db.execute(
                f"""SELECT p.id, p.title, p.authors, p.abstract, p.keywords, p.url, p.doi, p.source,
                           p.publish_date, p.journal, p.language, p.citation_count,
                           p.is_favorited, p.file_path, p.parse_status, p.created_at,
                           LENGTH(COALESCE(p.full_text, '')) as text_chars,
                           COUNT(c.id) as chunk_count,
                           COALESCE(MAX(c.page_end), MAX(c.page_start), 0) as page_count
                    FROM papers p
                    LEFT JOIN paper_chunks c ON c.paper_id = p.id
                    WHERE {where}
                    GROUP BY p.id
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

    async def replace_paper_chunks(self, paper_id: str, chunks: list[dict]) -> int:
        """Replace all stored chunks for a paper."""
        async with self._get_conn() as db:
            await db.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (paper_id,))
            for chunk in chunks:
                await db.execute(
                    """INSERT INTO paper_chunks
                       (id, paper_id, chunk_index, section, page_start, page_end, content, token_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk["id"],
                        paper_id,
                        chunk["chunk_index"],
                        chunk.get("section"),
                        chunk.get("page_start"),
                        chunk.get("page_end"),
                        chunk["content"],
                        chunk.get("token_count", 0),
                    ),
                )
            await db.commit()
            return len(chunks)

    async def get_paper_chunks(self, paper_id: str, limit: int = 200) -> list[dict]:
        """Return chunks for a paper in reading order."""
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT id, paper_id, chunk_index, section, page_start, page_end,
                          content, token_count, created_at
                   FROM paper_chunks
                   WHERE paper_id = ?
                   ORDER BY chunk_index
                   LIMIT ?""",
                (paper_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """Return chunks by id, preserving the requested order."""
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        async with self._get_conn() as db:
            cursor = await db.execute(
                f"""SELECT c.id, c.paper_id, c.chunk_index, c.section, c.page_start,
                           c.page_end, c.content, c.token_count,
                           p.title, p.authors, p.source, p.publish_date, p.journal,
                           p.url, p.doi
                    FROM paper_chunks c
                    JOIN papers p ON p.id = c.paper_id
                    WHERE c.id IN ({placeholders})""",
                chunk_ids,
            )
            rows = [dict(r) for r in await cursor.fetchall()]
        by_id = {row["id"]: row for row in rows}
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    async def fts_search_chunks(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 search over full-text chunks."""
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT c.id, c.paper_id, c.chunk_index, c.section, c.page_start,
                          c.page_end, c.content, c.token_count,
                          p.title, p.authors, p.source, p.publish_date, p.journal,
                          p.url, p.doi, rank AS fts_score
                   FROM paper_chunks_fts fts
                   JOIN paper_chunks c ON c.rowid = fts.rowid
                   JOIN papers p ON p.id = c.paper_id
                   WHERE paper_chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

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
                          p.file_path, p.parse_status,
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

            cursor = await db.execute(
                """SELECT
                       COUNT(*) as total_calls,
                       COALESCE(SUM(input_tokens), 0) as input_tokens,
                       COALESCE(SUM(output_tokens), 0) as output_tokens,
                       COALESCE(SUM(total_tokens), 0) as total_tokens,
                       COALESCE(SUM(tool_calls), 0) as tool_calls
                   FROM model_usage_logs"""
            )
            usage_row = await cursor.fetchone()

            cursor = await db.execute(
                """SELECT
                       COUNT(*) as total_calls,
                       COALESCE(SUM(input_tokens), 0) as input_tokens,
                       COALESCE(SUM(output_tokens), 0) as output_tokens,
                       COALESCE(SUM(total_tokens), 0) as total_tokens,
                       COALESCE(SUM(tool_calls), 0) as tool_calls
                   FROM model_usage_logs
                   WHERE date(created_at, 'localtime') = date('now', 'localtime')"""
            )
            today_usage_row = await cursor.fetchone()

            cursor = await db.execute(
                """SELECT model, COUNT(*) as calls, COALESCE(SUM(total_tokens), 0) as total_tokens
                   FROM model_usage_logs
                   GROUP BY model
                   ORDER BY total_tokens DESC"""
            )
            usage_by_model = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                """SELECT u.id, u.session_id, s.title, u.model, u.input_tokens,
                          u.output_tokens, u.total_tokens, u.tool_calls, u.created_at
                   FROM model_usage_logs u
                   LEFT JOIN chat_sessions s ON s.id = u.session_id
                   ORDER BY u.created_at DESC, u.id DESC
                   LIMIT 20"""
            )
            recent_usage = [dict(r) for r in await cursor.fetchall()]

            stats["agent_usage"] = {
                "total_calls": usage_row["total_calls"],
                "input_tokens": usage_row["input_tokens"],
                "output_tokens": usage_row["output_tokens"],
                "total_tokens": usage_row["total_tokens"],
                "tool_calls": usage_row["tool_calls"],
                "pricing": {
                    "currency": "USD",
                    "estimate_only": True,
                    "pricing_source": "manual_config",
                    "input_per_million": 0.14,
                    "output_per_million": 0.28,
                    "note": "Rough local estimate; provider billing is authoritative.",
                },
                "today": {
                    "total_calls": today_usage_row["total_calls"],
                    "input_tokens": today_usage_row["input_tokens"],
                    "output_tokens": today_usage_row["output_tokens"],
                    "total_tokens": today_usage_row["total_tokens"],
                    "tool_calls": today_usage_row["tool_calls"],
                },
                "budget": await self.get_token_budget_status(),
                "by_model": usage_by_model,
                "recent": recent_usage,
            }
            stats["recent_rag_hits"] = await self.get_recent_rag_hits(limit=8)

            return stats

    async def record_search(self, query: str, results_count: int, search_type: str = "hybrid"):
        """记录搜索历史"""
        async with self._get_conn() as db:
            await db.execute(
                "INSERT INTO search_history (query, results_count, search_type) VALUES (?, ?, ?)",
                (query, results_count, search_type),
            )
            await db.commit()

    # ==================== Readiness ====================

    async def get_readiness(self) -> dict:
        key = (DEEPSEEK_API_KEY or "").strip()
        api_key_configured = bool(key) and key.lower() not in PLACEHOLDER_KEYS

        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM papers WHERE source = 'local_pdf' OR (file_path IS NOT NULL AND file_path != '')"
            )
            local_pdf_count = (await cursor.fetchone())["cnt"]

            cursor = await db.execute(
                """SELECT COUNT(DISTINCT p.id) as cnt
                   FROM papers p
                   JOIN paper_chunks c ON c.paper_id = p.id
                   WHERE (p.source = 'local_pdf' OR (p.file_path IS NOT NULL AND p.file_path != ''))
                     AND c.id IS NOT NULL"""
            )
            searchable_pdf_count = (await cursor.fetchone())["cnt"]

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM paper_chunks")
            chunk_count = (await cursor.fetchone())["cnt"]

        if not api_key_configured:
            status = "needs_api_key"
        elif local_pdf_count == 0:
            status = "needs_pdf"
        elif searchable_pdf_count == 0:
            status = "needs_chunks"
        else:
            status = "ready"

        blockers = []
        if not api_key_configured:
            blockers.append({
                "code": "NO_API_KEY",
                "message": "DeepSeek API key is not configured",
                "action": "Set DEEPSEEK_API_KEY in .env file",
            })
        if local_pdf_count == 0:
            blockers.append({
                "code": "NO_PDF",
                "message": "No local PDF files uploaded",
                "action": "Upload a PDF through the papers page",
            })
        if api_key_configured and local_pdf_count > 0 and searchable_pdf_count == 0:
            blockers.append({
                "code": "NO_CHUNKS",
                "message": "PDFs have not been processed into searchable chunks",
                "action": "Run PDF parsing on uploaded papers",
            })

        from rag.embedder import get_embedding_status
        emb = get_embedding_status()
        warnings = []
        if emb["status"] == "loading":
            warnings.append(f"Embedding model is loading ({emb.get('model_name', '')}), first search may be slow")
        elif emb["status"] == "not_loaded":
            warnings.append("Embedding model has not been loaded yet; first search will trigger download")
        elif emb["status"] == "error":
            warnings.append(f"Embedding model failed to load: {emb.get('error', 'unknown error')}")

        token_budget = await self.get_token_budget_status()
        if token_budget["enabled"] and token_budget["exceeded"]:
            warnings.append(
                f"每日 token 预算已耗尽（已用 {token_budget['used']}，预算 {token_budget['budget']}），请明日再试"
            )

        return {
            "api_key_configured": api_key_configured,
            "local_pdf_count": local_pdf_count,
            "searchable_pdf_count": searchable_pdf_count,
            "chunk_count": chunk_count,
            "status": status,
            "blockers": blockers,
            "warnings": warnings,
            "embedding_model": emb,
            "token_budget": token_budget,
        }

    # ==================== DOI 存在性检查 ====================

    # ==================== Chat sessions ====================

    async def create_chat_session(self, title: str = "New chat") -> str:
        session_id = str(uuid.uuid4())
        async with self._get_conn() as db:
            await db.execute(
                "INSERT INTO chat_sessions (id, title) VALUES (?, ?)",
                (session_id, title[:80] if title else "New chat"),
            )
            await db.commit()
            return session_id

    async def get_chat_session(self, session_id: str) -> Optional[dict]:
        async with self._get_conn() as db:
            cursor = await db.execute(
                "SELECT * FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_chat_messages(self, session_id: str, limit: int = 200) -> list[dict]:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT id, session_id, role, content, tool_name, metadata,
                          token_estimate, created_at
                   FROM chat_messages
                   WHERE session_id = ?
                   ORDER BY rowid ASC
                   LIMIT ?""",
                (session_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_recent_chat_messages(self, session_id: str, limit: int = 10) -> list[dict]:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT id, session_id, role, content, tool_name, metadata,
                          token_estimate, created_at
                   FROM chat_messages
                   WHERE session_id = ? AND role IN ('user', 'assistant')
                   ORDER BY rowid DESC
                   LIMIT ?""",
                (session_id, limit),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
            return list(reversed(rows))

    async def get_recent_rag_hits(self, limit: int = 8) -> list[dict]:
        """Return recent search_chunks tool calls with their retrieved chunk hits."""
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT m.id, m.session_id, s.title, m.content, m.metadata, m.created_at
                   FROM chat_messages m
                   LEFT JOIN chat_sessions s ON s.id = m.session_id
                   WHERE m.role = 'tool' AND m.tool_name = 'search_chunks'
                   ORDER BY m.rowid DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = [dict(r) for r in await cursor.fetchall()]

        calls = []
        for row in rows:
            metadata = {}
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    metadata = {}

            hits = metadata.get("rag_hits")
            if hits is None and row.get("content"):
                try:
                    tool_payload = json.loads(row["content"])
                    hits = tool_payload.get("data") or []
                except json.JSONDecodeError:
                    hits = []

            calls.append(
                {
                    "message_id": row["id"],
                    "session_id": row["session_id"],
                    "session_title": row.get("title"),
                    "created_at": row["created_at"],
                    "hits": hits or [],
                }
            )
        return calls

    async def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        message_id = str(uuid.uuid4())
        token_estimate = max(1, len(content or "") // 4)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        async with self._get_conn() as db:
            await db.execute(
                """INSERT INTO chat_messages
                   (id, session_id, role, content, tool_name, metadata, token_estimate)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    session_id,
                    role,
                    content or "",
                    tool_name,
                    metadata_json,
                    token_estimate,
                ),
            )
            await db.execute(
                "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,),
            )
            await db.commit()
            return message_id

    async def update_chat_summary(self, session_id: str, summary: str) -> bool:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """UPDATE chat_sessions
                   SET summary = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (summary[:4000], session_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def record_model_usage(
        self,
        session_id: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        tool_calls: int = 0,
    ) -> int:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """INSERT INTO model_usage_logs
                   (session_id, model, input_tokens, output_tokens, total_tokens, tool_calls)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, model, input_tokens, output_tokens, total_tokens, tool_calls),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_today_model_usage(self) -> dict:
        async with self._get_conn() as db:
            cursor = await db.execute(
                """SELECT
                       COUNT(*) as total_calls,
                       COALESCE(SUM(input_tokens), 0) as input_tokens,
                       COALESCE(SUM(output_tokens), 0) as output_tokens,
                       COALESCE(SUM(total_tokens), 0) as total_tokens,
                       COALESCE(SUM(tool_calls), 0) as tool_calls
                   FROM model_usage_logs
                   WHERE date(created_at, 'localtime') = date('now', 'localtime')"""
            )
            row = await cursor.fetchone()
            return dict(row) if row else {
                "total_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "tool_calls": 0,
            }

    async def get_token_budget_status(self) -> dict:
        if DAILY_TOKEN_BUDGET <= 0:
            return {"enabled": False, "budget": 0, "used": 0, "remaining": 0, "exceeded": False}

        today = await self.get_today_model_usage()
        used = today["total_tokens"]
        remaining = max(0, DAILY_TOKEN_BUDGET - used)
        return {
            "enabled": True,
            "budget": DAILY_TOKEN_BUDGET,
            "used": used,
            "remaining": remaining,
            "exceeded": used >= DAILY_TOKEN_BUDGET,
        }

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
