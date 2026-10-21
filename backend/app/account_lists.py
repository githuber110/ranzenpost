import logging
import threading

from .failure import error_kind
from .iserv.errors import DataError, OutageError
from .iserv.forums import FORUMS_PATH, ForumShapeError, is_forum_page, parse_forums
from .iserv.infodisplay import INFODISPLAY_PATH, ScreenShapeError, is_infodisplay_page, parse_screens
from .iserv.texts import TEXTS_PATH, TextShapeError, is_text_page, parse_texts
from .iserv.whiteboards import WHITEBOARDS_PATH, WhiteboardShapeError, is_whiteboard_page, parse_whiteboards
from .pathpattern import path_pattern
from .school_lists import CARRY_FIELD, PART_CURRENT, list_extra, module_answer

logger = logging.getLogger(__name__)

FORUMS_FIELD = "forums"
TEXTS_FIELD = "texts"
SCREENS_FIELD = "infodisplay"
WHITEBOARDS_FIELD = "whiteboards"
FILTERS_FIELD = "filters"
MARK_READ_FIELD = "mark_read"
COMPLETE_FIELD = "complete"
FILTER_LIMIT = 8


def read_forums(client):
    response = module_answer(client, FORUMS_PATH, is_forum_page)
    try:
        parsed = parse_forums(getattr(response, "text", "") or "", FORUMS_PATH)
    except ForumShapeError as error:
        raise DataError(str(error), detail={"path": FORUMS_PATH}) from error
    return {FORUMS_FIELD: parsed["forums"], CARRY_FIELD: [], MARK_READ_FIELD: parsed["mark_read"], COMPLETE_FIELD: parsed["complete"]}


def _text_page(client, params=None):
    response = module_answer(client, TEXTS_PATH, is_text_page, params)
    try:
        return parse_texts(getattr(response, "text", "") or "", TEXTS_PATH)
    except TextShapeError as error:
        raise DataError(str(error), detail={"path": TEXTS_PATH}) from error


class TextReader:
    def __init__(self):
        self._lock = threading.Lock()
        self._standard = None
        self._stuck = False

    def read(self, client):
        with self._lock:
            return self._read(client)

    def _read(self, client):
        first = _text_page(client)
        field = first["filter_field"]
        active = next((choice["value"] for choice in first["filters"] if choice["selected"]), None)
        values = [choice["value"] for choice in first["filters"]]
        standard = self._standard if self._stuck and self._standard in values else active
        choices = _kept_choices(first["filters"], {standard, active})
        collected = TextCollection()
        collected.take(first["texts"], active or "")
        carry = []
        restored = True
        try:
            for choice in choices:
                if choice["value"] == active:
                    continue
                try:
                    following = _text_page(client, {field: choice["value"]})
                except (DataError, OutageError) as error:
                    logger.info("text list filter %d unreadable, the texts it adds are kept from earlier: %s", values.index(choice["value"]), error_kind(error))
                    carry = [PART_CURRENT]
                    continue
                collected.take(following["texts"], choice["value"])
        finally:
            if standard is not None and (len(choices) > 1 or standard != active):
                restored = self._restore(client, field, standard)
                self._stuck = not restored
                if restored:
                    self._standard = standard
                elif self._standard is None:
                    self._standard = standard
        filters = [
            {"value": choice["value"], "label": choice["label"], "default": restored and choice["value"] == standard}
            for choice in choices
        ]
        return {TEXTS_FIELD: collected.listed(), CARRY_FIELD: carry, FILTERS_FIELD: filters}

    @staticmethod
    def _restore(client, field, standard):
        try:
            module_answer(client, TEXTS_PATH, is_text_page, {field: standard})
        except Exception as error:
            logger.warning("text list filter not set back at %s: %s", path_pattern(TEXTS_PATH), error_kind(error))
            return False
        return True


class TextCollection:
    def __init__(self):
        self.texts = {}
        self.order = []
        self.member = {}

    def take(self, listed, value):
        for entry in listed:
            if entry["id"] not in self.texts:
                self.texts[entry["id"]] = entry
                self.order.append(entry["id"])
            if value and value not in self.member.get(entry["id"], []):
                self.member.setdefault(entry["id"], []).append(value)

    def listed(self):
        return [dict(self.texts[key], filters=self.member.get(key, [])) for key in self.order]


def _kept_choices(choices, wanted):
    kept = [choice for choice in choices if choice["value"] in wanted]
    for choice in choices:
        if len(kept) >= FILTER_LIMIT:
            break
        if choice not in kept:
            kept.append(choice)
    return [choice for choice in choices if choice in kept]


def read_texts(client):
    return TextReader().read(client)


def read_screens(client):
    response = module_answer(client, INFODISPLAY_PATH, is_infodisplay_page)
    try:
        parsed = parse_screens(getattr(response, "text", "") or "", INFODISPLAY_PATH)
    except ScreenShapeError as error:
        raise DataError(str(error), detail={"path": INFODISPLAY_PATH}) from error
    return {SCREENS_FIELD: parsed["screens"], CARRY_FIELD: []}


def read_whiteboards(client):
    response = module_answer(client, WHITEBOARDS_PATH, is_whiteboard_page)
    try:
        parsed = parse_whiteboards(getattr(response, "text", "") or "", WHITEBOARDS_PATH)
    except WhiteboardShapeError as error:
        raise DataError(str(error), detail={"path": WHITEBOARDS_PATH}) from error
    return {WHITEBOARDS_FIELD: parsed["whiteboards"], CARRY_FIELD: []}


def list_extra_of(listed):
    extra = {}
    if isinstance(listed.get(FILTERS_FIELD), list):
        extra[FILTERS_FIELD] = [dict(entry) for entry in listed[FILTERS_FIELD] if isinstance(entry, dict)]
    if isinstance(listed.get(MARK_READ_FIELD), bool):
        extra[MARK_READ_FIELD] = listed[MARK_READ_FIELD]
    return extra or None


def combined_extra(listed):
    extra = dict(list_extra(listed) or {})
    extra.update(list_extra_of(listed) or {})
    return extra or None


def school_extras(listed):
    found = {}
    filters = listed.get(FILTERS_FIELD) if isinstance(listed, dict) else None
    if isinstance(filters, list):
        found[FILTERS_FIELD] = [dict(entry) for entry in filters if isinstance(entry, dict)]
    mark_read = listed.get(MARK_READ_FIELD) if isinstance(listed, dict) else None
    if isinstance(mark_read, bool):
        found[MARK_READ_FIELD] = mark_read
    return found
