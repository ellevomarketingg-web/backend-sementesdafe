import pytest
from app.utils.email import normalize_email, is_valid_email
from app.utils.phone import normalize_phone
from app.core.security import (
    create_download_token,
    verify_download_token,
    generate_numeric_code,
    verify_admin_api_key,
    verify_webhook_signature,
)
from app.core.config import settings


def test_email_normalization_and_validation():
    assert normalize_email("  Patrick.User@Example.COM  ") == "patrick.user@example.com"
    assert is_valid_email("teste@dominio.com.br") is True
    assert is_valid_email("email_invalido.com") is False


def test_phone_normalization():
    assert normalize_phone("(11) 98765-4321") == "5511987654321"
    assert normalize_phone("+55 11 98765-4321") == "5511987654321"
    assert normalize_phone("5511987654321") == "5511987654321"
    assert normalize_phone(None) is None


def test_security_helpers():
    # 2FA Numeric code
    code = generate_numeric_code(6)
    assert len(code) == 6
    assert code.isdigit()

    # Admin Key
    assert verify_admin_api_key(settings.ADMIN_API_KEY) is True
    assert verify_admin_api_key("wrong-key") is False
    assert verify_admin_api_key(None) is False

    # Download Token
    token = create_download_token("book_uuid_123", "usuario@email.com")
    payload = verify_download_token(token)
    assert payload is not None
    assert payload["sub"] == "book_uuid_123"
    assert payload["email"] == "usuario@email.com"

    # Invalid token
    assert verify_download_token("invalid.jwt.token") is None

    # Webhook signature
    body = b'{"event":"test"}'
    secret = "my-secret-key"
    import hmac, hashlib
    expected_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, expected_sig, secret) is True
    assert verify_webhook_signature(body, f"sha256={expected_sig}", secret) is True
    assert verify_webhook_signature(body, "wrong_sig", secret) is False
