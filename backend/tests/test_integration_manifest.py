import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = REPO_ROOT / "custom_components" / "ranzenpost"
MANIFEST = INTEGRATION / "manifest.json"
STRINGS = INTEGRATION / "strings.json"
TRANSLATIONS = INTEGRATION / "translations"
HACS = REPO_ROOT / "hacs.json"
CODEOWNERS = REPO_ROOT / "CODEOWNERS"
ADDON_CONFIG = REPO_ROOT / "iserv_connector" / "config.yaml"
PACKAGE_JSON = REPO_ROOT / "package.json"
CHANGELOG = REPO_ROOT / "iserv_connector" / "CHANGELOG.md"

LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
REQUIRED_MANIFEST_KEYS = {
    "domain": "ranzenpost",
    "name": "Ranzenpost",
    "config_flow": True,
    "iot_class": "local_polling",
    "dependencies": ["http"],
    "after_dependencies": ["hassio", "lovelace"],
    "requirements": [],
    "codeowners": ["@githuber110"],
    "integration_type": "hub",
}
LINKED_KEYS = ("documentation", "issue_tracker")
REPOSITORY = "https://github.com/githuber110/ranzenpost"
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
VERSION = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:b(\d{1,3}))?$")


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(node, prefix=""):
    flat = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _addon_version():
    match = re.search(r'^version:\s*"([^"]+)"', ADDON_CONFIG.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "config.yaml has no version field"
    return match.group(1)


def _changelog_top_heading():
    match = re.search(r"^## (\S+)", CHANGELOG.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "the changelog has no version heading"
    return match.group(1)


def version_key(version):
    match = VERSION.match(version)
    assert match, version
    beta = match.group(4)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 10**6 if beta is None else int(beta))


def test_manifest_is_valid_json_with_the_required_keys():
    manifest = _json(MANIFEST)
    for key, expected in REQUIRED_MANIFEST_KEYS.items():
        assert manifest.get(key) == expected, key
    for key in LINKED_KEYS:
        assert manifest.get(key, "").startswith(REPOSITORY), key
    assert VERSION.match(manifest["version"]), manifest["version"]


def test_hacs_json_and_codeowners_exist_with_the_agreed_content():
    hacs = _json(HACS)
    assert hacs == {"name": "Ranzenpost", "render_readme": True, "homeassistant": "2025.6.0"}
    assert CODEOWNERS.read_text(encoding="utf-8").strip() == "* @githuber110"


def test_all_six_language_files_exist():
    assert sorted(path.stem for path in TRANSLATIONS.glob("*.json")) == sorted(LANGUAGES)


@pytest.mark.parametrize("language", LANGUAGES)
def test_translation_keys_match_strings_json(language):
    base = _flatten(_json(STRINGS))
    translated = _flatten(_json(TRANSLATIONS / f"{language}.json"))
    assert set(translated) == set(base)
    assert [key for key, value in translated.items() if not str(value).strip()] == []
    mismatched = [
        key
        for key, value in translated.items()
        if set(PLACEHOLDER.findall(str(value))) != set(PLACEHOLDER.findall(str(base[key])))
    ]
    assert mismatched == []


def test_english_translation_mirrors_strings_json():
    assert _json(TRANSLATIONS / "en.json") == _json(STRINGS)


def test_every_entity_key_has_a_translated_name_and_an_icon():
    strings = _json(STRINGS)["entity"]
    icons = _json(INTEGRATION / "icons.json")["entity"]
    assert set(icons) == set(strings)
    for platform, entries in strings.items():
        assert set(icons[platform]) == set(entries), platform
        for key, entry in entries.items():
            assert entry.get("name"), f"{platform}.{key}"
            assert icons[platform][key]["default"].startswith("mdi:"), f"{platform}.{key}"


def test_addon_package_and_integration_share_one_version():
    addon_version = _addon_version()
    manifest_version = _json(MANIFEST)["version"]
    package_version = _json(PACKAGE_JSON)["version"]
    assert VERSION.match(addon_version), addon_version
    assert VERSION.match(package_version), package_version
    assert manifest_version == addon_version == package_version


def test_changelog_top_section_names_this_version_or_a_later_public_one():
    heading = _changelog_top_heading()
    assert VERSION.match(heading), heading
    assert version_key(heading) >= version_key(_addon_version())
