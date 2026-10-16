import threading
import time

from . import school_lists
from .iserv.errors import DataError

SECTION_SECONDS = 600
SECTION_UNKNOWN_KEY = "api.news.sectionUnknown"
ITEM_UNKNOWN_KEY = "api.news.itemUnknown"


class NewsSections:
    def __init__(self, connection):
        self.connection = connection
        self._lock = threading.Lock()
        self._cache = {}

    def _now(self):
        return float(getattr(self.connection, "clock", time.time)())

    def linked(self):
        stored = school_lists.stored_list(self.connection.store, self.connection.id, school_lists.NEWS_FIELD) or {}
        sections = stored.get(school_lists.SECTIONS_FIELD)
        if not isinstance(sections, dict):
            return {}
        return {name: str(path) for name, path in sections.items() if name in school_lists.NEWS_SECTIONS and isinstance(path, str)}

    def _cached(self, section, path):
        with self._lock:
            cached = self._cache.get(section)
        if cached and cached["path"] == path and self._now() - cached["at"] < SECTION_SECONDS:
            return cached["items"]
        return None

    def items(self, section):
        path = self.linked().get(section)
        if not path:
            raise DataError("the news section is not linked", message_key=SECTION_UNKNOWN_KEY)
        cached = self._cached(section, path)
        if cached is not None:
            return cached
        items = school_lists.read_news_section(self.connection._session(), path, section)
        with self._lock:
            earlier = self._cache.get(section) or {}
            known = {str(item.get("id")): item for item in earlier.get("items") or []}
            for item in items:
                before = known.get(str(item.get("id")))
                if before and isinstance(before.get("detail"), dict) and school_lists.same_entry(before, item):
                    item["detail"] = before["detail"]
            self._cache[section] = {"path": path, "at": self._now(), "items": items}
        return items

    def _item(self, section, item_id):
        for item in self.items(section):
            if str(item.get("id")) == str(item_id):
                return item
        raise DataError("the news item is not listed", message_key=ITEM_UNKNOWN_KEY)

    def detail(self, section, item_id):
        item = self._item(section, item_id)
        school_url = self.connection.store.load_config().get("school_url", "")
        detail = school_lists.read_news_detail(self.connection._session(), school_url, item.get("path") or "", item.get("title") or "")
        with self._lock:
            item["detail"] = detail
        return detail

    def file_path(self, section, item_id, kind, index):
        with self._lock:
            cached = self._cache.get(section) or {}
            items = list(cached.get("items") or [])
        return school_lists.news_file_path(items, item_id, kind, index)
