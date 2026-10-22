#!/usr/bin/env python3
"""Create a deterministic, read-only inventory of one Mind+ V1 library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SKIP_DIRS = {".git", ".mindplus-agent", ".ms", "node_modules", "build", "dist", "__pycache__", ".idea"}
GENERATOR_CALLS = {
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
MODE_SOURCES = {
    "UPLOAD": ("arduinoC", "main.ts"),
    "PYTHON_BLOCK": ("python", "main.ts"),
    "MICROPYTHON": ("micropython", "main.ts"),
    "REALTIME": ("javascript", "index.js"),
}


def mode_entries(source: Path, config: object) -> dict[str, Path]:
    asset = config.get("asset", {}) if isinstance(config, dict) else {}
    result = {}
    for mode, (language, filename) in MODE_SOURCES.items():
        declaration = asset.get(language, {}) if isinstance(asset, dict) else {}
        directory = declaration.get("dir", language) if isinstance(declaration, dict) else language
        main = declaration.get("main", filename) if isinstance(declaration, dict) else filename
        entry = (source / directory / main).resolve()
        # The official realtime development template declares built main.js,
        # but supplies javascript/index.js as its source entry.
        if mode == "REALTIME" and not entry.is_file() and main == "main.js":
            entry = (source / directory / "index.js").resolve()
        if not entry.is_relative_to(source) or not (source / directory).resolve().is_relative_to(source):
            raise ValueError(f"V1 {language} entry is outside source")
        result[mode] = entry
    return result


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def iter_files(root: Path):
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path, relative


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def active_typescript(text: str) -> str:
    """Remove ordinary comments while leaving V1 //% directives available elsewhere."""
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(line.split("//", 1)[0] for line in without_blocks.splitlines())


def has_generator_call(text: str, method: str) -> bool:
    return re.search(rf"\bGenerator\s*\.\s*{re.escape(method)}\s*\(", text) is not None


def config_python(config: object, language: str = "python") -> dict:
    if not isinstance(config, dict):
        return {}
    asset = config.get("asset")
    if not isinstance(asset, dict):
        return {}
    python = asset.get(language)
    return python if isinstance(python, dict) else {}


def config_dependency_line(name: str, version_spec: str) -> str:
    """Convert one V1 config declaration without consulting source imports."""
    if not version_spec:
        return name
    if re.match(r"^(===|==|!=|~=|>=|<=|>|<)", version_spec):
        return f"{name}{version_spec}"
    return f"{name}=={version_spec}"


def dependency_inventory(source: Path, config: object, relative_files: list[Path], language: str = "python", directory: Path | None = None) -> dict:
    python = config_python(config, language)
    library_root = (directory or Path(language)) / "libraries"
    requirements_path = library_root / "requirements.txt"
    raw_dependencies = python.get("dependencies")
    config_dependencies = []
    if isinstance(raw_dependencies, dict):
        for name, raw_spec in raw_dependencies.items():
            spec = "" if raw_spec is None else str(raw_spec).strip()
            config_dependencies.append(
                {
                    "name": str(name),
                    "version_spec": spec,
                    "has_version_spec": bool(spec),
                    "source": f"config.json:asset.{language}.dependencies",
                }
            )

    requirement_files = []
    ignored_requirement_files = []
    for relative in relative_files:
        if relative.name.casefold() != "requirements.txt":
            continue
        path_parts = tuple(part.casefold() for part in relative.parts)
        if path_parts != tuple(part.casefold() for part in requirements_path.parts):
            ignored_requirement_files.append(relative.as_posix())
            continue
        text = read_text(source / relative)
        specs = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        requirement_files.append(
            {
                "path": relative.as_posix(),
                "specs": specs,
                "sha256": digest(source / relative),
                "source": requirements_path.as_posix(),
            }
        )

    local_libraries = sorted(
        relative.as_posix()
        for relative in relative_files
        if relative.suffix.casefold() == ".py"
        and relative.is_relative_to(library_root)
    )
    expected_requirement_lines = []
    for dependency in config_dependencies:
        expected_requirement_lines.append(
            config_dependency_line(dependency["name"], dependency["version_spec"])
        )
    for requirement_file in requirement_files:
        expected_requirement_lines.extend(requirement_file["specs"])
    expected_requirement_lines = list(dict.fromkeys(expected_requirement_lines))
    return {
        "authoritative_sources": [
            f"config.json:asset.{language}.dependencies",
            requirements_path.as_posix(),
        ],
        "config_dependencies": config_dependencies,
        "requirements_files": requirement_files,
        "expected_requirement_lines": expected_requirement_lines,
        "ignored_requirement_files": ignored_requirement_files,
        "local_libraries": local_libraries,
    }


def common_features(source_text: str, active_text: str, relative_files: list[Path]) -> set[str]:
    features: set[str] = set()
    lowered_parts = [[part.casefold() for part in relative.parts] for relative in relative_files]
    has_menu_dir = any("_menus" in parts for parts in lowered_parts)
    if has_menu_dir or re.search(r"\.shadow\s*=\s*[\"']dropdown[\"']", source_text, re.IGNORECASE):
        features.add("menu")
    if any(
        "_menus" in parts and Path(relative).suffix.casefold() in {".js", ".ts"}
        for parts, relative in zip(lowered_parts, relative_files)
    ):
        features.add("dynamic-menu")
    # MakeCode-style palette separator between blocks (documented V2 usage: "---" entry)
    if re.search(r"[\"']---[\"']", source_text):
        features.add("separator")
    for shadow, feature in {
        "dropdown": "field-dropdown",
        "range": "field-slider",
        "string": "field-string",
        "normal": "field-string",
        "number": "field-number",
    }.items():
        if re.search(rf"\.shadow\s*=\s*[\"']{shadow}[\"']", source_text, re.IGNORECASE):
            features.add(feature)
    if has_generator_call(active_text, "addErrorPrompt"):
        features.add("validation")
    if re.search(r"\b(getCurrentDeviceId|getBoardPinsByType|getDevice|runtime)\b", active_text):
        features.add("runtime")
    if any(parts and parts[0] == "examples" for parts in lowered_parts):
        features.add("examples")
    return features


def canonical_v2_id(value: object) -> str:
    """Return the deterministic V2 id candidate used by the migration workflow."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).lower()


MPEXT_NAME_RE = re.compile(r"^(?P<identity>.+)-V\d+(?:\.\d+){1,3}\.mpext$", re.IGNORECASE)
SOURCE_VERSION_SUFFIX_RE = re.compile(r"-V\d+(?:\.\d+){1,3}$", re.IGNORECASE)


def normalize_identity_text(value: object) -> str:
    """Mind+ V1 的包身份不含空白字符。

    空白在导出/匹配旧包时被写成 `-`：author `DJKJ` + id `ESP8266 IOT` 对应的旧包是
    `djkj-esp8266-iot-thirdex-V0.0.1.mpext`，而不是保留空格的形式。只做小写与空白替换，
    下划线、中文、括号等原始字符保留（与已发布仓库的 compatibilityId 一致）。
    """
    return re.sub(r"\s", "-", str(value)).lower()


def config_package_identity(config: object) -> str | None:
    """从 V1 `author`/`id` 派生的旧包身份；缺少字段时返回 None。"""
    if not isinstance(config, dict) or not config.get("author") or not config.get("id"):
        return None
    return f"{normalize_identity_text(config['author'])}-{normalize_identity_text(config['id'])}-thirdex"


def legacy_package_identities(source: Path) -> list[str]:
    """收集可证明的旧包身份，优先使用实际 `.mpext` 文件名。

    V1 源有两种常见布局：包在源目录**内部**，或与源目录**并列**（目录名等于包名去掉
    版本号，例如 `x-thirdex-V0.0.1/` 与 `x-thirdex-V0.0.1.mpext` 同级）。后者只采纳与
    源目录同名的同级包，避免把同级其它扩展的包计入。
    """
    candidates = list(source.glob("*.mpext"))
    source_prefix = SOURCE_VERSION_SUFFIX_RE.sub("", source.name)
    try:
        siblings = sorted(source.parent.glob("*.mpext"), key=lambda item: item.as_posix().casefold())
    except OSError:
        siblings = []
    for package in siblings:
        match = MPEXT_NAME_RE.match(package.name)
        if match and match.group("identity").casefold() == source_prefix.casefold():
            candidates.append(package)
    identities = set()
    for package in candidates:
        match = MPEXT_NAME_RE.match(package.name)
        if match:
            identities.add(match.group("identity").lower())
    return sorted(identities, key=str.casefold)


def localization_inventory(source: Path, relative_files: list[Path]) -> dict:
    locale_files = []
    locale_keys = set()
    for relative in relative_files:
        if "_locales" not in {part.casefold() for part in relative.parts} or relative.suffix.casefold() != ".json":
            continue
        data = None
        try:
            data = json.loads((source / relative).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
        keys = sorted(data) if isinstance(data, dict) else []
        locale_keys.update(keys)
        locale_files.append({"path": relative.as_posix(), "keys": keys, "valid_object": isinstance(data, dict)})

    menu_files = []
    for relative in relative_files:
        if "_menus" not in {part.casefold() for part in relative.parts} or relative.suffix.casefold() != ".json":
            continue
        data = None
        try:
            data = json.loads((source / relative).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
        menu_files.append({"path": relative.as_posix(), "valid_json": data is not None})

    return {
        "has_locale_data": bool(locale_files),
        "locale_files": locale_files,
        "locale_keys": sorted(locale_keys),
        "localized_block_key_count": sum(key.endswith("|block") for key in locale_keys),
        "localized_menu_key_count": sum(key.endswith("|menu") for key in locale_keys),
        "menu_files": menu_files,
    }


def secondary_labels(text: str) -> list[dict]:
    """Extract explicitly annotated V1 tag declarations; do not infer members."""
    labels = []
    pattern = r"(?P<annotations>(?:^[ \t]*//%[^\r\n]*[\r\n]+)+)[ \t]*export\s+function\s+(?P<function>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{(?P<body>[^{}]*)\}"
    for match in re.finditer(pattern, text, re.MULTILINE):
        annotations = match["annotations"]
        if not re.search(r"\bblockType\s*=\s*['\"]tag['\"]", annotations):
            continue
        title = re.search(r"\bblock\s*=\s*([\"'])(.*?)\1", annotations)
        labels.append({"function": match["function"], "text": title.group(2) if title else None,
                       "line": text.count("\n", 0, match.start()) + 1,
                       "empty_body": not match["body"].strip(), "target_kind": "SUBMENU"})
    return labels


def entry_inventory(signatures: dict[str, Path]) -> dict[str, dict]:
    """Capture V1 function names, source namespace hints, and declared color."""
    result: dict[str, dict] = {}
    for mode, entry in signatures.items():
        if not entry.is_file():
            continue
        text = read_text(entry)
        functions = sorted(
            set(re.findall(r"\bexport\s+function\s+([A-Za-z_$][\w$]*)\s*\(", text))
            | set(re.findall(r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", text))
        )
        if mode == "REALTIME":
            functions = sorted(set(re.findall(r"\bopcode\s*:\s*['\"]([^'\"]+)['\"]", active_typescript(text))))
        labels = secondary_labels(text)
        layout_functions = {item["function"] for item in labels if item["empty_body"] and item["text"]}
        functions = [name for name in functions if name not in layout_functions]
        namespaces = sorted(set(re.findall(r"\bnamespace\s+([A-Za-z_$][\w$]*)\s*\{", text)))
        color_match = re.search(r"//%[^\r\n]*\bcolor\s*=\s*[\"'](#?[0-9A-Fa-f]{6})[\"']", text)
        if mode == "REALTIME":
            color_match = re.search(r"\bcolor1\s*:\s*['\"](#?[0-9A-Fa-f]{6})['\"]", text)
        result[mode] = {
            "entry": str(entry),
            "block_functions": functions,
            "secondary_labels": labels,
            "source_namespaces": namespaces,
            "declared_color1": color_match.group(1).lower() if color_match else None,
        }
        if mode == "REALTIME":
            result[mode]["execution_methods"] = sorted(set(re.findall(
                r"^\s+(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", text, re.MULTILINE
            )) - {"constructor", "getInfo", "if", "for", "while", "switch", "catch"})
            result[mode]["imports"] = sorted(set(re.findall(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]", text))
                                              | set(re.findall(r"\bfrom\s+['\"]([^'\"]+)['\"]", text)))
    return result


def source_anomalies(
    signatures: dict[str, Path], dependencies: dict, config: object, package_identities: list[str]
) -> list[dict]:
    findings = []
    for mode, entry in signatures.items():
        if not entry.is_file():
            continue
        for line_number, line in enumerate(read_text(entry).splitlines(), start=1):
            match = re.search(r"\bblockType\s*=\s*([\"'])", line)
            if match and match.group(1) not in line[match.end():]:
                findings.append(
                    {
                        "code": "MALFORMED_BLOCK_TYPE",
                        "mode": mode,
                        "entry": Path(entry.parent.name, entry.name).as_posix(),
                        "line": line_number,
                    }
                )
    if signatures["PYTHON_BLOCK"].is_file() and dependencies["ignored_requirement_files"]:
        findings.append(
            {
                "code": "PYTHON_REQUIREMENTS_OUTSIDE_AUTHORITY",
                "mode": "PYTHON_BLOCK",
                "paths": dependencies["ignored_requirement_files"],
            }
        )
    if isinstance(config, dict):
        source_id = config.get("id")
        candidate = canonical_v2_id(source_id)
        if not re.fullmatch(r"[A-Za-z0-9]+", str(source_id or "")):
            findings.append(
                {
                    "code": "V1_ID_INVALID_FOR_V2",
                    "source_id": source_id,
                    "canonical_v2_id": candidate or None,
                }
            )
        if not candidate:
            findings.append({"code": "V2_ID_NORMALIZATION_EMPTY", "source_id": source_id})
    if len(package_identities) > 1:
        findings.append(
            {"code": "LEGACY_PACKAGE_IDENTITY_CONFLICT", "identities": package_identities}
        )
    elif len(package_identities) == 1:
        config_identity = config_package_identity(config)
        if config_identity and package_identities[0] != config_identity:
            findings.append(
                {
                    "code": "LEGACY_PACKAGE_CONFIG_IDENTITY_CONFLICT",
                    "package_identity": package_identities[0],
                    "config_identity": config_identity,
                }
            )
    return findings


def features_by_mode(
    config: object,
    signatures: dict[str, Path],
    relative_files: list[Path],
    dependencies: dict,
    micropython_dependencies: dict | None = None,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mode, entry in signatures.items():
        if not entry.is_file():
            continue
        raw = read_text(entry)
        active = active_typescript(raw)
        features = common_features(raw, active, relative_files)

        if mode in {"PYTHON_BLOCK", "MICROPYTHON"}:
            mode_dependencies = dependencies if mode == "PYTHON_BLOCK" else micropython_dependencies
            if mode_dependencies["config_dependencies"] or any(
                item["specs"] for item in mode_dependencies["requirements_files"]
            ):
                features.add("dependencies")
            if mode_dependencies["local_libraries"]:
                features.add("local-library")
            for method, feature in GENERATOR_CALLS.items():
                if has_generator_call(active, method):
                    features.add(feature)
            if re.search(r"blockType\s*=\s*[\"']?(hat|event)\b", raw, re.IGNORECASE):
                features.add("event-callback")
            if has_generator_call(active, "addComment") or re.search(
                r"\bget_asset_path_by_name\s*\(", active
            ):
                features.add("advanced")
            if mode == "MICROPYTHON":
                features.add("board-condition")
                for method, feature in {"addWhile": "add-while", "getSetup": "get-setup", "getStaticFunction": "get-static-function"}.items():
                    if has_generator_call(active, method):
                        features.add(feature)
        elif mode == "REALTIME":
            if re.search(r"\bmenus\s*:", active):
                features.add("menu")
            if re.search(r"\bitems\s*:\s*['\"]", active):
                features.add("dynamic-menu")
            if re.search(r"\bfirmata\b", active):
                features.add("firmata")
            if isinstance(config, dict) and config.get("isSupportStage") is True:
                features.add("stage")
            else:
                features.add("board-condition")
        elif mode == "UPLOAD":
            for method, feature in UPLOAD_GENERATOR_CALLS.items():
                if has_generator_call(active, method):
                    features.add(feature)
            config_text = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else ""
            board_condition = bool(
                re.search(r"//%[^\n]*\b(?:board|boards)\s*=", raw, re.IGNORECASE)
                or re.search(r'"(?:board|boards|supportDevices|supportArch)"\s*:', config_text)
            )
            if board_condition:
                features.add("board-condition")
                if "menu" in features:
                    features.add("dynamic-menu")
            if any(has_generator_call(active, method) for method in ("addComment", "addErrorPrompt")):
                features.add("advanced")

        result[mode] = sorted(features)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_dir():
        print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": f"not a directory: {source}"}, ensure_ascii=False))
        return 2

    config_path = source / "config.json"
    config = None
    config_error = None
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            config_error = str(exc)
        if config is not None and not isinstance(config, dict):
            config_error = "config.json root must be an object"
            config = None

    candidates = []
    try:
        signatures = mode_entries(source, config)
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": str(exc)}))
        return 2
    for mode, entry in signatures.items():
        if entry.is_file():
            candidates.append({"mode": mode, "entry": str(entry.relative_to(source)), "confidence": "C3"})

    files = []
    relative_files = []
    for path, relative in iter_files(source):
        relative_files.append(relative)
        files.append({"path": relative.as_posix(), "size": path.stat().st_size, "sha256": digest(path)})

    dependencies = dependency_inventory(source, config, relative_files)
    micropython_dependencies = dependency_inventory(source, config, relative_files, "micropython", signatures["MICROPYTHON"].parent.relative_to(source))
    package_identities = legacy_package_identities(source)
    localization = localization_inventory(source, relative_files)
    entry_facts = entry_inventory(signatures)
    for mode in ("MICROPYTHON", "REALTIME"):
        if mode in entry_facts:
            language = MODE_SOURCES[mode][0]
            entry_facts[mode]["asset_key"] = language
            entry_facts[mode]["source_asset"] = config_python(config, language)
    mode_features = features_by_mode(config, signatures, relative_files, dependencies, micropython_dependencies)
    reference_features = sorted({feature for values in mode_features.values() for feature in values})
    findings = source_anomalies(signatures, dependencies, config, package_identities)
    if signatures["REALTIME"].is_file() and not entry_facts["REALTIME"]["block_functions"]:
        findings.append({"code": "REALTIME_BLOCKS_UNRESOLVED", "mode": "REALTIME", "entry": str(signatures["REALTIME"]),
                         "message": "Trace imported/computed block definitions and record their opcodes before conversion; do not treat an empty literal scan as complete."})
    if signatures["MICROPYTHON"].is_file() and micropython_dependencies["ignored_requirement_files"]:
        findings.append({"code": "MICROPYTHON_REQUIREMENTS_OUTSIDE_AUTHORITY", "mode": "MICROPYTHON",
                         "paths": micropython_dependencies["ignored_requirement_files"]})

    fallback_compatibility = config_package_identity(config)
    expected_compatibility = package_identities[0] if len(package_identities) == 1 else fallback_compatibility
    compatibility_source = "mpext_filename" if len(package_identities) == 1 else "config_author_id" if not package_identities else None

    result = {
        "status": "PASS" if config is not None and candidates else "BLOCKED",
        "reason_code": None if config is not None and candidates else "INPUT",
        "source": str(source),
        "config_path": str(config_path) if config_path.is_file() else None,
        "config_error": config_error,
        "config_fields": sorted(config.keys()) if isinstance(config, dict) else [],
        "identity": {
            "id": config.get("id"),
            "author": config.get("author"),
            "version": config.get("version"),
            "canonical_v2_id": canonical_v2_id(config.get("id")),
            "legacy_package_identities": package_identities,
            "expected_compatibility_id": expected_compatibility,
            "compatibility_evidence": compatibility_source,
        } if isinstance(config, dict) else {},
        "candidates": candidates,
        "reference_features": reference_features,
        "reference_features_by_mode": mode_features,
        "source_anomalies": findings,
        "python_dependency_inventory": dependencies,
        "micropython_dependency_inventory": micropython_dependencies,
        "localization_inventory": localization,
        "v1_entry_inventory": entry_facts,
        "file_count": len(files),
        "files": files,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8", newline="\n") as output_handle:
                output_handle.write(encoded + "\n")
        except OSError as exc:
            print(json.dumps({"status": "BLOCKED", "reason_code": "WORKSPACE", "error": str(exc)}, ensure_ascii=False))
            return 2
    print(encoded)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
