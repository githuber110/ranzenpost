import math
import struct
from pathlib import Path

ARGS_ARE_WORDS = 0x0001
HAS_SCALE = 0x0008
MORE_COMPONENTS = 0x0020
HAS_X_AND_Y_SCALE = 0x0040
HAS_TWO_BY_TWO = 0x0080

CHECKSUM_MAGIC = 0xB1B0AFBA
SUBSET_TAG_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class FontDataError(Exception):
    pass


def _u16(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def _s16(data, offset):
    return struct.unpack_from(">h", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def _checksum(data):
    padded = bytes(data) + b"\x00" * (-len(data) % 4)
    total = 0
    for index in range(0, len(padded), 4):
        total = (total + struct.unpack_from(">I", padded, index)[0]) & 0xFFFFFFFF
    return total


def _parse_cmap_format_4(data, offset):
    segment_count = _u16(data, offset + 6) // 2
    ends = offset + 14
    starts = ends + segment_count * 2 + 2
    deltas = starts + segment_count * 2
    ranges = deltas + segment_count * 2
    mapping = {}
    for index in range(segment_count):
        end = _u16(data, ends + index * 2)
        start = _u16(data, starts + index * 2)
        delta = _u16(data, deltas + index * 2)
        range_offset = _u16(data, ranges + index * 2)
        if start > end or start == 0xFFFF:
            continue
        for code in range(start, end + 1):
            if range_offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                position = ranges + index * 2 + range_offset + (code - start) * 2
                if position + 2 > len(data):
                    continue
                glyph = _u16(data, position)
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            if glyph:
                mapping[code] = glyph
    return mapping


def _parse_cmap_format_12(data, offset):
    groups = _u32(data, offset + 12)
    mapping = {}
    for index in range(groups):
        base = offset + 16 + index * 12
        start = _u32(data, base)
        end = _u32(data, base + 4)
        glyph = _u32(data, base + 8)
        if end - start > 0x10FFFF:
            continue
        for step in range(end - start + 1):
            mapping[start + step] = glyph + step
    return mapping


def _parse_cmap_format_6(data, offset):
    first = _u16(data, offset + 6)
    count = _u16(data, offset + 8)
    mapping = {}
    for index in range(count):
        glyph = _u16(data, offset + 10 + index * 2)
        if glyph:
            mapping[first + index] = glyph
    return mapping


def _subtable_rank(platform, encoding):
    if (platform, encoding) == (3, 10):
        return 4
    if (platform, encoding) == (3, 1):
        return 3
    if platform == 0:
        return 2
    return 1


class TrueTypeFont:
    def __init__(self, data, source=""):
        self.data = bytes(data)
        self.source = source
        self.tables = {}
        self._read_directory()
        self._read_headers()
        self._read_hmtx()
        self._read_loca()
        self.cmap = self._read_cmap()

    def _read_directory(self):
        if len(self.data) < 12 or _u32(self.data, 0) not in (0x00010000, 0x74727565):
            raise FontDataError("unsupported font container")
        count = _u16(self.data, 4)
        for index in range(count):
            base = 12 + index * 16
            tag = self.data[base : base + 4].decode("latin-1")
            offset = _u32(self.data, base + 8)
            length = _u32(self.data, base + 12)
            if offset + length > len(self.data):
                raise FontDataError("truncated font table")
            self.tables[tag] = (offset, length)
        for tag in ("head", "hhea", "maxp", "hmtx", "loca", "glyf", "cmap"):
            if tag not in self.tables:
                raise FontDataError("font is missing table " + tag)

    def table(self, tag):
        offset, length = self.tables[tag]
        return self.data[offset : offset + length]

    def _read_headers(self):
        head = self.table("head")
        self.units_per_em = _u16(head, 18) or 1000
        self.index_to_loc_format = _s16(head, 50)
        self.bbox = (_s16(head, 36), _s16(head, 38), _s16(head, 40), _s16(head, 42))
        maxp = self.table("maxp")
        self.num_glyphs = _u16(maxp, 4)
        hhea = self.table("hhea")
        self.ascent = _s16(hhea, 4)
        self.descent = _s16(hhea, 6)
        self.number_of_h_metrics = _u16(hhea, 34)

    def _read_hmtx(self):
        hmtx = self.table("hmtx")
        self.advances = []
        self.side_bearings = []
        last = 0
        for index in range(self.num_glyphs):
            if index < self.number_of_h_metrics:
                last = _u16(hmtx, index * 4)
                bearing = _s16(hmtx, index * 4 + 2)
            else:
                position = self.number_of_h_metrics * 4 + (index - self.number_of_h_metrics) * 2
                bearing = _s16(hmtx, position) if position + 2 <= len(hmtx) else 0
            self.advances.append(last)
            self.side_bearings.append(bearing)

    def _read_loca(self):
        loca = self.table("loca")
        self.loca = []
        if self.index_to_loc_format:
            for index in range(self.num_glyphs + 1):
                self.loca.append(_u32(loca, index * 4))
        else:
            for index in range(self.num_glyphs + 1):
                self.loca.append(_u16(loca, index * 2) * 2)

    def _read_cmap(self):
        cmap = self.table("cmap")
        count = _u16(cmap, 2)
        best = None
        best_rank = 0
        for index in range(count):
            base = 4 + index * 8
            platform = _u16(cmap, base)
            encoding = _u16(cmap, base + 2)
            offset = _u32(cmap, base + 4)
            if offset + 4 > len(cmap):
                continue
            rank = _subtable_rank(platform, encoding)
            if rank > best_rank:
                best_rank = rank
                best = offset
        if best is None:
            raise FontDataError("font has no usable cmap subtable")
        table_format = _u16(cmap, best)
        if table_format == 4:
            return _parse_cmap_format_4(cmap, best)
        if table_format == 12:
            return _parse_cmap_format_12(cmap, best)
        if table_format == 6:
            return _parse_cmap_format_6(cmap, best)
        raise FontDataError("unsupported cmap format")

    def postscript_name(self):
        if "name" not in self.tables:
            return "EmbeddedFont"
        name = self.table("name")
        count = _u16(name, 2)
        storage = _u16(name, 4)
        found = ""
        for index in range(count):
            base = 6 + index * 12
            platform = _u16(name, base)
            name_id = _u16(name, base + 6)
            length = _u16(name, base + 8)
            offset = _u16(name, base + 10)
            if name_id != 6:
                continue
            raw = name[storage + offset : storage + offset + length]
            text = raw.decode("utf-16-be", "ignore") if platform == 3 else raw.decode("latin-1", "ignore")
            text = "".join(char for char in text if 33 <= ord(char) <= 126 and char not in "()<>[]{}/%")
            if text:
                found = text
                if platform == 3:
                    break
        return found or "EmbeddedFont"

    def italic_angle(self):
        if "post" not in self.tables:
            return 0.0
        post = self.table("post")
        if len(post) < 8:
            return 0.0
        return struct.unpack_from(">l", post, 4)[0] / 65536.0

    def cap_height(self):
        if "OS/2" not in self.tables:
            return self.ascent
        table = self.table("OS/2")
        if _u16(table, 0) >= 2 and len(table) >= 90:
            return _s16(table, 88) or self.ascent
        return self.ascent

    def weight_class(self):
        if "OS/2" not in self.tables:
            return 400
        return _u16(self.table("OS/2"), 4)

    def embedding_allowed(self):
        if "OS/2" not in self.tables:
            return True
        return not _u16(self.table("OS/2"), 8) & 0x0002

    def glyph_id(self, codepoint):
        return self.cmap.get(codepoint)

    def missing_glyphs(self, text):
        return [char for char in text if ord(char) not in self.cmap]

    def scale(self, value):
        return value * 1000.0 / self.units_per_em

    def advance_for(self, codepoint):
        glyph = self.cmap.get(codepoint)
        if glyph is None or glyph >= len(self.advances):
            return 0
        return self.advances[glyph]

    def text_width(self, text, size):
        total = sum(self.advance_for(ord(char)) for char in text)
        return total * size / self.units_per_em

    def glyph_bytes(self, glyph):
        glyf_offset, _ = self.tables["glyf"]
        start = self.loca[glyph]
        end = self.loca[glyph + 1]
        if end <= start:
            return b""
        return self.data[glyf_offset + start : glyf_offset + end]

    def _components(self, blob):
        if len(blob) < 10 or _s16(blob, 0) >= 0:
            return []
        found = []
        position = 10
        while position + 4 <= len(blob):
            flags = _u16(blob, position)
            found.append(_u16(blob, position + 2))
            position += 4
            position += 4 if flags & ARGS_ARE_WORDS else 2
            if flags & HAS_SCALE:
                position += 2
            elif flags & HAS_X_AND_Y_SCALE:
                position += 4
            elif flags & HAS_TWO_BY_TWO:
                position += 8
            if not flags & MORE_COMPONENTS:
                break
        return found

    def _closure(self, glyphs):
        seen = set()
        pending = list(glyphs)
        while pending:
            glyph = pending.pop()
            if glyph in seen or glyph >= self.num_glyphs:
                continue
            seen.add(glyph)
            pending.extend(self._components(self.glyph_bytes(glyph)))
        return seen

    def _remapped_glyph(self, glyph, remap):
        blob = self.glyph_bytes(glyph)
        if not blob or _s16(blob, 0) >= 0:
            return blob
        out = bytearray(blob)
        position = 10
        while position + 4 <= len(out):
            flags = _u16(out, position)
            component = _u16(out, position + 2)
            struct.pack_into(">H", out, position + 2, remap.get(component, 0))
            position += 4
            position += 4 if flags & ARGS_ARE_WORDS else 2
            if flags & HAS_SCALE:
                position += 2
            elif flags & HAS_X_AND_Y_SCALE:
                position += 4
            elif flags & HAS_TWO_BY_TWO:
                position += 8
            if not flags & MORE_COMPONENTS:
                break
        return bytes(out)

    def subset(self, codepoints):
        wanted = {}
        for codepoint in sorted(set(codepoints)):
            glyph = self.cmap.get(codepoint)
            if glyph is not None:
                wanted[codepoint] = glyph
        order = sorted(self._closure(set(wanted.values()) | {0}))
        remap = {old: new for new, old in enumerate(order)}
        glyf = bytearray()
        offsets = []
        for old in order:
            offsets.append(len(glyf))
            blob = self._remapped_glyph(old, remap)
            if blob:
                glyf += blob
                glyf += b"\x00" * (-len(glyf) % 4)
        offsets.append(len(glyf))
        loca = b"".join(struct.pack(">I", offset) for offset in offsets)
        hmtx = b"".join(
            struct.pack(">Hh", self.advances[old], self.side_bearings[old]) for old in order
        )
        head = bytearray(self.table("head"))
        struct.pack_into(">I", head, 8, 0)
        struct.pack_into(">h", head, 50, 1)
        hhea = bytearray(self.table("hhea"))
        struct.pack_into(">H", hhea, 34, len(order))
        maxp = bytearray(self.table("maxp"))
        struct.pack_into(">H", maxp, 4, len(order))
        tables = {
            "head": bytes(head),
            "hhea": bytes(hhea),
            "maxp": bytes(maxp),
            "hmtx": hmtx,
            "loca": loca,
            "glyf": bytes(glyf),
            "cmap": _build_cmap({code: remap[glyph] for code, glyph in wanted.items()}),
        }
        for tag in ("cvt ", "fpgm", "prep"):
            if tag in self.tables:
                tables[tag] = self.table(tag)
        widths = [int(round(self.scale(self.advances[old]))) for old in order]
        return SubsetFont(
            _assemble(tables),
            {code: remap[glyph] for code, glyph in wanted.items()},
            widths,
        )


class SubsetFont:
    def __init__(self, data, cid_for, widths):
        self.data = data
        self.cid_for = cid_for
        self.widths = widths


def _build_cmap(mapping):
    codes = sorted(code for code in mapping if code < 0xFFFF)
    segments = [(code, code, (mapping[code] - code) & 0xFFFF) for code in codes]
    segments.append((0xFFFF, 0xFFFF, 1))
    count = len(segments)
    entry_selector = int(math.log2(count)) if count else 0
    search_range = 2 * (2**entry_selector)
    subtable = struct.pack(
        ">HHHHHHH",
        4,
        16 + count * 8,
        0,
        count * 2,
        search_range,
        entry_selector,
        count * 2 - search_range,
    )
    subtable += b"".join(struct.pack(">H", end) for _, end, _ in segments)
    subtable += b"\x00\x00"
    subtable += b"".join(struct.pack(">H", start) for start, _, _ in segments)
    subtable += b"".join(struct.pack(">H", delta) for _, _, delta in segments)
    subtable += b"\x00\x00" * count
    return struct.pack(">HHHHI", 0, 1, 3, 1, 12) + subtable


def _assemble(tables):
    tags = sorted(tables)
    count = len(tags)
    entry_selector = int(math.log2(count)) if count else 0
    search_range = 16 * (2**entry_selector)
    header = struct.pack(
        ">IHHHH", 0x00010000, count, search_range, entry_selector, count * 16 - search_range
    )
    offset = 12 + 16 * count
    records = b""
    body = b""
    head_position = None
    for tag in tags:
        data = bytes(tables[tag])
        if tag == "head":
            head_position = offset
        records += struct.pack(">4sIII", tag.encode("latin-1"), _checksum(data), offset, len(data))
        padded = data + b"\x00" * (-len(data) % 4)
        body += padded
        offset += len(padded)
    font = bytearray(header + records + body)
    if head_position is not None:
        adjustment = (CHECKSUM_MAGIC - _checksum(font)) & 0xFFFFFFFF
        struct.pack_into(">I", font, head_position + 8, adjustment)
    return bytes(font)


def subset_tag(codepoints):
    total = 0
    for codepoint in sorted(set(codepoints)):
        total = (total * 131 + codepoint) & 0xFFFFFFFF
    letters = ""
    for _ in range(6):
        letters += SUBSET_TAG_LETTERS[total % 26]
        total //= 26
    return letters


_CACHE = {}


def load_font(path):
    key = str(path)
    font = _CACHE.get(key)
    if font is None:
        font = TrueTypeFont(Path(path).read_bytes(), source=Path(path).name)
        _CACHE[key] = font
    return font
