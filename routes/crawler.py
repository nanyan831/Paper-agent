import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/api/crawl", tags=["Crawler"])

class CrawlRequest(BaseModel):
    source: str
    topic: str = None
    max_results: int = 20

@router.post("/trigger")
async def trigger_crawl(request: Request, req: CrawlRequest, background_tasks: BackgroundTasks):
    manager = request.app.state.crawler_manager
    
    # 异步执行爬取，立即返回以避免超时
    background_tasks.add_task(
        manager.run_crawl, 
        source=req.source, 
        query=req.topic, 
        max_results=req.max_results
    )
    
    return {
        "success": True, 
        "message": f"Crawler {req.source} triggered for '{req.topic or 'latest'}'"
    }

@router.get("/logs")
async def get_logs(request: Request, limit: int = 50):
    db = request.app.state.db
    logs = await db.get_crawl_logs(limit)
    return {"logs": logs}
