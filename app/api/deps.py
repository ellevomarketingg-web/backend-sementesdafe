from typing import Optional
from fastapi import Header, HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from app.core.security import verify_admin_api_key

API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def get_admin_user(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Valida se a requisição possui a chave administrativa válida."""
    if not api_key or not verify_admin_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API administrativa inválida ou ausente.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return "admin"
