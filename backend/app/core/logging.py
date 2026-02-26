"""Structured logging configuration with request ID tracking."""
import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from app.core.config import get_settings

settings = get_settings()

# Context variable to store request ID across async operations
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that adds structured fields to log records.
    
    Adds:
    - timestamp (ISO format)
    - level
    - request_id (if available)
    - message
    - logger name
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured fields."""
        request_id = request_id_var.get()
        
        # Build structured log message
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add correlation ID if present (request_id / X-Correlation-ID)
        if request_id:
            log_data["request_id"] = request_id
            log_data["correlation_id"] = request_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Include extra fields (e.g., path, status_code)
        reserved = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message"
        }
        for key, value in record.__dict__.items():
            if key not in reserved and key not in log_data:
                log_data[key] = value
        
        return json.dumps(log_data, default=str)


def setup_logging() -> None:
    """
    Configure application-wide logging.
    
    Sets up:
    - Root logger with configured level
    - Structured formatter
    - Console handler
    - Uvicorn access logs
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler with structured formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL)
    
    formatter = StructuredFormatter(
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)
    
    # Configure uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    # Reduce noise from third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_request_id() -> str:
    """
    Get current request ID or generate a new one.
    
    Returns:
        str: Request ID (UUID format)
    """
    request_id = request_id_var.get()
    if not request_id:
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
    return request_id


def set_request_id(request_id: str) -> None:
    """
    Set request ID for current context.
    
    Args:
        request_id: Unique identifier for the request
    """
    request_id_var.set(request_id)

