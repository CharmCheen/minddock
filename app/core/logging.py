"""Logging configuration for the API service."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

TRACE_LEVEL_NUM = 5
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_MAX_LOG_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3
_NOISY_LOGGER_LEVELS = {
    "chromadb.telemetry": logging.CRITICAL,
    "chromadb.telemetry.product.posthog": logging.CRITICAL,
    "sentence_transformers": logging.WARNING,
    "urllib3": logging.WARNING,
}


class _ExactLevelFilter(logging.Filter):
    """Allow records for a single exact logging level."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self._level


def _register_trace_level() -> None:
    """Register TRACE level and logger.trace()."""

    if hasattr(logging, "TRACE"):
        return

    logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")
    logging.TRACE = TRACE_LEVEL_NUM  # type: ignore[attr-defined]

    def trace(self: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(TRACE_LEVEL_NUM):
            self._log(TRACE_LEVEL_NUM, message, args, **kwargs)

    logging.Logger.trace = trace  # type: ignore[attr-defined]


def _resolve_level(level_name: str) -> int:
    if level_name == "TRACE":
        return TRACE_LEVEL_NUM
    return getattr(logging, level_name, logging.INFO)


def _build_rotating_handler(path: Path, level: int, exact_level: bool = False) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        filename=path,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    if exact_level:
        handler.addFilter(_ExactLevelFilter(level))
    return handler


def setup_logging(log_level: str = "INFO", log_dir: str = "logs", service_name: str = "minddock") -> None:
    """Configure console and rotating file logging with fixed log locations."""

    _register_trace_level()

    level_name = str(log_level).upper()
    console_level = _resolve_level(level_name)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(TRACE_LEVEL_NUM)

    resolved_log_dir = Path(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    service_slug = service_name.lower()
    trace_log_path = resolved_log_dir / f"{service_slug}.trace.log"
    debug_log_path = resolved_log_dir / f"{service_slug}.debug.log"
    info_log_path = resolved_log_dir / f"{service_slug}.info.log"

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    trace_handler = _build_rotating_handler(trace_log_path, TRACE_LEVEL_NUM, exact_level=True)
    debug_handler = _build_rotating_handler(debug_log_path, logging.DEBUG, exact_level=True)
    info_handler = _build_rotating_handler(info_log_path, logging.INFO)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(trace_handler)
    root_logger.addHandler(debug_handler)
    root_logger.addHandler(info_handler)

    for logger_name, logger_level in _NOISY_LOGGER_LEVELS.items():
        logging.getLogger(logger_name).setLevel(logger_level)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging initialized: console_level=%s log_dir=%s trace_log=%s debug_log=%s info_log=%s",
        level_name,
        resolved_log_dir,
        trace_log_path.name,
        debug_log_path.name,
        info_log_path.name,
    )
