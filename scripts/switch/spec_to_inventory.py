#!/usr/bin/env python3
"""Map one extension-spec.json into the shared V1-inventory shape (pure mapping, no inference).

The output feeds the same pipe conversion uses: scripts/switch/select_reference_topics.py
(topic selection) and scripts/switch/check_converted_extension.py (static gates). Fields the
spec does not carry are omitted here, never guessed; selection then loads only the
"always" topics and the checker reports what is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


PYTHON_GENERATOR_CALLS = {
    "addImport": "add-import",
    "addDeclaration": "add-variable",
    "addVariable": "add-variable",
    "addInit": "add-init",
    "addInitHeader": "add-init",
    "addFunction": "add-function",
    "addCode": "inline-code",
}
UPLOAD_GENERATOR_CALLS = {
    "addInclude": "add-include",
    "addDefine": "add-define",
    "addObject": "add-object",
    "addVariable": "add-variable",
    "addDeclaration": "add-variable",
    "addConst": "add-const",
    "addFunction": "add-function",
    "addSetup": "add-setup",
    "addCode": "inline-code",
}
PARAMETER_FIELD_FEATURES = {
    "dropdown": "field-dropdown",
    "slider": "field-slider",
    "range": "field-slider",
    "string": "field-string",
    "number": "field-number",
    "menu": "menu",
    "dynamic-menu": "dynamic-menu",
}
RUNTIME_RE = re.compile(r"\b(getCurrentDeviceId|getBoardPinsByType|getDevice|runtime)\b")
SUPPORTED_MODES = {"UPLOAD", "PYTHON_BLOCK", "MICROPYTHON", "REALTIME"}


class SpecError(RuntimeError):
    pass


def emit(value: dict[str, Any], output: Path | None) -> int:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        target = output.expanduser().resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded)
    print(encoded, end="")
    if value.get("status") == "PASS":
        return 0
    return 2


def load_spec(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read extension spec {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecError(f"extension spec root must be an object: {path}")
    return value


def require(mapping: object, key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping or mapping[key] in (None, "", [], {}):
        raise SpecError(f"SPEC_FIELD_MISSING: {where}.{key} is required to build the inventory")
    return mapping[key]


def derive_features(spec: dict[str, Any], mode: str, anomalies: list[dict[str, Any]]) -> list[str]:
    features: set[str] = set()

    explicit = spec.get("reference_features")
    if explicit is not None:
        if not isinstance(explicit, list) or any(not isinstance(item, str) or not item for item in explicit):
            raise SpecError("SPEC_FIELD_INVALID: reference_features must be a list of feature ids")
        features.update(explicit)

    if mode in {"PYTHON_BLOCK", "MICROPYTHON"}:
        generator_calls = PYTHON_GENERATOR_CALLS
        if mode == "MICROPYTHON":
            generator_calls = dict(generator_calls, addWhile="add-while", getSetup="get-setup", getStaticFunction="get-static-function")
    else:
        generator_calls = UPLOAD_GENERATOR_CALLS if mode == "UPLOAD" else {}
    if mode == "REALTIME" and spec.get("is_support_stage") is True:
        features.add("stage")
    if mode in {"MICROPYTHON", "REALTIME"} and spec.get("devices"):
        features.add("board-condition")
    if mode == "MICROPYTHON" and spec.get("dependencies"):
        features.add("dependencies")
    for block in spec.get("blocks", []):
        if not isinstance(block, dict):
            continue
        for parameter in block.get("parameters", []) or []:
            if not isinstance(parameter, dict):
                anomalies.append({"mode": mode, "note": "parameter is not an object", "block": block.get("opcode")})
                continue
            field = parameter.get("field")
            if field is None:
                anomalies.append(
                    {
                        "mode": mode,
                        "note": "parameter without field key; no reference feature derived",
                        "block": block.get("opcode"),
                        "parameter": parameter,
                    }
                )
                continue
            feature = PARAMETER_FIELD_FEATURES.get(str(field))
            if feature:
                features.add(feature)
            else:
                anomalies.append(
                    {
                        "mode": mode,
                        "note": "parameter field value maps to no reference feature; declare it in reference_features if it is a real Mind+ field",
                        "block": block.get("opcode"),
                        "field": field,
                    }
                )
        if isinstance(block.get("boards"), list) and block["boards"]:
            features.add("board-condition")
        if isinstance(block.get("submenu"), str) and block["submenu"]:
            features.add("submenu")

        claim = block.get("generator_claim")
        if isinstance(claim, str):
            if mode == "REALTIME" and re.search(r"\b(firmata|pinMode|digitalRead|digitalWrite|analogRead|pwmWrite|i2c\w*|serial\w*)\b", claim):
                features.add("firmata")
            for method, feature in generator_calls.items():
                if re.search(rf"\b{re.escape(method)}\s*\(", claim):
                    features.add(feature)
            if RUNTIME_RE.search(claim):
                features.add("runtime")

    return sorted(features)


def build_inventory(spec: dict[str, Any], spec_path: Path, explicit_mode: str | None) -> dict[str, Any]:
    identity = require(spec, "identity", "spec")
    mode = str(require(spec, "mode", "spec")).upper()
    if mode not in SUPPORTED_MODES:
        raise SpecError(f"SPEC_FIELD_INVALID: spec.mode must be one of {sorted(SUPPORTED_MODES)}, got {mode}")
    if explicit_mode and explicit_mode.upper() != mode:
        raise SpecError(f"SPEC_FIELD_INVALID: explicit mode {explicit_mode} conflicts with spec.mode {mode}")
    if "is_support_stage" in spec and (mode != "REALTIME" or not isinstance(spec["is_support_stage"], bool)):
        raise SpecError("SPEC_FIELD_INVALID: is_support_stage is a boolean for REALTIME only")
    if (mode == "MICROPYTHON" or (mode == "REALTIME" and not spec.get("is_support_stage", False))) and not spec.get("devices"):
        raise SpecError("SPEC_FIELD_MISSING: devices are required for MicroPython and realtime hardware modules")
    if mode == "REALTIME" and spec.get("is_support_stage") and spec.get("devices"):
        raise SpecError("SPEC_FIELD_INVALID: realtime stage extensions omit devices")
    blocks = require(spec, "blocks", "spec")
    if not isinstance(blocks, list) or any(not isinstance(block, dict) for block in blocks):
        raise SpecError("SPEC_FIELD_INVALID: spec.blocks must be a list of objects")

    spec_id = require(identity, "id", "identity")
    if not isinstance(spec_id, str) or not re.fullmatch(r"[a-z0-9]+", spec_id):
        raise SpecError(f"SPEC_FIELD_INVALID: identity.id must be lowercase alphanumeric, got {spec_id!r}")
    author = require(identity, "author", "identity")
    if not isinstance(author, str) or not re.fullmatch(r"[A-Za-z]+", author):
        raise SpecError("SPEC_FIELD_INVALID: normalize new identity.author to nonempty ASCII letters before freezing the spec")

    compatibility = identity.get("compatibility_id")
    if compatibility is None:
        compatibility = ""
    if not isinstance(compatibility, str):
        raise SpecError("SPEC_FIELD_INVALID: identity.compatibility_id must be a string or null")

    anomalies: list[dict[str, Any]] = []
    opcodes = []
    for block in blocks:
        opcode = require(block, "opcode", f"spec.blocks[{len(opcodes)}]")
        if not isinstance(opcode, str) or not opcode or "." in opcode:
            raise SpecError(f"SPEC_FIELD_INVALID: block opcode must be a non-empty short name without dots, got {opcode!r}")
        opcodes.append(opcode)

    entry_facts: dict[str, Any] = {"block_functions": opcodes}
    style = spec.get("style")
    if isinstance(style, dict) and isinstance(style.get("color1"), str) and style["color1"]:
        entry_facts["declared_color1"] = style["color1"]

    inventory: dict[str, Any] = {
        "status": "PASS",
        "reason_code": None,
        "source": {"type": "extension-spec", "path": str(spec_path), "sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest()},
        "candidates": [{"mode": mode, "evidence": "extension-spec.mode"}],
        "identity": {
            "id": spec_id,
            "canonical_v2_id": spec_id,
            "expected_compatibility_id": compatibility,
        },
        "v1_entry_inventory": {mode: entry_facts},
        "reference_features_by_mode": {mode: derive_features(spec, mode, anomalies)},
        "source_anomalies": anomalies,
    }

    if isinstance(spec.get("devices"), list):
        inventory["spec_devices"] = spec["devices"]
    if mode == "REALTIME":
        inventory["spec_is_support_stage"] = spec.get("is_support_stage", False)

    if mode in {"PYTHON_BLOCK", "MICROPYTHON"}:
        expected_lines = []
        for index, dependency in enumerate(spec.get("dependencies", []) or []):
            if not isinstance(dependency, dict) or not isinstance(dependency.get("requirement"), str) or not dependency["requirement"].strip():
                raise SpecError(
                    f"SPEC_FIELD_MISSING: spec.dependencies[{index}].requirement (exact requirements.txt line) is required for {mode}"
                )
            expected_lines.append(dependency["requirement"].strip())
        inventory["python_dependency_inventory" if mode == "PYTHON_BLOCK" else "micropython_dependency_inventory"] = {
            "authoritative_sources": ["extension-spec:dependencies"],
            "config_dependencies": [],
            "requirements_files": [],
            "expected_requirement_lines": list(dict.fromkeys(expected_lines)),
            "ignored_requirement_files": [],
            "local_libraries": [],
        }

    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES))
    args = parser.parse_args()

    spec_path = args.spec.expanduser().resolve(strict=False)
    try:
        spec = load_spec(spec_path)
        inventory = build_inventory(spec, spec_path, args.mode)
    except (OSError, SpecError) as exc:
        return emit(
            {
                "status": "BLOCKED",
                "reason_code": "INPUT.SPEC_TO_INVENTORY",
                "error": str(exc),
                "message": "Fix the reported spec field and rerun; do not let the adapter infer values.",
            },
            args.output,
        )
    return emit(inventory, args.output)


if __name__ == "__main__":
    sys.exit(main())
