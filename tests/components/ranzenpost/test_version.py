import json
import pathlib

import pytest

from custom_components.ranzenpost.const import MIN_ADDON_VERSION
from custom_components.ranzenpost.version import (
    ADDON_TOO_OLD,
    APP_UPDATE_NEEDED,
    INTEGRATION_TOO_OLD,
    FINAL,
    mismatch_is_severe,
    newer_version,
    parse_version,
    release_line,
    restart_pending,
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
        ("2609.03.02", "2609.03.01", False, INTEGRATION_TOO_OLD),
        ("2609.03.01", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "2609.01.33", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "2609.02.03", False, APP_UPDATE_NEEDED),
        ("2609.01.36", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.05", False, APP_UPDATE_NEEDED),
        ("2609.01.30", "2609.02.00", False, ADDON_TOO_OLD),
        ("2608.03.00", "2609.02.00", False, ADDON_TOO_OLD),
        ("2609.02.00", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", True, ADDON_TOO_OLD),
        ("", "2609.02.00", False, None),
        ("2609.02.05", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.03.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.03.00", "2609.02.07", False, INTEGRATION_TOO_OLD),
        ("2610.01.00", "2609.02.00", False, INTEGRATION_TOO_OLD),
        ("2609.02.00", "", False, None),
        ("2609.03.00", "2609.04.00", False, APP_UPDATE_NEEDED),
        ("2609.3.0", "2609.4.0", False, APP_UPDATE_NEEDED),
        ("2609.4.0", "2610.1.0", False, APP_UPDATE_NEEDED),
        ("2609.4.1b1", "2609.4.1", False, APP_UPDATE_NEEDED),
        ("2609.4.1", "2609.4.1b1", False, INTEGRATION_TOO_OLD),
        ("2609.04.00", "2609.4.0", False, None),
    ],
)
def test_the_mismatch_names_which_side_is_behind(addon, integration, legacy, expected):
    assert version_mismatch(addon, integration, legacy) == expected


def test_the_minimum_addon_version_is_a_real_version_not_ahead_of_the_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    assert parse_version(MIN_ADDON_VERSION) is not None
    assert parse_version(MIN_ADDON_VERSION) <= parse_version(manifest)


def test_the_minimum_addon_version_is_written_without_padding():
    assert MIN_ADDON_VERSION == "{}.{}.{}".format(*parse_version(MIN_ADDON_VERSION)[:3])
    assert version_mismatch("2609.02.00", "2609.02.00", False) is None
    assert version_mismatch("2609.01.99", "2609.02.00", False) == ADDON_TOO_OLD


@pytest.mark.parametrize(
    ("addon", "integration", "legacy", "severe"),
    [
        ("2609.3.0", "2609.4.0", False, True),
        ("2609.4.0", "2610.1.0", False, True),
        ("2609.4.0", "2609.4.1", False, False),
        ("2609.4.1b1", "2609.4.1", False, False),
        ("2609.4.0", "2609.3.0", False, False),
        ("2609.4.1", "2609.4.0", False, False),
        ("2609.1.0", "2609.4.0", False, True),
        ("2609.4.0", "2609.4.0", True, True),
        ("2609.4.0", "2609.4.0", False, False),
    ],
)
def test_an_app_a_feature_release_behind_is_an_error_and_a_fix_release_behind_a_warning(
    addon, integration, legacy, severe
):
    mismatch = version_mismatch(addon, integration, legacy)
    assert mismatch_is_severe(mismatch, addon, integration) is severe


@pytest.mark.parametrize(
    ("loaded", "installed", "pending", "target"),
    [
        ("2609.3.0", "2609.4.0", True, "2609.4.0"),
        ("2609.4.0", "2609.4.0", False, "2609.4.0"),
        ("2609.4.0", "2609.3.0", False, "2609.4.0"),
        ("2609.4.0", "", False, "2609.4.0"),
        ("2609.4.0", "garbage", False, "2609.4.0"),
        ("", "2609.4.0", False, "2609.4.0"),
        ("2609.4.0", "2609.4.1b1", True, "2609.4.1b1"),
    ],
)
def test_a_newer_manifest_on_disk_means_a_restart_is_pending(loaded, installed, pending, target):
    assert restart_pending(loaded, installed) is pending
    assert newer_version(loaded, installed) == target


def test_every_released_pair_either_matches_or_names_exactly_one_side():
    versions = ["2609.2.0", "2609.3.0", "2609.3.1", "2609.4.0", "2609.4.1b1", "2609.4.1", "2610.1.0"]
    for addon in versions:
        for integration in versions:
            mismatch = version_mismatch(addon, integration, False)
            if addon == integration:
                assert mismatch is None
            elif parse_version(addon) < parse_version(integration):
                assert mismatch == APP_UPDATE_NEEDED
            else:
                assert mismatch == INTEGRATION_TOO_OLD
