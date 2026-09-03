import re
from pathlib import Path

from tests.test_i18n import GERMAN_LETTERS, GERMAN_WORD_PATTERN, STRING_LITERAL

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"

NOTIFICATION_WORDS = (
    "anmeldung", "ansehen", "ausfall", "beitrag", "elternbrief", "elternbriefe",
    "elternsprechtag", "krankmeldung", "neue", "neuer", "neues", "pinnwand",
    "stundenplan", "vertretung",
)
NOTIFICATION_WORD_PATTERN = re.compile(
    r"(?<![\w])(" + "|".join(NOTIFICATION_WORDS) + r")(?![\w])", re.IGNORECASE
)

GERMAN_HAYSTACK_MODULES = {
    "twofactor.py": "matches IServ's own German pages, never shown to the user",
    "lockout.py": "matches IServ's own German pages, never shown to the user",
    "conferences.py": "matches IServ's own German pages, never shown to the user",
    "holidays.py": "region names and transliteration for the public holiday feeds",
    "sick_note_pdf.py": "the sick note is a German letter handed in at a German school",
}

TRANSLITERATION_LITERALS = {'"ä"', '"ö"', '"ü"', '"ß"', "'ä'", "'ö'", "'ü'", "'ß'"}

GERMAN_HAYSTACK_LITERALS = {
    ("client.py", '"Anmeldung fehlgeschlagen"'): "marker text on IServ's own login page",
    ("iserv_prober.py", '"Anmeldung fehlgeschlagen"'): "marker text on IServ's own login page",
    ("timetable.py", '"ausfall"'): "IServ change-kind token in the timetable JSON",
}

GERMAN_TEXT_DEBT = {}


def modules():
    return sorted(
        path
        for path in BACKEND_APP.rglob("*.py")
        if path.name not in GERMAN_HAYSTACK_MODULES
    )


def german_literals_in(text):
    found = []
    for match in STRING_LITERAL.finditer(text):
        literal = match.group(0)
        if literal in TRANSLITERATION_LITERALS:
            continue
        body = literal[1:-1]
        if (
            GERMAN_LETTERS.search(body)
            or GERMAN_WORD_PATTERN.search(body)
            or NOTIFICATION_WORD_PATTERN.search(body)
        ):
            found.append((literal, text.count("\n", 0, match.start()) + 1))
    return found


def scan():
    found = {}
    for path in modules():
        for literal, _line in german_literals_in(path.read_text(encoding="utf-8")):
            key = (path.name, literal)
            if key in GERMAN_HAYSTACK_LITERALS:
                continue
            found[key] = found.get(key, 0) + 1
    return found


def test_no_new_german_user_text_enters_the_backend():
    found = scan()
    offenders = []
    for key in sorted(found):
        allowed = GERMAN_TEXT_DEBT.get(key, 0)
        if found[key] > allowed:
            offenders.append(f"{key[0]}: {key[1][:80]}")
    assert offenders == [], (
        "backend text that reaches the user goes through messages.text_in(language, key) - "
        f"a German literal in the code cannot follow the language choice: {offenders}"
    )


def test_the_german_text_debt_list_holds_no_entry_that_is_already_paid():
    found = scan()
    stale = [
        f"{key[0]}: {key[1][:80]}"
        for key in sorted(GERMAN_TEXT_DEBT)
        if found.get(key, 0) < GERMAN_TEXT_DEBT[key]
    ]
    assert stale == [], (
        "delete these lines from GERMAN_TEXT_DEBT in "
        f"backend/tests/test_i18n_backend.py: {stale}"
    )


def test_every_skipped_module_still_exists_and_carries_a_reason():
    names = {path.name for path in BACKEND_APP.rglob("*.py")}
    for name, reason in GERMAN_HAYSTACK_MODULES.items():
        assert name in names, f"{name} is no longer part of the backend"
        assert reason.strip()
    for (name, literal), reason in GERMAN_HAYSTACK_LITERALS.items():
        assert name in names, f"{name} is no longer part of the backend"
        assert reason.strip()
        assert literal.strip()


def test_the_backend_tripwire_still_catches_a_planted_notification():
    planted = 'MESSAGE = "Neue Elternbriefe warten in der App"\n'
    assert german_literals_in(planted)
    assert german_literals_in('URL = "api/letters"') == []
    assert german_literals_in('KEY = "notify.letters.new"') == []
