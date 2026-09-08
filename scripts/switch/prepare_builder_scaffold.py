#!/usr/bin/env python3
"""Download or extract the pinned Git-free Mind+ V2 Builder scaffold."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath


RELEASE_TAG = "v0.0.1"
ARCHIVE_NAME = "mindplus-ext2-builder-Scaffold.zip"
ARCHIVE_URL = (
    "https://gitee.com/mind-plus/mindplus-ext2-builder/releases/download/"
    f"{RELEASE_TAG}/{ARCHIVE_NAME}"
)
ARCHIVE_SHA256 = "c2cdc6857b39073719dc795dee4b6a603677c35f6d064d86684565fa759ae6d2"
ARCHIVE_ROOT = "mindplus-ext2-builder-Scaffold"
FORBIDDEN_PARTS = {".git", "examples", "node_modules", "build"}
REQUIRED_PATHS = {
    ".babelrc",
    ".gitignore",
    "extension",
    "package-lock.json",
    "package.json",
    "scripts",
    "utils",
    "webpack.config.js",
}
MAX_FILES = 1000
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


class ScaffoldError(RuntimeError):
    pass


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_target(project: Path) -> None:
    if not project.is_absolute():
        raise ScaffoldError("project_root must be absolute")
    if project.exists() and (not project.is_dir() or any(project.iterdir())):
        raise ScaffoldError("project_root must be absent or an empty directory")
    if not project.parent.is_dir():
        raise ScaffoldError("project_root parent must already exist")


def download_archive(target: Path) -> None:
    request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "MindPlus-Switch/0.5"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def inspect_archive(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries = []
    total_size = 0
    files = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ScaffoldError(f"unsafe archive path: {info.filename}")
        if path.parts[0] != ARCHIVE_ROOT:
            raise ScaffoldError(f"unexpected archive root: {path.parts[0]}")
        relative = PurePosixPath(*path.parts[1:])
        if any(part.casefold() in FORBIDDEN_PARTS for part in relative.parts):
            raise ScaffoldError(f"forbidden scaffold path: {relative}")
        unix_mode = info.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise ScaffoldError(f"symbolic links are not allowed: {relative}")
        if not info.is_dir():
            files += 1
            total_size += info.file_size
        entries.append((info, relative))
    if files > MAX_FILES or total_size > MAX_UNCOMPRESSED_BYTES:
        raise ScaffoldError("archive exceeds scaffold safety limits")
    return entries


def extract_checked(archive_path: Path, project: Path) -> dict:
    actual_hash = digest(archive_path)
    if actual_hash != ARCHIVE_SHA256:
        raise ScaffoldError(f"archive sha256 mismatch: {actual_hash}")

    staging = project.parent / f".{project.name}.scaffold-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            entries = inspect_archive(archive)
            for info, relative in entries:
                if not relative.parts:
                    continue
                target = staging.joinpath(*relative.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        present = {item.name for item in staging.iterdir()}
        missing = sorted(REQUIRED_PATHS - present)
        if missing:
            raise ScaffoldError(f"scaffold is missing required paths: {missing}")
        if any(path.name.casefold() in FORBIDDEN_PARTS for path in staging.rglob("*")):
            raise ScaffoldError("extracted scaffold contains a forbidden path")

        if project.exists():
            project.rmdir()
        os.replace(staging, project)
        return {
            "status": "PASS",
            "project_root": str(project),
            "release_tag": RELEASE_TAG,
            "archive_url": ARCHIVE_URL,
            "archive_sha256": actual_hash,
            "archive_root": ARCHIVE_ROOT,
            "git_inherited": False,
            "examples_present": False,
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded verified archive")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = args.project_root.expanduser().resolve()
    temporary_archive = None
    try:
        validate_target(project)
        if args.archive:
            archive_path = args.archive.expanduser().resolve()
            if not archive_path.is_file():
                raise ScaffoldError(f"archive does not exist: {archive_path}")
        else:
            handle, name = tempfile.mkstemp(prefix="mindplus-switch-scaffold-", suffix=".zip")
            os.close(handle)
            temporary_archive = Path(name)
            download_archive(temporary_archive)
            archive_path = temporary_archive
        result = extract_checked(archive_path, project)
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8", newline="\n") as output_handle:
                output_handle.write(encoded + "\n")
        print(encoded)
        return 0
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ScaffoldError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "BUILDER_SCAFFOLD", "error": str(exc)}, ensure_ascii=False))
        return 2
    finally:
        if temporary_archive and temporary_archive.exists():
            temporary_archive.unlink()


if __name__ == "__main__":
    sys.exit(main())

