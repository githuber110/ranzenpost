import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRAND = ROOT / "custom_components" / "ranzenpost" / "brand"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path):
    head = path.read_bytes()[:24]
    assert head[:8] == PNG_SIGNATURE, path.name
    return struct.unpack(">II", head[16:24])


def test_the_license_is_plain_mit_so_github_and_hacs_can_name_it():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n")
    assert text.rstrip().endswith("SOFTWARE.")


def test_the_integration_ships_square_brand_icons_for_hacs():
    assert png_size(BRAND / "icon.png") == (256, 256)
    assert png_size(BRAND / "icon@2x.png") == (512, 512)
