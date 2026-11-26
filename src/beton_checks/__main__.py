"""Command-line entry point for the standalone BETON packages."""

import argparse
import json
import sys
from pathlib import Path

from beton_checks.discovery import PROJECT_MARKERS, affected_tests


def project_root(source: Path) -> Path:
    for directory in (source.parent, *source.parent.parents):
        if any((directory / marker).exists() for marker in PROJECT_MARKERS):
            return directory
    return Path.cwd().resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="beton", description="List Python tests affected by local static imports."
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.3.1")
    commands = parser.add_subparsers(dest="command", required=True)
    affected = commands.add_parser(
        "affected", help="list affected Python tests without running them"
    )
    affected.add_argument("file", type=Path, help="existing Python source or test file")
    affected.add_argument(
        "--root", type=Path, help="project directory (default: nearest project marker)"
    )
    affected.add_argument(
        "--json", action="store_true", help="print a JSON array of absolute paths"
    )
    arguments = parser.parse_args()
    source = arguments.file.parent.resolve() / arguments.file.name
    root = arguments.root.resolve() if arguments.root else project_root(source)
    if source.suffix != ".py" or not source.is_file():
        parser.error("file must be an existing Python (.py) file")
    if not root.is_dir() or not source.is_relative_to(root) or not source.resolve().is_relative_to(root):
        parser.error("file must be inside the project root")
    try:
        selected = [str(path) for path in affected_tests(source, root)]
    except OSError as error:
        print(f"beton: discovery failed: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(selected))
    elif selected:
        print("\n".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
