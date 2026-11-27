#!/usr/bin/env python3
"""Create the exact V2 config skeleton for one fresh conversion target."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = SKILL_ROOT / "references" / "switch" / "config-schema.json"


def load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc


def locale_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"zh-cn": "", "en": ""}
    return {
        language: value.get(language, "") if isinstance(value.get(language, ""), str) else ""
        for language in ("zh-cn", "en")
    }


def default_for_type(type_name: str) -> object:
    if type_name == "locale_map":
        return {"zh-cn": "", "en": ""}
    if type_name == "array":
        return []
    if type_name == "meta":
        return {"runtimeVersion": ""}
    if type_name == "object":
        return {}
    if type_name == "boolean":
        return False
    return ""


def build_config(source_config: dict, inventory: dict, mode: str, schema: dict) -> dict:
    profiles = schema.get("modes")
    if not isinstance(profiles, dict) or not isinstance(profiles.get(mode), dict):
        raise ValueError(f"no config schema profile for mode {mode}")
    profile = profiles[mode]
    required = profile.get("required_fields")
    types = profile.get("types")
    fixed = profile.get("fixed_values")
    if not isinstance(required, list) or not isinstance(types, dict) or not isinstance(fixed, dict):
        raise ValueError(f"invalid config schema profile for mode {mode}")
    if any(not isinstance(field, str) or not isinstance(types.get(field), str) for field in required):
        raise ValueError(f"config schema has an untyped required field for mode {mode}")

    identity = inventory.get("identity")
    if not isinstance(identity, dict):
        identity = {}
    values: dict[str, object] = {
        field: default_for_type(types[field])
        for field in required
        if isinstance(field, str) and isinstance(types.get(field), str)
    }
    values.update(
        {
            "id": str(identity.get("canonical_v2_id") or ""),
            "version": str(source_config.get("version") or ""),
            "name": locale_map(source_config.get("name")),
            "description": locale_map(source_config.get("description")),
            "author": str(source_config.get("author") or ""),
            "compatibilityId": str(identity.get("expected_compatibility_id") or ""),
            "cover": "cover.png",
            "sku": source_config.get("sku") if isinstance(source_config.get("sku"), str) else "",
            "mode": fixed.get("mode", ""),
            "isDevice": fixed.get("isDevice", False),
            "main": fixed.get("main", "main.js"),
        }
    )
    result = {field: values[field] for field in required}
    # A device scope cannot be fabricated: keep it out of the skeleton unless
    # the source actually declares one. The conversion checker then reports
    # V2_CONFIG_DEVICE_SCOPE_MISSING until V1 board evidence is mapped, instead
    # of an empty object silently looking complete.
    if not isinstance(source_config.get("supportDevices"), dict):
        result.pop("supportDevices", None)
    else:
        result["supportDevices"] = source_config["supportDevices"]
    if mode == "REALTIME" and isinstance(source_config.get("isSupportStage"), bool):
        result["isSupportStage"] = source_config["isSupportStage"]
        if result["isSupportStage"]:
            result.pop("supportDevices", None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--mode", choices=["UPLOAD", "PYTHON_BLOCK", "MICROPYTHON", "REALTIME"], required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    inventory_path = args.inventory.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_dir():
        print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": str(source)}, ensure_ascii=False))
        return 2
    if output == source or source in output.parents:
        print(json.dumps({"status": "BLOCKED", "reason_code": "SOURCE_WRITE", "error": str(output)}, ensure_ascii=False))
        return 2

    try:
        source_config = load_json(source / "config.json", "V1 config.json")
        inventory = load_json(inventory_path, "V1 inventory")
        schema = load_json(SCHEMA_PATH, "config schema")
        if not isinstance(source_config, dict) or not isinstance(inventory, dict) or not isinstance(schema, dict):
            raise ValueError("source config, inventory, and schema must be JSON objects")
        config = build_config(source_config, inventory, args.mode, schema)
        if not re.fullmatch(r"[a-z0-9]+", str(config.get("id") or "")):
            raise ValueError("inventory has no lowercase alphanumeric canonical_v2_id")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "CONFIG_SKELETON", "error": str(exc)}, ensure_ascii=False))
        return 2

    result = {
        "status": "PASS",
        "mode": args.mode,
        "output": str(output),
        "fields": list(config),
        "empty_string_fields": [
            field
            for field, value in config.items()
            if value == "" or (field == "meta" and value == {"runtimeVersion": ""})
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
