import zlib

from .truetype import subset_tag

HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
TO_UNICODE_HEAD = (
    "/CIDInit /ProcSet findresource begin\n"
    "12 dict begin\n"
    "begincmap\n"
    "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
    "/CMapName /Adobe-Identity-UCS def\n"
    "/CMapType 2 def\n"
    "1 begincodespacerange\n<0000> <ffff>\nendcodespacerange\n"
)
TO_UNICODE_TAIL = "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
BFCHAR_BLOCK = 100


class PdfBuilder:
    def __init__(self):
        self.bodies = []

    def reserve(self):
        self.bodies.append(None)
        return len(self.bodies)

    def put(self, number, body):
        self.bodies[number - 1] = body

    def add(self, body):
        number = self.reserve()
        self.put(number, body)
        return number

    def add_stream(self, entries, data, compress=False):
        payload = zlib.compress(data, 9) if compress else data
        fields = [entries] if entries else []
        if compress:
            fields.append("/Filter /FlateDecode")
        fields.append(f"/Length {len(payload)}")
        head = ("<< " + " ".join(fields) + " >>").encode("latin-1")
        return self.add(head + b"\nstream\n" + payload + b"\nendstream")

    def render(self, root):
        parts = [HEADER]
        offsets = []
        for index, body in enumerate(self.bodies, start=1):
            offsets.append(sum(len(part) for part in parts))
            parts.append(f"{index} 0 obj\n".encode("latin-1") + body + b"\nendobj\n")
        xref_offset = sum(len(part) for part in parts)
        count = len(self.bodies) + 1
        xref = [f"xref\n0 {count}\n".encode("latin-1"), b"0000000000 65535 f \n"]
        for offset in offsets:
            xref.append(f"{offset:010d} 00000 n \n".encode("latin-1"))
        trailer = (
            f"trailer\n<< /Size {count} /Root {root} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
        return b"".join(parts) + b"".join(xref) + trailer


def _to_unicode_stream(cid_for):
    entries = sorted((cid, code) for code, cid in cid_for.items())
    body = TO_UNICODE_HEAD
    for start in range(0, len(entries), BFCHAR_BLOCK):
        block = entries[start : start + BFCHAR_BLOCK]
        body += f"{len(block)} beginbfchar\n"
        for cid, code in block:
            target = chr(code).encode("utf-16-be").hex()
            body += f"<{cid:04x}> <{target}>\n"
        body += "endbfchar\n"
    return (body + TO_UNICODE_TAIL).encode("latin-1")


def _widths_array(widths):
    return "[0 [" + " ".join(str(width) for width in widths) + "]]"


def embed_truetype(builder, font, codepoints):
    result = font.subset(codepoints)
    base_name = f"{subset_tag(codepoints)}+{font.postscript_name()}"
    file_number = builder.add_stream(
        f"/Length1 {len(result.data)}", result.data, compress=True
    )
    left, bottom, right, top = (int(round(font.scale(value))) for value in font.bbox)
    descriptor = (
        f"<< /Type /FontDescriptor /FontName /{base_name} /Flags 32 "
        f"/FontBBox [{left} {bottom} {right} {top}] /ItalicAngle {font.italic_angle():.1f} "
        f"/Ascent {int(round(font.scale(font.ascent)))} "
        f"/Descent {int(round(font.scale(font.descent)))} "
        f"/CapHeight {int(round(font.scale(font.cap_height())))} "
        f"/StemV {160 if font.weight_class() >= 600 else 80} "
        f"/FontFile2 {file_number} 0 R >>"
    ).encode("latin-1")
    descriptor_number = builder.add(descriptor)
    descendant = (
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{base_name} "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {descriptor_number} 0 R /DW 1000 /W {_widths_array(result.widths)} "
        "/CIDToGIDMap /Identity >>"
    ).encode("latin-1")
    descendant_number = builder.add(descendant)
    to_unicode_number = builder.add_stream("", _to_unicode_stream(result.cid_for), compress=True)
    number = builder.add(
        (
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{base_name} /Encoding /Identity-H "
            f"/DescendantFonts [{descendant_number} 0 R] /ToUnicode {to_unicode_number} 0 R >>"
        ).encode("latin-1")
    )
    return number, result.cid_for


def hex_string(text, cid_for):
    return "<" + "".join(f"{cid_for[ord(char)]:04x}" for char in text) + ">"
