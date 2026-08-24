import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.database import engine, AsyncSessionLocal
from app.models.base import Base
from app.api.router import api_router
from app.api.routes import health
from app.services.communication_service import CommunicationService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Setup logging
    setup_logging()
    logger.info(f"Iniciando {settings.PROJECT_NAME} em ambiente {settings.ENVIRONMENT}")

    # 2. Assegura diretório de storage
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)

    # 3. Cria tabelas se banco SQLite / dev
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 4. Assegura templates padrão
    async with AsyncSessionLocal() as session:
        try:
            await CommunicationService.ensure_default_templates(session)
        except Exception as e:
            logger.warning(f"Não foi possível inicializar templates padrão no startup: {e}")

    yield

    logger.info(f"Encerrando {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API do backend da plataforma 'Deus Conhece o Seu Nome' — Checkout, Livros, Templates, WhatsApp e Entregas.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root level health checks
app.include_router(health.router)

# Main API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "api_v1": settings.API_V1_STR,
    }
