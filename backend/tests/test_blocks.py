from app import blocks, modules


def test_the_catalogue_names_every_block_once_with_a_known_module():
    assert len(blocks.BLOCK_KEYS) == len(set(blocks.BLOCK_KEYS)) == 10
    for block in blocks.BLOCKS:
        assert block["module"] in modules.MODULES
        assert block["area"] in blocks.AREA_MODULES
        assert block["module"] in blocks.AREA_MODULES[block["area"]]
        assert block["size"] in blocks.SIZES
        assert 1 <= block["compact"] <= block["normal"]


def test_every_module_has_at_least_one_block():
    for module in modules.MODULES:
        assert any(block["module"] == module for block in blocks.BLOCKS), module


def test_the_default_overview_holds_the_six_agreed_blocks_in_catalogue_order():
    listed = blocks.default_overview_blocks()
    assert [entry["key"] for entry in listed] == ["today", "letters", "noticeboard", "conferences", "changes", "chat"]
    assert listed[0] == {"key": "today", "size": "normal"}
    for key in blocks.DEFAULT_OVERVIEW_KEYS:
        assert key in blocks.BLOCK_BY_KEY


def test_unknown_keys_and_duplicates_are_dropped_and_sizes_fall_back():
    kept = blocks.normalize_overview_blocks(
        [{"key": "letters", "size": "huge"}, "today", {"key": "letters"}, {"key": "nope"}, 7, {"size": "compact"}]
    )
    assert kept == [{"key": "letters", "size": "normal"}, {"key": "today", "size": "normal"}]


def test_blocks_of_a_disabled_module_are_dropped():
    kept = blocks.normalize_overview_blocks([{"key": "today"}, {"key": "chat"}], disabled=["messenger"])
    assert kept == [{"key": "today", "size": "normal"}]


def test_a_missing_overview_list_means_the_default_but_an_empty_list_stays_empty():
    assert blocks.normalize_overview_blocks(None) == blocks.default_overview_blocks()
    assert blocks.normalize_overview_blocks([]) == []


def test_navigation_keeps_known_areas_in_order_and_appends_the_missing_ones():
    assert blocks.normalize_navigation(["messenger", "nope", "timetable", "messenger"]) == [
        "messenger",
        "timetable",
        "absence",
        "post",
        "conferences",
    ]
    assert blocks.normalize_navigation(None) == list(blocks.DEFAULT_NAVIGATION)


def test_modules_disabled_keeps_only_known_module_names():
    assert blocks.normalize_modules_disabled(["messenger", "x", 3, "messenger", "letters"]) == ["messenger", "letters"]
    assert blocks.normalize_modules_disabled("messenger") == []


def test_an_area_is_enabled_when_any_of_its_modules_is_available_and_not_disabled():
    available = {"letters": False, "pinboard": True, "messenger": True}
    assert blocks.area_enabled("post", available, set())
    assert not blocks.area_enabled("post", available, {"pinboard"})
    assert not blocks.area_enabled("messenger", available, {"messenger"})
    assert blocks.area_enabled("timetable", {}, set())
