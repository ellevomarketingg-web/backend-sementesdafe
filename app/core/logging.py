import logging
import sys
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] [{record.levelname}] [{record.name}]"
        
        # Attach contextual attributes if present
        context_parts = []
        for attr in ["request_id", "event_id", "order_id", "book_id", "message_id", "buyer_id"]:
            if hasattr(record, attr):
                val = getattr(record, attr)
                if val is not None:
                    context_parts.append(f"{attr}={val}")
                    
        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        return f"{base}{context_str} {record.getMessage()}"


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    
    # Silence noisy loggers if needed
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


logger = logging.getLogger("deus_conhece_nome")
