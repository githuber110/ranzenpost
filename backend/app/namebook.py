import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from . import atomic_write
from .store import host_of
from .vocabulary import TOKEN, fold_variants, known_word

FILE_NAME = "namebook.json"
NAME_MARK = "<name>"
MIN_TOKEN = 3
MIN_CLASS_TOKEN = 2
REFRESH_SECONDS = 2.0
SCHOOL_FIELDS = ("school_name", "label", "short_name")
TEACHER_FIELDS = ("label", "surname", "forename", "name")


def _learnable(token, minimum):
    if len(token) < minimum or token.isdigit():
        return False
    return not known_word(token)


def tokens_of(text, minimum=MIN_TOKEN):
    return [token for token in TOKEN.findall(str(text or "")) if _learnable(token, minimum)]


def host_tokens(url):
    labels = host_of(url).split(".")
    return [token for label in labels[:-1] for token in tokens_of(label)]


def connection_names(entry):
    if not isinstance(entry, dict):
        return [], []
    names = []
    classes = []
    for child in entry.get("children") or []:
        if isinstance(child, dict):
            names.append(child.get("name"))
            classes.append(child.get("class_name"))
    for teacher in (entry.get("teachers") or {}).values() if isinstance(entry.get("teachers"), dict) else []:
        if isinstance(teacher, dict):
            names.extend(teacher.get(field) for field in TEACHER_FIELDS)
    names.extend(entry.get(field) for field in SCHOOL_FIELDS)
    return names, classes


def raw_config_names(config_path):
    try:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], [], []
    if not isinstance(raw, dict):
        return [], [], []
    entries = [entry for entry in raw.get("connections") or [] if isinstance(entry, dict)] + [raw]
    names = []
    classes = []
    urls = []
    for entry in entries:
        found, grades = connection_names(entry)
        names.extend(found)
        classes.extend(grades)
        urls.append(entry.get("school_url"))
    return names, classes, urls


class NameBook:
    def __init__(self, path, config_path=None, clock=time.monotonic):
        self.path = Path(path)
        self.config_path = Path(config_path) if config_path else None
        self.clock = clock
        self.lock = threading.RLock()
        self.salt = ""
        self.hashes = set()
        self.cache = {}
        self.config_stamp = None
        self.checked_at = None
        self.refreshing = False
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        salt = data.get("salt") if isinstance(data, dict) else ""
        self.salt = salt if isinstance(salt, str) and len(salt) >= 32 else secrets.token_hex(32)
        listed = data.get("hashes") if isinstance(data, dict) else []
        self.hashes = {entry for entry in listed or [] if isinstance(entry, str)}
        if not isinstance(data, dict) or data.get("salt") != self.salt:
            self._save()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write.write_json(self.path, {"salt": self.salt, "hashes": sorted(self.hashes)})
        except OSError:
            pass

    def _digest(self, variant):
        return hashlib.sha256((self.salt + "\n" + variant).encode("utf-8")).hexdigest()

    def learn_tokens(self, tokens):
        added = False
        with self.lock:
            for token in tokens:
                for variant in fold_variants(token):
                    digest = self._digest(variant)
                    if digest not in self.hashes:
                        self.hashes.add(digest)
                        added = True
            if added:
                self.cache = {}
                self._save()
        return added

    def learn(self, names=(), classes=(), urls=()):
        tokens = []
        for name in names:
            tokens.extend(tokens_of(name))
        for grade in classes:
            tokens.extend(tokens_of(grade, MIN_CLASS_TOKEN))
        for url in urls:
            tokens.extend(host_tokens(url))
        return self.learn_tokens(tokens)

    def knows(self, token):
        folded = token.casefold()
        with self.lock:
            hit = self.cache.get(folded)
            if hit is None:
                hit = len(token) >= MIN_CLASS_TOKEN and not token.isdigit() and any(
                    self._digest(variant) in self.hashes for variant in fold_variants(token)
                )
                self.cache[folded] = hit
        return hit

    def mask(self, text, marker=NAME_MARK):
        if not self.hashes:
            return str(text or "")
        return TOKEN.sub(lambda match: marker if self.knows(match.group(0)) else match.group(0), str(text or ""))

    def refresh_from_config(self):
        if self.config_path is None or self.refreshing:
            return
        now = self.clock()
        if self.checked_at is not None and now - self.checked_at < REFRESH_SECONDS:
            return
        self.checked_at = now
        try:
            stamp = self.config_path.stat().st_mtime_ns
        except OSError:
            return
        if stamp == self.config_stamp:
            return
        self.refreshing = True
        try:
            self.config_stamp = stamp
            names, classes, urls = raw_config_names(self.config_path)
            self.learn(names, classes, urls)
        finally:
            self.refreshing = False

    def learn_store(self, store):
        names = []
        classes = []
        urls = []
        try:
            config = store.load_config()
        except Exception:
            config = {}
        for entry in [entry for entry in config.get("connections") or [] if isinstance(entry, dict)] + [config]:
            found, grades = connection_names(entry)
            names.extend(found)
            classes.extend(grades)
            urls.append(entry.get("school_url"))
            connection_id = entry.get("id")
            if connection_id:
                try:
                    names.append(store.load_secrets(connection_id).get("username"))
                except Exception:
                    continue
        return self.learn(names, classes, urls)

    def scrub(self, text):
        try:
            self.refresh_from_config()
        except Exception:
            pass
        return self.mask(text)


BOOK = None


def install(data_dir, store=None):
    global BOOK
    directory = Path(data_dir)
    BOOK = NameBook(directory / FILE_NAME, directory / "config.json")
    if store is not None:
        BOOK.learn_store(store)
    return BOOK


def current():
    return BOOK


def scrub(text):
    book = BOOK
    return book.scrub(text) if book is not None else str(text or "")
