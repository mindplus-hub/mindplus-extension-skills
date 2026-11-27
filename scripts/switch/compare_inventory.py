#!/usr/bin/env python3
"""Compare two MindPlus-Switch V1 inventory snapshots without reading source files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HEADER_KEYS = (
    "status",
    "reason_code",
    "source",
    "config_path",
    "config_error",
    "config_fields",
    "candidates",
)


def load_inventory(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read inventory {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError(f"inventory must be an object with a files list: {path}")
    return payload


def file_map(payload: dict, label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in payload["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"{label} inventory has an invalid file entry")
        relative = item["path"]
        if relative in result:
            raise ValueError(f"{label} inventory has a duplicate file path: {relative}")
        result[relative] = {"size": item.get("size"), "sha256": item.get("sha256")}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    initial_path = args.initial.expanduser().resolve()
    current_path = args.current.expanduser().resolve()
    try:
        initial = load_inventory(initial_path)
        current = load_inventory(current_path)
        initial_files = file_map(initial, "initial")
        current_files = file_map(current, "current")
    except ValueError as exc:
        result = {"status": "FAIL", "reason_code": "INPUT", "error": str(exc)}
        exit_code = 2
    else:
        initial_paths = set(initial_files)
        current_paths = set(current_files)
        header_changes = {
            key: {"initial": initial.get(key), "current": current.get(key)}
            for key in HEADER_KEYS
            if initial.get(key) != current.get(key)
        }
        changed = [
            {
                "path": path,
                "initial": initial_files[path],
                "current": current_files[path],
            }
            for path in sorted(initial_paths & current_paths)
            if initial_files[path] != current_files[path]
        ]
        added = sorted(current_paths - initial_paths)
        removed = sorted(initial_paths - current_paths)
        same = not header_changes and not changed and not added and not removed
        result = {
            "status": "PASS" if same else "FAIL",
            "reason_code": None if same else "SOURCE_DRIFT",
            "initial_inventory": str(initial_path),
            "current_inventory": str(current_path),
            "header_changes": header_changes,
            "added": added,
            "changed": changed,
            "removed": removed,
        }
        exit_code = 0 if same else 2

    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded + "\n")
    print(encoded)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

