import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import SERVER_HOST, SERVER_PORT, CORS_ORIGINS
from database.db import DatabaseManager
from database.models import init_database
from rag.vector_store import VectorStore
from rag.retriever import HybridRetriever
from crawlers.manager import CrawlerManager
from agent_tools.tools import init_tools_dependencies
from scheduler.jobs import start_scheduler, stop_scheduler

from routes import search_router, papers_router, crawler_router, agent_router, stats_router, translate_router, readiness_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 初始化数据库
    await init_database()
    
    # 2. 初始化核心组件
    db = DatabaseManager()
    vector_store = VectorStore()
    retriever = HybridRetriever(db=db, vector_store=vector_store)
    crawler_manager = CrawlerManager(db=db, vector_store=vector_store)
    
    # 3. 注入到 app.state
    app.state.db = db
    app.state.vector_store = vector_store
    app.state.retriever = retriever
    app.state.crawler_manager = crawler_manager
    
    # 4. 初始化 Agent 工具的依赖
    init_tools_dependencies(db, vector_store, retriever, crawler_manager)
    
    # 5. 启动定时任务
    start_scheduler(crawler_manager)
    
    yield
    
    # 清理资源
    stop_scheduler()
    await crawler_manager.close_all()


app = FastAPI(
    title="Paper Memory Agent",
    description="基于 RAG 的文科生论文记忆库系统，提供 Agent 接口和自动化爬虫。",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(search_router)
app.include_router(papers_router)
app.include_router(crawler_router)
app.include_router(agent_router)
app.include_router(stats_router)
app.include_router(translate_router)
app.include_router(readiness_router)

# 挂载静态文件 (前端)
import os
from pathlib import Path
STATIC_DIR = Path(__file__).parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
