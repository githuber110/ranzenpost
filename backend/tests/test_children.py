from app.iserv.children import parse_children


def test_parse_children_returns_named_children(fixture):
    children = parse_children(fixture("timetable_page.html"))
    assert [child.name for child in children] == ["Alex Example", "Robin Example"]
    assert children[0].child_id == "11111111-1111-4111-8111-111111111111"


def test_parse_children_ignores_placeholder_and_other_selects(fixture):
    children = parse_children(fixture("timetable_page.html"))
    ids = [child.child_id for child in children]
    assert "" not in ids
    assert "99999999-9999-4999-8999-999999999999" not in ids


def test_parse_children_without_select_returns_empty():
    assert parse_children("<html><body>no select</body></html>") == []
