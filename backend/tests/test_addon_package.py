import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_addon

COPY_LINE = re.compile(r"^COPY\s+(\S+)\s+(\S+)\s*$")
SHELL_SUFFIXES = (".sh",)
TEXT_SUFFIXES = (".yaml", ".yml", ".json", ".js", ".css", ".html", ".md", ".sh", ".txt", ".webmanifest")
BOM = b"\xef\xbb\xbf"


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    return build_addon.build(tmp_path_factory.mktemp("addon") / "ranzenpost")


def test_every_file_the_dockerfile_copies_is_in_the_package(package):
    missing = []
    for line in (package / "Dockerfile").read_text(encoding="utf-8").splitlines():
        match = COPY_LINE.match(line.strip())
        if not match:
            continue
        source = match.group(1)
        if not (package / source).exists():
            missing.append(f"{source} (from '{line.strip()}')")
    assert missing == [], (
        "the image is built from the package directory, so a COPY that points at a path which only "
        f"exists in the repository layout makes the build fail on the device: {missing}"
    )


def test_the_package_carries_no_reference_to_the_repository_layout(package):
    text = (package / "Dockerfile").read_text(encoding="utf-8")
    assert "iserv_connector/" not in text, (
        "the package is flat, so a repository directory name in the Dockerfile can only be a path "
        "that does not exist here"
    )


def test_the_local_build_is_not_talked_out_of_building(package):
    config = (package / "config.yaml").read_text(encoding="utf-8")
    assert not any(line.startswith("image:") for line in config.splitlines()), (
        "with an image line the supervisor looks for a published image instead of building the "
        "package that was just copied over"
    )
    assert config.startswith("name:"), "the first key is not readable, so the file starts with something else"


def test_no_text_file_in_the_package_starts_with_a_byte_order_mark(package):
    offenders = [
        str(path.relative_to(package))
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.suffix in TEXT_SUFFIXES and path.read_bytes().startswith(BOM)
    ]
    assert offenders == [], (
        "a byte order mark is invisible in an editor but is part of the first value the reader "
        f"parses: {offenders}"
    )


def test_every_shell_script_stays_runnable_inside_a_linux_container(package):
    offenders = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.suffix not in SHELL_SUFFIXES:
            continue
        raw = path.read_bytes()
        if b"\r\n" in raw:
            offenders.append(f"{path.relative_to(package)}: carriage returns")
        if not raw.startswith(b"#!"):
            offenders.append(f"{path.relative_to(package)}: no interpreter line")
    assert offenders == [], (
        "a carriage return becomes part of the interpreter name, and the container then reports "
        f"that the interpreter does not exist: {offenders}"
    )


def test_the_package_ships_no_build_leftovers(package):
    offenders = [
        str(path.relative_to(package))
        for path in sorted(package.rglob("*"))
        if path.name in build_addon.SKIP_NAMES or path.suffix in build_addon.SKIP_SUFFIXES
    ]
    assert offenders == [], f"these belong to the working copy, not to the image: {offenders}"


def test_the_package_ships_no_tests(package):
    offenders = [
        str(path.relative_to(package))
        for path in sorted(package.rglob("*"))
        if path.is_dir() and path.name == "tests"
    ]
    assert offenders == [], f"tests are not part of what the add-on runs: {offenders}"


def test_the_server_the_container_starts_is_in_the_package(package):
    start = (package / "run.sh").read_text(encoding="utf-8")
    match = re.search(r"uvicorn\s+([A-Za-z0-9_.]+):", start)
    assert match, "run.sh no longer names a module to start, so this guard cannot check it"
    module = match.group(1).split(".")
    target = package / "backend"
    for part in module[:-1]:
        target = target / part
    assert (target / f"{module[-1]}.py").exists(), (
        f"run.sh starts {'.'.join(module)}, but that module is not in the package"
    )


def test_the_version_is_the_same_everywhere_the_package_states_it(package):
    config = (package / "config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', config, re.M)
    assert match, "config.yaml carries no readable version"
    version = match.group(1)
    assert json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"] == version
    client = (ROOT / "backend" / "app" / "iserv" / "client.py").read_text(encoding="utf-8")
    assert f"ranzenpost/{version}" in client, (
        "the version the app tells IServ about is not the version this package claims to be"
    )


def test_the_changelog_describes_the_version_being_shipped(package):
    version = re.search(r'^version:\s*"([^"]+)"', (package / "config.yaml").read_text(encoding="utf-8"), re.M)
    changelog = (package / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {version.group(1)}" in changelog, (
        "the device shows this changelog next to the update button, so the version being installed "
        "has to be described in it"
    )
