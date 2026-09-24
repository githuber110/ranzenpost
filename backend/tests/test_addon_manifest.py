import json
import re
from pathlib import Path

ADDON = Path(__file__).resolve().parents[2] / "iserv_connector"
REPO_ROOT = Path(__file__).resolve().parents[2]


MQTT_FREE_ROOTS = ("backend", "frontend", "iserv_connector", "README.md", "Dockerfile", "CONTRIBUTING.md")
MQTT_ALLOWED = {"iserv_connector/CHANGELOG.md"}
MQTT_SKIPPED_DIRS = {"node_modules", ".git", "__pycache__", ".pytest_cache", "vendor", "fonts"}


def _text_files(root):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if not path.is_file() or MQTT_SKIPPED_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".woff2", ".ttf", ".ico", ".pdf"}:
            continue
        yield path


def test_nothing_but_the_changelog_still_mentions_mqtt():
    offenders = []
    for root in MQTT_FREE_ROOTS:
        for path in _text_files(REPO_ROOT / root):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative in MQTT_ALLOWED or path == Path(__file__).resolve():
                continue
            if "mqtt" in path.read_text(encoding="utf-8", errors="ignore").lower():
                offenders.append(relative)
    assert offenders == [], f"the MQTT bridge is gone; these still mention it: {offenders}"


def test_config_yaml_carries_no_mqtt_options_and_declares_only_the_passphrase():
    text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    options_block, schema_block = text.split("schema:", 1)
    assert "passphrase:" in options_block and "passphrase:" in schema_block
    assert "mqtt" not in text.lower()


def test_config_yaml_announces_the_integration_through_supervisor_discovery():
    text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    assert re.search(r"^discovery:\s*\[ranzenpost\]\s*$", text, re.MULTILINE), "config.yaml must declare discovery: [ranzenpost]"
    assert re.search(r"^hassio_api:\s*true\s*$", text, re.MULTILINE), "the discovery call needs hassio_api: true"


def test_run_sh_exports_only_the_passphrase_from_the_options():
    text = (ADDON / "run.sh").read_text(encoding="utf-8")
    assert "ISERV_PASSPHRASE" in text
    assert "mqtt" not in text.lower()


def test_the_dockerfile_links_the_image_to_the_repository():
    text = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'LABEL org.opencontainers.image.source="https://github.com/githuber110/ranzenpost"' in text


def test_the_requirements_no_longer_pull_an_mqtt_client():
    text = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "paho" not in text.lower()


def test_package_json_version_matches_addon_manifest_version():
    config_text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', config_text, re.MULTILINE)
    assert match, "config.yaml has no version field"
    addon_version = match.group(1)

    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package_json["version"] == addon_version


def test_shell_and_build_files_are_stored_with_unix_line_endings():
    import subprocess

    for path in ("iserv_connector/run.sh", "Dockerfile", "iserv_connector/config.yaml"):
        blob = subprocess.run(
            ["git", "cat-file", "blob", f"HEAD:{path}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout
        assert b"\r" not in blob, f"{path} carries CRLF in the committed blob"


def test_gitattributes_pins_lf_so_git_archive_cannot_smudge_the_package():
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in text.splitlines()[0]
