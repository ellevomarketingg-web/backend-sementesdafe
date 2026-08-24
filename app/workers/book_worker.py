from app.core.database import AsyncSessionLocal
from app.services.book_service import BookService
from app.core.logging import logger


async def process_book_generation_job(book_id: str) -> None:
    """Worker task para geração de livro em background."""
    logger.info(f"[BookWorker] Iniciando processamento do livro id={book_id}")
    async with AsyncSessionLocal() as session:
        try:
            book = await BookService.generate_book(session, book_id)
            logger.info(f"[BookWorker] Livro id={book_id} processado com sucesso status={book.status}")
        except Exception as e:
            logger.error(f"[BookWorker] Falha ao processar livro id={book_id}: {e}", exc_info=True)
