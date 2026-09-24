import json
import pathlib
import re

import pytest

from custom_components.ranzenpost.const import MIN_ADDON_VERSION
from custom_components.ranzenpost.version import (
    ADDON_TOO_OLD,
    INTEGRATION_TOO_OLD,
    parse_version,
    public_release,
    version_mismatch,
)

MANIFEST = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost" / "manifest.json"


def test_versions_parse_into_numbers_or_nothing():
    assert parse_version("2609.02.00") == (2609, 2, 0)
    assert parse_version("2610.11.07") == (2610, 11, 7)
    assert parse_version("") is None
    assert parse_version("unknown") is None
    assert parse_version("2609.2") is None
    assert parse_version("v2609.02.00") is None


def test_an_internal_build_belongs_to_the_public_release_it_leads_to():
    assert public_release((2609, 2, 0)) == (2609, 2)
    assert public_release((2609, 1, 33)) == (2609, 2)
    assert public_release((2609, 2, 1)) == (2609, 3)


@pytest.mark.parametrize(
    ("addon", "integration", "legacy", "expected"),
    [
        ("2609.02.00", "2609.02.00", False, None),
        ("2609.02.03", "2609.02.03", False, None),
        ("2609.02.00", "2609.01.33", False, None),
        ("2609.02.00", "2609.02.03", False, None),
        ("2609.01.36", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.05", False, None),
        ("2609.01.30", "2609.02.00", False, ADDON_TOO_OLD),
        ("2608.03.00", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", False, None),
        ("2609.02.05", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.03.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.03.00", "2609.02.07", False, None),
        ("2610.01.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "", False, None),
    ],
)
def test_the_mismatch_names_which_side_is_behind(addon, integration, legacy, expected):
    assert version_mismatch(addon, integration, legacy) == expected


def test_the_minimum_addon_version_is_a_real_version_not_ahead_of_the_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", MIN_ADDON_VERSION)
    assert parse_version(MIN_ADDON_VERSION) <= parse_version(manifest)
