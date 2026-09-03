import re

PRODID = "-//Ranzenpost//IServ Calendar//EN"
TIMEZONE_ID = "Europe/Berlin"
MAX_LINE_OCTETS = 75
REFRESH_INTERVAL = "PT1H"
LINE_BREAK = "\r\n"

VTIMEZONE_LINES = (
    "BEGIN:VTIMEZONE",
    f"TZID:{TIMEZONE_ID}",
    f"X-LIC-LOCATION:{TIMEZONE_ID}",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:+0100",
    "TZOFFSETTO:+0200",
    "TZNAME:CEST",
    "DTSTART:19700329T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0100",
    "TZNAME:CET",
    "DTSTART:19701025T030000",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
)


CSS3_COLORS = {
    "black": (0x00, 0x00, 0x00),
    "dimgray": (0x69, 0x69, 0x69),
    "gray": (0x80, 0x80, 0x80),
    "darkgray": (0xA9, 0xA9, 0xA9),
    "silver": (0xC0, 0xC0, 0xC0),
    "lightgray": (0xD3, 0xD3, 0xD3),
    "white": (0xFF, 0xFF, 0xFF),
    "maroon": (0x80, 0x00, 0x00),
    "firebrick": (0xB2, 0x22, 0x22),
    "brown": (0xA5, 0x2A, 0x2A),
    "indianred": (0xCD, 0x5C, 0x5C),
    "red": (0xFF, 0x00, 0x00),
    "crimson": (0xDC, 0x14, 0x3C),
    "tomato": (0xFF, 0x63, 0x47),
    "orangered": (0xFF, 0x45, 0x00),
    "darkorange": (0xFF, 0x8C, 0x00),
    "orange": (0xFF, 0xA5, 0x00),
    "sienna": (0xA0, 0x52, 0x2D),
    "chocolate": (0xD2, 0x69, 0x1E),
    "peru": (0xCD, 0x85, 0x3F),
    "tan": (0xD2, 0xB4, 0x8C),
    "darkgoldenrod": (0xB8, 0x86, 0x0B),
    "goldenrod": (0xDA, 0xA5, 0x20),
    "gold": (0xFF, 0xD7, 0x00),
    "yellow": (0xFF, 0xFF, 0x00),
    "olive": (0x80, 0x80, 0x00),
    "darkolivegreen": (0x55, 0x6B, 0x2F),
    "darkkhaki": (0xBD, 0xB7, 0x6B),
    "greenyellow": (0xAD, 0xFF, 0x2F),
    "forestgreen": (0x22, 0x8B, 0x22),
    "darkgreen": (0x00, 0x64, 0x00),
    "green": (0x00, 0x80, 0x00),
    "seagreen": (0x2E, 0x8B, 0x57),
    "mediumseagreen": (0x3C, 0xB3, 0x71),
    "lightgreen": (0x90, 0xEE, 0x90),
    "teal": (0x00, 0x80, 0x80),
    "darkcyan": (0x00, 0x8B, 0x8B),
    "lightseagreen": (0x20, 0xB2, 0xAA),
    "cadetblue": (0x5F, 0x9E, 0xA0),
    "turquoise": (0x40, 0xE0, 0xD0),
    "steelblue": (0x46, 0x82, 0xB4),
    "dodgerblue": (0x1E, 0x90, 0xFF),
    "royalblue": (0x41, 0x69, 0xE1),
    "blue": (0x00, 0x00, 0xFF),
    "navy": (0x00, 0x00, 0x80),
    "midnightblue": (0x19, 0x19, 0x70),
    "darkslateblue": (0x48, 0x3D, 0x8B),
    "slateblue": (0x6A, 0x5A, 0xCD),
    "mediumpurple": (0x93, 0x70, 0xDB),
    "purple": (0x80, 0x00, 0x80),
    "darkviolet": (0x94, 0x00, 0xD3),
    "orchid": (0xDA, 0x70, 0xD6),
    "magenta": (0xFF, 0x00, 0xFF),
    "mediumvioletred": (0xC7, 0x15, 0x85),
    "deeppink": (0xFF, 0x14, 0x93),
    "hotpink": (0xFF, 0x69, 0xB4),
    "pink": (0xFF, 0xC0, 0xCB),
}

HEX_COLOR = re.compile(r"^#?([0-9a-fA-F]{6})$")
COLOR_CHANNEL_WEIGHTS = (3, 4, 2)


def parse_hex_color(value):
    match = HEX_COLOR.match(str(value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    return tuple(int(digits[index : index + 2], 16) for index in (0, 2, 4))


def nearest_color_name(value):
    rgb = parse_hex_color(value)
    if rgb is None:
        return ""
    best = ""
    best_distance = None
    for name, reference in CSS3_COLORS.items():
        distance = sum(
            weight * (channel - other) ** 2
            for weight, channel, other in zip(COLOR_CHANNEL_WEIGHTS, rgb, reference)
        )
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = name
    return best


def apple_color(value):
    rgb = parse_hex_color(value)
    if rgb is None:
        return ""
    return "#{:02X}{:02X}{:02X}FF".format(*rgb)


def escape_text(value):
    if not value:
        return ""
    escaped = str(value).replace("\\", "\\\\")
    escaped = escaped.replace(";", "\\;")
    escaped = escaped.replace(",", "\\,")
    escaped = escaped.replace("\r\n", "\\n")
    escaped = escaped.replace("\n", "\\n")
    return escaped


def fold_line(line):
    raw = line.encode("utf-8")
    if len(raw) <= MAX_LINE_OCTETS:
        return line
    chunks = []
    start = 0
    limit = MAX_LINE_OCTETS
    while start < len(raw):
        end = min(start + limit, len(raw))
        while end > start and end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
        limit = MAX_LINE_OCTETS - 1
    return ("\r\n ").join(chunks)


def format_utc(moment):
    return moment.strftime("%Y%m%dT%H%M%SZ")


def format_local(moment):
    return moment.strftime("%Y%m%dT%H%M%S")


def format_day(value):
    return value.strftime("%Y%m%d")


def _start_property(value, all_day):
    if all_day:
        return f"DTSTART;VALUE=DATE:{format_day(value)}"
    return f"DTSTART;TZID={TIMEZONE_ID}:{format_local(value)}"


def _end_property(value, all_day):
    if all_day:
        return f"DTEND;VALUE=DATE:{format_day(value)}"
    return f"DTEND;TZID={TIMEZONE_ID}:{format_local(value)}"


def render_event(event, sequence, last_modified):
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.uid}",
        f"DTSTAMP:{last_modified}",
        f"LAST-MODIFIED:{last_modified}",
        f"SEQUENCE:{sequence}",
        _start_property(event.start, event.all_day),
        _end_property(event.end, event.all_day),
        f"SUMMARY:{escape_text(event.summary)}",
    ]
    if event.location:
        lines.append(f"LOCATION:{escape_text(event.location)}")
    if event.description:
        lines.append(f"DESCRIPTION:{escape_text(event.description)}")
    if event.category:
        lines.append(f"CATEGORIES:{escape_text(event.category)}")
    color_name = nearest_color_name(event.color)
    if color_name:
        lines.append(f"COLOR:{color_name}")
    lines.append("TRANSP:TRANSPARENT" if event.transparent else "TRANSP:OPAQUE")
    lines.append("END:VEVENT")
    return lines


def render_calendar(name, rendered_events, color=""):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"NAME:{escape_text(name)}",
        f"X-WR-CALNAME:{escape_text(name)}",
        f"X-WR-TIMEZONE:{TIMEZONE_ID}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH_INTERVAL}",
        f"X-PUBLISHED-TTL:{REFRESH_INTERVAL}",
    ]
    calendar_color = nearest_color_name(color)
    if calendar_color:
        lines.append(f"COLOR:{calendar_color}")
        lines.append(f"X-APPLE-CALENDAR-COLOR:{apple_color(color)}")
    lines.extend(VTIMEZONE_LINES)
    for block in rendered_events:
        lines.extend(block)
    lines.append("END:VCALENDAR")
    return LINE_BREAK.join(fold_line(line) for line in lines) + LINE_BREAK
