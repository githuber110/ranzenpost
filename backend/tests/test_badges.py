import pytest

from app.iserv.badges import BadgeShapeError, parse_badges


def test_readable_counts_stay_and_unreadable_ones_are_unknown_not_zero():
    assert parse_badges({"mail": 3, "exercise": 0, "news": "2", "flag": True, "huge": 10**9, "minus": -1}) == {
        "mail": 3,
        "exercise": 0,
        "news": None,
        "flag": None,
        "huge": None,
        "minus": None,
    }


def test_an_empty_list_means_no_badges():
    assert parse_badges([]) == {}


@pytest.mark.parametrize("payload", [None, "text", [1, 2], 5])
def test_an_unknown_shape_is_an_error(payload):
    with pytest.raises(BadgeShapeError):
        parse_badges(payload)
