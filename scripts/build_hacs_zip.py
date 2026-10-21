import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = REPO_ROOT / "custom_components" / "ranzenpost"
SKIPPED_PARTS = ("__pycache__",)
SKIPPED_SUFFIXES = (".pyc",)
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def shipped_files(source=INTEGRATION):
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and not any(part in SKIPPED_PARTS for part in path.parts) and path.suffix not in SKIPPED_SUFFIXES
    )


def build(target, source=INTEGRATION):
    target = Path(target)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in shipped_files(source):
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return target


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "ranzenpost.zip"))
