#!/usr/bin/env python3
"""Select, verify, and optionally update the MindPlus-Switch reference bundle."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


SKILL_VERSION = "0.6.0"
SUPPORTED_SCHEMA = 1
MAX_JSON_BYTES = 1024 * 1024
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 40 * 1024 * 1024
MAX_FILES = 1000


class ReferenceError(RuntimeError):
    """A reference source, integrity, compatibility, or cache failure."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReferenceError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"\d+(?:\.\d+)*", value.strip())
    if not match:
        raise ReferenceError(f"invalid numeric version: {value!r}")
    return tuple(int(item) for item in value.split("."))


def safe_relative(value: str) -> PurePosixPath:
    if "\\" in value:
        raise ReferenceError(f"backslashes are not allowed in bundle paths: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ReferenceError(f"unsafe bundle path: {value!r}")
    return path


def manifest_content_hash(files: list[dict]) -> str:
    canonical = "".join(
        f"{item['path']}\0{item['sha256']}\0{item['size']}\n"
        for item in sorted(files, key=lambda value: value["path"])
    )
    return sha256_bytes(canonical.encode("utf-8"))


def validate_bundle(root: Path, expected_bundle_id: str) -> dict:
    root = root.resolve()
    manifest = load_json(root / "manifest.json")
    if manifest.get("schema_version") != SUPPORTED_SCHEMA:
        raise ReferenceError(f"unsupported bundle schema: {manifest.get('schema_version')!r}")
    if manifest.get("bundle_id") != expected_bundle_id:
        raise ReferenceError(f"unexpected bundle_id: {manifest.get('bundle_id')!r}")
    release_id = str(manifest.get("release_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9._-]+", release_id):
        raise ReferenceError(f"bundle has an unsafe release_id: {release_id!r}")
    minimum = str(manifest.get("min_skill_version", ""))
    if version_tuple(minimum) > version_tuple(SKILL_VERSION):
        raise ReferenceError(f"bundle requires Skill {minimum}, installed is {SKILL_VERSION}")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise ReferenceError("bundle manifest has an invalid file list")
    declared: set[str] = set()
    normalized_files: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            raise ReferenceError("bundle file entry must be an object")
        relative = safe_relative(str(item.get("path", ""))).as_posix()
        if relative in declared or relative == "manifest.json":
            raise ReferenceError(f"duplicate or reserved bundle file: {relative}")
        declared.add(relative)
        target = root.joinpath(*PurePosixPath(relative).parts)
        if not target.is_file() or target.is_symlink():
            raise ReferenceError(f"declared bundle file is missing or unsafe: {relative}")
        actual_size = target.stat().st_size
        actual_hash = digest(target)
        if actual_size != item.get("size") or actual_hash != item.get("sha256"):
            raise ReferenceError(f"bundle file integrity mismatch: {relative}")
        normalized_files.append({"path": relative, "size": actual_size, "sha256": actual_hash})
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != declared:
        raise ReferenceError(f"bundle has undeclared or missing files: extra={sorted(actual-declared)}, missing={sorted(declared-actual)}")
    content_hash = manifest_content_hash(normalized_files)
    if content_hash != manifest.get("content_sha256"):
        raise ReferenceError("bundle content_sha256 mismatch")
    modes = manifest.get("supported_modes")
    if not isinstance(modes, list) or not modes or any(not isinstance(mode, str) or not mode for mode in modes):
        raise ReferenceError("bundle supported_modes must be a non-empty string list")
    if len(set(modes)) != len(modes):
        raise ReferenceError("bundle supported_modes contains duplicates")
    return manifest


def default_cache_root() -> Path:
    override = os.environ.get("MINDPLUS_AGENT_SWITCH_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return (Path(base) / "MindPlus-Agent-Skill" / "switch-reference-cache").resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Caches" / "MindPlus-Agent-Skill" / "switch-reference-cache").resolve()
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return (Path(base) / "mindplus-agent-skill" / "switch-reference-cache").resolve()
    return (Path.home() / ".cache" / "mindplus-agent-skill" / "switch-reference-cache").resolve()


def read_location(location: str, max_bytes: int) -> tuple[bytes, str, bool]:
    location = location.strip()
    if not location:
        raise ReferenceError("empty release location")
    is_windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", location))
    parsed = urllib.parse.urlparse(location)
    if is_windows_path or not parsed.scheme:
        path = Path(location).expanduser().resolve()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ReferenceError(f"cannot read local release file {path}: {exc}") from exc
        final = str(path)
        remote = False
    elif parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path)).resolve()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ReferenceError(f"cannot read local release file {path}: {exc}") from exc
        final = str(path)
        remote = False
    elif parsed.scheme == "https":
        request = urllib.request.Request(location, headers={"User-Agent": f"MindPlus-Switch/{SKILL_VERSION}"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read(max_bytes + 1)
                final = response.geturl()
        except OSError as exc:
            raise ReferenceError(f"release download failed: {exc}") from exc
        remote = True
    else:
        raise ReferenceError(f"release location must be HTTPS or a local test path: {location}")
    if len(data) > max_bytes:
        raise ReferenceError(f"release content exceeds {max_bytes} bytes")
    return data, final, remote


def resolve_bundle_location(resolved_channel: str, bundle_url: str, remote: bool) -> str:
    parsed = urllib.parse.urlparse(bundle_url)
    if re.match(r"^[A-Za-z]:[\\/]", bundle_url) or parsed.scheme in {"https", "file"}:
        return bundle_url
    if parsed.scheme:
        raise ReferenceError(f"unsupported bundle URL scheme: {parsed.scheme}")
    if remote:
        resolved = urllib.parse.urljoin(resolved_channel, bundle_url)
        if urllib.parse.urlparse(resolved).scheme != "https":
            raise ReferenceError("remote bundle URL did not resolve to HTTPS")
        return resolved
    return str((Path(resolved_channel).parent / bundle_url).resolve())


def extract_zip(data: bytes, destination: Path) -> None:
    total = 0
    count = 0
    seen: set[str] = set()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ReferenceError(f"release bundle is not a valid ZIP: {exc}") from exc
    with archive:
        for info in archive.infolist():
            name = info.filename
            if "\\" in name:
                raise ReferenceError(f"ZIP entry uses backslashes: {name!r}")
            relative = safe_relative(name.rstrip("/")) if name.rstrip("/") else None
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ReferenceError(f"ZIP symlink is not allowed: {name}")
            if info.is_dir():
                continue
            if relative is None:
                raise ReferenceError("ZIP contains an empty filename")
            normalized = relative.as_posix().casefold()
            if normalized in seen:
                raise ReferenceError(f"ZIP contains a duplicate or case-colliding path: {name}")
            seen.add(normalized)
            if info.flag_bits & 0x1:
                raise ReferenceError(f"encrypted ZIP entries are not allowed: {name}")
            count += 1
            total += info.file_size
            if count > MAX_FILES or total > MAX_UNPACKED_BYTES:
                raise ReferenceError("ZIP exceeds the allowed file count or unpacked size")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)


def choose_cached_bundle(cache_root: Path, expected_bundle_id: str) -> tuple[Path, dict] | None:
    active_path = cache_root / "active.json"
    if not active_path.is_file():
        return None
    try:
        active = load_json(active_path)
        release_id = str(active["release_id"])
        if not re.fullmatch(r"[A-Za-z0-9._-]+", release_id):
            return None
        root = (cache_root / "releases" / release_id).resolve()
        if root.parent != (cache_root / "releases").resolve():
            return None
        manifest = validate_bundle(root, expected_bundle_id)
        return root, manifest
    except (ReferenceError, KeyError, OSError):
        return None


def choose_local_bundle(
    cached: tuple[Path, dict] | None,
    bundled_root: Path,
    bundled_manifest: dict | None,
) -> tuple[Path, dict, str] | None:
    """Prefer the cache unless it omits a mode shipped by this Skill."""
    if cached and bundled_manifest:
        cached_modes = set(cached[1].get("supported_modes", []))
        bundled_modes = set(bundled_manifest.get("supported_modes", []))
        if not bundled_modes.issubset(cached_modes):
            return bundled_root, bundled_manifest, "bundled"
        return cached[0], cached[1], "cache"
    if cached:
        return cached[0], cached[1], "cache"
    if bundled_manifest:
        return bundled_root, bundled_manifest, "bundled"
    return None


def result_payload(status: str, root: Path, manifest: dict, source: str, warning: str | None = None) -> dict:
    result = {
        "status": status,
        "active_root": str(root.resolve()),
        "release_id": manifest["release_id"],
        "content_sha256": manifest["content_sha256"],
        "supported_modes": manifest["supported_modes"],
        "source": source,
        "skill_version": SKILL_VERSION,
    }
    if warning:
        result["warning"] = warning
    return result


def execute(args: argparse.Namespace) -> dict:
    skill_root = args.skill_root.expanduser().resolve()
    switch_reference_root = skill_root / "references" / "switch"
    bundled_root = switch_reference_root / "generated"
    channel_config_path = args.channel_config.expanduser().resolve() if args.channel_config else switch_reference_root / "release-channel.json"
    channel = load_json(channel_config_path)
    expected_bundle_id = str(channel.get("bundle_id", "mindplus-switch-references"))
    try:
        bundled_manifest = validate_bundle(bundled_root, expected_bundle_id)
        bundled_error = None
    except ReferenceError as exc:
        bundled_manifest = None
        bundled_error = str(exc)
    cache_root = args.cache_root.expanduser().resolve() if args.cache_root else default_cache_root()
    cached = choose_cached_bundle(cache_root, expected_bundle_id)
    local = choose_local_bundle(cached, bundled_root, bundled_manifest)

    if args.offline:
        if local:
            status = "LOCAL_CACHE" if local[2] == "cache" else "BUNDLED_ONLY"
            return result_payload(status, local[0], local[1], local[2])
        raise ReferenceError(f"no valid offline reference bundle; bundled error: {bundled_error}")

    channel_url = args.channel_url or str(channel.get("channel_url", "")).strip()
    enabled = bool(channel.get("enabled", False)) or bool(args.channel_url)
    if not enabled or not channel_url:
        if local:
            status = "LOCAL_CACHE" if local[2] == "cache" else "BUNDLED_ONLY"
            return result_payload(status, local[0], local[1], local[2], "remote release channel is not configured")
        raise ReferenceError(f"remote release channel is not configured and bundled is invalid: {bundled_error}")

    try:
        channel_data, resolved_channel, remote = read_location(channel_url, MAX_JSON_BYTES)
        latest = json.loads(channel_data.decode("utf-8-sig"))
        if not isinstance(latest, dict):
            raise ReferenceError("latest.json root must be an object")
        if latest.get("schema_version") != SUPPORTED_SCHEMA:
            raise ReferenceError("latest.json has an unsupported schema")
        if latest.get("bundle_id") != expected_bundle_id:
            raise ReferenceError("latest.json bundle_id mismatch")
        minimum = str(latest.get("min_skill_version", ""))
        if version_tuple(minimum) > version_tuple(SKILL_VERSION):
            raise ReferenceError(f"latest reference requires Skill {minimum}")
        release_id = str(latest.get("release_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9._-]+", release_id):
            raise ReferenceError("latest.json has an unsafe release_id")
        latest_modes = latest.get("supported_modes")
        if not isinstance(latest_modes, list) or not latest_modes or any(not isinstance(mode, str) or not mode for mode in latest_modes):
            raise ReferenceError("latest.json supported_modes must be a non-empty string list")
        if len(set(latest_modes)) != len(latest_modes):
            raise ReferenceError("latest.json supported_modes contains duplicates")
        if not re.fullmatch(r"[a-f0-9]{64}", str(latest.get("content_sha256", ""))):
            raise ReferenceError("latest.json has an invalid content_sha256")
        if not re.fullmatch(r"[a-f0-9]{64}", str(latest.get("bundle_sha256", ""))):
            raise ReferenceError("latest.json has an invalid bundle_sha256")
        candidates = [(cached[0], cached[1], "cache")] if cached else []
        if bundled_manifest:
            candidates.append((bundled_root, bundled_manifest, "bundled"))
        for root, manifest, source in candidates:
            if manifest.get("release_id") == release_id and manifest.get("content_sha256") == latest.get("content_sha256"):
                return result_payload("UNCHANGED", root, manifest, source)
        bundle_location = resolve_bundle_location(resolved_channel, str(latest.get("bundle_url", "")), remote)
        bundle_data, _, _ = read_location(bundle_location, MAX_ZIP_BYTES)
        bundle_size = latest.get("bundle_size")
        if bundle_size is not None and (not isinstance(bundle_size, int) or bundle_size != len(bundle_data)):
            raise ReferenceError("release ZIP size does not match latest.json")
        if sha256_bytes(bundle_data) != latest.get("bundle_sha256"):
            raise ReferenceError("release ZIP SHA-256 mismatch")
        cache_root.mkdir(parents=True, exist_ok=True)
        staging_parent = cache_root / "staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="reference-", dir=str(staging_parent)))
        try:
            extract_zip(bundle_data, staging)
            manifest = validate_bundle(staging, expected_bundle_id)
            if manifest.get("release_id") != release_id or manifest.get("content_sha256") != latest.get("content_sha256"):
                raise ReferenceError("release ZIP manifest does not match latest.json")
            if sorted(manifest.get("supported_modes", [])) != sorted(latest_modes):
                raise ReferenceError("release ZIP supported_modes does not match latest.json")
            releases_root = cache_root / "releases"
            releases_root.mkdir(parents=True, exist_ok=True)
            destination = releases_root / release_id
            if destination.exists():
                try:
                    existing = validate_bundle(destination, expected_bundle_id)
                except ReferenceError:
                    shutil.rmtree(destination)
                    shutil.copytree(staging, destination)
                else:
                    if existing.get("content_sha256") != manifest.get("content_sha256"):
                        raise ReferenceError("existing cache release_id has different content")
            else:
                shutil.copytree(staging, destination)
            installed = validate_bundle(destination, expected_bundle_id)
            if installed.get("release_id") != release_id or installed.get("content_sha256") != manifest.get("content_sha256"):
                raise ReferenceError("installed cache release does not match the verified staging bundle")
            write_json(cache_root / "active.json", {"release_id": release_id, "content_sha256": installed["content_sha256"]})
            return result_payload("UPDATED", destination, installed, "release")
        finally:
            if staging is not None and staging.exists():
                shutil.rmtree(staging)
    except (ReferenceError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        warning = str(exc)
        if bundled_error:
            warning = f"{warning}; bundled error: {bundled_error}"
        if local:
            status = "STALE_CACHE" if local[2] == "cache" else "BUNDLED_FALLBACK"
            return result_payload(status, local[0], local[1], local[2], warning)
        raise ReferenceError(f"no valid reference bundle after release check: {warning}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--channel-config", type=Path)
    parser.add_argument("--channel-url")
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
        exit_code = 0
    except (ReferenceError, OSError, KeyError, TypeError, ValueError) as exc:
        result = {"status": "BLOCKED", "reason_code": "REFERENCE_BUNDLE", "error": str(exc)}
        exit_code = 2
    if args.output:
        write_json(args.output.expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
