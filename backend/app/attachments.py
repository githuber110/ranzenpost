import re

from .iserv.errors import DataError

PINBOARD_ATTACHMENT_URL = "api/pinboard/attachment/{filename}?connection={connection}"
ABSENCE_ATTACHMENT_URL = "api/absences/attachment/{filename}?connection={connection}"
LETTERS_ATTACHMENT_URL = "api/letters/attachment/{attachment}?connection={connection}"
SAFE_FILENAME = re.compile(r"^[^\x00-\x1f/\\]{1,120}$")


def _clean_filename(value):
    value = (value or "").strip()
    if ".." in value or "/" in value or not SAFE_FILENAME.match(value):
        raise DataError("invalid filename")
    return value


def _attachment_file(attachment):
    candidate = (getattr(attachment, "file", "") or attachment.filename or "").strip()
    if ".." in candidate or not SAFE_FILENAME.match(candidate):
        return ""
    return candidate


def _absence_attachment_url(file_name, connection_id):
    file_name = (file_name or "").strip()
    if ".." in file_name or not SAFE_FILENAME.match(file_name):
        return ""
    return ABSENCE_ATTACHMENT_URL.format(filename=file_name, connection=connection_id)


def _attachment_dict(attachment, connection_id):
    file_name = _attachment_file(attachment)
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "extension": attachment.extension,
        "mimetype": attachment.mimetype,
        "size": attachment.size,
        "file": file_name,
        "url": PINBOARD_ATTACHMENT_URL.format(filename=file_name, connection=connection_id) if file_name else "",
        "created_at": attachment.created_at,
        "updated_at": attachment.updated_at,
        "image_width": attachment.image_width,
        "image_height": attachment.image_height,
    }
