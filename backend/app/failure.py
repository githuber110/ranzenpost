import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def error_kind(error):
    for name in ("reason", "stage", "message_key"):
        value = getattr(error, name, None)
        if isinstance(value, str) and value:
            return f"{type(error).__name__}/{value}"
    return type(error).__name__


def _app_frame(error):
    frames = traceback.extract_tb(error.__traceback__)
    for frame in reversed(frames):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(APP_DIR):
            return f"{path.relative_to(APP_DIR).as_posix()}:{frame.lineno}"
    return ""


def failure_cause(error):
    where = _app_frame(error)
    return f"{error_kind(error)} at {where}" if where else error_kind(error)
