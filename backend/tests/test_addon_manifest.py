import json
import re
from pathlib import Path

ADDON = Path(__file__).resolve().parents[2] / "iserv_connector"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_config_yaml_declares_mqtt_options_with_matching_schema():
    text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    options_block, schema_block = text.split("schema:", 1)
    for key in ("mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password"):
        assert f"{key}:" in options_block, f"{key} missing from options"
        assert f"{key}:" in schema_block, f"{key} missing from schema"


def test_run_sh_passes_mqtt_options_through_as_env_vars():
    text = (ADDON / "run.sh").read_text(encoding="utf-8")
    for env_var in ("ISERV_MQTT_HOST", "ISERV_MQTT_PORT", "ISERV_MQTT_USER", "ISERV_MQTT_PASSWORD"):
        assert env_var in text, f"{env_var} not wired in run.sh"
    assert 'if [ -n "$ISERV_MQTT_HOST" ]; then' in text


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
