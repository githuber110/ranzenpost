import html

THEMES = {
    "light": {"background": "#ffffff", "ink": "#101917", "link": "#0e6b70", "quote": "#66807a"},
    "dark": {"background": "#18201e", "ink": "#e9efed", "link": "#4fbdba", "quote": "#627470"},
}
FRAME_POLICY = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src 'none'; "
    "base-uri 'none'; form-action 'none'; upgrade-insecure-requests; "
    "sandbox allow-popups allow-popups-to-escape-sandbox"
)
STYLE = (
    "html{color-scheme:%(scheme)s}"
    "body{margin:0;padding:16px;background:%(background)s;color:%(ink)s;"
    "font:15px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;overflow-wrap:anywhere}"
    "a{color:%(link)s}img{max-width:100%%;height:auto}"
    "table,pre{max-width:100%%;overflow-x:auto;display:block}"
    "blockquote{margin:0;padding-inline-start:12px;border-inline-start:3px solid %(quote)s}"
    "pre.text{white-space:pre-wrap;font:inherit;margin:0}"
)


def theme_of(value):
    return value if value in THEMES else "light"


def document(detail, theme="light"):
    chosen = theme_of(theme)
    colours = dict(THEMES[chosen], scheme=chosen)
    if detail.get("body_html"):
        body = detail["body_html"]
    else:
        body = '<pre class="text" dir="auto">%s</pre>' % html.escape(detail.get("body_text") or "")
    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
        '<base target="_blank"><style>%s</style></head><body dir="auto">%s</body></html>'
    ) % (STYLE % colours, body)
