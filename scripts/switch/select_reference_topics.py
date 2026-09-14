#!/usr/bin/env python3
"""Select the verified reference topics required by one V1 inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


SUPPORTED_MODES = {"UPLOAD", "PYTHON_BLOCK"}


class SelectionError(RuntimeError):
    """A route, index, topic, or integrity check failed."""


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SelectionError(f"JSON root must be an object: {path}")
    return value


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_topic_path(root: Path, value: object) -> tuple[str, Path]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SelectionError(f"topic has an invalid path: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SelectionError(f"topic has an unsafe path: {value!r}")
    target = (root / Path(*relative.parts)).resolve()
    if not inside(target, root) or not target.is_file():
        raise SelectionError(f"topic file is missing or outside active_root: {value!r}")
    return relative.as_posix(), target


def choose_mode(inventory: dict, explicit_mode: str | None) -> str:
    candidates = []
    for candidate in inventory.get("candidates", []):
        if isinstance(candidate, dict) and candidate.get("mode") in SUPPORTED_MODES:
            candidates.append(str(candidate["mode"]))
    candidates = sorted(set(candidates))
    if explicit_mode:
        if explicit_mode not in candidates:
            raise SelectionError(
                f"explicit mode {explicit_mode} conflicts with V1 candidates {candidates}"
            )
        return explicit_mode
    if len(candidates) != 1:
        raise SelectionError(f"V1 inventory must have exactly one supported mode candidate: {candidates}")
    return candidates[0]


def features_for_mode(inventory: dict, mode: str) -> list[str]:
    by_mode = inventory.get("reference_features_by_mode")
    if isinstance(by_mode, dict) and isinstance(by_mode.get(mode), list):
        raw = by_mode[mode]
    else:
        raw = inventory.get("reference_features", [])
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item for item in raw):
        raise SelectionError("inventory reference features must be a string list")
    return sorted(set(raw))


def select(inventory_path: Path, active_root: Path, explicit_mode: str | None) -> dict:
    inventory_path = inventory_path.expanduser().resolve()
    active_root = active_root.expanduser().resolve()
    if not active_root.is_dir():
        raise SelectionError(f"active_root is not a directory: {active_root}")

    inventory = load_json(inventory_path)
    if inventory.get("status") != "PASS":
        raise SelectionError("V1 inventory is not PASS")
    mode = choose_mode(inventory, explicit_mode)

    index = load_json(active_root / "index.json")
    manifest = load_json(active_root / "manifest.json")
    if index.get("schema_version") != 1 or manifest.get("schema_version") != 1:
        raise SelectionError("unsupported reference schema")
    if index.get("bundle_id") != manifest.get("bundle_id"):
        raise SelectionError("index and manifest bundle_id differ")
    if mode not in index.get("supported_modes", []) or mode not in manifest.get("supported_modes", []):
        raise SelectionError(f"active reference bundle does not support {mode}")

    profiles = index.get("route_profiles")
    profile = profiles.get(mode) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise SelectionError(f"reference index has no route profile for {mode}")
    always = profile.get("always")
    feature_map = profile.get("features", {})
    if not isinstance(always, list) or not isinstance(feature_map, dict):
        raise SelectionError(f"reference route profile is malformed for {mode}")

    topics = index.get("topics")
    if not isinstance(topics, list):
        raise SelectionError("reference index topics must be a list")
    topic_map = {
        item.get("topic_id"): item
        for item in topics
        if isinstance(item, dict) and isinstance(item.get("topic_id"), str)
    }
    if len(topic_map) != len(topics):
        raise SelectionError("reference index contains duplicate or invalid topic IDs")

    manifest_entries = manifest.get("files")
    if not isinstance(manifest_entries, list):
        raise SelectionError("reference manifest files must be a list")
    manifest_files = {
        item.get("path"): item
        for item in manifest_entries
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if len(manifest_files) != len(manifest_entries):
        raise SelectionError("reference manifest contains duplicate or invalid file paths")
    features = features_for_mode(inventory, mode)
    raw_findings = inventory.get("source_anomalies", [])
    if not isinstance(raw_findings, list) or any(not isinstance(item, dict) for item in raw_findings):
        raise SelectionError("inventory source_anomalies must be an object list")
    findings = [item for item in raw_findings if item.get("mode") in (None, mode)]
    unknown_features = sorted(feature for feature in features if feature not in feature_map)
    if unknown_features:
        raise SelectionError(
            f"reference profile does not map observed features for {mode}: {unknown_features}"
        )

    requested: list[tuple[str, str]] = [(str(topic_id), "always") for topic_id in always]
    if inventory.get("v1_entry_inventory", {}).get(mode, {}).get("secondary_labels"):
        requested.append(("shared.block.special", "v1-secondary-label:submenu"))
    if "field-string" in features:
        requested.append(("shared.block.special", "field-string:shadow-symbol"))
    for feature in features:
        mapped = feature_map.get(feature)
        if not isinstance(mapped, list) or any(not isinstance(item, str) for item in mapped):
            raise SelectionError(f"reference feature mapping is malformed: {mode}/{feature}")
        requested.extend((topic_id, feature) for topic_id in mapped)

    selected = []
    positions: dict[str, int] = {}
    for topic_id, reason in requested:
        topic = topic_map.get(topic_id)
        if not isinstance(topic, dict):
            raise SelectionError(f"route references unknown topic: {topic_id}")
        if mode not in topic.get("modes", []):
            raise SelectionError(f"topic {topic_id} does not support {mode}")
        if topic_id in positions:
            selected[positions[topic_id]]["matched_by"].append(reason)
            continue
        relative, target = safe_topic_path(active_root, topic.get("path"))
        declared = manifest_files.get(relative)
        if not isinstance(declared, dict):
            raise SelectionError(f"selected topic is absent from manifest: {relative}")
        expected_sha = declared.get("sha256")
        if not isinstance(expected_sha, str) or digest(target) != expected_sha:
            raise SelectionError(f"selected topic failed SHA-256 verification: {relative}")
        positions[topic_id] = len(selected)
        selected.append(
            {
                "topic_id": topic_id,
                "title": topic.get("title"),
                "source_key": topic.get("source_key"),
                "relative_path": relative,
                "path": str(target),
                "matched_by": [reason],
            }
        )

    return {
        "status": "PASS",
        "reason_code": None,
        "mode": mode,
        "release_id": manifest.get("release_id"),
        "content_sha256": manifest.get("content_sha256"),
        "active_root": str(active_root),
        "inventory": str(inventory_path),
        "observed_features": features,
        "source_anomalies": findings,
        "topic_count": len(selected),
        "topics": selected,
    }


def write_result(path: Path, result: dict) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output_handle:
        output_handle.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--active-root", type=Path)
    source.add_argument("--reference-state", type=Path)
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if args.reference_state:
            state = load_json(args.reference_state.expanduser().resolve())
            if state.get("status") == "BLOCKED" or not state.get("active_root"):
                raise SelectionError("reference state has no usable active_root")
            active_root = Path(str(state["active_root"]))
        else:
            active_root = args.active_root
        result = select(args.inventory, active_root, args.mode)
        exit_code = 0
    except (SelectionError, OSError) as exc:
        result = {"status": "BLOCKED", "reason_code": "REFERENCE_SELECTION", "error": str(exc)}
        exit_code = 2

    if args.output:
        try:
            write_result(args.output, result)
        except OSError as exc:
            result = {"status": "BLOCKED", "reason_code": "WORKSPACE", "error": str(exc)}
            exit_code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
