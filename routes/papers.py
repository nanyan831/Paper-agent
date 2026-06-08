from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/api/papers", tags=["Papers"])

@router.get("")
async def list_papers(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    source: Optional[str] = None,
    favorited: bool = False
):
    db = request.app.state.db
    offset = (page - 1) * limit
    
    result = await db.list_papers(
        offset=offset, 
        limit=limit, 
        source=source,
        favorited_only=favorited
    )
    return result

@router.get("/{paper_id}")
async def get_paper(request: Request, paper_id: str):
    db = request.app.state.db
    paper = await db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # 获取标签
    tags = await db.get_tags(paper_id)
    paper["tags"] = tags
    return paper

@router.delete("/{paper_id}")
async def delete_paper(request: Request, paper_id: str):
    db = request.app.state.db
    vs = request.app.state.vector_store
    
    success = await db.delete_paper(paper_id)
    if success:
        vs.delete_paper(paper_id)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Paper not found")

@router.post("/{paper_id}/favorite")
async def toggle_favorite(request: Request, paper_id: str):
    db = request.app.state.db
    new_status = await db.toggle_favorite(paper_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {"success": True, "is_favorited": new_status}
