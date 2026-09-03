from app.iserv.html import clean_html, plain_text


def test_script_is_removed_entirely():
    assert "alert" not in clean_html("<p>hallo</p><script>alert(1)</script>")


def test_event_handlers_are_stripped():
    cleaned = clean_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in cleaned
    assert "alert" not in cleaned


def test_iframe_is_removed():
    assert "<iframe" not in clean_html('<iframe srcdoc="<script>alert(1)</script>"></iframe>')


def test_style_attribute_is_stripped():
    assert "style" not in clean_html('<p style="position:fixed;top:0">x</p>')


def test_javascript_url_is_dropped():
    cleaned = clean_html('<a href="javascript:alert(1)">klick</a>')
    assert "javascript" not in cleaned
    assert "klick" in cleaned


def test_data_url_that_is_not_an_image_is_dropped():
    assert "data:text" not in clean_html('<a href="data:text/html,<script>1</script>">x</a>')


def test_a_normal_link_survives_and_gets_noopener():
    cleaned = clean_html('<a href="https://example.org/brief.pdf">Brief</a>')
    assert 'href="https://example.org/brief.pdf"' in cleaned
    assert "noopener" in cleaned


def test_relative_links_survive():
    assert 'href="/iserv/x"' in clean_html('<a href="/iserv/x">x</a>')


def test_unknown_tags_keep_their_text():
    assert "Inhalt" in clean_html("<marquee>Inhalt</marquee>")


def test_formatting_survives():
    cleaned = clean_html("<p>Ein <b>fetter</b> und <em>schräger</em> Text</p>")
    assert "<b>fetter</b>" in cleaned
    assert "<em>schräger</em>" in cleaned


def test_tables_survive_with_spans():
    cleaned = clean_html('<table><tr><td colspan="2">x</td></tr></table>')
    assert "colspan" in cleaned


def test_images_survive():
    assert 'src="https://example.org/a.png"' in clean_html('<img src="https://example.org/a.png" alt="a">')


def test_empty_input_stays_empty():
    assert clean_html("") == ""
    assert clean_html(None) == ""


def test_plain_text_drops_all_markup():
    assert plain_text("<p>eins</p><p>zwei</p>") == "eins zwei"
    assert plain_text(None) == ""
