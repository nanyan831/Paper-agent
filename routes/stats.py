from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/stats", tags=["Stats"])

@router.get("")
async def get_stats(request: Request):
    db = request.app.state.db
    stats = await db.get_stats()
    return stats
