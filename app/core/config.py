import os
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Backend Deus Conhece o Seu Nome"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production-32chars"
    ADMIN_API_KEY: str = "dev-admin-api-key-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    DOWNLOAD_TOKEN_EXPIRE_MINUTES: int = 60 * 2  # 2 hours
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 15  # 15 minutes
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        return ["*"]

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "app"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "deus_conhece_nome"
    DATABASE_URL: Optional[str] = None

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql+asyncpg://"):
                return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
            elif url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+psycopg://")
            elif url.startswith("sqlite+aiosqlite://"):
                return url.replace("sqlite+aiosqlite://", "sqlite://")
            return url
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql+psycopg://"):
                return url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
            elif url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://")
            elif url.startswith("sqlite://"):
                return url.replace("sqlite://", "sqlite+aiosqlite://")
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Storage
    STORAGE_PATH: str = "./storage/books"
    DOWNLOAD_URL_BASE: str = "http://localhost:8000/api/v1/books"

    # Book Templates and Fonts (Fonte da Verdade)
    BOOK_TEMPLATES_DIR: str = "./livro-personalizado"
    BOOK_DEFAULT_FONT: str = "./livro-personalizado/Baloo2-Bold.ttf"
    BOOK_TEMPLATE_MENINO: str = "./livro-personalizado/menino_compressed.pdf"
    BOOK_TEMPLATE_MENINA: str = "./livro-personalizado/menina_compressed.pdf"

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str = "dev-evolution-key"
    EVOLUTION_INSTANCE: str = "deus-conhece-nome"

    # Webhook Secrets & Product IDs
    ORDER_WEBHOOK_SECRET: str = "dev-orders-webhook-secret"
    EVOLUTION_WEBHOOK_SECRET: str = "dev-evolution-webhook-secret"
    CAKTO_WEBHOOK_SECRET: str = "dev-cakto-webhook-secret"
    CAKTO_PRODUCT_ID: str = "d4c39c54-735b-416f-bbdf-47752679b492"

    # Order Bumps Cakto IDs & Configs
    CAKTO_ORDER_BUMP_STICKERS_ID: str = "af1a7083-5a78-48d5-9dac-3273b55a3fbd"
    CAKTO_ORDER_BUMP_CALENDAR_ID: str = "f0b39622-36e0-453d-a44b-90c7075cedf0"
    ORDER_BUMP_STORAGE_PATH: str = "./storage/order_bumps"
    ORDER_BUMP_DOWNLOAD_URL_BASE: str = "http://localhost:8000/api/v1/order-bumps"

    @property
    def order_bumps_catalog(self) -> dict:
        return {
            self.CAKTO_ORDER_BUMP_STICKERS_ID: {
                "id": self.CAKTO_ORDER_BUMP_STICKERS_ID,
                "name": "💬 Pack de Figurinhas Cristãs para WhatsApp",
                "code": "STICKERS_PACK",
                "filename": "Pack_Figurinhas_Cristas_WhatsApp.zip",
                "content_type": "application/zip",
                "description": "Pacote exclusivo com mais de 50 figurinhas cristãs e devocionais infantis para WhatsApp.",
            },
            self.CAKTO_ORDER_BUMP_CALENDAR_ID: {
                "id": self.CAKTO_ORDER_BUMP_CALENDAR_ID,
                "name": "🎄 Calendário Cristão Infantil — Datas Especiais com Deus",
                "code": "CHRISTIAN_CALENDAR",
                "filename": "Calendario_Cristao_Infantil.pdf",
                "content_type": "application/pdf",
                "description": "Calendário anual ilustrado com atividades, passagens bíblicas e datas especiais com Deus.",
            },
        }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
