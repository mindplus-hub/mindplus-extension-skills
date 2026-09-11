#!/usr/bin/env python3
"""Update the active skill in place, with one compressed rollback snapshot.

Do not sweep temporary directories or old backups during an update. Host safety
reviews still apply to required filesystem changes; never split deletion work
to avoid review. Backups live outside skill discovery directories as ZIP files.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RELEASES = "https://gitee.com/api/v5/repos/mind-plus/mindplus-extension-skills/releases"
RELEASE_PAGE = "https://gitee.com/mind-plus/mindplus-extension-skills/releases/"
IGNORED = {".git", "__pycache__", ".mindplus-agent", ".ms", "node_modules", "dist", "tests"}
LIMIT = 64 * 1024 * 1024
DOWNLOAD_HOST = "gitee.com"
CACHE_FILE = "mindplus-extension-skills-check-cache.json"
CACHE_TTL_SECONDS = 3600
# Release-managed directories are synced exactly to the release content and
# pruned of superseded files; everything else in the installation (e.g.
# _user_meta.json, .git, local notes) belongs to the host and is preserved.
DISTRIBUTED = ("scripts", "references", "assets", "agents")
STAGE_PREFIX = "mindplus-extension-skills-update-"
# tempfile.mkdtemp suffixes use [a-z0-9_]; keep the match tight so only
# staging dirs created by this script are ever swept.
STAGE_NAME = re.compile(r"mindplus-extension-skills-update-[a-z0-9_]{8}")
copy_file = shutil.copy2


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
    host = (urlparse(url).hostname or "").lower()
    if host != DOWNLOAD_HOST and not host.endswith("." + DOWNLOAD_HOST):
        raise ValueError("Release downloads must come from " + DOWNLOAD_HOST)
    req = urllib.request.Request(url, headers={"User-Agent": "mindplus-extension-skills-updater/0.1.0"})
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
        pattern = rf"mindplus-extension-skills-v?{re.escape(label)}-{suffix}\.zip"
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


def version_digest(root: Path) -> str:
    return hashlib.sha256((root / "VERSION").read_bytes()).hexdigest()


def cache_path() -> Path:
    return Path(tempfile.gettempdir()) / CACHE_FILE


def load_cache(root: Path, current: tuple, kind: str) -> dict | None:
    """Return a still-valid cached check for this exact installation, else None.

    The cache binds to the VERSION content digest and layout variant, lives in
    the system temp dir, and never outlives CACHE_TTL_SECONDS or a local
    version change, so cached results expire within an hour. Use --refresh when a newer release is known to exist. Anything unreadable, tampered, or from the clock's future is
    rejected and treated as a cache miss.
    """
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        checked = data["checked_at"]
        if isinstance(checked, bool) or not isinstance(checked, (int, float)):
            return None
        if not 0 <= time.time() - checked <= CACHE_TTL_SECONDS:
            return None
        if (data.get("installation_root") != str(root.resolve()) or data["version"] != ".".join(map(str, current))
                or data["version_sha256"] != version_digest(root)
                or data["variant"] != kind):
            return None
        if data["remote_version"] is not None:
            asset = data["asset"]
            if not isinstance(asset, dict) or not all(
                    isinstance(asset.get(key), str) and asset[key]
                    for key in ("name", "browser_download_url")):
                return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def store_cache(root: Path, current: tuple, kind: str, selected) -> None:
    """Best-effort cache of one successful network check; failures are ignored.

    `selected` is None for CURRENT or a (version tuple, asset dict) pair;
    only the asset fields needed to install are persisted.
    """
    try:
        payload = {
            "checked_at": time.time(),
            "installation_root": str(root.resolve()),
            "ttl_seconds": CACHE_TTL_SECONDS,
            "version": ".".join(map(str, current)),
            "version_sha256": version_digest(root),
            "variant": kind,
            "remote_version": None if selected is None else ".".join(map(str, selected[0])),
            "asset": None if selected is None else {"name": selected[1]["name"],
                                                    "browser_download_url": selected[1]["browser_download_url"]},
        }
        cache_path().write_text(json.dumps(payload), encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError):
        pass


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


def validate_install_root(root: Path) -> None:
    for part in root.parts:
        if part == ".mindplus-skill-backups" or part.startswith(STAGE_PREFIX) or part == "mindplus-skill-updater":
            raise ValueError("Refusing to update a backup or staging copy. Run the updater from the active installed skill directory.")


def backup_path(root: Path) -> Path:
    identity = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:20]
    return Path(tempfile.gettempdir()) / "mindplus-skill-updater" / identity / "previous.zip"


def write_backup(root: Path, backup: Path) -> None:
    # Assemble fully before replacing the previous snapshot, so a read failure
    # leaves the existing rollback archive intact.
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file() and not any(part in IGNORED for part in path.relative_to(root).parts):
                archive.write(path, path.relative_to(root).as_posix())
    backup.parent.mkdir(parents=True, exist_ok=True)
    pending = backup.with_suffix(".pending.zip")
    pending.write_bytes(stream.getvalue())
    os.replace(pending, backup)


def sync_release(stage: Path, root: Path) -> int:
    """Overlay the staged release onto the installation in place.

    Files are copied over their existing counterparts instead of swapping the
    whole directory, so local files the release does not ship (e.g.
    _user_meta.json, .git) survive untouched. Afterwards the release-managed
    directories are pruned of files the release no longer contains, subject to host permissions, keeping the installation layout identical to the release.
    Returns the number of pruned files (0 for pure-overwrite releases).
    """
    for src in sorted(stage.rglob("*"), key=lambda p: (p.name == "VERSION", str(p))):
        if src.is_symlink() or not src.is_file():
            continue
        dst = root / src.relative_to(stage)
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy_file(src, dst)
    staged = {p.relative_to(stage) for p in stage.rglob("*") if p.is_file() or p.is_symlink()}
    pruned = 0
    for folder in DISTRIBUTED:
        base = root / folder
        if not base.is_dir():
            continue
        for path in list(base.rglob("*")):
            if (path.is_symlink() or path.is_file()) and path.relative_to(root) not in staged:
                path.unlink()
                pruned += 1
    return pruned


def restore_installation(backup: Path, root: Path, staged_files: set[Path]) -> None:
    """Restore snapshot; propagate any incomplete rollback instead of hiding it."""
    with zipfile.ZipFile(backup) as archive:
        kept = {Path(name) for name in archive.namelist()}
        for name in archive.namelist():
            dst = root / name
            if not dst.resolve().is_relative_to(root.resolve()):
                raise ValueError("Rollback path escapes installation")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(archive.read(name))
        for relative in staged_files - kept:
            path = root / relative
            if path.is_file():
                path.unlink()


def install(root: Path, data: bytes, number: tuple, kind: str) -> dict:
    root = root.resolve()
    validate_install_root(root)
    if number <= version(root):
        raise ValueError("Selected release is not newer than the installed version")
    try:
        stage = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX))
    except OSError as exc:
        raise ValueError("Cannot create the update staging directory in the system temp "
                         "folder; the sandbox may deny writes there. " + str(exc)) from exc
    backup = backup_path(root)
    unpack(data, stage, number, kind)
    for path in root.rglob("*"):
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked installation requires manual update")
    if (root / ".git").is_dir():
        result = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode or result.stdout.strip():
            raise ValueError("Local Git changes or unavailable Git: update skipped")
    write_backup(root, backup)
    staged_files = {p.relative_to(stage) for p in stage.rglob("*") if p.is_file()}
    try:
        pruned = sync_release(stage, root)
        if version(root) != number or variant(root) != kind:
            raise ValueError("Installed version or layout does not match selected release")
        for relative in staged_files:
            if (root / relative).read_bytes() != (stage / relative).read_bytes():
                raise ValueError(f"Installed file verification failed: {relative}")
    except (OSError, ValueError) as exc:
        try:
            restore_installation(backup, root, staged_files)
        except (OSError, ValueError) as rollback:
            raise ValueError(f"Update failed and rollback is incomplete. Stop using this installation; recovery ZIP: {backup}; {rollback}") from exc
        raise ValueError(f"Update failed; original files restored. Resolve the reported error before retry: {exc}") from exc
    return {"backup": str(backup), "pruned": pruned, "removed_backup_dirs": 0}


def update(root: Path, check_only: bool = False, refresh: bool = False) -> dict:
    root = root.resolve()
    validate_install_root(root)
    swept = 0
    current, kind = version(root), variant(root)
    result = {"current_version": ".".join(map(str, current)), "variant": kind, "releases": RELEASE_PAGE,
              "swept_stage_files": swept, "installation_root": str(root)}
    cached = None if refresh else load_cache(root, current, kind)
    selected = None
    if cached is not None and cached.get("remote_version") is not None:
        try:
            selected = (parse_version(cached["remote_version"]), cached["asset"])
        except ValueError:
            cached = None
    if cached is None:
        releases = []
        for page in range(1, 11):
            batch = json.loads(download(f"{RELEASES}?page={page}&per_page=100"))
            if not isinstance(batch, list):
                raise ValueError("Invalid releases response")
            releases.extend(batch)
            if len(batch) < 100:
                break
        selected = choose(releases, current, kind)
        store_cache(root, current, kind, selected)
    result["cache_hit"] = cached is not None
    if not selected:
        return {**result, "status": "CURRENT", "detail": "No newer stable Release with a matching package"}
    number, asset = selected
    result.update(remote_version=".".join(map(str, number)), asset=asset["name"])
    if check_only:
        return {**result, "status": "UPDATE_AVAILABLE"}
    info = install(root, download(asset["browser_download_url"]), number, kind)
    return {**result, "status": "UPDATED", "backup": info["backup"],
            "installed_version": ".".join(map(str, version(root))),
            "pruned_release_files": info["pruned"],
            "removed_backup_dirs": info["removed_backup_dirs"],
            "next_action": "Reload SKILL.md before routing. Do not run the update check again in this task."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cached check result and query the network now")
    args = parser.parse_args()
    try:
        result = update(ROOT, args.check_only, args.refresh)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        result = {"status": "SKIPPED", "reason": "UPDATE_UNAVAILABLE", "detail": str(exc),
                  "next_action": "Briefly report the skipped update and continue with the installed "
                                 "version. If detail mentions files in use, close the program holding "
                                 "them and retry once."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
