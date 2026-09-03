import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ALLOWED_FILES = {"CLAUDE.md", "LICENSE", "iserv_connector/config.yaml", "repository.yaml", "package.json"}
BINARY_EXTENSIONS = {".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".gif", ".ico"}

FORBIDDEN_HASHES = {
    (11, "6d0b3b6d8a8b63913f448bb0e9d009d2fc232af16d5784537ca1940db2db9049"),
    (6, "fc5a299cd6cd644f40bdcc8f7ae00e89a4ae4fbc44031c4bc27e54dd4bcb9773"),
    (5, "3f122fd6ff97ebdcef91e2e1af20b136397fc6442af86be4ebc20114eab8fa91"),
    (7, "8a2140bb41b8594f25b2ce4f1b2377ee257db5d008c4cb5ac69307c9f0f02b22"),
    (9, "ff3c33ca7d5abd5121abc30b75a5e8469ec928ae398331f50d9f15b840fee9e8"),
    (8, "a0bb92396a73fed1f520d0a51e3e4bee96b9206d5d5b385a878e311b4cc96198"),
    (9, "359a37823b522a49eed4545382a72788e93bc93d2a5ee581ac3bb98c93e06fd1"),
    (10, "d4ec0dea385722b6cd22475338b979fb48ed1e7867a53f04f5a719b1ef6a70be"),
    (6, "a27d6fe29184d35eb8a103c02c8fad6bbb74b39b1299c4f45e78278c4d06f6ea"),
    (6, "e7bf78c94f618255197e53b92692a68e8a36c861e78c7151fbbc9f515e16ef78"),
}

FORBIDDEN_LENGTHS = sorted({length for length, _ in FORBIDDEN_HASHES})
FORBIDDEN_HASH_SET = {digest for _, digest in FORBIDDEN_HASHES}


def tracked_files():
    output = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [
        line
        for line in output.splitlines()
        if line
        and line not in ALLOWED_FILES
        and pathlib.PurePosixPath(line).suffix.lower() not in BINARY_EXTENSIONS
    ]


def line_contains_forbidden_token(lowered_line):
    for length in FORBIDDEN_LENGTHS:
        if len(lowered_line) < length:
            continue
        for start in range(0, len(lowered_line) - length + 1):
            candidate = lowered_line[start : start + length]
            if hashlib.sha256(candidate.encode("utf-8")).hexdigest() in FORBIDDEN_HASH_SET:
                return True
    return False


def find_offenders():
    offenders = []
    for name in tracked_files():
        path = ROOT / name
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if line_contains_forbidden_token(line.lower()):
                offenders.append(f"{name}:{number}")
    return offenders


def test_tracked_files_contain_no_personal_data():
    assert find_offenders() == []


def test_tripwire_still_detects_a_real_violation(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    synthetic_word = "zzzcanaryleak"
    synthetic_hash = hashlib.sha256(synthetic_word.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        sys.modules[__name__],
        "FORBIDDEN_LENGTHS",
        sorted(set(FORBIDDEN_LENGTHS) | {len(synthetic_word)}),
    )
    monkeypatch.setattr(
        sys.modules[__name__], "FORBIDDEN_HASH_SET", FORBIDDEN_HASH_SET | {synthetic_hash}
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    planted = tmp_path / "planted_leak.py"
    planted.write_text(f"child_name = '{synthetic_word}'\n", encoding="utf-8")
    subprocess.run(["git", "add", "planted_leak.py"], cwd=tmp_path, check=True)
    assert find_offenders() == ["planted_leak.py:1"]


def test_hash_list_has_no_accidental_short_collision():
    for length, digest in FORBIDDEN_HASHES:
        assert len(digest) == 64
        assert length >= 5
