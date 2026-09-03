import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import messages

BUNDLE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "i18n"
LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")

CLDR_CARDINAL_CATEGORIES = {
    language: set(categories)
    for language, categories in messages.CLDR_CARDINAL_CATEGORIES.items()
}

PLURAL_CATEGORY_DEBT = {}


def load_bundle(language):
    return json.loads((BUNDLE_DIR / f"{language}.json").read_text(encoding="utf-8"))


def counted_families(bundle):
    grouped = {}
    for key, value in bundle.items():
        head, _, tail = key.rpartition(".")
        if head and tail in PLURAL_CATEGORIES:
            grouped.setdefault(head, {})[tail] = value
    families = {}
    for family, members in grouped.items():
        categories = set(members)
        carries_count = any("{count}" in value for value in members.values())
        if carries_count or categories - {"other"}:
            families[family] = categories
    return families


def missing_categories(language):
    required = CLDR_CARDINAL_CATEGORIES[language]
    gaps = {}
    for family, categories in counted_families(load_bundle(language)).items():
        absent = required - categories
        if absent:
            gaps[family] = absent
    return gaps


def debt_for(language):
    return PLURAL_CATEGORY_DEBT.get(language, {})


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_shipped_language_has_a_cldr_category_set(language):
    assert language in CLDR_CARDINAL_CATEGORIES, (
        f"{language} has no CLDR cardinal category set - read it from "
        f"Intl.PluralRules('{language}').resolvedOptions().pluralCategories and add it"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_counted_keys_carry_every_category_the_language_demands(language):
    gaps = missing_categories(language)
    known = debt_for(language)
    unlisted = {
        family: sorted(absent)
        for family, absent in gaps.items()
        if absent - known.get(family, set())
    }
    assert unlisted == {}, (
        f"{language}.json: these counted keys lack plural categories that "
        f"Intl.PluralRules demands: {unlisted}"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_plural_debt_list_holds_no_entry_that_is_already_paid(language):
    gaps = missing_categories(language)
    stale = {
        family: sorted(categories - gaps.get(family, set()))
        for family, categories in debt_for(language).items()
        if categories - gaps.get(family, set())
    }
    assert stale == {}, (
        f"{language}.json now carries these forms - delete them from "
        f"PLURAL_CATEGORY_DEBT in backend/tests/test_i18n_plurals.py: {stale}"
    )


def test_the_debt_list_names_no_language_and_no_family_that_does_not_exist():
    unknown_languages = sorted(set(PLURAL_CATEGORY_DEBT) - set(LANGUAGES))
    assert unknown_languages == []
    for language, families in PLURAL_CATEGORY_DEBT.items():
        present = set(counted_families(load_bundle(language)))
        assert sorted(set(families) - present) == [], f"{language}: debt names unknown families"


def test_a_planted_gap_turns_the_guard_red():
    bundle = {"letters.count.other": "{count} letters"}
    families = counted_families(bundle)
    assert families == {"letters.count": {"other"}}
    assert CLDR_CARDINAL_CATEGORIES["ru"] - families["letters.count"] == {"one", "few", "many"}


def test_a_key_group_without_counting_is_not_mistaken_for_a_plural_family():
    bundle = {
        "settings.notify.category.other": "Weitere Dienste",
        "settings.notify.category.group": "An alle Geraete",
    }
    assert counted_families(bundle) == {}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_backend_only_ever_picks_a_category_the_language_defines(language):
    picked = {messages.plural_category(language, count) for count in range(0, 210)}
    picked |= {messages.plural_category(language, count) for count in (1000, 1001, 1002, 1011)}
    assert picked <= CLDR_CARDINAL_CATEGORIES[language]


def test_the_backend_plural_picker_follows_the_cldr_rules():
    assert [messages.plural_category("de", n) for n in (0, 1, 2, 11)] == [
        "other", "one", "other", "other"
    ]
    assert [messages.plural_category("ar", n) for n in (0, 1, 2, 3, 11, 100, 103)] == [
        "zero", "one", "two", "few", "many", "other", "few"
    ]
    assert [messages.plural_category("ru", n) for n in (1, 2, 5, 11, 21, 22, 25, 111)] == [
        "one", "few", "many", "many", "one", "few", "many", "many"
    ]
    assert [messages.plural_category("uk", n) for n in (1, 3, 14, 32)] == [
        "one", "few", "many", "few"
    ]


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_notification_family_renders_in_every_category(language):
    for family in (
        "notify.letters.new",
        "notify.pinboard.new",
        "notify.conferences.new",
        "notify.timetable.changes",
    ):
        for count in range(0, 130):
            rendered = messages.text_count(language, family, count, {"name": "Alex"})
            assert rendered and not rendered.startswith(family), (
                f"{language}:{family} has no form for {count}"
            )
            assert "{" not in rendered, f"{language}:{family}.{count} keeps a placeholder"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_the_cldr_table_matches_intl_pluralrules():
    script = (
        "const out={};"
        f"for (const l of {json.dumps(list(LANGUAGES))})"
        " out[l]=new Intl.PluralRules(l).resolvedOptions().pluralCategories;"
        "console.log(JSON.stringify(out));"
    )
    completed = subprocess.run(
        [shutil.which("node"), "-e", script], capture_output=True, text=True, timeout=60
    )
    assert completed.returncode == 0, completed.stderr
    from_runtime = {
        language: set(categories)
        for language, categories in json.loads(completed.stdout).items()
    }
    assert from_runtime == {
        language: CLDR_CARDINAL_CATEGORIES[language] for language in LANGUAGES
    }
