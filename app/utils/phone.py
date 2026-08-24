import re
from typing import Optional


def normalize_phone(phone: Optional[str], default_country_code: str = "55") -> Optional[str]:
    """
    Normaliza telefone para formato de dígitos contínuos (ex: 5511999999999).
    Remove caracteres não numéricos (+, -, (, ), espaços).
    Adiciona DDI brasileiro (55) caso falte e tamanho aparente seja DDD + número (10 ou 11 dígitos).
    """
    if not phone:
        return None
        
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
        
    # Se tem 10 ou 11 dígitos (DDD + número), assume Brasil e adiciona 55
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = f"{default_country_code}{digits}"
        
    return digits
