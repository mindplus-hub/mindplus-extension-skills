#!/usr/bin/env python3
"""Install newer official Release ZIPs, selecting WB or universal by layout depth."""
from __future__ import annotations
import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
RELEASES = "https://gitee.com/api/v5/repos/mind-plus/mindplus-agent-skill/releases"
RELEASE_PAGE = "https://gitee.com/mind-plus/mindplus-agent-skill/releases/"
IGNORED = {".git", "__pycache__", ".mindplus-agent", ".ms", "node_modules", "dist", "tests"}
LIMIT = 64 * 1024 * 1024


def parse_version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value.strip()):
        raise ValueError("Expected stable version vX.Y.Z")
    return tuple(map(int, value.strip().lstrip("v").split(".")))


def version(root: Path) -> tuple[int, int, int]:
    return parse_version((root / "VERSION").read_text(encoding="utf-8-sig"))


def variant(root: Path) -> str:
    # Only inspect distributed runtime directories; Git and host caches are irrelevant.
    files = [p for folder in ("scripts", "references", "assets", "agents")
             for p in (root / folder).rglob("*") if p.is_file()
             and not any(part in IGNORED for part in p.relative_to(root).parts)]
    if not files:
        raise ValueError("Skill runtime files are missing")
    return "wb" if all(len(p.relative_to(root).parts) <= 2 for p in files) else "universal"


def download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Release downloads must use HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": "mindplus-agent-skill-updater/0.1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Insecure download redirect")
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Release response exceeds size limit")
    return data


def choose(releases: list, current: tuple, kind: str):
    candidates = []
    for release in releases:
        if release.get("prerelease") or release.get("draft"):
            continue
        try:
            number = parse_version(release.get("tag_name", ""))
        except ValueError:
            continue
        if number <= current:
            continue
        label = ".".join(map(str, number))
        suffix = "(?:wb|workbuddy)" if kind == "wb" else "(?:universal|others)"
        pattern = rf"mindplus-agent-skill-v?{re.escape(label)}-{suffix}\.zip"
        matches = [a for a in release.get("assets", []) if re.fullmatch(pattern, a.get("name", ""), re.I)]
        if kind == "universal" and not matches:
            # Gitee exposes its source ZIP as a Release asset named <tag>.zip.
            matches = [a for a in release.get("assets", [])
                       if a.get("name") == release["tag_name"] + ".zip"]
        if len(matches) > 1:
            raise ValueError("Ambiguous Release packages for one version")
        if matches:
            candidates.append((number, matches[0]))
    return max(candidates, key=lambda x: x[0]) if candidates else None


def unpack(data: bytes, stage: Path, expected: tuple, kind: str) -> None:
    seen = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(x.file_size for x in archive.infolist()) > LIMIT * 4 or len(archive.infolist()) > 10000:
            raise ValueError("Unpacked release exceeds size limit")
        members = [PurePosixPath(x.filename) for x in archive.infolist() if not x.is_dir()]
        wrapper = None
        if kind == "universal" and members and all(len(x.parts) > 1 for x in members):
            roots = {x.parts[0] for x in members}
            if len(roots) == 1:
                wrapper = next(iter(roots))
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename
                    or any(":" in p or p.rstrip(" .") != p or p.upper().split(".")[0] in
                           {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}
                           for p in name.parts)
                    or ".git" in name.parts
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe Release ZIP path")
            if item.is_dir():
                continue
            if wrapper:
                name = PurePosixPath(*name.parts[1:])
            key = str(name).casefold()
            if key in seen:
                raise ValueError("Duplicate Release ZIP path")
            seen.add(key)
            if kind == "wb" and len(name.parts) > 2:
                raise ValueError("WB package contains nested directories")
            target = stage.joinpath(*name.parts)
            if not target.resolve().is_relative_to(stage.resolve()):
                raise ValueError("Release path escapes staging")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(item)
            if target.suffix == ".py":
                ast.parse(content.decode("utf-8-sig"))
            elif target.suffix == ".json":
                json.loads(content)
            target.write_bytes(content)
    if not (stage / "SKILL.md").is_file() or not (stage / "scripts/mpa.py").is_file():
        raise ValueError("Release ZIP must contain SKILL.md and scripts/mpa.py at its root")
    if version(stage) != expected or variant(stage) != kind:
        raise ValueError("Release version or layout does not match the selected package")


def install(root: Path, data: bytes, number: tuple, kind: str) -> str:
    stage = Path(tempfile.mkdtemp(prefix=root.name + "-update-", dir=root.parent))
    backup = root.parent / ".mindplus-skill-backups" / (root.name + "-" + uuid.uuid4().hex)
    try:
        unpack(data, stage, number, kind)
        for path in root.rglob("*"):
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked installation requires manual update")
        if (root / ".git").is_dir():
            result = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode or result.stdout.strip():
                raise ValueError("Local Git changes or unavailable Git: update skipped")
            shutil.copytree(root / ".git", stage / ".git")
        backup.parent.mkdir(exist_ok=True)
        root.rename(backup)
        try:
            stage.rename(root)
        except OSError:
            backup.rename(root)
            raise
    finally:
        if stage.exists() and stage.parent == root.parent and stage.name.startswith(root.name + "-update-"):
            shutil.rmtree(stage)
    return str(backup)


def update(root: Path, check_only: bool = False) -> dict:
    root = root.resolve()
    current, kind = version(root), variant(root)
    releases = []
    for page in range(1, 11):
        batch = json.loads(download(f"{RELEASES}?page={page}&per_page=100"))
        if not isinstance(batch, list):
            raise ValueError("Invalid releases response")
        releases.extend(batch)
        if len(batch) < 100:
            break
    selected = choose(releases, current, kind)
    result = {"current_version": ".".join(map(str, current)), "variant": kind, "releases": RELEASE_PAGE}
    if not selected:
        return {**result, "status": "CURRENT", "detail": "No newer stable Release with a matching package"}
    number, asset = selected
    result.update(remote_version=".".join(map(str, number)), asset=asset["name"])
    if check_only:
        return {**result, "status": "UPDATE_AVAILABLE"}
    backup = install(root, download(asset["browser_download_url"]), number, kind)
    return {**result, "status": "UPDATED", "backup": backup,
            "next_action": "Reload SKILL.md before routing. Do not run the update check again in this task."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        result = update(ROOT, args.check_only)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        result = {"status": "SKIPPED", "reason": "UPDATE_UNAVAILABLE", "detail": str(exc),
                  "next_action": "Briefly report the skipped update and continue with the installed version."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
