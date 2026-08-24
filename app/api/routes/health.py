import os
from fastapi import APIRouter, Depends, status, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check básico."""
    return {"status": "ok"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(response: Response, db: AsyncSession = Depends(get_db)):
    """Readiness check verificando conectividade com o banco de dados e diretório de storage."""
    checks = {
        "database": "unknown",
        "storage": "unknown",
    }
    
    # 1. Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # 2. Storage check
    try:
        os.makedirs(settings.STORAGE_PATH, exist_ok=True)
        test_file = os.path.join(settings.STORAGE_PATH, ".storage_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "checks": checks}

    return {"status": "ready", "checks": checks}
