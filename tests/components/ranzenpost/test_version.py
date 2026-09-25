import json
import pathlib

import pytest

from custom_components.ranzenpost.const import MIN_ADDON_VERSION
from custom_components.ranzenpost.version import (
    ADDON_TOO_OLD,
    INTEGRATION_TOO_OLD,
    FINAL,
    parse_version,
    release_line,
    version_mismatch,
)

MANIFEST = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost" / "manifest.json"


def test_versions_parse_into_numbers_or_nothing():
    assert parse_version("2609.02.00") == (2609, 2, 0, FINAL)
    assert parse_version("2609.2.1") == (2609, 2, 1, FINAL)
    assert parse_version("2610.11.7b2") == (2610, 11, 7, 2)
    assert parse_version("") is None
    assert parse_version("unknown") is None
    assert parse_version("2609.2") is None
    assert parse_version("v2609.02.00") is None
    assert parse_version("2609.2.1-b0") is None


def test_a_beta_sorts_below_its_release_and_padding_does_not_matter():
    assert parse_version("2609.2.1b0") < parse_version("2609.2.1b1") < parse_version("2609.2.1")
    assert parse_version("2609.2.2b0") > parse_version("2609.2.1")
    assert parse_version("2609.02.01") == parse_version("2609.2.1")
    assert parse_version("2609.2.1") > parse_version("2609.02.00")


def test_the_release_line_is_the_first_two_numbers_whatever_the_third_says():
    assert release_line((2609, 2, 0)) == (2609, 2)
    assert release_line((2609, 2, 1)) == (2609, 2)
    assert release_line((2609, 3, 1)) == (2609, 3)


@pytest.mark.parametrize(
    ("addon", "integration", "legacy", "expected"),
    [
        ("2609.02.00", "2609.02.00", False, None),
        ("2609.02.03", "2609.02.03", False, None),
        ("2609.03.01", "2609.03.01", False, None),
        ("2609.03.02", "2609.03.01", False, None),
        ("2609.03.01", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "2609.01.33", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "2609.02.03", False, None),
        ("2609.01.36", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.05", False, None),
        ("2609.01.30", "2609.02.00", False, ADDON_TOO_OLD),
        ("2608.03.00", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", False, None),
        ("2609.02.05", "2609.02.00", False, None),
        ("2609.03.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.03.00", "2609.02.07", False, INTEGRATION_TOO_OLD),
        ("2610.01.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "", False, None),
    ],
)
def test_the_mismatch_names_which_side_is_behind(addon, integration, legacy, expected):
    assert version_mismatch(addon, integration, legacy) == expected


def test_the_minimum_addon_version_is_a_real_version_not_ahead_of_the_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    assert parse_version(MIN_ADDON_VERSION) is not None
    assert parse_version(MIN_ADDON_VERSION) <= parse_version(manifest)
