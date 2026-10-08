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
