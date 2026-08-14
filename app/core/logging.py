from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure compact application logs without logging request/job payload content."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
