import os
import base64
import mimetypes
from typing import Optional, Dict, Any
import httpx
from app.core.config import settings
from app.core.logging import logger


class EvolutionService:
    """Cliente HTTP para integração com a Evolution API (WhatsApp)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        instance: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.EVOLUTION_API_URL).rstrip("/")
        self.api_key = api_key or settings.EVOLUTION_API_KEY
        self.instance = instance or settings.EVOLUTION_INSTANCE
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normaliza o número de telefone removendo caracteres não-numéricos
        e garantindo DDI 55 (Brasil) caso seja omitido.
        """
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) in (10, 11) and not digits.startswith("55"):
            digits = f"55{digits}"
        return digits

    async def send_text(
        self,
        phone: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Envia mensagem de texto via WhatsApp através da Evolution API.
        Retorna dict com status de sucesso e external_message_id.
        """
        norm_phone = self.normalize_phone(phone)
        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": norm_phone,
            "options": {
                "delay": 1200,
                "presence": "composing",
                "linkPreview": True,
            },
            "textMessage": {
                "text": message,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                
                if response.status_code in (200, 201):
                    data = response.json()
                    # Evolution API message ID extractor
                    ext_id = (
                        data.get("key", {}).get("id")
                        or data.get("messageId")
                        or data.get("id")
                        or str(data.get("keyId", ""))
                    )
                    logger.info(f"Mensagem WhatsApp enviada com sucesso para {norm_phone} ext_id={ext_id}")
                    return {
                        "success": True,
                        "external_message_id": ext_id,
                        "data": data,
                        "error": None,
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Falha ao enviar mensagem WhatsApp para {norm_phone}: {error_msg}")
                    return {
                        "success": False,
                        "external_message_id": None,
                        "data": None,
                        "error": error_msg,
                    }
        except httpx.RequestError as e:
            error_msg = f"Erro de conexão com Evolution API: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "external_message_id": None,
                "data": None,
                "error": error_msg,
            }

    async def send_document(
        self,
        phone: str,
        document_url_or_base64: str,
        filename: str = "Deus_Conhece_o_Seu_Nome.pdf",
        caption: str = "",
    ) -> Dict[str, Any]:
        """
        Envia documento (PDF do livro, calendário, etc.) via WhatsApp.
        Se document_url_or_base64 for um caminho de arquivo local no disco,
        converte automaticamente para base64 data URI.
        """
        norm_phone = self.normalize_phone(phone)
        media_content = document_url_or_base64

        # Se for um arquivo existente no disco, lê e converte para base64 puro
        resolved_path = document_url_or_base64
        if not os.path.exists(resolved_path) and not resolved_path.startswith(("http://", "https://")):
            # Tenta resolver relativo a partir da raiz do app
            potential = os.path.abspath(resolved_path)
            if os.path.exists(potential):
                resolved_path = potential

        if os.path.exists(resolved_path) and os.path.isfile(resolved_path):
            try:
                with open(resolved_path, "rb") as f:
                    encoded_b64 = base64.b64encode(f.read()).decode("utf-8")
                # Evolution API aceita base64 puro ou URL HTTP(s)
                media_content = encoded_b64
                logger.info(f"Arquivo local '{resolved_path}' codificado em base64 puro ({len(encoded_b64)} chars)")
            except Exception as e:
                logger.error(f"Erro ao converter arquivo local para base64: {e}")

        url = f"{self.base_url}/message/sendMedia/{self.instance}"
        payload = {
            "number": norm_phone,
            "options": {
                "delay": 1200,
                "presence": "composing",
            },
            "mediaMessage": {
                "mediatype": "document",
                "fileName": filename,
                "caption": caption,
                "media": media_content,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in (200, 201):
                    data = response.json()
                    ext_id = data.get("key", {}).get("id") or data.get("messageId")
                    logger.info(f"Documento WhatsApp enviado com sucesso para {norm_phone} ext_id={ext_id}")
                    return {
                        "success": True,
                        "external_message_id": ext_id,
                        "data": data,
                        "error": None,
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Falha ao enviar documento WhatsApp: {error_msg}")
                    return {
                        "success": False,
                        "external_message_id": None,
                        "data": None,
                        "error": error_msg,
                    }
        except httpx.RequestError as e:
            error_msg = f"Erro de conexão com Evolution API: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "external_message_id": None,
                "data": None,
                "error": error_msg,
            }


evolution_service = EvolutionService()
