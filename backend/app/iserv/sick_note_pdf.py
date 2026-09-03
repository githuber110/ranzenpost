import unicodedata
from datetime import date
from pathlib import Path

from .absences import WEEKDAYS
from .pdf import PdfBuilder, embed_truetype, hex_string
from .truetype import load_font

DEFAULT_SICK_NOTE_TERM = "Krankmeldung"

BRAND_NAME = "IServ"
BRAND_COLOR = (0.196, 0.408, 0.612)
BLACK = (0, 0, 0)

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_LEFT = 56
MARGIN_RIGHT = 56
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

FONT_DIR = Path(__file__).resolve().parent / "fonts"
REGULAR = "F1"
BOLD = "F2"
START = "start"
END = "end"
FONT_FILES = {REGULAR: "NotoSans-Regular.ttf", BOLD: "NotoSans-Bold.ttf"}

UNSHAPED_SCRIPT_RANGES = (
    (0x0300, 0x036F),
    (0x0483, 0x0489),
    (0x0590, 0x08FF),
    (0x0900, 0x0FFF),
    (0x1000, 0x109F),
    (0x1780, 0x17FF),
    (0x1AB0, 0x1AFF),
    (0x1DC0, 0x1DFF),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2066, 0x2069),
    (0x20D0, 0x20F0),
    (0xFB1D, 0xFDFF),
    (0xFE20, 0xFE2F),
    (0xFE70, 0xFEFF),
)


class UnsupportedTextError(Exception):
    def __init__(self, characters):
        self.characters = list(characters)
        super().__init__("text contains characters the embedded font cannot render")


def sick_note_title(settings):
    settings = settings or {}
    term = str(settings.get("sickNotes_replaceTerm") or "").strip() or DEFAULT_SICK_NOTE_TERM
    return f"Schriftliche Bestätigung der {term}"


def _normalize(value):
    return unicodedata.normalize("NFC", str(value or ""))


def sick_note_pdf_filename(title, name, today=None):
    today = today or date.today()
    stamp = today.strftime("%d.%m.%Y")
    safe_title = _sanitize_filename_part(title)
    safe_name = _sanitize_filename_part(name)
    return f"{safe_title} [{safe_name}] [{stamp}].pdf"


def _sanitize_filename_part(value):
    text = _normalize(value)
    kept = []
    for char in text:
        if char in '"\\/:*?<>|':
            kept.append(" ")
        elif unicodedata.category(char)[0] == "C":
            kept.append(" ")
        else:
            kept.append(char)
    return " ".join("".join(kept).split())


def _format_day(iso_value):
    day = date.fromisoformat(str(iso_value)[:10])
    return f"{WEEKDAYS[day.weekday()]}, den {day.strftime('%d.%m.%Y')}"


def _single_day_period_suffix(from_period, till_period):
    if from_period is not None and till_period is not None:
        if from_period == till_period:
            return f", in der {from_period}. Stunde"
        return f", von der {from_period}. bis einschließlich der {till_period}. Stunde"
    if from_period is not None:
        return f", ab der {from_period}. Stunde"
    if till_period is not None:
        return f", bis einschließlich der {till_period}. Stunde"
    return ""


def sick_note_period_description(from_date, till_date, from_period=None, till_period=None):
    if not from_date:
        return ""
    till_date = till_date or from_date
    if from_date == till_date:
        return f"am {_format_day(from_date)}{_single_day_period_suffix(from_period, till_period)}"
    from_clause = f", ab der {from_period}. Stunde" if from_period is not None else ""
    till_clause = f", bis einschließlich der {till_period}. Stunde" if till_period is not None else ""
    return f"vom {_format_day(from_date)}{from_clause} bis {_format_day(till_date)}{till_clause}"


def _core_sentence(name, class_code, period_text):
    child = f"{name} ({class_code})" if class_code else name
    return (
        f"meine Tochter/mein Sohn, {child}, kann aus gesundheitlichen Gründen "
        f"{period_text}, nicht am Schulunterricht teilnehmen."
    )


def font_for(key):
    return load_font(FONT_DIR / FONT_FILES[key])


def _needs_shaping(char):
    code = ord(char)
    if unicodedata.combining(char):
        return True
    return any(start <= code <= end for start, end in UNSHAPED_SCRIPT_RANGES)


def _unsupported_characters(runs):
    offenders = []
    for text, key, _, _, _, _, _ in runs:
        font = font_for(key)
        for char in text:
            if char in offenders:
                continue
            if _needs_shaping(char) or font.glyph_id(ord(char)) is None:
                offenders.append(char)
    return offenders


def _wrap(font, text, size, max_width):
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.text_width(candidate, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
        while font.text_width(current, size) > max_width and len(current) > 1:
            cut = len(current)
            while cut > 1 and font.text_width(current[:cut], size) > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
    if current:
        lines.append(current)
    return lines


def render_sick_note_pdf(title, name, class_code, from_date, till_date, from_period=None, till_period=None, today=None):
    today = today or date.today()
    title = _normalize(title)
    name = _normalize(name)
    class_code = _normalize(class_code)
    period_text = sick_note_period_description(from_date, till_date, from_period, till_period)
    runs = []
    y = PAGE_HEIGHT - 60
    runs.append((today.strftime("%d.%m.%Y"), REGULAR, 10, BRAND_COLOR, PAGE_WIDTH - MARGIN_RIGHT, y, END))
    y -= 30
    runs.append((BRAND_NAME, BOLD, 17, BRAND_COLOR, MARGIN_LEFT, y, START))
    y -= 40
    for row in _wrap(font_for(BOLD), title, 12, CONTENT_WIDTH):
        runs.append((row, BOLD, 12, BLACK, MARGIN_LEFT, y, START))
        y -= 18
    y -= 12
    runs.append(("Sehr geehrte(r) __________________________,", REGULAR, 11, BLACK, MARGIN_LEFT, y, START))
    y -= 26
    for row in _wrap(font_for(REGULAR), _core_sentence(name, class_code, period_text), 11, CONTENT_WIDTH):
        runs.append((row, REGULAR, 11, BLACK, MARGIN_LEFT, y, START))
        y -= 16
    y -= 10
    runs.append(("Ich bitte Sie, das Fehlen zu entschuldigen.", REGULAR, 11, BLACK, MARGIN_LEFT, y, START))
    y -= 40
    runs.append(("Mit freundlichen Grüßen", REGULAR, 11, BLACK, MARGIN_LEFT, y, START))
    offenders = _unsupported_characters(runs)
    if offenders:
        raise UnsupportedTextError(offenders)
    return _compose(runs)


def _compose(runs):
    used = {}
    for text, key, _, _, _, _, _ in runs:
        used.setdefault(key, set()).update(ord(char) for char in text)
    builder = PdfBuilder()
    catalog = builder.reserve()
    pages = builder.reserve()
    page = builder.reserve()
    resources = []
    cid_maps = {}
    for key in sorted(used):
        number, cid_for = embed_truetype(builder, font_for(key), used[key])
        resources.append(f"/{key} {number} 0 R")
        cid_maps[key] = cid_for
    operations = []
    for text, key, size, color, x, y, align in runs:
        font = font_for(key)
        position = x - font.text_width(text, size) if align == END else x
        red, green, blue = color
        operations.append(
            f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
            f"BT /{key} {size} Tf {position:.2f} {y:.2f} Td "
            f"{hex_string(text, cid_maps[key])} Tj ET"
        )
    content = builder.add_stream("", "\n".join(operations).encode("latin-1"))
    builder.put(catalog, f"<< /Type /Catalog /Pages {pages} 0 R >>".encode("latin-1"))
    builder.put(pages, f"<< /Type /Pages /Kids [{page} 0 R] /Count 1 >>".encode("latin-1"))
    builder.put(
        page,
        (
            f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << {' '.join(resources)} >> >> /Contents {content} 0 R >>"
        ).encode("latin-1"),
    )
    return builder.render(catalog)
