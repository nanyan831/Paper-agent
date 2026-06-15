from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["readiness"])


@router.get("/readiness")
async def get_readiness(request: Request):
    db = request.app.state.db
    return await db.get_readiness()
