from .search import router as search_router
from .papers import router as papers_router
from .crawler import router as crawler_router
from .agent import router as agent_router
from .stats import router as stats_router
from .translate import router as translate_router

__all__ = [
    "search_router",
    "papers_router",
    "crawler_router",
    "agent_router",
    "stats_router",
    "translate_router"
]
