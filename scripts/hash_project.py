#!/usr/bin/env python3
"""Compute a deterministic hash of reviewable Mind+ project source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".mindplus-agent",
    ".ms",
    "__pycache__",
    "node_modules",
    "build",
}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}


class HashError(RuntimeError):
    pass


# Path.is_junction() only exists on Python 3.12+; st_file_attributes works on
# 3.11 Windows. Junctions and mount points carry this attribute without a
# symlink flag, so the reparse check must not follow the link (lstat).
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_reparse_point(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def reviewable_files(project: Path) -> list[Path]:
    files: list[Path] = []
    for root, directories, filenames in os.walk(project, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_directories: list[str] = []
        for name in sorted(directories):
            candidate = root_path / name
            if name in IGNORED_DIRECTORIES:
                continue
            if candidate.is_symlink() or is_reparse_point(candidate):
                raise HashError(f"symbolic link or junction is not reviewable: {candidate}")
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(filenames):
            if name in IGNORED_FILES or name.endswith((".pyc", ".pyo")):
                continue
            path = root_path / name
            if path.is_symlink() or is_reparse_point(path):
                raise HashError(f"symbolic link or junction is not reviewable: {path}")
            if not path.is_file():
                raise HashError(f"non-regular source entry is not reviewable: {path}")
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(project).as_posix())


def compute_project_hash(project: Path) -> tuple[str, int]:
    project = project.expanduser().resolve(strict=False)
    if not project.is_absolute() or not project.is_dir():
        raise HashError("project_root must be an existing absolute directory")
    hasher = hashlib.sha256()
    files = reviewable_files(project)
    for path in files:
        relative = path.relative_to(project).as_posix().encode("utf-8")
        digest = file_digest(path).encode("ascii")
        size = path.stat().st_size
        hasher.update(len(relative).to_bytes(4, "big"))
        hasher.update(relative)
        hasher.update(size.to_bytes(8, "big"))
        hasher.update(digest)
    return hasher.hexdigest(), len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        project = args.project_root.expanduser().resolve(strict=False)
        digest, file_count = compute_project_hash(project)
        result = {
            "status": "PASS",
            "project_root": str(project),
            "sha256": digest,
            "file_count": file_count,
            "ignored_directories": sorted(IGNORED_DIRECTORIES),
        }
        code = 0
    except (OSError, HashError) as exc:
        result = {"status": "BLOCKED", "reason_code": "REVIEW.PROJECT_HASH_FAILED", "error": str(exc)}
        code = 2
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve(strict=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded)
    print(encoded, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
