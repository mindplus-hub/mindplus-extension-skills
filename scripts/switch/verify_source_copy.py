#!/usr/bin/env python3
"""Verify a JSON list of source-to-target file copies by size and SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--target-root", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    target_root = args.target_root.expanduser().resolve()
    mapping_path = args.mapping.expanduser().resolve()
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason_code": "INPUT", "error": str(exc)}, ensure_ascii=False))
        return 2

    copies = payload.get("copies", payload) if isinstance(payload, dict) else payload
    if not isinstance(copies, list):
        print(json.dumps({"status": "FAIL", "reason_code": "INPUT", "error": "mapping must be a list or {copies: list}"}, ensure_ascii=False))
        return 2

    checks = []
    for item in copies:
        if not isinstance(item, dict) or not item.get("source") or not item.get("target"):
            checks.append({"status": "FAIL", "error": "each copy needs source and target"})
            continue
        source = (source_root / str(item["source"])).resolve()
        target = (target_root / str(item["target"])).resolve()
        entry = {"source": str(source), "target": str(target)}
        if not inside(source, source_root) or not inside(target, target_root):
            entry.update({"status": "FAIL", "error": "path escapes declared root"})
        elif not source.is_file() or not target.is_file():
            entry.update({"status": "FAIL", "error": "source or target file is missing"})
        else:
            source_hash = digest(source)
            target_hash = digest(target)
            entry.update({"source_size": source.stat().st_size, "target_size": target.stat().st_size, "source_sha256": source_hash, "target_sha256": target_hash, "status": "PASS" if source_hash == target_hash else "FAIL"})
            if source_hash != target_hash:
                entry["error"] = "sha256 mismatch"
        checks.append(entry)

    result = {"status": "PASS" if checks and all(item.get("status") == "PASS" for item in checks) else "FAIL", "count": len(checks), "checks": checks}
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8", newline="\n")
    print(encoded)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())


