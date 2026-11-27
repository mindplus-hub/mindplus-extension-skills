#!/usr/bin/env python3
"""Validate source-bound BASIC evidence and the exact distributable ZIP, without executing it."""
from __future__ import annotations

import argparse
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from hash_project import compute_project_hash, file_digest, is_reparse_point

MAX_PACKAGE_BYTES = 5_000_000
BASIC_CHECKS = {"config_schema", "extension_static_integrity", "source_semantics", "malicious_code_review",
                "builder_build", "blocks_visible", "blocks_functional", "package_size"}
EVIDENCE_CHECKS = BASIC_CHECKS - {"package_size"}


def regular_file(path):
    if not path.is_absolute() or path.is_symlink() or is_reparse_point(path) or not path.is_file():
        raise ValueError(f"expected an absolute regular file: {path}")
    return path


def package_facts(path):
    regular_file(path)
    size = path.stat().st_size
    if size > MAX_PACKAGE_BYTES:
        raise ValueError(f"build ZIP is {size} bytes; maximum is {MAX_PACKAGE_BYTES}; do not publish")
    if path.suffix.casefold() != ".zip" or not zipfile.is_zipfile(path):
        raise ValueError("build artifact must be the actual extension ZIP")
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 10000:
            raise ValueError("build ZIP contains too many entries to inspect")
        names = []
        total = 0
        for entry in archive.infolist():
            name = entry.filename
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or "\\" in name or ":" in name or ".." in parts or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("unsafe build ZIP entry")
            if entry.is_dir():
                continue
            if name in names:
                raise ValueError("duplicate build ZIP entry")
            names.append(name)
            total += entry.file_size
        if total > 128 * 1024 * 1024:
            raise ValueError("build ZIP uncompressed content exceeds inspection limit")
        if not any(PurePosixPath(n).name == "main.js" for n in names) or not any(PurePosixPath(n).name == "config.json" for n in names):
            raise ValueError("build ZIP lacks main.js or config.json")
        if archive.testzip() is not None:
            raise ValueError("build ZIP CRC check failed")
    return {"path": str(path), "size_bytes": size, "sha256": file_digest(path), "max_bytes": MAX_PACKAGE_BYTES}


def verify(project, report):
    """Fail closed for missing, stale or downgraded evidence. Evidence remains an auditable claim, not a signature."""
    if not isinstance(report, dict) or report.get("schema_version") != "mindplus.review-basic/v1":
        raise ValueError("BASIC review schema is missing or unsupported")
    if Path(report.get("project_root", "")).resolve() != project.resolve():
        raise ValueError("BASIC project does not match publication target")
    if report.get("project_sha256") != compute_project_hash(project)[0]:
        raise ValueError("BASIC evidence is stale; source changed")
    artifact = report.get("artifact", {})
    if not isinstance(artifact, dict):
        raise ValueError("BASIC artifact must be an object")
    facts = package_facts(Path(artifact.get("path", "")))
    if artifact.get("sha256") != facts["sha256"]:
        raise ValueError("build ZIP changed after BASIC verification")
    checks = report.get("checks", {})
    if not isinstance(checks, dict):
        raise ValueError("BASIC checks must be an object")
    for name in EVIDENCE_CHECKS:
        check = checks.get(name, {})
        if not isinstance(check, dict) or check.get("result") != "PASS" or not check.get("summary") or not check.get("method"):
            raise ValueError(f"BASIC requires verified PASS with method and scope: {name}")
        evidence = check.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"BASIC requires concrete evidence: {name}")
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError(f"BASIC evidence must contain path and sha256: {name}")
            path = regular_file(Path(item.get("path", "")))
            if item.get("sha256") != file_digest(path):
                raise ValueError(f"BASIC evidence changed: {name}")
    if checks["builder_build"].get("exit_code") != 0:
        raise ValueError("builder_build must record actual exit_code 0")
    for name in ("builder_build", "blocks_visible", "blocks_functional"):
        if checks[name].get("artifact_sha256") != facts["sha256"]:
            raise ValueError(f"{name} must verify this exact ZIP")
    return facts


def require_passed(report):
    """A BASIC report only authorizes publication once it already reads PASS.

    The check is fail-closed on an explicit top-level ``status``; it is never
    inferred from the eight checks. Report the actual reason so a missing field
    is not mistaken for a failed review.
    """
    if not isinstance(report, dict):
        raise ValueError(f'BASIC evidence must be a JSON object, not {type(report).__name__}')
    status = report.get("status")
    if status == "PASS":
        return report
    if status is None:
        raise ValueError(
            'BASIC evidence is missing the top-level "status" field; this validator is fail-closed and '
            'requires an explicit "status": "PASS" in the input file (the eight checks alone are not enough)'
        )
    detail = ", ".join(f"{key}={report[key]!r}" for key in ("reason_code", "error") if report.get(key))
    raise ValueError(f'BASIC evidence status is {status!r}, expected "PASS"' + (f" ({detail})" if detail else ""))


def verify_file(project, path):
    regular_file(path)
    report = require_passed(json.loads(path.read_text(encoding="utf-8-sig")))
    return verify(project, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = require_passed(json.loads(args.evidence.read_text(encoding="utf-8-sig")))
        facts = verify(args.project_root, report)
        report.update(status="PASS", artifact=facts)
        report["checks"]["package_size"] = {"result": "PASS", "size_bytes": facts["size_bytes"], "max_bytes": MAX_PACKAGE_BYTES}
        code = 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        report = {"schema_version": "mindplus.review-basic/v1", "status": "BLOCKED", "reason_code": "REVIEW.BASIC_NOT_READY", "error": str(exc)}
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
