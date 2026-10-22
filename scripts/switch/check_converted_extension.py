#!/usr/bin/env python3
"""Check deterministic identity and localization gates before the one V2 build."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
CONFIG_SCHEMA_PATH = SKILL_ROOT / "references" / "switch" / "config-schema.json"
DEVICE_IDS_PATH = SKILL_ROOT / "references" / "switch" / "device-ids.json"
SKU_PATTERN = re.compile(r"^[A-Z0-9]+(\|[A-Z0-9]+)*$")
DEVICE_VERSION_SPEC_PATTERN = re.compile(r"^[~^]?=?\d+(\.\d+){0,3}$")
SUBMENU_DECLARATION_RE = re.compile(r"blockType\s*:\s*BlockType\.SUBMENU\b")
SUBMENU_REFERENCE_RE = re.compile(r"\bsubmenuId\s*:\s*['\"]([^'\"]+)['\"]")
OBJECT_ID_RE = re.compile(r"\bid\s*:\s*['\"]([^'\"]+)['\"]")
CAMEL_CASE_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")
ADD_INCLUDE_CALL_RE = re.compile(r"addInclude\s*\(")


def _literal_arguments(text: str, open_paren: int) -> list[tuple[str, str | None]]:
    """Split one call's arguments, returning ``(kind, value)`` pairs.

    ``kind`` is ``"literal"`` (value is the string content) or ``"expression"``.
    Scanning is quote-aware so an argument may contain the other quote character,
    e.g. ``'#include "oled.h"'``.
    """
    arguments: list[tuple[str, str | None]] = []
    depth = 0
    quote: str | None = None
    start = open_paren + 1
    index = start
    while index < len(text):
        character = text[index]
        if quote:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
        elif character in "\"'`":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            if character == ")" and depth == 0:
                chunk = text[start:index]
                if chunk.strip():
                    arguments.append(_classify_argument(chunk))
                return arguments
            depth -= 1
        elif character == "," and depth == 0:
            arguments.append(_classify_argument(text[start:index]))
            start = index + 1
        index += 1
    return arguments


def _classify_argument(chunk: str) -> tuple[str, str | None]:
    stripped = chunk.strip()
    if len(stripped) >= 2 and stripped[0] in "\"'" and stripped[-1] == stripped[0]:
        return ("literal", stripped[1:-1])
    return ("expression", None)


def check_add_include_calls(func_text: str) -> list[dict]:
    """Flag `addInclude` calls whose arguments are not bare header names.

    Runtime behaviour (upload-gui generator, verified 2026-09-15 from the installed
    Mind+ runtime):

        addInclude(id)        -> #include <id>
        addInclude(id, code)  -> #include "code"

    so both arguments are inserted verbatim and must be bare header names.
    Copying the V1 shape `Generator.addInclude(id, '#include <X.h>')` would emit
    `#include "#include <X.h>"`. Only string literals are judged; a computed
    argument is left alone.
    """
    findings = []
    for match in ADD_INCLUDE_CALL_RE.finditer(func_text):
        arguments = _literal_arguments(func_text, match.end() - 1)
        if not arguments:
            continue
        id_kind, id_value = arguments[0]
        code_kind, code_value = arguments[1] if len(arguments) > 1 else ("expression", None)
        if id_kind != "literal":
            continue
        if code_kind == "literal":
            if any(marker in code_value for marker in ("#", "<", ">", '"')):
                findings.append(
                    {
                        "code": "ADD_INCLUDE_CODE_IS_INCLUDE_DIRECTIVE",
                        "call": match.group(0) + "...",
                        "id": id_value,
                        "code_argument": code_value,
                        "expected": "a bare header name, e.g. addInclude('THS', 'DFRobot_DHT.h') -> #include \"DFRobot_DHT.h\"",
                    }
                )
        elif len(arguments) == 1 and any(marker in id_value for marker in ("#", "<", ">")):
            findings.append(
                {
                    "code": "ADD_INCLUDE_ID_NOT_BARE_HEADER",
                    "call": match.group(0) + "...",
                    "id": id_value,
                    "expected": "a bare header name, e.g. 'DFRobot_DHT.h' -> #include <DFRobot_DHT.h>",
                }
            )
    return findings


def enclosing_object(text: str, position: int) -> str:
    """Return the brace-delimited object around ``position`` (best effort)."""
    start = text.rfind("{", 0, position)
    if start < 0:
        return ""
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def collect_submenus(index_text: str) -> tuple[dict[str, str], set[str]]:
    """Split V2 two-level menus from translation message ids.

    A ``BlockType.SUBMENU`` entry carries an entity ``id`` used by its members'
    ``submenuId``; that id is not a translation id and must not be required in
    the locale files. Returns ``(declared entity id -> object text, referenced
    submenuId values)``.
    """
    declared: dict[str, str] = {}
    for match in SUBMENU_DECLARATION_RE.finditer(index_text):
        body = enclosing_object(index_text, match.start())
        id_match = OBJECT_ID_RE.search(body)
        if id_match:
            declared.setdefault(id_match.group(1), body)
    referenced = set(SUBMENU_REFERENCE_RE.findall(index_text))
    return declared, referenced


def load_object(path: Path, label: str, findings: list[dict]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append({"code": "INVALID_JSON", "file": str(path), "detail": str(exc), "label": label})
        return {}
    if not isinstance(value, dict):
        findings.append({"code": "JSON_ROOT_NOT_OBJECT", "file": str(path), "label": label})
        return {}
    return value


def requirement_lines(path: Path) -> list[str] | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def load_config_schema(findings: list[dict]) -> dict:
    try:
        value = json.loads(CONFIG_SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            {
                "code": "CONFIG_SCHEMA_UNREADABLE",
                "file": str(CONFIG_SCHEMA_PATH),
                "detail": str(exc),
            }
        )
        return {}
    if not isinstance(value, dict):
        findings.append({"code": "CONFIG_SCHEMA_ROOT_NOT_OBJECT", "file": str(CONFIG_SCHEMA_PATH)})
        return {}
    return value


def matches_config_type(value: object, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object" or type_name == "meta":
        return isinstance(value, dict)
    if type_name == "locale_map":
        return (
            isinstance(value, dict)
            and isinstance(value.get("zh-cn"), str)
            and isinstance(value.get("en"), str)
        )
    return False


def check_config_schema(config: dict, mode: str, findings: list[dict]) -> dict:
    schema = load_config_schema(findings)
    profiles = schema.get("modes") if isinstance(schema.get("modes"), dict) else {}
    profile = profiles.get(mode) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        findings.append({"code": "CONFIG_SCHEMA_MODE_UNSUPPORTED", "mode": mode})
        return {"path": str(CONFIG_SCHEMA_PATH), "mode": mode}

    allowed = profile.get("allowed_fields")
    required = profile.get("required_fields")
    types = profile.get("types")
    fixed_values = profile.get("fixed_values")
    if not all(isinstance(value, list) for value in (allowed, required)) or not isinstance(types, dict):
        findings.append({"code": "CONFIG_SCHEMA_PROFILE_INVALID", "mode": mode})
        return {"path": str(CONFIG_SCHEMA_PATH), "mode": mode}

    allowed_set = set(allowed)
    required_set = set(required)
    actual_set = set(config)
    forbidden = schema.get("forbidden_v1_fields")
    forbidden_set = set(forbidden) if isinstance(forbidden, list) else set()
    forbidden_leaked = sorted(actual_set & forbidden_set)
    unexpected = sorted((actual_set - allowed_set) - forbidden_set)
    if forbidden_leaked:
        findings.append(
            {
                "code": "V2_CONFIG_FORBIDDEN_V1_FIELDS",
                "mode": mode,
                "fields": forbidden_leaked,
            }
        )
    missing = sorted(required_set - actual_set)
    if mode == "REALTIME":
        if config.get("isSupportStage") is True:
            if "supportDevices" in config:
                findings.append({"code": "REALTIME_STAGE_SUPPORT_DEVICES_FORBIDDEN"})
        elif "supportDevices" not in config:
            missing.append("supportDevices")
    if unexpected:
        findings.append(
            {
                "code": "V2_CONFIG_UNSUPPORTED_FIELDS",
                "mode": mode,
                "fields": unexpected,
            }
        )
    if missing:
        findings.append(
            {
                "code": "V2_CONFIG_REQUIRED_FIELDS_MISSING",
                "mode": mode,
                "fields": missing,
            }
        )

    type_errors = []
    for field, type_name in types.items():
        if field not in config or not isinstance(type_name, str):
            continue
        if not matches_config_type(config[field], type_name):
            type_errors.append(
                {
                    "field": field,
                    "expected": type_name,
                    "actual": type(config[field]).__name__,
                }
            )
    if type_errors:
        findings.append({"code": "V2_CONFIG_FIELD_TYPES_INVALID", "mode": mode, "fields": type_errors})

    if isinstance(fixed_values, dict):
        fixed_errors = []
        for field, expected in fixed_values.items():
            if field in config and config[field] != expected:
                fixed_errors.append({"field": field, "expected": expected, "actual": config[field]})
        if fixed_errors:
            findings.append({"code": "V2_CONFIG_FIXED_VALUES_INVALID", "mode": mode, "fields": fixed_errors})

    non_empty_if_present = profile.get("non_empty_if_present", [])
    empty_structured = []
    if isinstance(non_empty_if_present, list):
        for field in non_empty_if_present:
            if field in config and isinstance(config[field], (dict, list)) and not config[field]:
                empty_structured.append(field)
    if empty_structured:
        findings.append(
            {
                "code": "V2_CONFIG_OPTIONAL_STRUCTURED_FIELD_EMPTY",
                "mode": mode,
                "fields": empty_structured,
            }
        )

    nested_profiles = profile.get("nested_fields")
    if isinstance(nested_profiles, dict):
        for parent, nested in nested_profiles.items():
            if not isinstance(nested, dict) or not isinstance(config.get(parent), dict):
                continue
            nested_allowed = nested.get("allowed_fields")
            nested_required = nested.get("required_fields")
            nested_types = nested.get("types")
            if not all(isinstance(value, list) for value in (nested_allowed, nested_required)) or not isinstance(nested_types, dict):
                findings.append({"code": "V2_CONFIG_NESTED_SCHEMA_INVALID", "field": parent})
                continue
            nested_value = config[parent]
            nested_keys = set(nested_value)
            nested_unexpected = sorted(nested_keys - set(nested_allowed))
            nested_missing = sorted(set(nested_required) - nested_keys)
            if nested_unexpected or nested_missing:
                findings.append(
                    {
                        "code": "V2_CONFIG_NESTED_FIELDS_MISMATCH",
                        "field": parent,
                        "expected": nested_allowed,
                        "required": nested_required,
                        "actual": sorted(nested_keys),
                        "missing": nested_missing,
                        "extra": nested_unexpected,
                    }
                )
            nested_type_errors = []
            for child, type_name in nested_types.items():
                if child not in nested_value or not isinstance(type_name, str):
                    continue
                if not matches_config_type(nested_value[child], type_name):
                    nested_type_errors.append(
                        {
                            "field": f"{parent}.{child}",
                            "expected": type_name,
                            "actual": type(nested_value[child]).__name__,
                        }
                    )
            if nested_type_errors:
                findings.append(
                    {"code": "V2_CONFIG_NESTED_FIELD_TYPES_INVALID", "fields": nested_type_errors}
                )

    return {
        "path": str(CONFIG_SCHEMA_PATH),
        "mode": mode,
        "allowed_fields": allowed,
        "required_fields": required,
        "optional_fields": profile.get("optional_fields", []),
    }


def load_device_dictionary(findings: list[dict]) -> dict:
    try:
        value = json.loads(DEVICE_IDS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            {
                "code": "DEVICE_DICTIONARY_UNREADABLE",
                "file": str(DEVICE_IDS_PATH),
                "detail": str(exc),
            }
        )
        return {}
    if not isinstance(value, dict) or not isinstance(value.get("device_ids"), dict):
        findings.append({"code": "DEVICE_DICTIONARY_ROOT_INVALID", "file": str(DEVICE_IDS_PATH)})
        return {}
    return value


def check_device_conventions(config: dict, findings: list[dict]) -> None:
    dictionary = load_device_dictionary(findings)
    known_ids = set(dictionary.get("device_ids", {})) if dictionary else set()

    support_devices = config.get("supportDevices")
    if support_devices is not None:
        if not isinstance(support_devices, dict):
            findings.append({"code": "V2_CONFIG_FIELD_TYPES_INVALID", "mode": "supportDevices", "fields": "not an object"})
            return
        unknown_devices = sorted(key for key in support_devices if key not in known_ids)
        if unknown_devices:
            findings.append(
                {
                    "code": "CONFIG_DEVICE_ID_UNKNOWN",
                    "device_ids": unknown_devices,
                    "known_count": len(known_ids),
                    "message": "Device IDs must come from references/switch/device-ids.json. Pick boards from the dictionary by name; for a missing board ask the user for the exact dev-DFRobot-... ID, scope by supportArch architecture, or omit supportDevices for a whole-arch extension. Never invent an ID.",
                }
            )
        bad_versions = sorted(
            {
                key
                for key, version in support_devices.items()
                if not isinstance(version, str) or not DEVICE_VERSION_SPEC_PATTERN.fullmatch(version)
            }
        )
        if bad_versions:
            findings.append({"code": "CONFIG_DEVICE_VERSION_SPEC_INVALID", "device_ids": bad_versions})

    support_arch = config.get("supportArch")
    if support_arch is not None:
        if not isinstance(support_arch, list):
            findings.append({"code": "V2_CONFIG_FIELD_TYPES_INVALID", "mode": "supportArch", "fields": "not an array"})
        else:
            bad_archs = sorted(
                value
                for value in support_arch
                if not isinstance(value, str)
                or not (value == "all" or re.fullmatch(r"[a-z0-9]+:[a-z0-9]+", value))
            )
            if bad_archs:
                findings.append(
                    {
                        "code": "CONFIG_SUPPORT_ARCH_FORMAT_INVALID",
                        "values": bad_archs,
                        "expected": "\"all\" or a <platform>:<arch> prefix of boardConfig.board, e.g. arduino:avr",
                    }
                )

    sku = config.get("sku")
    if isinstance(sku, str) and sku and not SKU_PATTERN.fullmatch(sku):
        findings.append(
            {
                "code": "CONFIG_SKU_FORMAT_INVALID",
                "actual": sku,
                "expected": "empty string, or uppercase alphanumeric segments joined by | (e.g. SEN0664|SEN0665)",
            }
        )


def check_python_requirements(extension: Path, inventory: dict, findings: list[dict], mode: str = "PYTHON_BLOCK") -> None:
    language = "PYTHON" if mode == "PYTHON_BLOCK" else "MICROPYTHON"
    dependency_inventory = inventory.get(f"{language.lower()}_dependency_inventory")
    if not isinstance(dependency_inventory, dict):
        findings.append({"code": f"V1_{language}_DEPENDENCY_INVENTORY_MISSING"})
        return
    expected = dependency_inventory.get("expected_requirement_lines")
    if not isinstance(expected, list) or any(not isinstance(item, str) for item in expected):
        findings.append({"code": f"V1_{language}_DEPENDENCY_INVENTORY_INCOMPLETE"})
        return

    target = extension / "public" / "requirements.txt"
    actual = requirement_lines(target) if target.is_file() else None
    if actual is None:
        if expected:
            findings.append(
                {
                    "code": f"V2_{language}_REQUIREMENTS_MISSING",
                    "expected": expected,
                    "file": str(target),
                }
            )
        return
    if not expected:
        findings.append({"code": f"V2_{language}_REQUIREMENTS_UNEXPECTED_FILE", "file": str(target)})
    elif actual != expected:
        findings.append(
            {
                "code": f"V2_{language}_REQUIREMENTS_MISMATCH",
                "expected": expected,
                "actual": actual,
                "file": str(target),
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--mode", choices=["UPLOAD", "PYTHON_BLOCK", "MICROPYTHON", "REALTIME"], default="UNKNOWN")
    parser.add_argument("--expected-v2-id", help="Approved lowercase alphanumeric V2 id; defaults to inventory candidate")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = args.project_root.expanduser().resolve()
    inventory_path = args.inventory.expanduser().resolve()
    extension = project / "extension"
    config_path = extension / "public" / "config.json"
    index_path = extension / "index.js"
    findings: list[dict] = []

    inventory = load_object(inventory_path, "V1 inventory", findings)
    config = load_object(config_path, "V2 config", findings)
    config_schema = check_config_schema(config, args.mode, findings)
    check_device_conventions(config, findings)
    index_text = ""
    try:
        index_text = index_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        findings.append({"code": "INDEX_UNREADABLE", "file": str(index_path), "detail": str(exc)})

    mode_facts = inventory.get("v1_entry_inventory", {}).get(args.mode, {}) if isinstance(inventory.get("v1_entry_inventory"), dict) else {}
    expected_opcodes = set(mode_facts.get("block_functions", []))
    if args.mode in {"MICROPYTHON", "REALTIME"} and not expected_opcodes:
        findings.append({"code": "V1_MODE_BLOCK_INVENTORY_EMPTY", "mode": args.mode})
    if expected_opcodes:
        target_opcodes = set(re.findall(r"\bopcode\s*:\s*['\"]([^'\"]+)['\"]", index_text))
        namespaced_opcodes = sorted(opcode for opcode in target_opcodes if "." in opcode)
        if namespaced_opcodes:
            findings.append({"code": "V2_BLOCK_OPCODE_HAS_NAMESPACE", "opcodes": namespaced_opcodes})
        missing_opcodes = sorted(expected_opcodes - target_opcodes)
        extra_opcodes = sorted(target_opcodes - expected_opcodes)
        if missing_opcodes or extra_opcodes:
            findings.append(
                {
                    "code": "V2_BLOCK_OPCODE_MISMATCH",
                    "expected_short_opcodes": sorted(expected_opcodes),
                    "actual_opcodes": sorted(target_opcodes),
                    "missing": missing_opcodes,
                    "extra": extra_opcodes,
                }
            )

    color_matches = dict(
        re.findall(r"\b(color[123])\s*:\s*['\"](#?[0-9A-Fa-f]{6})['\"]", index_text, re.IGNORECASE)
    )
    normalized_colors = {key.casefold(): value.lower() for key, value in color_matches.items()}
    if set(normalized_colors) != {"color1", "color2", "color3"}:
        findings.append({"code": "V2_BLOCK_COLORS_INCOMPLETE", "actual": normalized_colors})
    elif len(set(normalized_colors.values())) == 1:
        findings.append({"code": "V2_BLOCK_COLORS_ALL_IDENTICAL", "colors": normalized_colors})
    expected_color = str(mode_facts.get("declared_color1") or "").lower()
    if expected_color and normalized_colors.get("color1") != expected_color:
        findings.append({"code": "V2_COLOR1_NOT_FROM_V1", "expected": expected_color, "actual": normalized_colors.get("color1")})

    icon_root = extension / "icon"
    svg_text = {}
    for icon_name in ("blockIcon.svg", "menuIcon.svg"):
        path = icon_root / icon_name
        try:
            svg_text[icon_name] = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            findings.append({"code": "SVG_UNREADABLE", "file": str(path), "detail": str(exc)})
            svg_text[icon_name] = ""
    menu_colors = {value.lower() for value in re.findall(r"#[0-9A-Fa-f]{6}", svg_text.get("menuIcon.svg", ""))}
    if normalized_colors.get("color1") and normalized_colors["color1"] not in menu_colors:
        findings.append(
            {
                "code": "MENU_SVG_COLOR_NOT_ALIGNED",
                "expected_color1": normalized_colors["color1"],
                "svg_colors": sorted(menu_colors),
            }
        )
    if svg_text.get("blockIcon.svg") and svg_text.get("blockIcon.svg") == svg_text.get("menuIcon.svg"):
        findings.append({"code": "MENU_SVG_UNCHANGED_FROM_BLOCK_SVG"})

    func_path = extension / "func.js"
    try:
        func_text = func_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        findings.append({"code": "FUNC_UNREADABLE", "file": str(func_path), "detail": str(exc)})
        func_text = ""
    method_names = set(re.findall(r"Func\.prototype\[['\"]([^'\"]+)['\"]\s*=", func_text))
    method_names.update(
        name for name in re.findall(r"^\s{2,}(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", func_text, re.MULTILINE)
        if name not in {"constructor", "if", "else", "for", "while", "switch", "catch"}
    )
    namespaced_methods = sorted(name for name in method_names if "." in name)
    if namespaced_methods:
        findings.append(
            {
                "code": "FUNC_METHOD_HAS_NAMESPACE",
                "methods": namespaced_methods,
                "expected_short_opcodes": sorted(expected_opcodes),
            }
        )
    if expected_opcodes:
        missing_methods = sorted(expected_opcodes - method_names)
        if missing_methods:
            findings.append({"code": "FUNC_METHOD_MISSING", "missing": missing_methods, "methods": sorted(method_names)})
    if args.mode == "UPLOAD":
        findings.extend(check_add_include_calls(func_text))
    if args.mode == "MICROPYTHON":
        check_python_requirements(extension, inventory, findings, args.mode)
        if not re.search(r"\bgetCodePrimitives\s*\(", index_text):
            findings.append({"code": "MICROPYTHON_CODE_PRIMITIVES_MISSING"})
        if re.search(r"\bgenerator\s*\.\s*addCode\s*\(", func_text):
            findings.append({"code": "MICROPYTHON_USES_UPLOAD_ADD_CODE"})
        if re.search(r"\bgenerator\s*\.\s*addWhile\s*\(", func_text):
            findings.append({"code": "MICROPYTHON_ADD_WHILE_HAS_NO_EFFECT"})
    if args.mode == "REALTIME":
        if "spec_is_support_stage" in inventory and config.get("isSupportStage", False) != inventory["spec_is_support_stage"]:
            findings.append({"code": "REALTIME_STAGE_SPEC_MISMATCH"})
        if not re.search(r"\bgetPrimitives\s*\(", index_text):
            findings.append({"code": "REALTIME_PRIMITIVES_MISSING"})
        if re.search(r"\bgetCodePrimitives\s*\(", index_text) or re.search(r"\bgenerator\s*\.", func_text):
            findings.append({"code": "REALTIME_USES_CODE_GENERATOR"})
    if args.mode == "PYTHON_BLOCK":
        check_python_requirements(extension, inventory, findings)
        if re.search(r"\bgenerator\s*\.\s*addCode\s*\(", func_text):
            findings.append({"code": "PYTHON_USES_UPLOAD_ADD_CODE"})
        for opcode in sorted(expected_opcodes):
            method_match = re.search(
                rf"(?:Func\.prototype\[['\"]{re.escape(opcode)}['\"]\s*=\s*function\b|^\s{{2,}}{re.escape(opcode)}\s*\([^)]*\)\s*\{{)",
                func_text,
                re.MULTILINE,
            )
            if method_match:
                next_method = re.search(
                    r"\n\s{2,}(?:[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{|\nFunc\.prototype\[",
                    func_text[method_match.end():],
                )
                body = func_text[method_match.start() : method_match.end() + (next_method.start() if next_method else len(func_text))]
                if not re.search(r"\breturn\b", body):
                    findings.append({"code": "PYTHON_METHOD_DOES_NOT_RETURN_CODE", "opcode": opcode})

    identity = inventory.get("identity") if isinstance(inventory.get("identity"), dict) else {}
    expected_id = args.expected_v2_id or identity.get("canonical_v2_id")
    if args.expected_v2_id and not re.fullmatch(r"[a-z0-9]+", args.expected_v2_id):
        findings.append({"code": "EXPECTED_V2_ID_INVALID", "actual": args.expected_v2_id})
    actual_id = config.get("id")
    if not isinstance(actual_id, str) or not re.fullmatch(r"[a-z0-9]+", actual_id):
        findings.append({"code": "V2_ID_NOT_LOWER_ALPHANUMERIC", "actual": actual_id})
    if expected_id and actual_id != expected_id:
        findings.append({"code": "V2_ID_MISMATCH", "expected": expected_id, "actual": actual_id})

    expected_compatibility = identity.get("expected_compatibility_id")
    actual_compatibility = config.get("compatibilityId")
    if expected_compatibility is None:
        findings.append({"code": "LEGACY_COMPATIBILITY_ID_UNPROVEN"})
    elif actual_compatibility != expected_compatibility:
        findings.append(
            {"code": "COMPATIBILITY_ID_MISMATCH", "expected": expected_compatibility, "actual": actual_compatibility}
        )
    if not isinstance(actual_compatibility, str) or actual_compatibility != actual_compatibility.lower():
        findings.append({"code": "COMPATIBILITY_ID_NOT_LOWERCASE", "actual": actual_compatibility})

    for field in ("name", "description"):
        value = config.get(field)
        missing_languages = [language for language in ("zh-cn", "en") if not isinstance(value, dict) or not value.get(language)]
        if missing_languages:
            findings.append({"code": "CONFIG_LANGUAGE_MISSING", "field": field, "languages": missing_languages})

    locales_root = extension / "locales"
    locale_objects = {}
    for locale in ("en", "zh-cn"):
        path = locales_root / f"{locale}.json"
        locale_objects[locale] = load_object(path, f"{locale} locale", findings)
    en_keys = set(locale_objects["en"])
    zh_keys = set(locale_objects["zh-cn"])
    if en_keys != zh_keys:
        findings.append(
            {"code": "LOCALE_KEY_MISMATCH", "only_en": sorted(en_keys - zh_keys), "only_zh_cn": sorted(zh_keys - en_keys)}
        )

    # 二级菜单的实体 id 不是翻译 message ID：翻译由 SUBMENU 的 text 提供，
    # 实体 id 不得被当成翻译键要求出现在 locales 中。
    submenu_ids, submenu_references = collect_submenus(index_text)
    undeclared_submenus = sorted(submenu_references - set(submenu_ids))
    if undeclared_submenus:
        findings.append(
            {
                "code": "SUBMENU_ID_NOT_DECLARED",
                "submenu_ids": undeclared_submenus,
                "declared": sorted(submenu_ids),
            }
        )
    for entity_id, body in sorted(submenu_ids.items()):
        if not CAMEL_CASE_RE.fullmatch(entity_id):
            findings.append({"code": "SUBMENU_ENTITY_ID_NOT_CAMEL", "id": entity_id, "object": body.strip()[:180]})

    literal_ids = set(
        re.findall(r"\bid\s*:\s*['\"]([^'\"]+)['\"]", index_text)
    ) - set(submenu_ids)
    for message_id in sorted(literal_ids):
        missing = [locale for locale, values in locale_objects.items() if message_id not in values]
        if missing:
            findings.append({"code": "FORMAT_MESSAGE_ID_MISSING", "id": message_id, "locales": missing})

    old_id = str(identity.get("id") or "")
    if old_id and expected_id and old_id.casefold() != expected_id.casefold():
        stale_ids = sorted(message_id for message_id in literal_ids if old_id.casefold() in message_id.casefold())
        if stale_ids:
            findings.append({"code": "LOCALE_ID_USES_LEGACY_EXTENSION_ID", "ids": stale_ids})

    raw_visible = []
    for match in re.finditer(r"\b(name|text)\s*:\s*(['\"])(.*?)\2", index_text):
        raw_visible.append({"field": match.group(1), "value": match.group(3), "line": index_text.count("\n", 0, match.start()) + 1})
    if raw_visible:
        findings.append({"code": "RAW_USER_VISIBLE_TEXT", "occurrences": raw_visible})

    result = {
        "status": "PASS" if not findings else "FAIL",
        "reason_code": None if not findings else "CONVERSION_CHECK",
        "project_root": str(project),
        "extension_root": str(extension),
        "expected_v2_id": expected_id,
        "actual_v2_id": actual_id,
        "expected_compatibility_id": expected_compatibility,
        "actual_compatibility_id": actual_compatibility,
        "config_schema": config_schema,
        "format_message_literal_ids": sorted(literal_ids),
        "findings": findings,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded + "\n")
    print(encoded)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
