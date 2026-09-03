from app.iserv.models import Lesson
from app.mapping import merge_discovered_codes, subject_label, teacher_label, to_display


def lesson(subject="D", teacher="BEH", period=1):
    return Lesson(
        date="31.08.2026", day_of_week=1, period=period,
        subject=subject, teacher=teacher, room="R1", class_name="1a",
    )


def test_merge_adds_new_codes_with_defaults():
    merged = merge_discovered_codes({"subjects": {}, "teachers": {}}, [lesson("D", "BEH"), lesson("M", "ERN")])
    assert merged["subjects"]["D"]["label"] == "D"
    assert merged["subjects"]["D"]["color"]
    assert merged["subjects"]["M"]["color"] != merged["subjects"]["D"]["color"]
    assert merged["teachers"]["ERN"]["is_class_teacher"] is False


def test_merge_preserves_existing_names_and_colors():
    config = {
        "subjects": {"D": {"label": "Deutsch", "color": "#111111"}},
        "teachers": {"BEH": {"label": "Fr. Behrend", "is_class_teacher": True}},
    }
    merged = merge_discovered_codes(config, [lesson("D", "BEH"), lesson("M", "ERN")])
    assert merged["subjects"]["D"] == {"label": "Deutsch", "color": "#111111", "color_source": "user"}
    assert merged["teachers"]["BEH"]["is_class_teacher"] is True
    assert "M" in merged["subjects"]
    assert "ERN" in merged["teachers"]


def test_to_display_applies_config():
    config = {
        "subjects": {"D": {"label": "Deutsch", "color": "#111111"}},
        "teachers": {"BEH": {"label": "Fr. Behrend", "is_class_teacher": True}},
        "period_times": {"1": "08:00"},
    }
    display = to_display(lesson("D", "BEH", 1), config)
    assert display["subject_label"] == "Deutsch"
    assert display["color"] == "#111111"
    assert display["teacher_label"] == "Fr. Behrend"
    assert display["is_class_teacher"] is True
    assert display["start_time"] == "08:00"


def test_to_display_falls_back_to_raw_code():
    display = to_display(lesson("XY", "ZZ", 3), {})
    assert display["subject_label"] == "XY"
    assert display["teacher_label"] == "ZZ"
    assert display["start_time"] == ""


def test_to_display_defaults_to_no_change():
    display = to_display(lesson("D", "BEH", 1), {})
    assert display["change_kind"] == ""
    assert display["changed_fields"] == []
    assert display["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_to_display_maps_previous_values_to_labels():
    config = {
        "subjects": {"D": {"label": "Deutsch", "color": "#111111"}},
        "teachers": {"BEH": {"label": "Fr. Behrend", "is_class_teacher": True}},
    }
    change = {
        "kind": "changed",
        "fields": ["teacher", "room"],
        "previous": {"subject": "D", "teacher": "BEH", "room": "R1"},
    }
    display = to_display(lesson("D", "ERN", 1), config, change)
    assert display["change_kind"] == "changed"
    assert display["changed_fields"] == ["teacher", "room"]
    assert display["previous"] == {"subject": "Deutsch", "teacher": "Fr. Behrend", "room": "R1"}


def test_to_display_previous_falls_back_to_raw_codes():
    change = {"kind": "changed", "fields": ["subject"], "previous": {"subject": "XY", "teacher": "ZZ", "room": "R9"}}
    display = to_display(lesson("D", "BEH", 1), {}, change)
    assert display["previous"] == {"subject": "XY", "teacher": "ZZ", "room": "R9"}


def test_to_display_cancelled_lesson_keeps_its_own_data():
    display = to_display(lesson("SP", "OTT", 3), {}, {"kind": "cancelled", "fields": [], "previous": {}})
    assert display["change_kind"] == "cancelled"
    assert display["subject_label"] == "SP"
    assert display["changed_fields"] == []
    assert display["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_to_display_survives_partial_change_dicts():
    display = to_display(lesson("D", "BEH", 1), {}, {"kind": "added"})
    assert display["change_kind"] == "added"
    assert display["changed_fields"] == []
    assert display["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_subject_and_teacher_label_helpers():
    config = {"subjects": {"D": {"label": "Deutsch"}}, "teachers": {"BEH": {"label": "Fr. Behrend"}}}
    assert subject_label(config, "D") == "Deutsch"
    assert subject_label(config, "XY") == "XY"
    assert subject_label(config, "") == ""
    assert teacher_label(config, "BEH") == "Fr. Behrend"
    assert teacher_label({}, "ZZ") == "ZZ"
    assert teacher_label({}, "") == ""


def test_merge_lifts_an_old_palette_colour_onto_its_new_counterpart_once():
    config = {"subjects": {"D": {"label": "Deutsch", "color": "#16a34a"}}, "teachers": {}}
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["D"]["color"] == "#2dae4b"
    assert merged["subjects"]["D"]["label"] == "Deutsch"
    assert merged["subjects"]["D"]["color_source"] == "user"
    assert merge_discovered_codes(merged, []) == merged


def test_merge_keeps_a_colour_the_user_picked():
    config = {"subjects": {"D": {"label": "Deutsch", "color": "#ff0000"}}, "teachers": {}}
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["D"]["color"] == "#ff0000"


def test_every_current_palette_colour_maps_to_its_own_new_colour():
    from app.mapping import PALETTE_MIGRATION

    reachable = [
        "#0e6b70", "#7a4b9c", "#b4602a", "#2f6b3a", "#9c3b5e",
        "#3a5a9c", "#8a6a1f", "#2a6f63", "#5b4a9c", "#1f6b8a",
    ]
    values = [PALETTE_MIGRATION[color] for color in reachable]
    assert len(set(values)) == len(values), "two subjects would end up with the same colour"


def test_no_new_palette_colour_is_migrated_again():
    from app.mapping import DEFAULT_COLORS, PALETTE_MIGRATION

    assert not set(PALETTE_MIGRATION.values()) & set(PALETTE_MIGRATION), "a migrated colour would migrate again"
    assert not set(DEFAULT_COLORS) & set(PALETTE_MIGRATION), "a current palette colour would be migrated away"


def test_two_automatic_subjects_never_keep_the_same_colour():
    config = {
        "subjects": {
            "SU": {"label": "Sachunterricht", "color": "#31aed2", "color_source": "auto"},
            "MU": {"label": "Musik", "color": "#31aed2", "color_source": "auto"},
        },
        "teachers": {},
    }
    subjects = merge_discovered_codes(config, [])["subjects"]
    assert subjects["SU"]["color"] != subjects["MU"]["color"]


def test_two_subjects_may_share_a_colour_the_user_picked():
    config = {
        "subjects": {
            "SU": {"label": "Sachunterricht", "color": "#31aed2", "color_source": "user"},
            "MU": {"label": "Musik", "color": "#31aed2", "color_source": "user"},
        },
        "teachers": {},
    }
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["SU"]["color"] == "#31aed2"
    assert merged["subjects"]["MU"]["color"] == "#31aed2"
    assert merged == config


def test_automatic_colours_step_aside_for_a_colour_the_user_picked():
    config = {
        "subjects": {
            "AA": {"label": "AA", "color": "#2486ed", "color_source": "auto"},
            "ZZ": {"label": "ZZ", "color": "#2486ed", "color_source": "user"},
        },
        "teachers": {},
    }
    subjects = merge_discovered_codes(config, [])["subjects"]
    assert subjects["ZZ"]["color"] == "#2486ed"
    assert subjects["AA"]["color"] != "#2486ed"
    assert subjects["AA"]["color_source"] == "auto"


def test_a_reload_leaves_an_untouched_config_alone():
    from app.mapping import DEFAULT_COLORS

    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    config = {"subjects": {code: {"label": code, "color": "", "color_source": "auto"} for code in codes}, "teachers": {}}
    first = merge_discovered_codes(config, [])
    assert first == merge_discovered_codes(first, [])
    colors = [entry["color"] for entry in first["subjects"].values()]
    assert len(set(colors)) == len(codes), "a full week must not hand out the same colour twice"
    assert set(colors) <= set(DEFAULT_COLORS)


def test_unclashing_keeps_the_labels_and_the_order():
    config = {
        "subjects": {
            "B": {"label": "Bio", "color": "#111111"},
            "A": {"label": "Astro", "color": "#111111"},
        },
        "teachers": {},
    }
    subjects = merge_discovered_codes(config, [])["subjects"]
    assert list(subjects) == ["B", "A"]
    assert subjects["B"]["label"] == "Bio"
    assert subjects["A"]["label"] == "Astro"


def test_more_subjects_than_palette_entries_still_get_a_colour():
    subjects = {chr(65 + i): {"label": chr(65 + i), "color": ""} for i in range(14)}
    merged = merge_discovered_codes({"subjects": subjects, "teachers": {}}, [])["subjects"]
    assert all(entry["color"] for entry in merged.values())
