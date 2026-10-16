from .iserv.conferences import LIST_PATH as CONFERENCE_LIST_PATH
from .iserv.conferences import MODULE_PREFIX as CONFERENCE_PREFIX
from .iserv.conferences import is_tab_path, parse_conference_page, parse_conferences
from .iserv.exercises import EXERCISE_PATH, PAST_EXERCISE_PATH, ExerciseShapeError, map_columns, parse_exercises
from .iserv.news import NEWS_PATH, SECTIONS, first_item_shape, parse_news, section_links
from .iserv.news_detail import detail_shape
from .iserv.pages import path_of, status_of
from .pageshape import body_kind, code_text
from .pathpattern import placeholders
from .valueshape import link_shape

from .task_service import stored_shape

EXERCISE_SLUG = "exercise"
CONFERENCE_SLUG = "parentconference"
NEWS_SLUG = "news"
EXTRA_TARGETS = {EXERCISE_SLUG: ((PAST_EXERCISE_PATH, None),)}
UNMAPPED = "-"
OTHER = "other"


def extra_targets(slug):
    return EXTRA_TARGETS.get(slug, ())


def _html(response):
    if response is None or status_of(response) != 200 or body_kind(response) != "html":
        return None
    return getattr(response, "text", "") or ""


def _task_lines(path, response):
    html = _html(response)
    if html is None:
        return []
    try:
        parsed = parse_exercises(html, path, path == PAST_EXERCISE_PATH)
    except ExerciseShapeError:
        return ["- Task list %s: no task table found" % link_shape(path)]
    mapping = map_columns(parsed["labels"])
    columns = [mapping.get(index) or (OTHER if label else UNMAPPED) for index, label in enumerate(parsed["labels"])]
    tasks = parsed["tasks"]
    return [
        "- Task list %s: columns %s; tasks read %d (with detail link %d, with due date %d, done known %d); more pages %d"
        % (
            link_shape(path),
            " | ".join(columns) or "none",
            len(tasks),
            sum(1 for task in tasks if task["path"]),
            sum(1 for task in tasks if task["due"]),
            sum(1 for task in tasks if task["done"] is not None),
            len(parsed["pages"]),
        )
    ]


def _shape_label(shape):
    return shape["tag"] + "".join("." + code_text(placeholders(name)) for name in shape["classes"])


def _counts(shape):
    return ", ".join("%s x%d" % (name, count) for name, count in sorted(shape["children"].items())) or "none"


def _yes(value):
    return "yes" if value else "no"


def _news_detail_lines(client, items):
    if client is None or not items:
        return []
    path = items[0]["path"]
    try:
        response = client.fetch(path)
    except Exception as error:
        return ["- News detail %s: error (%s)" % (link_shape(path), type(error).__name__)]
    html = _html(response)
    final = path_of(getattr(response, "url", "") or "") if response is not None else ""
    if html is None or final.rstrip("/") != path.rstrip("/"):
        moved = ", final %s" % link_shape(final) if final and final.rstrip("/") != path.rstrip("/") else ""
        status = status_of(response) if response is not None else "-"
        return ["- News detail %s: answered %s%s" % (link_shape(path), status, moved)]
    shape = detail_shape(html, path)
    return [
        "- News detail shape: %s with %s; text lines %d, images %d, files %d, links %d, time tag %s, definition list %s"
        % (
            _shape_label(shape),
            _counts(shape),
            shape["lines"],
            shape["images"],
            shape["files"],
            shape["links"],
            _yes(shape["time_tag"]),
            _yes(shape["definition_list"]),
        )
    ]


def _news_lines(response, client=None):
    html = _html(response)
    if html is None:
        return []
    parsed = parse_news(html, NEWS_PATH)
    found = section_links(html)
    lines = [
        "- News list: items read %d, with date %d, more pages %d" % (
            len(parsed["items"]),
            sum(1 for item in parsed["items"] if item["date"]),
            len(parsed["pages"]),
        ),
        "- News sections linked: %s" % ", ".join("%s %s" % (section, _yes(section in found)) for section in SECTIONS),
    ]
    shape = first_item_shape(html)
    if shape is None:
        return lines
    label = _shape_label(shape)
    inner = _counts(shape)
    lines.append(
        "- News item shape: %s with %s; title %s, date %s, time tag %s, category link %s"
        % (
            label,
            inner,
            "yes" if shape["title"] else "no",
            "yes" if shape["date"] else "no",
            "yes" if shape["time_tag"] else "no",
            "yes" if shape["category"] else "no",
        )
    )
    return lines + _news_detail_lines(client, parsed["items"])


def _form_line(form):
    fields = ", ".join("%s %s" % (code_text(placeholders(field["name"])), field["type"]) for field in form.get("fields") or []) or "none"
    return "  - Form %s (%s%s%s): operations %s; submits %d; targets %d; fields %s" % (
        form.get("kind"),
        form.get("method"),
        ", multipart" if form.get("multipart") else "",
        "" if form.get("writable") else ", not writable",
        " ".join(form.get("operations") or []) or "none",
        int(form.get("submits") or 0),
        int(form.get("targets") or 0),
        fields,
    )


def task_detail_lines(store, connection_id):
    if store is None or not connection_id:
        return []
    try:
        shape = stored_shape(store, connection_id)
    except Exception as error:
        return ["- Task detail shape: unreadable (%s)" % type(error).__name__]
    if not shape:
        return ["- Task detail shape: no task opened in the app yet; the report does not open one"]
    sections = shape.get("sections") or {}
    parts = [
        "%s lines %d files %d images %d links %d facts %d" % (
            name,
            int(counts.get("lines") or 0),
            int(counts.get("files") or 0),
            int(counts.get("images") or 0),
            int(counts.get("links") or 0),
            int(counts.get("facts") or 0),
        )
        for name, counts in sorted(sections.items())
        if isinstance(counts, dict)
    ]
    lines = [
        "- Task detail shape (as seen when a task was last opened in the app): headings %s; %s; start %s, due %s, tags %d, state %s"
        % (
            " ".join(str(item) for item in shape.get("headings") or []) or "none",
            "; ".join(parts) or "no sections",
            _yes(shape.get("start")),
            _yes(shape.get("due")),
            int(shape.get("tags") or 0),
            _yes(shape.get("state")),
        )
    ]
    lines.extend(_form_line(form) for form in shape.get("forms") or [] if isinstance(form, dict))
    return lines


def list_lines(slug, answers, client=None):
    if slug == EXERCISE_SLUG:
        lines = []
        for path in (EXERCISE_PATH, PAST_EXERCISE_PATH):
            lines.extend(_task_lines(path, answers.get(path)))
        return lines
    if slug == NEWS_SLUG:
        return _news_lines(answers.get(NEWS_PATH), client)
    if slug == CONFERENCE_SLUG:
        return conference_list_lines(CONFERENCE_LIST_PATH, answers.get(CONFERENCE_LIST_PATH))
    return []


def conference_list_lines(path, response):
    html = _html(response)
    if html is None:
        return []
    parsed = parse_conferences(html, str(getattr(response, "url", "") or ""))
    items = parsed.get("items") or []
    if parsed.get("error"):
        state = "unreadable"
    elif parsed.get("empty"):
        state = "empty"
    elif any(item.get("headers") for item in items):
        state = "table"
    else:
        state = "blocks"
    cells = sorted({len(item.get("cells") or []) for item in items})
    return [
        "- Conference list %s: read as %s, items %d, with page link %d, cells per item %s"
        % (
            link_shape(path),
            state,
            len(items),
            sum(1 for item in items if item.get("paths")),
            ",".join(str(count) for count in cells) or "-",
        )
    ]


def crawl_page_lines(prefix, response):
    if prefix != CONFERENCE_PREFIX:
        return []
    html = _html(response)
    if html is None:
        return []
    url = str(getattr(response, "url", "") or "")
    if is_tab_path(path_of(url)):
        return conference_list_lines(path_of(url), response)
    return conference_page_lines(parse_conference_page(html, url))


def conference_page_lines(page):
    kinds = {}
    for block in page["blocks"]:
        kinds[block["kind"]] = kinds.get(block["kind"], 0) + 1
    tables = [block for block in page["blocks"] if block["kind"] == "table"]
    links = sum(len(block["links"]) for block in page["blocks"] if block["kind"] == "links")
    tones = {}
    for notice in page["notices"]:
        tones[notice["tone"]] = tones.get(notice["tone"], 0) + 1
    lines = [
        "- App reading: title %s, blocks %s; page links %d; notices %s"
        % (
            "yes" if page["title"] else "no",
            ", ".join("%s %d" % (kind, count) for kind, count in sorted(kinds.items())) or "none",
            links,
            ", ".join("%s %d" % (tone, count) for tone, count in sorted(tones.items())) or "none",
        )
    ]
    for number, table in enumerate(tables, 1):
        rows = table["rows"]
        lines.append(
            "- App table %d: columns %d, rows %d, rows with page link %d, rows with form %d"
            % (number, len(table["headers"]), len(rows), sum(1 for row in rows if row["links"]), sum(1 for row in rows if row["forms"]))
        )
    for number, form in enumerate(page["forms"], 1):
        lines.append(conference_form_line(number, form))
    return lines


def conference_form_line(number, form):
    kinds = {}
    for field in form["fields"]:
        kinds[field["kind"]] = kinds.get(field["kind"], 0) + 1
    choices = []
    for field in form["fields"]:
        if field["kind"] in ("radio", "select"):
            options = field["options"]
            choices.append("%s %d/%d" % (field["kind"], sum(1 for option in options if not option["disabled"]), len(options)))
    return "- App form %d: %s %s; fields %s; open choices %s; required %d; submits %d (destructive %d); errors %d%s" % (
        number,
        form["method"].upper(),
        link_shape(form["action"]),
        ", ".join("%s %d" % (kind, count) for kind, count in sorted(kinds.items())) or "none",
        ", ".join(choices) or "none",
        sum(1 for field in form["fields"] if field.get("required")),
        len(form["submits"]),
        sum(1 for submit in form["submits"] if submit["destructive"]),
        len(form["errors"]),
        "; file upload present" if form["unsupported"] else "",
    )
