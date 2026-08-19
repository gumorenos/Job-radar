from __future__ import annotations

import logging
import os
import signal
import socket
from threading import Event

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.domains.notifications.delivery import enqueue_due_telegram_notifications
from app.worker.tasks import claim_next_task, execute_task, fail_task, recover_stale_tasks

logger = logging.getLogger(__name__)
_shutdown = Event()


def _request_shutdown(signum: int, _frame: object) -> None:
    logger.info("worker_shutdown_requested signal=%s", signum)
    _shutdown.set()


def run() -> None:
    settings = get_settings()
    settings.validate_runtime()
    configure_logging(settings.log_level)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"

    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    with get_session_factory()() as session:
        recovered = recover_stale_tasks(session, settings.worker_stale_task_seconds)
    logger.info("worker_started worker_id=%s recovered_stale_tasks=%s", worker_id, recovered)

    while not _shutdown.is_set():
        if settings.telegram_enabled:
            with get_session_factory()() as notification_session:
                enqueued = enqueue_due_telegram_notifications(notification_session)
            if enqueued:
                logger.info("worker_notifications_enqueued count=%s", enqueued)

        with get_session_factory()() as claim_session:
            claimed = claim_next_task(claim_session, worker_id)

        if claimed is None:
            _shutdown.wait(settings.worker_poll_interval_seconds)
            continue

        try:
            with get_session_factory()() as work_session:
                execute_task(work_session, claimed)
            logger.info(
                "worker_task_completed task_id=%s task_type=%s entity_id=%s",
                claimed.id,
                claimed.task_type,
                claimed.entity_id,
            )
        except Exception as exc:
            logger.exception(
                "worker_task_failed task_id=%s task_type=%s entity_id=%s",
                claimed.id,
                claimed.task_type,
                claimed.entity_id,
            )
            with get_session_factory()() as failure_session:
                fail_task(failure_session, claimed, exc)

    logger.info("worker_stopped worker_id=%s", worker_id)


if __name__ == "__main__":
    run()
