from app.valueshape import MAX_ITEMS, shape_lines


def test_keys_that_only_later_entries_carry_are_shown():
    data = {
        "entries": [
            {"id": 1, "room": {"id": 2, "name": "101"}, "timetableBlock": None},
            {"id": 3, "room": {"id": 4, "name": "102"}, "timetableBlock": {"id": 5, "type": "cancelled"}},
            {"id": 6, "room": None, "substitution": {"id": 7, "note": "Vertretung"}},
        ]
    }

    lines = shape_lines(data)

    assert "entries[].timetableBlock: null (null 1, missing 1)" in lines
    assert "entries[].timetableBlock.type: string len 9, letters" in lines
    assert "entries[].substitution: object keys 2 (missing 2)" in lines
    assert "entries[].substitution.note: string len 10, letters" in lines
    assert sum(line.startswith("entries[].id:") for line in lines) == 1


def test_only_the_first_entries_of_a_long_list_are_read():
    data = [{"id": 1}] * MAX_ITEMS + [{"late": 1}]

    assert not any("late" in line for line in shape_lines(data))


def test_strings_across_entries_show_their_length_range_empties_and_gaps():
    data = {"events": [{"title": "abc", "location": ""}, {"title": "a" * 40, "location": "hall"}, {"title": "abcdef"}]}

    lines = shape_lines(data)

    assert "events[].title: string len 3, letters (len 3-40 of 3)" in lines
    assert "events[].location: string len 0, blank (len 0-4 of 2, empty 1, missing 1)" in lines


def test_a_single_value_keeps_the_plain_shape():
    assert shape_lines({"title": "abc"}) == ["(root): object keys 1", "title: string len 3, letters"]


def test_shape_lines_keep_order_spread_and_limits_of_the_tree_walk():
    from app import valueshape

    data = {"rows": [{"name": "a", "note": None}, {"name": "bcd"}], "total": 3}
    assert valueshape.shape_lines(data) == [
        "(root): object keys 2",
        "rows: array len 2 of object",
        "rows[]: object keys 2",
        "rows[].name: string len 1, letters (len 1-3 of 2)",
        "rows[].note: null (missing 1)",
        "total: int >0",
    ]
    assert valueshape.shape_lines(data, 2) == ["(root): object keys 2", "rows: array len 2 of object"]
    deep = "x"
    for _ in range(valueshape.MAX_DEPTH + 3):
        deep = {"a": deep}
    assert len(valueshape.shape_lines(deep)) == valueshape.MAX_DEPTH + 1


def test_numbers_across_entries_count_their_zeros_and_values_below_zero():
    data = {"slots": [{"number": 1}, {"number": 0}, {"number": 2}, {"number": -1}, {"number": 0}]}

    assert "slots[].number: int >0 (zero 2, below zero 1)" in shape_lines(data)


def test_numbers_that_share_one_sign_keep_the_plain_shape():
    assert "slots[].number: int >0" in shape_lines({"slots": [{"number": 1}, {"number": 5}]})
    assert "slots[].number: int 0" in shape_lines({"slots": [{"number": 0}, {"number": 0}]})
