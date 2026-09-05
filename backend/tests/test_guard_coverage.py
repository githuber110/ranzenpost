import tests.test_frontend_error_handling as error_guard
import tests.test_frontend_literals as literal_guard
import tests.test_i18n as i18n_guard
from tests.frontend_sources import (
    FRONTEND,
    GUARDED_SUFFIXES,
    MARKUP_SUFFIXES,
    SCRIPT_SUFFIXES,
    STYLE_SUFFIXES,
    TEST_TREE_PATHS,
    TEST_TREE_REASON,
    VENDOR_EXEMPT_PATHS,
    VENDOR_EXEMPT_REASON,
    is_shipped,
    shipped_names,
    shipped_paths,
)

MARKUP_GUARD_NAMES = ("index.html",)

PLANTED_GERMAN_STRING = '\nconst plantedGuardCoverageCheck = "Bitte pruefen Sie dieses Passwort";\n'
PLANTED_PHYSICAL_RULE = "\n.planted-guard-coverage-check { margin-left: 4px; }\n"
PLANTED_EMPTY_CATCH = "\ntry { plantedGuardCoverageCheck(); } catch (error) {}\n"


def _css_has_undirected_physical_rule(text):
    for match in i18n_guard.PHYSICAL_PROPERTY.finditer(text):
        token = " ".join(match.group(0).split())
        selector = i18n_guard.rule_selector(text, match.start())
        if i18n_guard.CENTERED_OFFSET.match(token) and any(
            bar in selector for bar in i18n_guard.CENTERED_BARS
        ):
            continue
        return True
    return False


def script_is_watched_by_a_real_guard(text):
    if i18n_guard.hardcoded_german(text + PLANTED_GERMAN_STRING):
        return True
    if error_guard.empty_catches_in(text + PLANTED_EMPTY_CATCH):
        return True
    return False


def stylesheet_is_watched_by_a_real_guard(text):
    return _css_has_undirected_physical_rule(text + PLANTED_PHYSICAL_RULE)


def test_every_shipped_frontend_file_is_watched_by_at_least_one_guard():
    unwatched_scripts = [
        name
        for name in shipped_names(SCRIPT_SUFFIXES)
        if not script_is_watched_by_a_real_guard((FRONTEND / name).read_text(encoding="utf-8"))
    ]
    unwatched_styles = [
        name
        for name in shipped_names(STYLE_SUFFIXES)
        if not stylesheet_is_watched_by_a_real_guard((FRONTEND / name).read_text(encoding="utf-8"))
    ]
    uncovered_markup = sorted(set(shipped_names(MARKUP_SUFFIXES)) - set(MARKUP_GUARD_NAMES))
    uncovered = sorted(unwatched_scripts) + sorted(unwatched_styles) + uncovered_markup
    assert uncovered == [], (
        "a shipped frontend file that no guard's real detector reacts to even after a "
        "violation is planted into its content is a silent blind spot - the German, "
        f"comment and logical-property rules simply stop applying to it: {uncovered}"
    )


def test_the_guards_read_files_by_glob_and_not_from_a_hand_kept_list():
    for name in ("SCANNED_FILES", "JS_SOURCES", "STYLESHEETS"):
        assert callable(getattr(i18n_guard, name)), f"{name} must stay a glob, not a frozen tuple"
    assert callable(literal_guard.SOURCES)


def test_the_globs_actually_find_the_files_that_exist_today():
    scripts = set(i18n_guard.SCANNED_FILES())
    styles = set(i18n_guard.STYLESHEETS())
    assert {"app.js", "wizard.js", "steps.js", "qr.js", "bootdir.js", "pdfviewer.js"} <= scripts
    assert {"styles.css", "wizard.css", "pdfviewer.css"} <= styles
    assert set(shipped_names(MARKUP_SUFFIXES)) == {"index.html"}


def test_a_file_planted_next_to_the_others_would_be_seen(tmp_path, monkeypatch):
    import tests.frontend_sources as sources_guard

    frontend = tmp_path / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "fresh.js").write_text("const a = 1;\n", encoding="utf-8")
    (frontend / "fresh.css").write_text(".a { color: red; }\n", encoding="utf-8")
    monkeypatch.setattr(sources_guard, "ROOT", tmp_path)
    monkeypatch.setattr(sources_guard, "FRONTEND", frontend)
    assert set(sources_guard.script_names()) == {"fresh.js"}
    assert set(sources_guard.stylesheet_names()) == {"fresh.css"}


def test_the_two_exemptions_are_named_and_reasoned_in_code_not_in_a_comment():
    assert VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert TEST_TREE_PATHS == ("frontend/tests",)
    assert len(VENDOR_EXEMPT_REASON.split()) >= 8
    assert len(TEST_TREE_REASON.split()) >= 8
    assert not is_shipped(FRONTEND / "vendor" / "pdfjs" / "pdf.mjs")
    assert not is_shipped(FRONTEND / "tests" / "loadApp.js")
    assert is_shipped(FRONTEND / "app.js")


def test_the_guarded_suffixes_cover_script_style_and_markup():
    assert set(GUARDED_SUFFIXES) == set(SCRIPT_SUFFIXES) | set(STYLE_SUFFIXES) | set(MARKUP_SUFFIXES)
    assert shipped_paths(SCRIPT_SUFFIXES)
    assert shipped_paths(STYLE_SUFFIXES)
    assert shipped_paths(MARKUP_SUFFIXES)
