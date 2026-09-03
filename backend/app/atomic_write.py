import json
import os
import uuid
from pathlib import Path

TEMP_SUFFIX = ".tmp"
PRIVATE_MODE = 0o600


def temp_path_for(path):
    target = Path(path)
    return target.with_name(f"{target.name}.{uuid.uuid4().hex}{TEMP_SUFFIX}")


def _sync_directory(directory):
    flags = getattr(os, "O_DIRECTORY", None)
    if flags is None:
        return
    try:
        descriptor = os.open(str(directory), flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _discard(temp):
    try:
        os.unlink(str(temp))
    except OSError:
        pass


def write_bytes(path, payload, mode=PRIVATE_MODE):
    target = Path(path)
    temp = temp_path_for(target)
    descriptor = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp), str(target))
    except BaseException:
        _discard(temp)
        raise
    _sync_directory(target.parent)


def write_text(path, text, encoding="utf-8", mode=PRIVATE_MODE):
    write_bytes(path, text.encode(encoding), mode)


def write_json(path, data, mode=PRIVATE_MODE):
    write_bytes(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), mode)


def clear_stale_temp_files(directory):
    folder = Path(directory)
    if not folder.is_dir():
        return
    for candidate in folder.glob(f"*{TEMP_SUFFIX}"):
        if candidate.is_file():
            _discard(candidate)
