import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG = REPO_ROOT / "iserv_connector" / "CHANGELOG.md"
SECTION_HEADING = re.compile(r"^##\s+(\S+)\s*$", re.MULTILINE)


class SectionNotFound(ValueError):
    pass


def extract_section(changelog_text: str, version: str) -> str:
    headings = list(SECTION_HEADING.finditer(changelog_text))
    for index, match in enumerate(headings):
        if match.group(1) != version:
            continue
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog_text)
        return changelog_text[start:end].strip("\n") + "\n"
    raise SectionNotFound(f"no '## {version}' section in the changelog")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print one version's section of the changelog.")
    parser.add_argument("version", help="the version heading to extract, e.g. 2609.01.31")
    parser.add_argument("--file", type=Path, default=DEFAULT_CHANGELOG, help="path to the changelog")
    args = parser.parse_args(argv)

    try:
        section = extract_section(args.file.read_text(encoding="utf-8"), args.version)
    except SectionNotFound as error:
        print(error, file=sys.stderr)
        return 1

    sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
