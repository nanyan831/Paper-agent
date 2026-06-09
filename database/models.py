"""
数据库表结构定义与初始化
"""
import aiosqlite
from config import DB_PATH


# SQL 建表语句
CREATE_PAPERS_TABLE = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    keywords TEXT,
    url TEXT,
    doi TEXT UNIQUE,
    source TEXT,
    publish_date TEXT,
    journal TEXT,
    full_text TEXT,
    file_path TEXT,
    parse_status TEXT DEFAULT 'metadata_only',
    language TEXT DEFAULT 'zh',
    citation_count INTEGER DEFAULT 0,
    is_favorited INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PAPER_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    section TEXT,
    page_start INTEGER,
    page_end INTEGER,
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    UNIQUE(paper_id, chunk_index)
);
"""

CREATE_CHUNKS_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts USING fts5(
    content,
    section,
    content='paper_chunks',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

CREATE_CHUNKS_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_insert AFTER INSERT ON paper_chunks BEGIN
    INSERT INTO paper_chunks_fts(rowid, content, section)
    VALUES (new.rowid, new.content, new.section);
END;
"""

CREATE_CHUNKS_FTS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_delete AFTER DELETE ON paper_chunks BEGIN
    INSERT INTO paper_chunks_fts(paper_chunks_fts, rowid, content, section)
    VALUES ('delete', old.rowid, old.content, old.section);
END;
"""

CREATE_CHUNKS_FTS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_update AFTER UPDATE ON paper_chunks BEGIN
    INSERT INTO paper_chunks_fts(paper_chunks_fts, rowid, content, section)
    VALUES ('delete', old.rowid, old.content, old.section);
    INSERT INTO paper_chunks_fts(rowid, content, section)
    VALUES (new.rowid, new.content, new.section);
END;
"""

CREATE_PAPER_TAGS_TABLE = """
CREATE TABLE IF NOT EXISTS paper_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    UNIQUE(paper_id, tag)
);
"""

CREATE_CRAWL_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS crawl_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    query TEXT,
    status TEXT NOT NULL,
    papers_found INTEGER DEFAULT 0,
    papers_added INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
"""

CREATE_RSS_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS rss_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    category TEXT,
    last_checked TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SEARCH_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    results_count INTEGER DEFAULT 0,
    search_type TEXT DEFAULT 'hybrid',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# FTS5 全文搜索虚拟表
CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title,
    abstract,
    keywords,
    authors,
    content='papers',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

# FTS 触发器 —— 保持 FTS 表与 papers 表同步
CREATE_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS papers_fts_insert AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, abstract, keywords, authors)
    VALUES (new.rowid, new.title, new.abstract, new.keywords, new.authors);
END;
"""

CREATE_FTS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS papers_fts_delete AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, keywords, authors)
    VALUES ('delete', old.rowid, old.title, old.abstract, old.keywords, old.authors);
END;
"""

CREATE_FTS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS papers_fts_update AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, keywords, authors)
    VALUES ('delete', old.rowid, old.title, old.abstract, old.keywords, old.authors);
    INSERT INTO papers_fts(rowid, title, abstract, keywords, authors)
    VALUES (new.rowid, new.title, new.abstract, new.keywords, new.authors);
END;
"""

# 索引
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);",
    "CREATE INDEX IF NOT EXISTS idx_papers_publish_date ON papers(publish_date);",
    "CREATE INDEX IF NOT EXISTS idx_papers_language ON papers(language);",
    "CREATE INDEX IF NOT EXISTS idx_papers_favorited ON papers(is_favorited);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_paper ON paper_chunks(paper_id);",
    "CREATE INDEX IF NOT EXISTS idx_paper_tags_paper ON paper_tags(paper_id);",
    "CREATE INDEX IF NOT EXISTS idx_paper_tags_tag ON paper_tags(tag);",
    "CREATE INDEX IF NOT EXISTS idx_crawl_logs_source ON crawl_logs(source);",
]


async def _ensure_paper_columns(db):
    cursor = await db.execute("PRAGMA table_info(papers)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "file_path" not in columns:
        await db.execute("ALTER TABLE papers ADD COLUMN file_path TEXT")
    if "parse_status" not in columns:
        await db.execute("ALTER TABLE papers ADD COLUMN parse_status TEXT DEFAULT 'metadata_only'")


async def init_database():
    """初始化数据库：建表、建索引、建 FTS"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        # 启用 WAL 模式提升并发性能
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        # 建表
        await db.execute(CREATE_PAPERS_TABLE)
        await _ensure_paper_columns(db)
        await db.execute(CREATE_PAPER_CHUNKS_TABLE)
        await db.execute(CREATE_PAPER_TAGS_TABLE)
        await db.execute(CREATE_CRAWL_LOGS_TABLE)
        await db.execute(CREATE_RSS_SOURCES_TABLE)
        await db.execute(CREATE_SEARCH_HISTORY_TABLE)

        # FTS 全文搜索
        await db.execute(CREATE_FTS_TABLE)
        await db.execute(CREATE_FTS_INSERT_TRIGGER)
        await db.execute(CREATE_FTS_DELETE_TRIGGER)
        await db.execute(CREATE_FTS_UPDATE_TRIGGER)
        await db.execute(CREATE_CHUNKS_FTS_TABLE)
        await db.execute(CREATE_CHUNKS_FTS_INSERT_TRIGGER)
        await db.execute(CREATE_CHUNKS_FTS_DELETE_TRIGGER)
        await db.execute(CREATE_CHUNKS_FTS_UPDATE_TRIGGER)
        await db.execute("INSERT INTO paper_chunks_fts(paper_chunks_fts) VALUES('rebuild')")

        # 索引
        for idx_sql in CREATE_INDEXES:
            await db.execute(idx_sql)

        await db.commit()

    print("Database initialized successfully.")
