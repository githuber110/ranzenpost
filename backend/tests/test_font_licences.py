from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "frontend" / "fonts"
FONT_EXTENSIONS = {".woff2", ".woff", ".ttf", ".otf"}

FONT_LICENCES = {
    "archivo-600-700.woff2": "OFL-Archivo.txt",
    "inter-cyrillic-400-700.woff2": "OFL-Inter.txt",
    "noto-sans-arabic-400-700.woff2": "OFL-NotoSansArabic.txt",
    "schibsted-grotesk-400-700.woff2": "OFL-SchibstedGrotesk.txt",
}


def _font_files(font_dir):
    return sorted(p.name for p in font_dir.iterdir() if p.suffix.lower() in FONT_EXTENSIONS)


def _missing_licences(font_dir, licences):
    offenders = []
    for name in _font_files(font_dir):
        mapped = licences.get(name)
        if not mapped:
            offenders.append(f"{name}: no licence mapping")
            continue
        licence_path = font_dir / mapped
        if not licence_path.exists() or not licence_path.read_text(encoding="utf-8").strip():
            offenders.append(f"{name}: licence file {mapped} is missing or empty")
    return offenders


def test_every_bundled_font_file_has_a_licence_file():
    fonts = _font_files(FONT_DIR)
    assert fonts, "no font files found under frontend/fonts, update the test"
    assert _missing_licences(FONT_DIR, FONT_LICENCES) == []


def test_the_licence_guard_bites_on_a_font_file_without_a_mapping(tmp_path):
    (tmp_path / "newfont-400-700.woff2").write_bytes(b"fake font bytes")
    assert _missing_licences(tmp_path, FONT_LICENCES) == ["newfont-400-700.woff2: no licence mapping"]


def test_the_licence_guard_bites_on_a_missing_licence_file(tmp_path):
    (tmp_path / "archivo-600-700.woff2").write_bytes(b"fake font bytes")
    offenders = _missing_licences(tmp_path, {"archivo-600-700.woff2": "OFL-Archivo.txt"})
    assert offenders == ["archivo-600-700.woff2: licence file OFL-Archivo.txt is missing or empty"]


def test_the_licence_guard_passes_when_the_licence_file_is_present(tmp_path):
    (tmp_path / "archivo-600-700.woff2").write_bytes(b"fake font bytes")
    (tmp_path / "OFL-Archivo.txt").write_text("Copyright 2020 The Archivo Project Authors\n", encoding="utf-8")
    assert _missing_licences(tmp_path, {"archivo-600-700.woff2": "OFL-Archivo.txt"}) == []
