"""Logging setup for the runtime."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("auto_check_in")


def setup_logging(debug: bool = False) -> None:
    level = "DEBUG" if debug else os.getenv("CHECK_IN_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
