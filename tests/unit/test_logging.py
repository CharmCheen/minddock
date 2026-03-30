import logging
from pathlib import Path

from app.core.logging import TRACE_LEVEL_NUM, setup_logging


def test_setup_logging_creates_fixed_level_log_files(tmp_path: Path) -> None:
    setup_logging(log_level="DEBUG", log_dir=str(tmp_path), service_name="MindDock")

    logger = logging.getLogger("tests.logging")
    logger.trace("trace message")  # type: ignore[attr-defined]
    logger.debug("debug message")
    logger.info("info message")

    for handler in logging.getLogger().handlers:
        handler.flush()

    trace_log = tmp_path / "minddock.trace.log"
    debug_log = tmp_path / "minddock.debug.log"
    info_log = tmp_path / "minddock.info.log"

    assert trace_log.exists()
    assert debug_log.exists()
    assert info_log.exists()

    assert "trace message" in trace_log.read_text(encoding="utf-8")
    assert "debug message" in debug_log.read_text(encoding="utf-8")
    assert "info message" in info_log.read_text(encoding="utf-8")
    assert logging.getLevelName(TRACE_LEVEL_NUM) == "TRACE"
