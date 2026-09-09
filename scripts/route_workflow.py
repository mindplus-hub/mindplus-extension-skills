#!/usr/bin/env python3
"""Build a deterministic MindPlus Agent workflow route from explicit path facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mindplus-agent.route-result/v1"
SUPPORTED_GOALS = {"CONVERT", "CREATE", "UPGRADE", "REVIEW", "PUBLISH", "SYNC"}
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
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "references" / "workflow-registry.json"


class RouteError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouteError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RouteError(f"JSON root must be an object: {path}")
    return value


def normalize_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RouteError("path values must be strings or null")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RouteError(f"path must be absolute: {value}")
    return path.resolve(strict=False)


def target_state(path: Path | None) -> str:
    if path is None:
        return "MISSING"
    if not path.exists():
        return "ABSENT"
    if not path.is_dir():
        return "FILE"
    try:
        next(path.iterdir())
    except StopIteration:
        return "EMPTY"
    return "NON_EMPTY"


def result(
    *,
    state: str,
    status: str,
    reason_code: str | None,
    message: str,
    facts: dict[str, Any],
    workflows: list[str] | None = None,
    leaf_references: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "status": status,
        "reason_code": reason_code,
        "message": message,
        "facts": facts,
        "workflows": workflows or [],
        "leaf_references": leaf_references or [],
    }


def route(request: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schema_version") != "mindplus-agent.workflow-registry/v1":
        raise RouteError("unsupported workflow registry schema_version")
    registry_workflows = registry.get("workflows")
    expected_workflows = {"CONVERT_FRESH", "CREATE_FRESH", "UPGRADE_EXISTING", "REVIEW_EXISTING", "PUBLISH_GITEE"}
    if not isinstance(registry_workflows, dict) or set(registry_workflows) != expected_workflows:
        raise RouteError("workflow registry must contain exactly the five supported workflows")

    review_profile = request.get("review_profile", "BASIC")
    if review_profile not in {"BASIC", "HOST_READY"}:
        raise RouteError("review_profile must be BASIC or HOST_READY")

    raw_goals = request.get("goals")
    if not isinstance(raw_goals, list) or not raw_goals:
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="INPUT.GOALS_REQUIRED",
            message="At least one lifecycle goal is required.",
            facts={},
        )
    if not all(isinstance(goal, str) for goal in raw_goals):
        raise RouteError("every goal must be a string")
    goals = {goal.strip().upper() for goal in raw_goals}
    unknown = sorted(goals - SUPPORTED_GOALS)
    if unknown:
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="ROUTE.UNKNOWN_GOAL",
            message=f"Unsupported goals: {unknown}",
            facts={"goals": sorted(goals)},
        )

    paths = request.get("paths")
    if not isinstance(paths, dict):
        raise RouteError("paths must be an object")
    allowed_path_fields = {"v1_source", "project_root", "extension_spec", "review_handoff"}
    unknown_path_fields = sorted(set(paths) - allowed_path_fields)
    if unknown_path_fields:
        raise RouteError(f"unsupported path fields: {unknown_path_fields}")
    project = normalize_path(paths.get("project_root"))
    v1_source = normalize_path(paths.get("v1_source"))
    extension_spec = normalize_path(paths.get("extension_spec"))
    review_handoff = normalize_path(paths.get("review_handoff"))
    project_state = target_state(project)
    raw_authorizations = request.get("authorizations", {})
    if not isinstance(raw_authorizations, dict):
        raise RouteError("authorizations must be an object")
    unknown_authorizations = sorted(set(raw_authorizations) - AUTHORIZATION_FIELDS)
    if unknown_authorizations:
        raise RouteError(f"unsupported authorization fields: {unknown_authorizations}")
    authorizations = {
        field: raw_authorizations.get(field) is True for field in AUTHORIZATION_FIELDS
    }
    facts: dict[str, Any] = {
        "goals": sorted(goals),
        "project_root": str(project) if project else None,
        "project_state": project_state,
        "v1_source_exists": bool(v1_source and v1_source.is_dir()),
        "extension_spec_exists": bool(extension_spec and extension_spec.is_file()),
        "review_handoff_exists": bool(review_handoff and review_handoff.is_file()),
        "authorizations": authorizations,
    }

    if "SYNC" in goals:
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="ROUTE.UNSUPPORTED_EXISTING_V2_SYNC",
            message="Existing-V2 synchronization is not supported; fresh conversion must not overwrite it.",
            facts=facts,
        )
    if len(goals & {"CONVERT", "CREATE", "UPGRADE"}) > 1:
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="ROUTE.CONFLICTING_PRODUCERS",
            message="Choose one producer: fresh conversion, creation, or existing V2 upgrade.",
            facts=facts,
        )
    if "PUBLISH" in goals and not (authorizations["commit"] and authorizations["push"]):
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="AUTH.PUSH_NOT_AUTHORIZED",
            message="Publication requires explicit commit and push authorization in the request. Ask the user, then resubmit with authorizations.commit and authorizations.push set to true.",
            facts=facts,
        )
    if goals & {"CONVERT", "CREATE", "UPGRADE"} and not authorizations["local_write"]:
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="AUTH.LOCAL_WRITE_REQUIRED",
            message="Creation, conversion and upgrade require local project writes. Ask the user, then resubmit with authorizations.local_write set to true.",
            facts=facts,
        )
    if project is None:
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="INPUT.PROJECT_ROOT_REQUIRED",
            message="An absolute project_root is required.",
            facts=facts,
        )
    if project_state == "FILE":
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="WORKSPACE.PROJECT_ROOT_NOT_DIRECTORY",
            message="project_root points to a file.",
            facts=facts,
        )

    producer: str | None = None
    if "CONVERT" in goals:
        if not v1_source:
            return result(
                state="WAITING_USER",
                status="BLOCKED",
                reason_code="INPUT.V1_SOURCE_REQUIRED",
                message="Fresh conversion requires an absolute v1_source.",
                facts=facts,
            )
        if not v1_source.is_dir():
            return result(
                state="TERMINAL",
                status="BLOCKED",
                reason_code="INPUT.V1_SOURCE_NOT_FOUND",
                message="The supplied v1_source directory does not exist.",
                facts=facts,
            )
        if project_state == "NON_EMPTY":
            return result(
                state="TERMINAL",
                status="BLOCKED",
                reason_code="ROUTE.UNSUPPORTED_EXISTING_V2_SYNC",
                message="Fresh conversion cannot target an existing non-empty V2 project.",
                facts=facts,
            )
        producer = "CONVERT_FRESH"
    elif "CREATE" in goals:
        if project_state == "NON_EMPTY":
            return result(
                state="TERMINAL",
                status="BLOCKED",
                reason_code="WORKSPACE.TARGET_NOT_EMPTY",
                message="Fresh creation requires an absent or empty project_root.",
                facts=facts,
            )
        producer = "CREATE_FRESH"

    elif "UPGRADE" in goals:
        if project_state != "NON_EMPTY":
            return result(state="TERMINAL", status="BLOCKED",
                          reason_code="WORKSPACE.EXISTING_PROJECT_REQUIRED",
                          message="Upgrade requires an existing V2 project; inspect its format in the upgrade leaf.", facts=facts)
        producer = "UPGRADE_EXISTING"

    if producer and not project.parent.is_dir():
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="WORKSPACE.PROJECT_PARENT_NOT_FOUND",
            message="The project_root parent directory must already exist.",
            facts=facts,
        )

    if not producer and goals & {"REVIEW", "PUBLISH"} and project_state != "NON_EMPTY":
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="WORKSPACE.EXISTING_PROJECT_REQUIRED",
            message="Review or publication requires an existing non-empty project_root.",
            facts=facts,
        )

    if review_handoff and not review_handoff.is_file():
        return result(
            state="WAITING_USER",
            status="BLOCKED",
            reason_code="INPUT.REVIEW_HANDOFF_NOT_FOUND",
            message="The supplied review_handoff does not exist.",
            facts=facts,
        )

    workflows: list[str] = []
    if producer:
        workflows.append(producer)

    review_needed = "REVIEW" in goals or review_profile == "HOST_READY"
    if review_needed:
        workflows.append("REVIEW_EXISTING")
    if "PUBLISH" in goals:
        workflows.append("PUBLISH_GITEE")

    if not workflows:
        return result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="ROUTE.NO_WORKFLOW",
            message="No supported workflow matched the request.",
            facts=facts,
        )

    leaf_references: list[str] = []
    for workflow in workflows:
        entry = registry_workflows.get(workflow)
        if not isinstance(entry, dict) or not isinstance(entry.get("leaf"), str):
            raise RouteError(f"workflow registry has no leaf for {workflow}")
        leaf_references.append(entry["leaf"])

    return result(
        state="RUNNING",
        status="PASS",
        reason_code=None,
        message="Route selected. Load only the first leaf and advance through validated handoffs.",
        facts=facts,
        workflows=workflows,
        leaf_references=leaf_references,
    )


def write_result(value: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        output = output.expanduser().resolve(strict=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded)
    print(encoded, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        request = read_json(args.input.expanduser().resolve(strict=False))
        registry = read_json(args.registry.expanduser().resolve(strict=False))
        routed = route(request, registry)
        write_result(routed, args.output)
        return 0 if routed["status"] == "PASS" else 3
    except RouteError as exc:
        failed = result(
            state="TERMINAL",
            status="BLOCKED",
            reason_code="INPUT.INVALID_ROUTE_REQUEST",
            message=str(exc),
            facts={},
        )
        write_result(failed, args.output)
        return 2


if __name__ == "__main__":
    sys.exit(main())
