import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from app.core.config import settings

ALGORITHM = "HS256"


def create_download_token(book_id: str, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Gera token assinado e temporário para download de livro."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.DOWNLOAD_TOKEN_EXPIRE_MINUTES)
        
    to_encode = {
        "sub": str(book_id),
        "email": email,
        "type": "book_download",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_download_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida token temporário de download."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "book_download":
            return None
        return payload
    except JWTError:
        return None


def generate_numeric_code(length: int = 6) -> str:
    """Gera código numérico de verificação temporário."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def verify_admin_api_key(api_key: Optional[str]) -> bool:
    """Valida a chave administrativa."""
    if not api_key:
        return False
    return secrets.compare_digest(api_key, settings.ADMIN_API_KEY)


def verify_webhook_signature(payload_bytes: bytes, signature: Optional[str], secret: str) -> bool:
    """Valida assinatura HMAC-SHA256 de webhook."""
    if not signature or not secret:
        return False
    expected_signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    # Normalize if header contains 'sha256=' prefix
    clean_sig = signature.removeprefix("sha256=").strip()
    return secrets.compare_digest(clean_sig, expected_signature)
