from app.iserv.news import parse_news

HEAD = """<html><body><nav class="navbar"><a href="/iserv/">Home</a><a href="/iserv/news">News</a></nav>
<div class="container"><h1>Alle News</h1>
<form action="/iserv/news" method="get"><input name="search"></form>
<ul class="nav"><li><a href="/iserv/news/general">General</a></li><li><a href="/iserv/news/sport">Sport</a></li></ul>
"""
TAIL = "</div></body></html>"


def test_panels_with_dates_and_categories_read_every_item():
    html = HEAD + """
    <div class="panel panel-default">
      <div class="panel-heading"><h3 class="panel-title"><a href="/iserv/news/general/12">Library opens later</a></h3></div>
      <div class="panel-body"><p>From Monday the library opens at nine.</p>
        <small class="text-muted"><a href="/iserv/news/general">General</a> · 03.10.2026 14:05</small>
        <a href="/iserv/news/general/12">Read more</a></div>
    </div>
    <div class="panel panel-default">
      <div class="panel-heading"><h3 class="panel-title"><a href="/iserv/news/sport/13">Sports day</a></h3></div>
      <div class="panel-body"><p>Bring water.</p><time datetime="2026-09-30T10:00:00+02:00">30.09.2026</time></div>
    </div>""" + TAIL
    parsed = parse_news(html)
    first, second = parsed["items"]
    assert first == {
        "id": "general/12",
        "title": "Library opens later",
        "date": "2026-10-03T14:05",
        "date_text": "General · 03.10.2026 14:05",
        "category": "General",
        "category_slug": "general",
        "summary": "From Monday the library opens at nine.",
        "path": "/iserv/news/general/12",
    }
    assert second["id"] == "sport/13"
    assert second["title"] == "Sports day"
    assert second["date"] == "2026-09-30T10:00"
    assert second["category"] == ""
    assert second["category_slug"] == "sport"


def test_items_without_dates_keep_an_empty_date():
    html = HEAD + """<ul class="list-group">
      <li class="list-group-item"><a href="/iserv/news/general/1">First notice</a></li>
      <li class="list-group-item"><a href="/iserv/news/general/2">Second notice</a></li></ul>""" + TAIL
    items = parse_news(html)["items"]
    assert [(item["title"], item["date"], item["date_text"]) for item in items] == [("First notice", "", ""), ("Second notice", "", "")]


def test_a_single_item_does_not_take_the_page_heading_as_its_title():
    html = HEAD + '<div><div><a href="/iserv/news/general/5">Only one</a></div></div>' + TAIL
    assert parse_news(html)["items"][0]["title"] == "Only one"


def test_a_page_without_items_reads_an_empty_list():
    parsed = parse_news(HEAD + "<p>Keine News</p>" + TAIL)
    assert parsed["items"] == []


def test_unknown_markup_does_not_crash():
    assert parse_news("<<<not html")["items"] == []
    assert parse_news("")["items"] == []


def test_a_date_in_the_summary_text_is_not_the_publication_date():
    html = HEAD + """<ul class="list-group"><li class="list-group-item">
      <h4><a href="/iserv/news/general/7">Autumn fair</a></h4>
      <p>The fair takes place on 12.11.2026 in the hall.</p></li></ul>""" + TAIL
    item = parse_news(html)["items"][0]
    assert item["date"] == ""
    assert item["summary"] == "The fair takes place on 12.11.2026 in the hall."


def test_a_date_in_the_item_metadata_beside_the_summary_is_read():
    html = HEAD + """<ul class="list-group"><li class="list-group-item">
      <h4><a href="/iserv/news/general/8">Autumn fair</a></h4>
      <p>The fair takes place on 12.11.2026 in the hall.</p>
      <small class="text-muted">01.10.2026</small></li></ul>""" + TAIL
    item = parse_news(html)["items"][0]
    assert (item["date"], item["date_text"]) == ("2026-10-01", "01.10.2026")
