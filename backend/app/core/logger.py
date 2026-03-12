"""Structured logging setup."""

import logging
import sys

from app.core.config import settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_initialized = False


def _init_root():
    global _initialized
    if _initialized:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.addHandler(handler)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Initializes root logging on first call."""
    _init_root()
    return logging.getLogger(name)
