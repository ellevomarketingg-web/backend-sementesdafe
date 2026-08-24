import re
from typing import Optional


def normalize_email(email: str) -> str:
    """Normaliza o e-mail para minúsculas e remove espaços extras."""
    if not email:
        return ""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """Validação básica de formato de e-mail."""
    normalized = normalize_email(email)
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, normalized))
