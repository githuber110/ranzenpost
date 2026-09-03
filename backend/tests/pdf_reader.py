import re
import zlib

OBJECT_START = re.compile(rb" obj\n")
TEXT_OP = re.compile(
    rb"BT /(\w+) ([\d.]+) Tf (-?[\d.]+) (-?[\d.]+) Td <([0-9a-f]*)> Tj ET"
)
BFCHAR = re.compile(rb"<([0-9a-fA-F]{4})> <([0-9a-fA-F]+)>")


def _xref_offsets(pdf):
    start = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    lines = pdf[start:].split(b"\n")
    count = int(lines[1].split()[1])
    return [int(lines[2 + number].split()[0]) for number in range(1, count)]


def objects(pdf):
    found = {}
    for number, offset in enumerate(_xref_offsets(pdf), start=1):
        body = OBJECT_START.split(pdf[offset:], maxsplit=1)[1]
        if b"stream\n" in body[:400]:
            head, rest = body.split(b"stream\n", 1)
            length = int(re.search(rb"/Length (\d+)", head).group(1))
            data = rest[:length]
            if b"/FlateDecode" in head:
                data = zlib.decompress(data)
            found[number] = (head, data)
        else:
            found[number] = (body.split(b"\nendobj", 1)[0], None)
    return found


def _reference(head, key):
    match = re.search(key.encode("ascii") + rb" (\d+) 0 R", head)
    return int(match.group(1)) if match else None


def _page(parsed):
    for head, _ in parsed.values():
        if b"/Type /Page " in head:
            return head
    raise AssertionError("pdf has no page object")


def font_resources(pdf):
    parsed = objects(pdf)
    page = _page(parsed)
    block = re.search(rb"/Font << (.*?) >>", page).group(1)
    return {
        name.decode("ascii"): int(number)
        for name, number in re.findall(rb"/(\w+) (\d+) 0 R", block)
    }, parsed


def to_unicode_maps(pdf):
    resources, parsed = font_resources(pdf)
    maps = {}
    for name, number in resources.items():
        head = parsed[number][0]
        stream = parsed[_reference(head, "/ToUnicode")][1]
        maps[name] = {
            int(cid, 16): bytes.fromhex(target.decode("ascii")).decode("utf-16-be")
            for cid, target in BFCHAR.findall(stream)
        }
    return maps


def font_programs(pdf):
    resources, parsed = font_resources(pdf)
    programs = {}
    for name, number in resources.items():
        block = re.search(rb"/DescendantFonts \[(\d+) 0 R\]", parsed[number][0])
        descendant = int(block.group(1))
        descriptor = _reference(parsed[descendant][0], "/FontDescriptor")
        head, data = parsed[_reference(parsed[descriptor][0], "/FontFile2")]
        programs[name] = (int(re.search(rb"/Length1 (\d+)", head).group(1)), data)
    return programs


def content_stream(pdf):
    resources, parsed = font_resources(pdf)
    page = _page(parsed)
    return parsed[_reference(page, "/Contents")][1]


def text_runs(pdf):
    maps = to_unicode_maps(pdf)
    runs = []
    for name, size, x, y, payload in TEXT_OP.findall(content_stream(pdf)):
        key = name.decode("ascii")
        digits = payload.decode("ascii")
        text = "".join(
            maps[key][int(digits[index : index + 4], 16)]
            for index in range(0, len(digits), 4)
        )
        runs.append((key, float(size), float(x), float(y), text))
    return runs


def visible_text(pdf):
    return "\n".join(run[4] for run in text_runs(pdf))
