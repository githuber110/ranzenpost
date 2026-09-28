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

    assert "entries[].timetableBlock: null" in lines
    assert "entries[].timetableBlock.type: string len 9, letters" in lines
    assert "entries[].substitution: object keys 2" in lines
    assert "entries[].substitution.note: string len 10, letters" in lines
    assert sum(line.startswith("entries[].id:") for line in lines) == 1


def test_only_the_first_entries_of_a_long_list_are_read():
    data = [{"id": 1}] * MAX_ITEMS + [{"late": 1}]

    assert not any("late" in line for line in shape_lines(data))
