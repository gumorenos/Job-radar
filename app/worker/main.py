from __future__ import annotations

import logging
import signal
from threading import Event

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import database_is_ready

logger = logging.getLogger(__name__)
_shutdown = Event()


def _request_shutdown(signum: int, _frame: object) -> None:
    logger.info("worker_shutdown_requested signal=%s", signum)
    _shutdown.set()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    logger.info("worker_started")
    database_warning_logged = False

    while not _shutdown.is_set():
        if not database_is_ready():
            if not database_warning_logged:
                logger.error("worker_database_unavailable")
                database_warning_logged = True
        elif database_warning_logged:
            logger.info("worker_database_recovered")
            database_warning_logged = False

        # Phase 2D will replace this heartbeat loop with durable processing_tasks polling.
        _shutdown.wait(settings.worker_poll_interval_seconds)

    logger.info("worker_stopped")


if __name__ == "__main__":
    run()
