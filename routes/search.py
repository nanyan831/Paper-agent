from fastapi import APIRouter, Request, Query
from typing import Optional

router = APIRouter(prefix="/api/search", tags=["Search"])

@router.get("")
async def search_papers(
    request: Request,
    q: str,
    top_k: int = Query(20, le=100),
    search_type: str = Query("hybrid", regex="^(hybrid|semantic|keyword)$"),
    source: Optional[str] = None
):
    retriever = request.app.state.retriever
    filters = {"source": source} if source else None
    
    results = await retriever.search(
        query=q,
        top_k=top_k,
        filters=filters,
        search_type=search_type
    )
    return {"results": results}

@router.get("/related/{paper_id}")
async def get_related(
    request: Request,
    paper_id: str,
    top_k: int = Query(10, le=50)
):
    retriever = request.app.state.retriever
    results = await retriever.find_related(paper_id, top_k)
    return {"results": results}
