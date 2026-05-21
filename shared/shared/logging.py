"""Loguru setup. JSON in prod, pretty in dev."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    logger.remove()
    if fmt == "json":
        logger.add(sys.stderr, level=level, serialize=True, backtrace=False, diagnose=False)
    else:
        logger.add(sys.stderr, level=level, backtrace=True, diagnose=True)
