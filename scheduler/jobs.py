import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import SCHEDULER_CONFIG
from crawlers.manager import CrawlerManager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def auto_crawl_job(crawler_manager: CrawlerManager):
    """定时自动爬取最新论文"""
    logger.info("开始执行定时爬虫任务 (Latest)...")
    await crawler_manager.run_all_latest()
    logger.info("定时爬虫任务执行完毕")


def start_scheduler(crawler_manager: CrawlerManager):
    """启动定时调度器"""
    global scheduler
    
    crawl_interval = SCHEDULER_CONFIG.get("auto_crawl_interval_hours", 6)
    
    # 添加爬取最新论文的任务
    scheduler.add_job(
        auto_crawl_job,
        trigger=IntervalTrigger(hours=crawl_interval),
        args=[crawler_manager],
        id="auto_crawl_latest",
        name="Auto crawl latest papers",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"调度器已启动, 每 {crawl_interval} 小时自动爬取一次")

def stop_scheduler():
    global scheduler
    if scheduler.running:
        scheduler.shutdown()
        logger.info("调度器已停止")
