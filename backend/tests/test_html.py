import re

import pytest
from bs4 import BeautifulSoup

from app.iserv.html import ALLOWED_ATTRS, ALLOWED_TAGS, clean_html, is_safe_url, plain_text, safe_url


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


XSS_PAYLOADS = [
    "<!--><img src=x onerror=alert(1)>-->",
    "<!---><img src=x onerror=alert(1)>-->",
    "<!-- a --!> <img src=x onerror=alert(1)> -->",
    "<![CDATA[ ><img src=x onerror=alert(1)> ]]>",
    "<?x ><img src=x onerror=alert(1)> ?>",
    "<!DOCTYPE x><p>ok</p><!ELEMENT x><!x ><img src=x onerror=alert(1)>>",
    "<scr<script>ipt>alert(1)</script>",
    "<ScRiPt>alert(1)</sCrIpT><IMG SRC=x OnErRoR=alert(1)>",
    "<scr\x00ipt>alert(1)</script><img src=x on\x00error=alert(1)>",
    '<a href="java\x00script:alert(1)">x</a>',
    '<a href="&#106;avascript:alert(1)">x</a>',
    '<a href="&#x6A;&#x61;vascript:alert(1)">x</a>',
    '<a href="java&Tab;script:alert(1)">x</a>',
    '<a href="jav&#x0A;ascript:alert(1)">x</a>',
    '<a href="javas&#99;ript&colon;alert(1)">x</a>',
    '<a href=" \x01javascript:alert(1)">x</a>',
    '<a href="JAVASCRIPT:alert(1)">x</a>',
    '<a href="vbscript:msgbox(1)">x</a>',
    '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    '<a href="data:image/svg+xml,<svg onload=alert(1)>">x</a>',
    '<img src="javascript:alert(1)"><img src="data:text/html,x">',
    "<svg onload=alert(1)><script>alert(1)</script></svg>",
    "<svg><a href=javascript:alert(1)><text>x</text></a></svg>",
    "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>",
    '<math href="javascript:alert(1)">x</math>',
    '<iframe srcdoc="<script src=\'api/letters/attachment/1\'></script>"></iframe>',
    '<iframe src="javascript:alert(1)"></iframe><frame src=x><frameset>',
    '<object data="javascript:alert(1)"></object><embed src="x.swf"><applet code=x>',
    '<form action="javascript:alert(1)"><button formaction="javascript:alert(1)">b</button></form>',
    '<base href="javascript:/"><meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
    '<link rel="stylesheet" href="x"><style>@import "x";</style>',
    '<p style="background:url(javascript:alert(1))">x</p>',
    "<template><img src=x onerror=alert(1)></template>",
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>',
    '<xmp><img src=x title="</xmp><img src=x onerror=alert(1)>"></xmp>',
    "<textarea><img src=x onerror=alert(1)></textarea><title><img src=x onerror=alert(1)></title>",
    "<noembed><img src=x onerror=alert(1)></noembed>",
    "<details open ontoggle=alert(1)>x</details><video><source onerror=alert(1)></video>",
    '<a href="https://example.org" onclick="alert(1)" target="_self">x</a>',
    '<img src="x" alt="&quot; onerror=&quot;alert(1)">',
    "<img src=x onerror=alert(1)//",
    '<abbr title="&lt;img src=x onerror=alert(1)&gt;">t</abbr>',
    "<div>" * 400 + "deep" + "</div>" * 400,
]

TAG_NAME = re.compile(r"<\s*/?\s*([^\s/>]+)")


def _attribute_problems(cleaned):
    problems = []
    for element in BeautifulSoup(cleaned, "html.parser").find_all(True):
        if element.name not in ALLOWED_TAGS:
            problems.append(element.name)
        allowed = ALLOWED_ATTRS.get(element.name, set()) | ({"rel", "target"} if element.name == "a" else set())
        for key, value in element.attrs.items():
            if key not in allowed:
                problems.append(f"{element.name}[{key}]")
            if key in {"href", "src"} and not re.match(r"^(https?:|mailto:|tel:|/|#|data:image/)", value):
                problems.append(f"{element.name}[{key}]={value}")
            if key == "target" and value != "_blank":
                problems.append(f"{element.name}[target]={value}")
    return problems


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_known_xss_payloads_leave_only_inert_markup(payload):
    cleaned = clean_html(payload)
    assert "\x00" not in cleaned
    for marker in ("<!", "<?", "]]>"):
        assert marker not in cleaned
    assert {name.lower() for name in TAG_NAME.findall(cleaned)} <= ALLOWED_TAGS
    assert _attribute_problems(cleaned) == []
    lowered = cleaned.lower()
    for scheme in ("javascript:", "vbscript:", "data:text"):
        assert f'="{scheme}' not in lowered
    assert clean_html(cleaned) == cleaned


def test_markup_inside_a_comment_or_cdata_never_comes_alive():
    assert clean_html("<p>a</p><!--><img src=x onerror=alert(1)>--><p>b</p>") == "<p>a</p><p>b</p>"
    assert clean_html("<![CDATA[ ><img src=x onerror=alert(2)> ]]>") == ""


def test_attribute_values_are_quoted_and_escaped():
    assert clean_html('<abbr title="a&quot; onmouseover=&quot;x">t</abbr>') == (
        '<abbr title="a&quot; onmouseover=&quot;x">t</abbr>'
    )


def test_obfuscated_script_urls_are_dropped_but_the_text_stays():
    for href in ("java&#x09;script:alert(1)", "&#106;avascript:alert(1)", " \x01javascript:alert(1)", "javas&#99;ript&colon;x"):
        assert clean_html(f'<a href="{href}">Link</a>') == '<a rel="noopener noreferrer" target="_blank">Link</a>'


def test_image_data_urls_only_stay_on_images():
    assert 'src="data:image/png;base64,AAAA"' in clean_html('<img src="data:image/png;base64,AAAA">')
    assert "data:" not in clean_html('<a href="data:image/png;base64,AAAA">x</a>')
    assert "data:" not in clean_html('<img src="data:image/x-icon;base64,AAAA">')


def test_size_attributes_only_keep_plain_numbers():
    assert clean_html('<img src="/a.png" width="120" height="50%">') == '<img src="/a.png" width="120" height="50%">'
    assert clean_html('<td colspan="2;x" rowspan="3">x</td>') == '<td rowspan="3">x</td>'


def test_school_links_and_mail_addresses_survive():
    cleaned = clean_html('<a href="mailto:office@school.example">m</a><a href="tel:+49301234">t</a>')
    assert 'href="mailto:office@school.example"' in cleaned
    assert 'href="tel:+49301234"' in cleaned


def test_safe_url_follows_browser_url_parsing():
    assert safe_url("https://example.org/x") == "https://example.org/x"
    assert safe_url(" /iserv/x ") == "/iserv/x"
    assert safe_url("ja\tva\nscript:alert(1)") is None
    assert safe_url("\x00javascript:alert(1)") is None
    assert safe_url("relative/path") is None
    assert is_safe_url("https://example.org") is True
    assert is_safe_url("javascript:alert(1)") is False
