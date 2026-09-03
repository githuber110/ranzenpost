import json
import os
from pathlib import Path

BASE_LANGUAGE = "de"
LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
BASE_FILE = f"{BASE_LANGUAGE}.json"

CLDR_CARDINAL_CATEGORIES = {
    "de": frozenset({"one", "other"}),
    "en": frozenset({"one", "other"}),
    "ar": frozenset({"zero", "one", "two", "few", "many", "other"}),
    "tr": frozenset({"one", "other"}),
    "ru": frozenset({"one", "few", "many", "other"}),
    "uk": frozenset({"one", "few", "many", "other"}),
}


def _candidates(filename):
    override = os.environ.get("ISERV_FRONTEND_DIR")
    if override:
        yield Path(override) / "i18n" / filename
    for parent in Path(__file__).resolve().parents:
        yield parent / "frontend" / "i18n" / filename


def _load(filename=BASE_FILE):
    for candidate in _candidates(filename):
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


BASE_MESSAGES = _load()
_BUNDLES = {BASE_LANGUAGE: BASE_MESSAGES}


def normalize_language(value):
    tag = str(value or "").strip().lower().split("-")[0]
    return tag if tag in LANGUAGES else BASE_LANGUAGE


def bundle(language):
    tag = normalize_language(language)
    if tag not in _BUNDLES:
        _BUNDLES[tag] = _load(f"{tag}.json")
    return _BUNDLES[tag]


def _render(template, variables):
    if not variables:
        return template
    rendered = template
    for name, value in variables.items():
        rendered = rendered.replace("{" + name + "}", str(value))
    return rendered


def text(key, variables=None):
    template = BASE_MESSAGES.get(key)
    if template is None:
        return key
    return _render(template, variables)


def text_in(language, key, variables=None):
    template = bundle(language).get(key)
    if template is None:
        return text(key, variables)
    return _render(template, variables)


def plural_category(language, count):
    tag = normalize_language(language)
    try:
        number = abs(int(count))
    except (TypeError, ValueError):
        return "other"
    if tag == "ar":
        remainder = number % 100
        if number == 0:
            return "zero"
        if number == 1:
            return "one"
        if number == 2:
            return "two"
        if 3 <= remainder <= 10:
            return "few"
        if 11 <= remainder <= 99:
            return "many"
        return "other"
    if tag in ("ru", "uk"):
        last, remainder = number % 10, number % 100
        if last == 1 and remainder != 11:
            return "one"
        if 2 <= last <= 4 and not 12 <= remainder <= 14:
            return "few"
        return "many"
    return "one" if number == 1 else "other"


def _known(tag, key):
    return bundle(tag).get(key) is not None or BASE_MESSAGES.get(key) is not None


def text_count(language, key, count, variables=None):
    tag = normalize_language(language)
    merged = dict(variables or {})
    merged["count"] = count
    candidate = f"{key}.{plural_category(tag, count)}"
    if not _known(tag, candidate):
        candidate = f"{key}.other"
    return text_in(tag, candidate, merged)


def payload(key, variables=None):
    body = {"message_key": key, "message": text(key, variables)}
    if variables:
        body["message_vars"] = dict(variables)
    return body


def result(ok, key, variables=None, **extra):
    body = {"ok": ok}
    body.update(payload(key, variables))
    body.update(extra)
    return body
