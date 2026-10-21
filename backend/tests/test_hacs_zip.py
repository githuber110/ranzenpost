import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_hacs_zip import INTEGRATION, build

HACS = REPO_ROOT / "hacs.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build.yml"


def test_the_zip_holds_the_integration_files_at_its_root_without_caches(tmp_path):
    cache = INTEGRATION / "__pycache__"
    cache.mkdir(exist_ok=True)
    stray = cache / "stray.cpython-312.pyc"
    stray.write_bytes(b"x")
    try:
        names = zipfile.ZipFile(build(tmp_path / "ranzenpost.zip")).namelist()
    finally:
        stray.unlink()
    assert "manifest.json" in names and "__init__.py" in names and "frontend/ranzenpost-card.js" in names
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
    assert not any(name.startswith("custom_components/") for name in names)


def test_the_zip_is_the_same_for_the_same_files(tmp_path):
    first = build(tmp_path / "a.zip").read_bytes()
    second = build(tmp_path / "b.zip").read_bytes()
    assert first == second


def test_hacs_reads_the_zip_that_the_release_job_attaches():
    filename = json.loads(HACS.read_text(encoding="utf-8"))["filename"]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert f"scripts/build_hacs_zip.py {filename}" in workflow
    assert f"gh release upload \"$tag\" {filename}" in workflow
