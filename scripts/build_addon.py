import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

ADDON_FILES = ("CHANGELOG.md", "DOCS.md", "icon.png", "logo.png", "run.sh")
ADDON_DIRS = ("translations",)
FRONTEND_SKIP = ("tests",)
DROP_CONFIG_KEYS = ("image:",)
FLATTENED = {"iserv_connector/run.sh": "run.sh"}
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def _wanted(path):
    return path.name not in SKIP_NAMES and path.suffix not in SKIP_SUFFIXES


def _copy_tree(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        if not _wanted(item):
            continue
        if item.is_dir():
            _copy_tree(item, target / item.name)
        else:
            shutil.copy2(item, target / item.name)


def _write_text(path, text):
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def _config_without_image():
    source = (ROOT / "iserv_connector" / "config.yaml").read_text(encoding="utf-8-sig")
    kept = [
        line
        for line in source.splitlines()
        if not any(line.startswith(key) for key in DROP_CONFIG_KEYS)
    ]
    return "\n".join(kept) + "\n"


def _dockerfile_for_flat_layout():
    source = (ROOT / "Dockerfile").read_text(encoding="utf-8-sig")
    for repo_path, addon_path in FLATTENED.items():
        source = source.replace("COPY %s " % repo_path, "COPY %s " % addon_path)
    return source


def build(target):
    target = pathlib.Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in sorted(target.iterdir()):
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for name in ADDON_FILES:
        shutil.copy2(ROOT / "iserv_connector" / name, target / name)
    for name in ADDON_DIRS:
        _copy_tree(ROOT / "iserv_connector" / name, target / name)

    _write_text(target / "config.yaml", _config_without_image())
    _write_text(target / "Dockerfile", _dockerfile_for_flat_layout())

    _copy_tree(ROOT / "backend" / "app", target / "backend" / "app")
    shutil.copy2(ROOT / "backend" / "requirements.txt", target / "backend" / "requirements.txt")

    frontend = target / "frontend"
    frontend.mkdir(parents=True)
    for item in sorted((ROOT / "frontend").iterdir()):
        if item.name in FRONTEND_SKIP or not _wanted(item):
            continue
        if item.is_dir():
            _copy_tree(item, frontend / item.name)
        else:
            shutil.copy2(item, frontend / item.name)

    return target


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    options = parser.parse_args(argv)
    target = build(options.target)
    files = sorted(path for path in target.rglob("*") if path.is_file())
    print("%s: %d files" % (target, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
