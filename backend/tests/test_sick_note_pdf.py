import json
import unicodedata
from datetime import date
from pathlib import Path

import pytest

from app.iserv.sick_note_pdf import (
    FONT_DIR,
    FONT_FILES,
    UnsupportedTextError,
    font_for,
    render_sick_note_pdf,
    sick_note_pdf_filename,
    sick_note_period_description,
    sick_note_title,
)
from app.iserv.truetype import TrueTypeFont
from tests.pdf_reader import font_programs, text_runs, visible_text

TITLE = "Schriftliche Bestätigung der Krankmeldung"
FOREIGN_NAMES = ("Şahin", "Софія", "Nguyễn", "Łukasz", "Παπαδόπουλος", "Björn Müller-Weiß")
UNRENDERABLE_NAMES = ("أمينة", "אברהם", "अमीना")
REPLACEMENT_MARKERS = ("?", "�", "□")


def test_single_day_same_period():
    assert sick_note_period_description("2026-09-01", "2026-09-01", 1, 1) == (
        "am Dienstag, den 01.09.2026, in der 1. Stunde"
    )


def test_single_day_different_periods():
    assert sick_note_period_description("2026-09-01", "2026-09-01", 1, 3) == (
        "am Dienstag, den 01.09.2026, von der 1. bis einschließlich der 3. Stunde"
    )


def test_single_day_only_from_period():
    assert sick_note_period_description("2026-09-01", "2026-09-01", 1, None) == (
        "am Dienstag, den 01.09.2026, ab der 1. Stunde"
    )


def test_single_day_only_till_period():
    assert sick_note_period_description("2026-09-01", "2026-09-01", None, 3) == (
        "am Dienstag, den 01.09.2026, bis einschließlich der 3. Stunde"
    )


def test_single_day_no_periods():
    assert sick_note_period_description("2026-09-01", "2026-09-01", None, None) == (
        "am Dienstag, den 01.09.2026"
    )


def test_single_day_falls_back_when_till_date_missing():
    assert sick_note_period_description("2026-09-01", "", None, None) == (
        "am Dienstag, den 01.09.2026"
    )


def test_multi_day_no_periods():
    assert sick_note_period_description("2026-09-01", "2026-09-03", None, None) == (
        "vom Dienstag, den 01.09.2026 bis Donnerstag, den 03.09.2026"
    )


def test_multi_day_only_from_period():
    assert sick_note_period_description("2026-09-01", "2026-09-03", 1, None) == (
        "vom Dienstag, den 01.09.2026, ab der 1. Stunde bis Donnerstag, den 03.09.2026"
    )


def test_multi_day_only_till_period():
    assert sick_note_period_description("2026-09-01", "2026-09-03", None, 3) == (
        "vom Dienstag, den 01.09.2026 bis Donnerstag, den 03.09.2026, "
        "bis einschließlich der 3. Stunde"
    )


def test_multi_day_both_periods():
    assert sick_note_period_description("2026-09-01", "2026-09-03", 1, 3) == (
        "vom Dienstag, den 01.09.2026, ab der 1. Stunde bis Donnerstag, den 03.09.2026, "
        "bis einschließlich der 3. Stunde"
    )


def test_no_from_date_returns_empty_text():
    assert sick_note_period_description("", "", None, None) == ""


def test_title_uses_default_term_when_school_has_no_replace_term():
    assert sick_note_title({}) == "Schriftliche Bestätigung der Krankmeldung"


def test_title_respects_school_replace_term():
    assert sick_note_title({"sickNotes_replaceTerm": "Fehlzeitenmeldung"}) == (
        "Schriftliche Bestätigung der Fehlzeitenmeldung"
    )


def test_filename_matches_documented_pattern():
    filename = sick_note_pdf_filename(
        "Schriftliche Bestätigung der Krankmeldung", "Mia Müller", today=date(2026, 9, 2)
    )
    assert filename == "Schriftliche Bestätigung der Krankmeldung [Mia Müller] [02.09.2026].pdf"


@pytest.mark.parametrize("name", FOREIGN_NAMES + UNRENDERABLE_NAMES)
def test_filename_keeps_foreign_names_unchanged(name):
    filename = sick_note_pdf_filename(TITLE, name, today=date(2026, 9, 2))
    assert filename == f"{TITLE} [{name}] [02.09.2026].pdf"
    assert not any(marker in filename for marker in REPLACEMENT_MARKERS if marker != "?")


def test_filename_drops_path_separators_and_control_characters():
    raw = "Mia" + chr(13) + chr(10) + "/Sophie" + chr(92) + "Müller:*?"
    filename = sick_note_pdf_filename(TITLE, raw, today=date(2026, 9, 2))
    assert filename == f"{TITLE} [Mia Sophie Müller] [02.09.2026].pdf"


def test_render_sick_note_pdf_produces_valid_pdf_bytes():
    pdf_bytes = render_sick_note_pdf(
        "Schriftliche Bestätigung der Krankmeldung",
        "Mia Müller",
        "5A",
        "2026-09-01",
        "2026-09-01",
        1,
        3,
        today=date(2026, 9, 2),
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")


def test_render_sick_note_pdf_puts_umlauts_into_the_document_text():
    pdf_bytes = render_sick_note_pdf(
        TITLE,
        "Björn Müller-Weiß",
        "",
        "2026-09-01",
        "2026-09-01",
        None,
        None,
    )
    assert pdf_bytes.startswith(b"%PDF")
    text = visible_text(pdf_bytes)
    assert "Björn Müller-Weiß" in text
    assert "Schriftliche Bestätigung der Krankmeldung" in text
    assert "Mit freundlichen Grüßen" in text
    assert not any(marker in text for marker in REPLACEMENT_MARKERS)


@pytest.mark.parametrize("name", FOREIGN_NAMES)
def test_render_sick_note_pdf_carries_foreign_names_into_the_document(name):
    pdf_bytes = render_sick_note_pdf(TITLE, name, "5A", "2026-09-01", "2026-09-01", 1, 3)
    text = visible_text(pdf_bytes)
    assert name in text
    assert not any(marker in text for marker in REPLACEMENT_MARKERS)
    assert all(ord(char) != 0xFFFD for char in text)


def test_render_sick_note_pdf_keeps_every_foreign_character_in_one_document():
    name = " ".join(FOREIGN_NAMES)
    pdf_bytes = render_sick_note_pdf(TITLE, name, "5A", "2026-09-01", "2026-09-01", None, None)
    text = visible_text(pdf_bytes)
    for character in set(name.replace(" ", "")):
        assert character in text


def test_render_sick_note_pdf_writes_no_replacement_byte_into_the_content_stream():
    pdf_bytes = render_sick_note_pdf(TITLE, "Şahin Софія", "5A", "2026-09-01", "2026-09-01")
    for _, _, _, _, text in text_runs(pdf_bytes):
        assert "?" not in text
        assert "�" not in text


def test_render_sick_note_pdf_embeds_a_subset_font_program_per_used_face():
    pdf_bytes = render_sick_note_pdf(TITLE, "Софія", "5A", "2026-09-01", "2026-09-01")
    programs = font_programs(pdf_bytes)
    assert set(programs) == {"F1", "F2"}
    for length1, data in programs.values():
        assert length1 == len(data)
        embedded = TrueTypeFont(data)
        assert embedded.num_glyphs < 200
        assert embedded.cmap
    assert len(pdf_bytes) < 40000


@pytest.mark.parametrize("name", UNRENDERABLE_NAMES)
def test_render_sick_note_pdf_refuses_scripts_it_cannot_shape(name):
    with pytest.raises(UnsupportedTextError) as raised:
        render_sick_note_pdf(TITLE, name, "", "2026-09-01", "2026-09-01")
    assert raised.value.characters
    assert set(raised.value.characters) <= set(name)


def test_render_sick_note_pdf_refuses_a_school_term_it_cannot_render():
    with pytest.raises(UnsupportedTextError):
        render_sick_note_pdf(
            sick_note_title({"sickNotes_replaceTerm": "إشعار"}),
            "Mia Müller",
            "",
            "2026-09-01",
            "2026-09-01",
        )


def test_render_sick_note_pdf_normalizes_decomposed_input():
    decomposed = unicodedata.normalize("NFD", "Nguyễn Thị Hạnh")
    assert decomposed != "Nguyễn Thị Hạnh"
    pdf_bytes = render_sick_note_pdf(TITLE, decomposed, "", "2026-09-01", "2026-09-01")
    assert "Nguyễn Thị Hạnh" in visible_text(pdf_bytes)


def test_render_sick_note_pdf_refuses_marks_that_do_not_compose():
    with pytest.raises(UnsupportedTextError) as raised:
        render_sick_note_pdf(TITLE, "Bo̧gna", "", "2026-09-01", "2026-09-01")
    assert "̧" in raised.value.characters


def test_sick_note_pdf_text_stays_german_and_is_never_translated():
    source_dir = Path(__file__).resolve().parents[1] / "app" / "iserv"
    source = (source_dir / "sick_note_pdf.py").read_text(encoding="utf-8")
    for forbidden in ("from ..messages", "from app.messages", "import messages", "i18n", "language"):
        assert forbidden not in source, forbidden
    pdf_bytes = render_sick_note_pdf(TITLE, "Mia Musterkind", "5A", "2026-09-01", "2026-09-01")
    flowing = " ".join(visible_text(pdf_bytes).split())
    assert "meine Tochter/mein Sohn" in flowing
    assert "nicht am Schulunterricht teilnehmen" in flowing
    assert "am Dienstag, den 01.09.2026" in flowing
    assert "Mit freundlichen Grüßen" in flowing


def test_pdf_modules_never_silently_substitute_characters():
    modules = ("sick_note_pdf.py", "pdf.py", "truetype.py")
    source_dir = Path(__file__).resolve().parents[1] / "app" / "iserv"
    for module in modules:
        text = (source_dir / module).read_text(encoding="utf-8")
        assert "cp1252" not in text, module
        assert "errors=" not in text, module
        assert "unicode_escape" not in text, module


def test_shipped_fonts_cover_the_scripts_the_app_promises():
    samples = {
        "de": "Björn Müller-Weiß",
        "tr": "Şahin Gülşen İpek Oğuz",
        "pl": "Łukasz Zażółć Ćwikła",
        "vi": "Nguyễn Thị Hạnh Đặng",
        "ru": "Софія Жуковський Ъь",
        "uk": "Софія Їжак Ґудзик Єва",
        "el": "Παπαδόπουλος Ξένη",
    }
    for key in FONT_FILES:
        font = font_for(key)
        assert font.embedding_allowed()
        for language, sample in samples.items():
            assert font.missing_glyphs(sample) == [], f"{FONT_FILES[key]} misses glyphs for {language}"


def test_shipped_fonts_are_present_and_stay_small_enough_to_package():
    total = 0
    for filename in FONT_FILES.values():
        path = FONT_DIR / filename
        assert path.is_file()
        total += path.stat().st_size
    assert (FONT_DIR / "OFL.txt").is_file()
    assert total < 1_100_000


def test_font_subset_keeps_advances_and_mapping_intact():
    font = font_for("F1")
    codepoints = {ord(char) for char in "".join(FOREIGN_NAMES) + TITLE}
    result = font.subset(codepoints)
    embedded = TrueTypeFont(result.data)
    assert set(result.cid_for) == codepoints
    for codepoint, cid in result.cid_for.items():
        assert embedded.cmap[codepoint] == cid
        assert embedded.advances[cid] == font.advances[font.glyph_id(codepoint)]
        assert embedded.glyph_bytes(cid) or codepoint == ord(" ")
    assert len(result.data) < len(font.data) // 10
