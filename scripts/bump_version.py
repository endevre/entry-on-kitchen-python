#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
from typing import Optional


PROJECT_VERSION_PATTERN = re.compile(r"^(version\s*=\s*)\"([^\"]+)\"", re.MULTILINE)


def read_file(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def extract_base_version(version: str) -> str:
    match = re.match(r"(\d+\.\d+\.\d+)", version)
    if not match:
        raise ValueError(f"Unsupported version format: {version}")
    return match.group(1)


def build_version(base: str, *, channel: Optional[str], sha: Optional[str], timestamp: Optional[str]) -> str:
    ts = timestamp or dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")

    if channel == "beta":
        version = f"{base}b{ts}"
    elif channel == "dev":
        version = f"{base}.dev{ts}"
    else:
        version = base

    # Note: PyPI does not allow local version identifiers (e.g., +gad0a71b)
    # so we don't append the SHA for beta/dev builds that will be uploaded to PyPI

    return version


def update_version(pyproject_path: pathlib.Path, *, channel: Optional[str], sha: Optional[str], timestamp: Optional[str]) -> str:
    content = read_file(pyproject_path)
    match = PROJECT_VERSION_PATTERN.search(content)
    if not match:
        raise RuntimeError("Could not locate version field in pyproject.toml")

    current_version = match.group(2)
    base_version = extract_base_version(current_version)
    new_version = build_version(base_version, channel=channel, sha=sha, timestamp=timestamp)

    if new_version == current_version:
        return new_version

    updated_content = PROJECT_VERSION_PATTERN.sub(f"\\1\"{new_version}\"", content, count=1)
    write_file(pyproject_path, updated_content)
    return new_version


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump project version for automated builds.")
    parser.add_argument("--channel", choices=["beta", "dev"], default=None, help="Release channel to use.")
    parser.add_argument("--sha", default=None, help="Commit SHA to include in local version segment.")
    parser.add_argument("--timestamp", default=None, help="Override timestamp (UTC). Format YYYYMMDDHHMMSS.")
    parser.add_argument("--path", default="pyproject.toml", help="Path to pyproject.toml")
    args = parser.parse_args()

    pyproject_path = pathlib.Path(args.path).resolve()
    new_version = update_version(pyproject_path, channel=args.channel, sha=args.sha, timestamp=args.timestamp)
    print(new_version)


if __name__ == "__main__":
    main()
