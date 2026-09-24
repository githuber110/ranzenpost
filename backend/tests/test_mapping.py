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
    assert merged["subjects"]["D"] == {"label": "Deutsch", "color": "#111111", "color_source": "user", "color_version": 2}
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
    assert display["previous"] == {"subject": "", "teacher": "", "teacher_surname": "", "room": ""}


def test_to_display_maps_previous_values_to_labels():
    config = {
        "subjects": {"D": {"label": "Deutsch", "color": "#111111"}},
        "teachers": {"BEH": {"label": "Fr. Behrend", "surname": "Behrend", "is_class_teacher": True}},
    }
    change = {
        "kind": "changed",
        "fields": ["teacher", "room"],
        "previous": {"subject": "D", "teacher": "BEH", "room": "R1"},
    }
    display = to_display(lesson("D", "ERN", 1), config, change)
    assert display["change_kind"] == "changed"
    assert display["changed_fields"] == ["teacher", "room"]
    assert display["previous"] == {
        "subject": "Deutsch", "teacher": "Fr. Behrend", "teacher_surname": "Behrend", "room": "R1"
    }


def test_to_display_previous_falls_back_to_raw_codes():
    change = {"kind": "changed", "fields": ["subject"], "previous": {"subject": "XY", "teacher": "ZZ", "room": "R9"}}
    display = to_display(lesson("D", "BEH", 1), {}, change)
    assert display["previous"] == {"subject": "XY", "teacher": "ZZ", "teacher_surname": "", "room": "R9"}


def test_to_display_cancelled_lesson_keeps_its_own_data():
    display = to_display(lesson("SP", "OTT", 3), {}, {"kind": "cancelled", "fields": [], "previous": {}})
    assert display["change_kind"] == "cancelled"
    assert display["subject_label"] == "SP"
    assert display["changed_fields"] == []
    assert display["previous"] == {"subject": "", "teacher": "", "teacher_surname": "", "room": ""}


def test_to_display_survives_partial_change_dicts():
    display = to_display(lesson("D", "BEH", 1), {}, {"kind": "added"})
    assert display["change_kind"] == "added"
    assert display["changed_fields"] == []
    assert display["previous"] == {"subject": "", "teacher": "", "teacher_surname": "", "room": ""}


def test_subject_and_teacher_label_helpers():
    config = {"subjects": {"D": {"label": "Deutsch"}}, "teachers": {"BEH": {"label": "Fr. Behrend"}}}
    assert subject_label(config, "D") == "Deutsch"
    assert subject_label(config, "XY") == "XY"
    assert subject_label(config, "") == ""
    assert teacher_label(config, "BEH") == "Fr. Behrend"
    assert teacher_label({}, "ZZ") == "ZZ"
    assert teacher_label({}, "") == ""


def test_merge_lifts_an_old_palette_colour_onto_its_new_name_once():
    config = {"subjects": {"D": {"label": "Deutsch", "color": "#16a34a"}}, "teachers": {}}
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["D"]["color"] == "green"
    assert merged["subjects"]["D"]["label"] == "Deutsch"
    assert merged["subjects"]["D"]["color_source"] == "user"
    assert merge_discovered_codes(merged, []) == merged


def test_merge_keeps_a_colour_the_user_picked():
    config = {"subjects": {"D": {"label": "Deutsch", "color": "#ff0000"}}, "teachers": {}}
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["D"]["color"] == "#ff0000"


OLD_PALETTE = [
    "#84142a", "#f7703e", "#ec932f", "#7b791d", "#404f0e",
    "#2dae4b", "#208068", "#135859", "#31aed2", "#2486ed",
    "#372daa", "#834ac9", "#a639a3", "#7a1362",
]


def test_every_old_palette_colour_maps_to_its_own_new_name():
    from app.mapping import LEGACY_COLORS, PALETTE_NAMES

    names = [LEGACY_COLORS[color] for color in OLD_PALETTE]
    assert len(set(names)) == len(names), "two subjects would end up with the same colour"
    assert set(LEGACY_COLORS.values()) <= set(PALETTE_NAMES)


def test_no_palette_name_is_migrated_again_and_unknown_names_fall_back():
    from app.mapping import DEFAULT_COLOR_NAME, LEGACY_COLORS, PALETTE_NAMES, normalize_color

    assert not set(PALETTE_NAMES) & set(LEGACY_COLORS)
    for name in PALETTE_NAMES:
        assert normalize_color(name) == name
        assert normalize_color(name.upper()) == name
    assert normalize_color("#ABCDEF") == "#abcdef"
    assert normalize_color("crimson") == DEFAULT_COLOR_NAME
    assert normalize_color("#abc") == DEFAULT_COLOR_NAME
    assert normalize_color("") == ""
    assert normalize_color(None) == ""


def test_migration_normalises_a_stored_colour_whatever_its_source():
    from app.mapping import migrate_subject_colors

    config = {"subjects": {
        "A": {"label": "A", "color": "#2486ed", "color_source": "user"},
        "B": {"label": "B", "color": "Plum", "color_source": "user"},
        "C": {"label": "C", "color": "#0e6b70", "color_source": "auto"},
        "D": {"label": "D", "color": "yellow", "color_source": "user"},
    }}
    migrated = migrate_subject_colors(config)
    assert migrated["subjects"]["A"] == {"label": "A", "color": "blue", "color_source": "user", "color_version": 2}
    assert migrated["subjects"]["B"] == {"label": "B", "color": "grey", "color_source": "user", "color_version": 2}
    assert migrated["subjects"]["C"] == {"label": "C", "color": "teal", "color_source": "auto", "color_version": 2}
    assert migrated["subjects"]["D"] == {"label": "D", "color": "yellow", "color_source": "user", "color_version": 2}
    assert migrate_subject_colors(migrated) is migrated


def test_two_automatic_subjects_never_keep_the_same_colour():
    config = {
        "subjects": {
            "SU": {"label": "Sachunterricht", "color": "sky", "color_source": "auto"},
            "MU": {"label": "Musik", "color": "sky", "color_source": "auto"},
        },
        "teachers": {},
    }
    subjects = merge_discovered_codes(config, [])["subjects"]
    assert subjects["SU"]["color"] != subjects["MU"]["color"]


def test_two_subjects_may_share_a_colour_the_user_picked():
    config = {
        "subjects": {
            "SU": {"label": "Sachunterricht", "color": "sky", "color_source": "user"},
            "MU": {"label": "Musik", "color": "sky", "color_source": "user"},
        },
        "teachers": {},
    }
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["SU"]["color"] == "sky"
    assert merged["subjects"]["MU"]["color"] == "sky"
    assert merge_discovered_codes(merged, []) == merged


def test_automatic_colours_step_aside_for_a_colour_the_user_picked():
    config = {
        "subjects": {
            "AA": {"label": "AA", "color": "blue", "color_source": "auto"},
            "ZZ": {"label": "ZZ", "color": "blue", "color_source": "user"},
        },
        "teachers": {},
    }
    subjects = merge_discovered_codes(config, [])["subjects"]
    assert subjects["ZZ"]["color"] == "blue"
    assert subjects["AA"]["color"] != "blue"
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


def test_a_name_iserv_delivered_is_corrected_when_iserv_changes_it():
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes

    lesson = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Beispiel Katrin", teacher_surname="Katrin",
    )
    config = merge_discovered_codes({}, [lesson])
    assert config["teachers"]["BEI"]["label"] == "Beispiel Katrin"
    better = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Katrin Beispiel", teacher_surname="Beispiel",
    )
    config = merge_discovered_codes(config, [better])
    assert config["teachers"]["BEI"]["label"] == "Katrin Beispiel"
    assert config["teachers"]["BEI"]["surname"] == "Beispiel"


def test_a_name_the_user_typed_is_never_overwritten():
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes

    config = {"teachers": {"BEI": {"label": "Frau B.", "label_source": "", "is_class_teacher": False}}}
    lesson = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Katrin Beispiel", teacher_surname="Beispiel",
    )
    merged = merge_discovered_codes(config, [lesson])
    assert merged["teachers"]["BEI"]["label"] == "Frau B."
    assert merged["teachers"]["BEI"]["surname"] == "Beispiel"


def test_a_name_stored_before_the_order_was_fixed_is_still_corrected():
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes

    config = {"teachers": {"BEI": {"label": "Beispiel Katrin", "is_class_teacher": False}}}
    lesson = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Katrin Beispiel", teacher_surname="Beispiel",
    )
    merged = merge_discovered_codes(config, [lesson])
    assert merged["teachers"]["BEI"]["label"] == "Katrin Beispiel"


def test_two_teachers_stored_in_the_old_order_are_corrected_together():
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes

    config = {"teachers": {"BEI": {"label": "Beispiel Katrin, Zweit Olga", "is_class_teacher": False}}}
    lesson = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Katrin Beispiel, Olga Zweit",
        teacher_surname="Beispiel, Zweit",
    )
    merged = merge_discovered_codes(config, [lesson])
    assert merged["teachers"]["BEI"]["label"] == "Katrin Beispiel, Olga Zweit"


def test_a_different_name_the_user_typed_survives_the_correction():
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes

    config = {"teachers": {"BEI": {"label": "Klassenlehrerin", "is_class_teacher": True}}}
    lesson = Lesson(
        date="07.09.2026", day_of_week=1, period=1, subject="D", teacher="BEI",
        room="", class_name="3b", teacher_name="Katrin Beispiel", teacher_surname="Beispiel",
    )
    merged = merge_discovered_codes(config, [lesson])
    assert merged["teachers"]["BEI"]["label"] == "Klassenlehrerin"


def named_lesson(subject, name, period=1):
    return Lesson(
        date="07.09.2026", day_of_week=1, period=period, subject=subject, teacher="BEH",
        room="R1", class_name="1a", subject_name=name,
    )


def test_derive_subject_code_prefers_first_two_letters():
    from app.mapping import derive_subject_code

    assert derive_subject_code("Mathematik", set()) == "MA"


def test_derive_subject_code_falls_back_to_three_letters_on_collision():
    from app.mapping import derive_subject_code

    assert derive_subject_code("Chor", {"CH"}) == "CHO"


def test_derive_subject_code_falls_back_to_consonants_on_double_collision():
    from app.mapping import derive_subject_code

    assert derive_subject_code("Biologie", {"BI", "BIO"}) == "BLG"


def test_derive_subject_code_strips_diacritics():
    from app.mapping import derive_subject_code

    assert derive_subject_code("Ökologie", set()) == "OK"
    assert derive_subject_code("Français", set()) == "FR"


def test_merge_derives_a_code_when_iserv_only_delivers_a_long_name():
    merged = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Mathematik", "Mathematik")])
    entry = merged["subjects"]["Mathematik"]
    assert entry["code"] == "MA"
    assert entry["derived"] is True
    assert entry["label"] == "Mathematik"


def test_merge_leaves_a_short_native_code_alone():
    merged = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("MA", "Mathematik")])
    entry = merged["subjects"]["MA"]
    assert "code" not in entry
    assert "derived" not in entry


def test_merge_resolves_a_derived_code_collision_between_two_long_names():
    lessons = [named_lesson("Chemie", "Chemie", period=1), named_lesson("Chor", "Chor", period=2)]
    merged = merge_discovered_codes({"subjects": {}, "teachers": {}}, lessons)
    assert merged["subjects"]["Chemie"]["code"] == "CH"
    assert merged["subjects"]["Chor"]["code"] == "CHO"


def test_merge_keeps_a_derived_code_stable_across_polls():
    first = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Mathematik", "Mathematik")])
    second = merge_discovered_codes(first, [named_lesson("Mathematik", "Mathematik")])
    assert second == first


def test_merge_never_overwrites_a_derived_code_the_user_edited():
    config = {
        "subjects": {"Mathematik": {"label": "Mathematik", "color": "#111111", "code": "M"}},
        "teachers": {},
    }
    merged = merge_discovered_codes(config, [named_lesson("Mathematik", "Mathematik")])
    assert merged["subjects"]["Mathematik"]["code"] == "M"
    assert "derived" not in merged["subjects"]["Mathematik"]


def test_to_display_uses_the_derived_code_as_subject_code():
    config = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Mathematik", "Mathematik")])
    display = to_display(named_lesson("Mathematik", "Mathematik"), config)
    assert display["subject_code"] == "MA"
    assert display["subject_label"] == "Mathematik"


def test_a_custom_hex_colour_survives_the_merge_and_the_migration():
    config = {"subjects": {"D": {"label": "Deutsch", "color": "#ABCDEF", "color_source": "user"}}, "teachers": {}}
    merged = merge_discovered_codes(config, [])
    assert merged["subjects"]["D"]["color"] == "#abcdef"
    assert merge_discovered_codes(merged, []) == merged


def test_the_palette_resolves_to_a_base_hex_for_the_feed_and_the_integration():
    from app.mapping import PALETTE_BY_NAME, subject_base

    assert subject_base("yellow") == PALETTE_BY_NAME["yellow"]["base"]
    assert subject_base("#84142a") == PALETTE_BY_NAME["maroon"]["base"]
    assert subject_base("#abcdef") == "#abcdef"
    assert subject_base("") == ""
    assert subject_base("no such colour") == PALETTE_BY_NAME["grey"]["base"]


def test_the_ink_follows_the_fill_and_the_bar_leans_away_from_the_ink():
    from app.mapping import DARK_INK, LIGHT_INK, bar_for, contrast_ratio, ink_for, subject_tokens

    assert ink_for("#ffffff") == DARK_INK
    assert ink_for("#000000") == LIGHT_INK
    assert ink_for("#ffe100") == DARK_INK
    assert ink_for("#1a2a66") == LIGHT_INK
    for fill in ("#ffffff", "#000000", "#ffe100", "#1a2a66", "#808080", "#ff0000", "#00ff00", "#0000ff"):
        assert contrast_ratio(ink_for(fill), fill) >= 4.5
        assert contrast_ratio(bar_for(fill), fill) >= 2.0
    assert bar_for("#ffe100") < "#ffe100"
    assert bar_for("#1a2a66") > "#1a2a66"
    assert subject_tokens("#abcdef") == {"fill": "#abcdef", "ink": DARK_INK, "bar": bar_for("#abcdef")}
    assert subject_tokens("navy", "dark") == {"fill": "#243580", "ink": LIGHT_INK, "bar": "#9db0ff"}
    assert subject_tokens("") is None


def test_an_own_colour_equal_to_an_old_palette_hex_is_never_renamed():
    from app.mapping import migrate_subject_colors

    legacy = migrate_subject_colors({"subjects": {"D": {"label": "D", "color": "#31aed2"}}})
    assert legacy["subjects"]["D"]["color"] == "sky"
    own = {"subjects": {"D": {"label": "D", "color": "#31AED2", "color_source": "user", "color_version": 2}}}
    kept = migrate_subject_colors(own)
    assert kept["subjects"]["D"]["color"] == "#31aed2"
    assert migrate_subject_colors(kept) is kept
    assert merge_discovered_codes(kept, [])["subjects"]["D"]["color"] == "#31aed2"


def test_an_own_colour_picked_after_the_migration_survives_a_store_round_trip(tmp_path):
    from app.store import Store
    from tests.support import add_school, scoped

    base = Store(tmp_path / "data")
    store = scoped(base, add_school(base))
    config = store.load_config()
    config["subjects"] = {"D": {"label": "Deutsch", "color": "#84142a"}}
    store.save_config(config)
    loaded = store.load_config()
    assert loaded["subjects"]["D"]["color"] == "maroon"
    loaded["subjects"]["D"]["color"] = "#31aed2"
    loaded["subjects"]["D"]["color_source"] = "user"
    store.save_config(loaded)
    assert store.load_config()["subjects"]["D"]["color"] == "#31aed2"
    assert store.load_config()["subjects"]["D"]["color"] == "#31aed2"


def _codes(config):
    return {key: entry.get("code") for key, entry in config["subjects"].items()}


def test_a_subject_learned_later_never_takes_the_code_of_a_known_subject():
    known = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Musik", "Musik")])
    assert _codes(known)["Musik"] == "MU"
    later = merge_discovered_codes(known, [named_lesson("Musical", "Musical")])
    assert _codes(later)["Musik"] == "MU"
    assert _codes(later)["Musical"] not in ("MU", None)
    again = merge_discovered_codes(later, [named_lesson("Musik", "Musik")])
    assert _codes(again) == _codes(later)


def test_a_known_derived_code_survives_a_week_without_that_subject():
    known = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Chor", "Chor")])
    assert _codes(known)["Chor"] == "CH"
    quiet = merge_discovered_codes(known, [named_lesson("Mathematik", "Mathematik")])
    back = merge_discovered_codes(quiet, [named_lesson("Chor", "Chor")])
    assert _codes(back)["Chor"] == "CH"


def test_a_new_subject_sorted_first_does_not_push_a_known_one_off_its_code():
    known = merge_discovered_codes({"subjects": {}, "teachers": {}}, [named_lesson("Mathematik", "Mathematik")])
    later = merge_discovered_codes(known, [named_lesson("Mathe-AG", "Mathe-AG")])
    assert _codes(later)["Mathematik"] == "MA"
    assert _codes(later)["Mathe-AG"] != "MA"
