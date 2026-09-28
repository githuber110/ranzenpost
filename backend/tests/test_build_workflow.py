import pathlib
import re

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build.yml"
TAG_ONLY = "startsWith(github.ref, 'refs/tags/v')"


def _image_job():
    text = WORKFLOW.read_text(encoding="utf-8")
    return text.split("\n  image:\n", 1)[1].split("\n  release:\n", 1)[0]


def test_the_image_is_pushed_only_for_a_version_tag():
    job = _image_job()
    assert re.findall(r"^\s+push:\s*(.+)$", job, re.MULTILINE) == ["${{ " + TAG_ONLY + " }}"]


def test_a_manual_run_logs_in_to_the_registry_only_for_a_version_tag():
    job = _image_job()
    login = job.split("docker/login-action", 1)[1].split("- uses:", 1)[0]
    assert f"if: {TAG_ONLY}" in login
