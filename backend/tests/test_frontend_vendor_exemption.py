import tests.frontend_sources as sources_guard
import tests.test_i18n as i18n_guard
import tests.test_frontend_literals as literal_guard


def write_frontend_tree(tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "vendor" / "pdfjs").mkdir(parents=True)
    (frontend / "other.js").write_text('const label = "Bitte warten";', encoding="utf-8")
    (frontend / "vendor" / "pdfjs" / "bad.js").write_text(
        'const label = "Bitte warten";', encoding="utf-8"
    )
    return frontend


def point_guards_at(monkeypatch, tmp_path, frontend):
    monkeypatch.setattr(sources_guard, "ROOT", tmp_path)
    monkeypatch.setattr(sources_guard, "FRONTEND", frontend)
    monkeypatch.setattr(i18n_guard, "ROOT", tmp_path)
    monkeypatch.setattr(i18n_guard, "FRONTEND", frontend)
    monkeypatch.setattr(literal_guard, "FRONTEND", frontend)


def test_the_i18n_guard_still_catches_a_bad_string_outside_vendor_but_not_inside(
    tmp_path, monkeypatch
):
    frontend = write_frontend_tree(tmp_path)
    point_guards_at(monkeypatch, tmp_path, frontend)

    offenders = i18n_guard.find_hardcoded_german()

    assert any("other.js" in offender for offender in offenders)
    assert all("vendor" not in offender for offender in offenders)


def test_the_literal_guard_exemption_never_reaches_beyond_vendor(tmp_path, monkeypatch):
    frontend = write_frontend_tree(tmp_path)
    point_guards_at(monkeypatch, tmp_path, frontend)

    kept = literal_guard.sources()

    assert frontend / "other.js" in kept
    assert frontend / "vendor" / "pdfjs" / "bad.js" not in kept


def test_a_brand_new_file_is_picked_up_without_anyone_editing_a_list(tmp_path, monkeypatch):
    frontend = write_frontend_tree(tmp_path)
    point_guards_at(monkeypatch, tmp_path, frontend)
    (frontend / "brand_new.js").write_text('const label = "Bitte warten";', encoding="utf-8")

    offenders = i18n_guard.find_hardcoded_german()

    assert any("brand_new.js" in offender for offender in offenders)


def test_only_frontend_vendor_is_named_in_the_exemption_list():
    assert sources_guard.VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert i18n_guard.VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert literal_guard.VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert sources_guard.VENDOR_EXEMPT_REASON.strip()
    assert sources_guard.TEST_TREE_PATHS == ("frontend/tests",)
    assert sources_guard.TEST_TREE_REASON.strip()
