#!/usr/bin/env python3
"""Download or extract the latest stable Git-free Mind+ V2 Builder scaffold."""

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


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from update_skill import download, parse_version

RELEASES_URL = "https://gitee.com/api/v5/repos/mind-plus/mindplus-ext2-builder/releases"
ARCHIVE_NAME = "mindplus-ext2-builder-Scaffold.zip"

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
    if not project.name.startswith("ext2-") or not project.name[5:].strip():
        raise ScaffoldError("fresh project_root must be named ext2-<name>")
    if not project.parent.is_dir():
        raise ScaffoldError("project_root parent must already exist")


def select_release(releases: list) -> dict:
    stable = []
    for release in releases:
        if release.get("prerelease") or release.get("draft"):
            continue
        try:
            number = parse_version(release.get("tag_name", ""))
        except ValueError:
            continue
        stable.append((number, release))
    if not stable:
        raise ScaffoldError("No stable Scaffold release found")
    release = max(stable, key=lambda item: item[0])[1]
    assets = release.get("assets", [])
    matches = [a for a in assets if a.get("name") == ARCHIVE_NAME]
    if len(matches) != 1:
        raise ScaffoldError("Latest stable release must contain exactly one Scaffold ZIP")
    checksums = [a for a in assets if a.get("name") == ARCHIVE_NAME + ".sha256"]
    if len(checksums) > 1:
        raise ScaffoldError("Duplicate scaffold checksum attachments")
    result = {"release_tag": release["tag_name"], "archive_url": matches[0]["browser_download_url"], "expected_sha256": None}
    if checksums:
        import re
        text = download(checksums[0]["browser_download_url"], limit=4096).decode("ascii").strip()
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]" + re.escape(ARCHIVE_NAME), text)
        if not match:
            raise ScaffoldError("Invalid scaffold SHA-256 attachment")
        result["expected_sha256"] = match[1].lower()
    return result


def latest_release() -> dict:
    releases = []
    for page in range(1, 11):
        batch = json.loads(download(f"{RELEASES_URL}?page={page}&per_page=100"))
        if not isinstance(batch, list):
            raise ScaffoldError("Invalid Scaffold releases response")
        releases.extend(batch)
        if len(batch) < 100:
            return select_release(releases)
    raise ScaffoldError("Incomplete Scaffold release listing")


def inspect_archive(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries = []
    total_size = 0
    files = 0
    names = [PurePosixPath(i.filename) for i in archive.infolist() if not i.is_dir()]
    roots = {name.parts[0] for name in names if name.parts}
    wrapper = next(iter(roots)) if len(roots) == 1 and all(len(n.parts) > 1 for n in names) else None
    seen = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in info.filename or any(":" in part or part.rstrip(" .") != part for part in path.parts):
            raise ScaffoldError(f"unsafe archive path: {info.filename}")
        relative = PurePosixPath(*path.parts[1:]) if wrapper else path
        key = str(relative).casefold()
        if key in seen:
            raise ScaffoldError(f"Duplicate scaffold path: {relative}")
        seen.add(key)
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


def extract_checked(archive_path: Path, project: Path, release: dict) -> dict:
    validate_target(project)
    actual_hash = digest(archive_path)
    if release.get("expected_sha256") and actual_hash != release["expected_sha256"]:
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
            "release_tag": release.get("release_tag"),
            "archive_url": release.get("archive_url"),
            "archive_sha256": actual_hash,
            "checksum_verified": bool(release.get("expected_sha256")),
            "checksum_status": "VERIFIED" if release.get("expected_sha256") else "RECORDED_ONLY",
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
    parser.add_argument("--sha256", help="Expected digest required with an explicitly supplied local --archive")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = args.project_root.expanduser().resolve()
    temporary_archive = None
    try:
        validate_target(project)
        if args.archive:
            import re
            if not args.sha256 or not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
                raise ScaffoldError("Local --archive requires --sha256")
            release = {"expected_sha256": args.sha256.lower(), "release_tag": None, "archive_url": None}
            archive_path = args.archive.expanduser().resolve()
            if not archive_path.is_file():
                raise ScaffoldError(f"archive does not exist: {archive_path}")
        else:
            release = latest_release()
            handle, name = tempfile.mkstemp(prefix="mindplus-switch-scaffold-", suffix=".zip")
            os.close(handle)
            temporary_archive = Path(name)
            temporary_archive.write_bytes(download(release["archive_url"]))
            archive_path = temporary_archive
        result = extract_checked(archive_path, project, release)
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8", newline="\n") as output_handle:
                output_handle.write(encoded + "\n")
        print(encoded)
        return 0
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ScaffoldError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "BUILDER_SCAFFOLD", "error": str(exc)}, ensure_ascii=False))
        return 2
    finally:
        if temporary_archive and temporary_archive.exists():
            temporary_archive.unlink()


if __name__ == "__main__":
    sys.exit(main())

