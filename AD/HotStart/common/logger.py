from __future__ import annotations

import logging
import sys

# Les logs AD utilisent des séparateurs box-drawing ("═", "─") — absents de cp1252,
# l'encodage par défaut d'une console Windows. Sans ceci, chaque ligne qui en contient
# lève UnicodeEncodeError (capturée par logging mais silencieusement perdue). On force
# l'UTF-8 une fois ici plutôt que dans chaque module appelant.
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def get_logger(name: str) -> logging.Logger:
    """
    Returns a module-level logger with a consistent format.
    Safe to call multiple times — handlers are registered only once.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt     = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
                datefmt = "%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
