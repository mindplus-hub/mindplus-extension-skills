#!/usr/bin/env python3
"""Validate a MindPlus Agent handoff and its claimed review profile."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from check_basic_review import BASIC_CHECKS, verify_file as verify_basic
from check_lite_review import verify_selection


SCHEMA_VERSION = "mindplus-agent.handoff/v1"
REQUIRED_FIELDS = {
    "schema_version",
    "run_id",
    "parent_run_id",
    "workflow",
    "producer",
    "state",
    "status",
    "outcome",
    "reason_code",
    "input_provenance",
    "project_root",
    "project_sha256",
    "artifacts",
    "checks",
    "authorizations",
    "next",
}
WORKFLOW_PRODUCER = {
    "CONVERT_FRESH": "mindplus-switch",
    "CREATE_FRESH": "mindplus-create",
    "UPGRADE_EXISTING": "mindplus-upgrade",
    "REVIEW_EXISTING": "mindplus-review",
    "PUBLISH_GITEE": "mindplus-gitee-publish",
}
AUTHORIZATION_FIELDS = {
    "local_write",
    "install",
    "build",
    "mindplus_ui",
    "commit",
    "create_repository",
    "push",
    "device_upload",
}
CHECK_RESULTS = {"PASS", "FAIL", "NOT_RUN", "ACCEPTED_LIMITATION", "CARRIED_RISK"}
REPORT_FIRST_OUTCOME = "REPORTED_FINDINGS"
REPORT_FIRST_STATIC_CHECKS = frozenset(
    {"config_schema", "extension_static_integrity", "source_semantics", "malicious_code_review"}
)
REPORT_FIRST_SKIPPED_CHECKS = frozenset({"blocks_visible", "blocks_functional", "package_size"})

CREDENTIAL_URL_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("handoff root must be an object")
    return value


def scan_secrets(value: Any, errors: list[str], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            folded = str(key).casefold()
            if any(part in folded for part in ("password", "token", "cookie", "authorization_header")):
                errors.append(f"secret-like key is forbidden: {path}.{key}")
            scan_secrets(child, errors, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_secrets(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        if CREDENTIAL_URL_RE.search(value) or "access_token=" in value.casefold():
            errors.append(f"credential-bearing string is forbidden: {path}")


def validate(data: dict[str, Any], require_outcome: str | None, check_artifacts: bool) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        errors.append(f"missing required fields: {missing}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    workflow = data.get("workflow")
    producer = data.get("producer")
    if workflow not in WORKFLOW_PRODUCER:
        errors.append(f"unknown workflow: {workflow!r}")
    elif producer != WORKFLOW_PRODUCER[workflow]:
        errors.append(f"producer {producer!r} does not match workflow {workflow!r}")

    state = data.get("state")
    status = data.get("status")
    is_report_first = data.get("outcome") == REPORT_FIRST_OUTCOME

    if state not in {"RUNNING", "WAITING_USER", "TERMINAL"}:
        errors.append(f"invalid state: {state!r}")
    if status not in {"NOT_RUN", "PASS", "FAIL", "BLOCKED"}:
        errors.append(f"invalid status: {status!r}")
    if state == "WAITING_USER" and status != "BLOCKED":
        errors.append("WAITING_USER requires status BLOCKED")
    if state == "TERMINAL" and status == "NOT_RUN":
        errors.append("TERMINAL cannot have status NOT_RUN")
    if status == "PASS" and data.get("reason_code") is not None:
        errors.append("PASS requires a null reason_code")
    if status in {"FAIL", "BLOCKED"} and not data.get("reason_code"):
        errors.append(f"{status} requires a reason_code")
    if require_outcome and data.get("outcome") != require_outcome:
        errors.append(f"required outcome is {require_outcome}, got {data.get('outcome')!r}")

    project_raw = data.get("project_root")
    project = Path(project_raw).expanduser() if isinstance(project_raw, str) and project_raw else None
    if project is None or not project.is_absolute():
        errors.append("project_root must be an absolute path")
    project_sha256 = data.get("project_sha256")
    if not isinstance(project_sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", project_sha256):
        errors.append("project_sha256 must be a 64-character SHA-256 hex digest")

    provenance = data.get("input_provenance")
    if not isinstance(provenance, dict) or not provenance.get("sha256"):
        errors.append("input_provenance must contain sha256")

    authorizations = data.get("authorizations")
    if not isinstance(authorizations, dict):
        errors.append("authorizations must be an object")
    else:
        missing_auth = sorted(AUTHORIZATION_FIELDS - authorizations.keys())
        if missing_auth:
            errors.append(f"missing authorization fields: {missing_auth}")
        for key in AUTHORIZATION_FIELDS & authorizations.keys():
            if not isinstance(authorizations[key], bool):
                errors.append(f"authorization {key} must be boolean")

    checks = data.get("checks")
    checks_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(checks, list):
        errors.append("checks must be an array")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            check_id = check.get("id")
            if not isinstance(check_id, str) or not check_id:
                errors.append(f"checks[{index}] has no id")
                continue
            if check_id in checks_by_id:
                errors.append(f"duplicate check id: {check_id}")
            checks_by_id[check_id] = check
            if check.get("result") not in CHECK_RESULTS:
                errors.append(f"check {check_id} has invalid result")
            if check.get("confirmed_by") not in (None, "user"):
                errors.append(f"check {check_id} has invalid confirmed_by (only 'user' or null)")
            priority = check.get("priority")
            if priority is not None and priority not in {"P0", "P1", "P2"}:
                errors.append(f"invalid priority for check: {check_id}")
            if priority == "P0" and check.get("required") is not True:
                errors.append(f"P0 check must be required: {check_id}")
            if priority in {"P1", "P2"} and check.get("required") is not False:
                errors.append(f"advisory check must be optional: {check_id}")
            protected = {"config_schema", "extension_static_integrity", "source_semantics",
                         "repository_ownership", "version_bump", "upgrade_regression",
                         "publication_snapshot_current", "publication_set_reviewed",
                         "git_commit", "gitee_repository", "remote_ref_verified", "repository_topic_verified", "lite_source_selection"} | BASIC_CHECKS
            if priority in {"P1", "P2"} and check_id in protected:
                errors.append(f"required gate cannot be downgraded: {check_id}")
            if priority and check.get("result") == "FAIL" and not check.get("evidence"):
                errors.append(f"classified finding needs evidence: {check_id}")
            evidence = check.get("evidence")
            if (
                status == "PASS"
                and not is_report_first
                and check.get("required") is True
                and check.get("result") == "PASS"
                and not (isinstance(evidence, list) and evidence)
            ):
                errors.append(f"passing required check has no evidence: {check_id}")
            if (
                status == "PASS"
                and not is_report_first
                and check.get("required") is True
                and check.get("result") != "PASS"
            ):
                errors.append(f"passing handoff has non-passing required check: {check_id}")


    if workflow in {"CREATE_FRESH", "CONVERT_FRESH", "UPGRADE_EXISTING"} and status == "PASS":
        check = checks_by_id.get("lite_source_selection", {})
        if check.get("required") is not True or check.get("result") != "PASS" or not check.get("evidence"):
            errors.append("producer requires evidenced PASS: lite_source_selection")
        elif check_artifacts and project:
            try:
                verify_selection(project, load(Path(check["evidence"][0])))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"Lite selection invalid: {exc}")

    if workflow == "UPGRADE_EXISTING" and status == "PASS":
        if data.get("outcome") != "UPGRADED" or state != "TERMINAL":
            errors.append("passing upgrade requires TERMINAL/UPGRADED")
        for check_id in ("repository_ownership", "version_bump", "config_schema", "extension_static_integrity", "source_semantics", "upgrade_regression"):
            check = checks_by_id.get(check_id, {})
            if check.get("required") is not True or check.get("result") != "PASS" or not check.get("evidence"):
                errors.append(f"upgrade requires evidenced PASS: {check_id}")

    if data.get("outcome") == "REVIEWED_BASIC":
        if workflow != "REVIEW_EXISTING" or state != "TERMINAL" or status != "PASS":
            errors.append("REVIEWED_BASIC requires a TERMINAL/PASS review")
        for check_id in sorted(BASIC_CHECKS):
            check = checks_by_id.get(check_id, {})
            if check.get("required") is not True or check.get("result") != "PASS" or not check.get("evidence"):
                errors.append(f"BASIC review requires evidenced PASS: {check_id}")
    if is_report_first:
        if workflow != "REVIEW_EXISTING" or state != "TERMINAL" or status != "PASS":
            errors.append("REPORTED_FINDINGS requires a TERMINAL/PASS review")
        if data.get("next") != []:
            errors.append("REPORTED_FINDINGS is only valid for a review-only run")
        def require_report_evidence(check_id: str, evidence: list[Any]) -> None:
            if not check_artifacts:
                return
            for item in evidence:
                path = Path(item).expanduser() if isinstance(item, str) else None
                if path is None or not path.is_absolute() or not path.is_file():
                    errors.append(f"report-first evidence must be an absolute file: {check_id}")

        for check_id in sorted(REPORT_FIRST_STATIC_CHECKS):
            check = checks_by_id.get(check_id, {})
            result = check.get("result")
            evidence = check.get("evidence")
            if result not in {"PASS", "FAIL"} or not (isinstance(evidence, list) and evidence):
                errors.append(f"report-first requires evidenced PASS or FAIL: {check_id}")
            else:
                require_report_evidence(check_id, evidence)
                if result == "PASS" and check.get("required") is not True:
                    errors.append(f"report-first PASS gate must be required: {check_id}")
                elif result == "FAIL" and check.get("priority") != "P0":
                    errors.append(f"report-first failed gate must be P0: {check_id}")
        build = checks_by_id.get("builder_build", {})
        build_result = build.get("result")
        build_evidence = build.get("evidence")
        if build_result not in {"PASS", "FAIL", "NOT_RUN"}:
            errors.append("report-first builder_build must be PASS, FAIL, or NOT_RUN")
        elif build_result == "NOT_RUN" and build.get("required") is not False:
            errors.append("report-first deferred builder_build must be optional")
        elif build_result != "NOT_RUN" and not (isinstance(build_evidence, list) and build_evidence):
            errors.append("report-first executed builder_build needs evidence")
        else:
            if build_result != "NOT_RUN":
                require_report_evidence("builder_build", build_evidence)
            if build_result == "FAIL" and build.get("priority") != "P0":
                errors.append("report-first failed builder_build must be P0")
        for check_id in sorted(REPORT_FIRST_SKIPPED_CHECKS):
            check = checks_by_id.get(check_id, {})
            if check.get("result") != "NOT_RUN" or check.get("required") is not False:
                errors.append(f"report-first must defer {check_id} as optional NOT_RUN")


    if workflow in {"REVIEW_EXISTING", "PUBLISH_GITEE"} and status == "PASS":
        if workflow == "REVIEW_EXISTING" and is_report_first:
            pass
        else:
            if workflow == "REVIEW_EXISTING" and data.get("outcome") != "REVIEWED_BASIC":
                errors.append("Review requires a complete REVIEWED_BASIC result")
            reports = [a for a in data.get("artifacts", []) if a.get("kind") == "basic_review"]
            if len(reports) != 1:
                errors.append("BASIC requires exactly one basic_review artifact")
            elif check_artifacts and project:
                try:
                    verify_basic(project, Path(reports[0]["path"]))
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f"BASIC report invalid: {exc}")


    if data.get("outcome") == "TOKEN_REQUIRED":
        if workflow not in {"PUBLISH_GITEE", "UPGRADE_EXISTING"}:
            errors.append("TOKEN_REQUIRED must come from publication or upgrade")
        if state != "WAITING_USER" or status != "BLOCKED":
            errors.append("TOKEN_REQUIRED requires WAITING_USER/BLOCKED")
        if data.get("reason_code") != "AUTH.GITEE_TOKEN_MISSING":
            errors.append("TOKEN_REQUIRED requires AUTH.GITEE_TOKEN_MISSING")
        if data.get("artifacts") not in ([], None):
            errors.append("missing-token handoff must not contain publication artifacts")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array")
    else:
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                errors.append(f"artifacts[{index}] must contain a path")
                continue
            artifact_path = Path(artifact["path"]).expanduser()
            if not artifact_path.is_absolute():
                errors.append(f"artifact path must be absolute: {artifact['path']}")
            elif check_artifacts and not artifact_path.exists():
                errors.append(f"artifact does not exist: {artifact_path}")
    if is_report_first and isinstance(artifacts, list) and any(
        isinstance(artifact, dict) and artifact.get("kind") == "basic_review" for artifact in artifacts
    ):
        errors.append("REPORTED_FINDINGS must not contain a basic_review artifact")

    if check_artifacts and project is not None and not project.is_dir():
        errors.append(f"project_root does not exist: {project}")

    scan_secrets(data, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--require-outcome")
    parser.add_argument("--check-artifacts", action="store_true")
    args = parser.parse_args()
    path = args.input.expanduser().resolve(strict=False)
    try:
        data = load(path)
        errors = validate(data, args.require_outcome, args.check_artifacts)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors = [str(exc)]
    output = {"status": "PASS" if not errors else "FAIL", "handoff": str(path), "errors": errors}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
