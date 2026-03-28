from typing import Any, Callable

from app.exceptions import APIException


def safe_execute(fn: Callable[[], Any], fallback: Any = None, context: str = "operation"):
    try:
        return fn()
    except APIException:
        raise
    except Exception:
        return fallback
