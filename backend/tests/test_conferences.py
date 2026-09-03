from app.iserv.conferences import parse_conferences

BASE = "https://school.example"


def test_parse_conferences_empty_page(fixture):
    result = parse_conferences(fixture("conferences_empty.html"), BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_without_table_is_a_parse_error_not_empty():
    result = parse_conferences("<div><p>Elternsprechtage</p></div>", BASE)
    assert result == {"error": "parse_failed", "items": []}


def test_parse_conferences_empty_table_body_is_empty():
    html = "<table><tbody></tbody></table>"
    result = parse_conferences(html, BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_empty_phrase_wins_over_table():
    html = "<p>Derzeit sind KEINE Elternsprechtage verfügbar.</p><table><tbody><tr><td>x</td></tr></tbody></table>"
    result = parse_conferences(html, BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_list(fixture):
    result = parse_conferences(fixture("conferences_list.html"), BASE)
    assert result["empty"] is False
    assert len(result["items"]) == 2
    first = result["items"][0]
    assert first["cells"] == ["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]
    assert first["links"] == ["https://school.example/iserv/parentconference/attendee/1/book"]
    second = result["items"][1]
    assert second["cells"] == ["22.09.2026", "Herr Beispiel", "Raum 202", "Termin buchen"]
    assert second["links"] == ["https://school.example/iserv/parentconference/attendee/2/book"]


def test_parse_conferences_drops_unsafe_link_schemes():
    html = (
        "<table><tbody><tr>"
        "<td>15.09.2026</td>"
        "<td><a href=\"javascript:alert(1)\">Termin buchen</a></td>"
        "</tr></tbody></table>"
    )
    result = parse_conferences(html, BASE)
    assert result["items"][0]["links"] == []
