import logging
import os


_LOGGER = None


def get_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger("ai-brain-service")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)

    logger.propagate = False
    _LOGGER = logger
    return logger
