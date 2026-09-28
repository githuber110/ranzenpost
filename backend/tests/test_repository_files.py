import pathlib
import struct
import subprocess
import zlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _git(*args):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        pytest.skip(f"git is not usable here: {result.stderr.strip()[:120]}")
    return result.stdout


def _has_git():
    return (ROOT / ".git").exists()


def _excluded_names():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    names = set()
    for line in text.splitlines():
        entry = line.strip().rstrip("/")
        if not entry or entry.startswith("#") or entry.startswith("!") or "*" in entry:
            continue
        names.add(entry.lower())
    return names


def test_nothing_the_ignore_list_excludes_is_tracked_anyway():
    if not _has_git():
        pytest.skip("no git checkout")
    excluded = _excluded_names()
    assert excluded, "the ignore list should not be empty"
    tracked = [line.strip() for line in _git("ls-files").splitlines() if line.strip()]
    offenders = [
        path
        for path in tracked
        if path.lower() in excluded or pathlib.PurePosixPath(path).name.lower() in excluded
    ]
    assert offenders == [], f"these are excluded but tracked anyway: {offenders}"


def _png_chunk(ctype, data):
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data))


def _minimal_png(text_chunks=()):
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    body = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
    for keyword, value in text_chunks:
        body += _png_chunk(b"tEXt", keyword.encode("latin-1") + b"\x00" + value.encode("latin-1"))
    body += _png_chunk(b"IEND", b"")
    return body


def _png_text_chunks(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return []
    i = 8
    n = len(data)
    found = []
    while i + 8 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        cdata = data[i + 8 : i + 8 + length]
        i += 8 + length + 4
        if ctype == b"tEXt":
            keyword, _, text = cdata.partition(b"\x00")
            found.append((keyword.decode("latin-1", "replace"), text.decode("latin-1", "replace")))
        elif ctype == b"zTXt":
            keyword, _, rest = cdata.partition(b"\x00")
            if len(rest) >= 1:
                payload = rest[1:]
                try:
                    text = zlib.decompress(payload).decode("latin-1", "replace")
                except zlib.error:
                    text = ""
                found.append((keyword.decode("latin-1", "replace"), text))
        elif ctype == b"iTXt":
            keyword, _, rest = cdata.partition(b"\x00")
            if len(rest) >= 2:
                flag = rest[0]
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _translated, _, text_bytes = rest.partition(b"\x00")
                if flag:
                    try:
                        text_bytes = zlib.decompress(text_bytes)
                    except zlib.error:
                        text_bytes = b""
                found.append((keyword.decode("latin-1", "replace"), text_bytes.decode("utf-8", "replace")))
    return found


def _tracked_pngs():
    return [line.strip() for line in _git("ls-files", "*.png", "*.PNG").splitlines() if line.strip()]


def test_no_tracked_png_carries_text_metadata():
    if not _has_git():
        pytest.skip("no git checkout")
    offenders = []
    for path in _tracked_pngs():
        full = ROOT / path
        try:
            data = full.read_bytes()
        except OSError:
            continue
        for keyword, text in _png_text_chunks(data):
            if text.strip():
                offenders.append(f"{path}: {keyword}={text[:80]!r}")
    assert offenders == [], f"a public repo should not ship screenshot metadata: {offenders}"


def test_png_text_chunk_scanner_flags_a_planted_chunk_and_ignores_a_clean_png():
    planted = _minimal_png([("Comment", "captured on a desktop")])
    hits = _png_text_chunks(planted)
    assert hits == [("Comment", "captured on a desktop")]

    clean = _minimal_png()
    assert _png_text_chunks(clean) == []
