from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/health", summary="Checks if the API is running")
async def health_check():
    return {"status": "OK"}
