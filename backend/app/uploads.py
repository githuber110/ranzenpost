UPLOAD_FIELD = "files"
FORM_OVERHEAD = 1024 * 1024
LIMIT_COUNT = "count"
LIMIT_FILE = "file"
LIMIT_TOTAL = "total"


class UploadLimitError(Exception):
    def __init__(self, limit):
        super().__init__(limit)
        self.limit = limit


def declared_too_large(request, max_total):
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError:
        return False
    return length > max_total + FORM_OVERHEAD


async def read_uploads(form, max_file, max_total, max_count=None, field=UPLOAD_FIELD):
    files = []
    total = 0
    for upload in form.getlist(field):
        if not hasattr(upload, "read"):
            continue
        if max_count is not None and len(files) >= max_count:
            raise UploadLimitError(LIMIT_COUNT)
        size = getattr(upload, "size", None)
        if isinstance(size, int):
            if size > max_file:
                raise UploadLimitError(LIMIT_FILE)
            if total + size > max_total:
                raise UploadLimitError(LIMIT_TOTAL)
        content = await upload.read(max_file + 1)
        if len(content) > max_file:
            raise UploadLimitError(LIMIT_FILE)
        total += len(content)
        if total > max_total:
            raise UploadLimitError(LIMIT_TOTAL)
        files.append({"filename": upload.filename, "content": content, "content_type": upload.content_type})
    return files
