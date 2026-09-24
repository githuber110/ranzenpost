import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

REQUIREMENTS = ROOT / "backend" / "requirements.txt"
LOCK = ROOT / "backend" / "requirements.lock.txt"

DIRECT_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*>=\s*([0-9][A-Za-z0-9.]*)\s*$")


def _canon(name):
    return name.lower().replace("_", "-")


def _version_tuple(text):
    parts = []
    for chunk in text.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _direct_requirements():
    floors = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = DIRECT_LINE.match(line)
        assert match, f"unexpected requirement line, extend this test's parser: {line!r}"
        floors[_canon(match.group(1))] = _version_tuple(match.group(2))
    return floors


def _lock_entries():
    entries = {}
    current = None
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash="):
            assert current is not None, "a hash line appears before any package"
            entries[current]["hashes"].append(line.rstrip("\\").strip())
            continue
        head = line.rstrip("\\").strip()
        assert "==" in head, f"lock entries must pin with '==', got: {line!r}"
        name, version = head.split("==", 1)
        current = _canon(name.strip())
        entries[current] = {"version": version.strip(), "hashes": []}
    return entries


def test_every_runtime_requirement_is_pinned_in_the_lock():
    direct = _direct_requirements()
    locked = _lock_entries()
    missing = sorted(name for name in direct if name not in locked)
    assert missing == [], f"requirements.txt lists these but the lock file does not: {missing}"


def test_the_lock_satisfies_the_declared_floor_for_every_direct_requirement():
    direct = _direct_requirements()
    locked = _lock_entries()
    too_low = []
    for name, floor in direct.items():
        locked_version = _version_tuple(locked[name]["version"])
        if locked_version < floor:
            floor_text = ".".join(str(part) for part in floor)
            too_low.append(f"{name}: locked {locked[name]['version']} is below the declared >={floor_text}")
    assert too_low == [], too_low


def test_every_locked_entry_pins_an_exact_version():
    locked = _lock_entries()
    vague = [name for name, info in locked.items() if not re.fullmatch(r"[0-9][0-9A-Za-z.]*", info["version"])]
    assert vague == [], f"a lock entry has to name one version, not a range: {vague}"


def test_every_locked_entry_carries_at_least_one_hash():
    locked = _lock_entries()
    missing_hash = sorted(name for name, info in locked.items() if not info["hashes"])
    assert missing_hash == [], f"pip --require-hashes needs a hash for every entry: {missing_hash}"


def test_every_locked_hash_looks_like_a_sha256_digest():
    locked = _lock_entries()
    bad = []
    for name, info in locked.items():
        for entry in info["hashes"]:
            if not re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", entry):
                bad.append(f"{name}: {entry!r}")
    assert bad == [], bad


def test_the_dockerfile_installs_from_the_lock_with_hash_checking():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements.lock.txt" in text, "the image should install the pinned runtime dependencies"
    assert "--require-hashes" in text, "pinning without --require-hashes leaves the hashes unchecked"


def test_the_dockerfile_pins_the_base_image_to_a_tag_and_a_digest():
    first_line = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()[0]
    match = re.match(r"^FROM\s+python:(\S+)@sha256:([0-9a-f]{64})\s*$", first_line)
    assert match, f"expected an explicit patch tag and digest, got: {first_line!r}"
    tag = match.group(1)
    assert tag != "3.12-slim", "a floating tag defeats the point of pinning the digest next to it"
    assert re.fullmatch(r"3\.12\.\d+-slim", tag), f"unexpected base image tag: {tag!r}"


def test_the_addon_package_carries_the_lock_file(tmp_path_factory):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import build_addon

    package = build_addon.build(tmp_path_factory.mktemp("addon") / "ranzenpost")
    assert (package / "backend" / "requirements.lock.txt").exists(), (
        "the Dockerfile in the packaged add-on copies backend/requirements.lock.txt, "
        "so the package has to carry it"
    )


def test_ci_installs_the_lock_with_hash_checking_before_the_loose_ranges():
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    lock_install = "pip install --require-hashes -r backend/requirements.lock.txt"
    dev_install = "pip install -r backend/requirements-dev.txt"
    assert lock_install in workflow, "CI should install the pinned runtime dependencies with hash checking"
    assert workflow.index(lock_install) < workflow.index(dev_install), (
        "the lock has to be installed before the loose dev ranges so a range can never resolve to "
        "something other than what the lock already pinned"
    )
