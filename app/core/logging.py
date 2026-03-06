"""Logging configuration for the API service."""

import logging


_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger to print logs to console."""

    level_name = str(log_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        force=True,
    )

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized", extra={"configured_level": level_name})
