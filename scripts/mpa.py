#!/usr/bin/env python3
"""Wizard entry for the MindPlus Agent lifecycle pipeline.

Composes the deterministic scripts so the calling model only copies one
command at a time: start routes a request and opens a parent run, handoff
assembles and validates a leaf handoff, transition advances through the
recorded gates, resume rebuilds position after an interruption. Every JSON
output ends with next_command; run it verbatim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from hash_project import HashError, compute_project_hash
from init_run import RUN_ID_RE, RunError, initialize_run, read_object
from route_workflow import AUTHORIZATION_FIELDS, REGISTRY_PATH
from route_workflow import read_json as read_route_json
from route_workflow import route as route_request_fn
from validate_handoff import (
    HOST_READY_CHECKS,
    USER_CONFIRMED_CHECKS,
    WORKFLOW_PRODUCER,
    load as load_handoff,
    validate as validate_handoff_data,
)


SKILL_ROOT = Path(__file__).resolve().parent.parent
CHECK_RESULTS = {"PASS", "FAIL", "NOT_RUN", "ACCEPTED_LIMITATION", "CARRIED_RISK"}
LEAF_FILES = {
    "CONVERT_FRESH": "switch.md",
    "CREATE_FRESH": "create.md",
    "UPGRADE_EXISTING": "upgrade.md",
    "REVIEW_EXISTING": "review.md",
    "PUBLISH_GITEE": "gitee-publish.md",
}
NEXT_CONDITIONS = {
    "REVIEW_EXISTING": "producer handoff PASS and project exists",
    "PUBLISH_GITEE": "passing requested checks and current project hash",
}
USER_EVIDENCE_CHECKLIST = [
    "1. Import the built extension package into the Mind+ host.",
    "2. Confirm the extension blocks appear in the palette and are correctly localized.",
    "3. Run a representative target compilation for the declared board scope.",
    "4. Only after the user confirms these observations, rerun with --confirmed <check_id>.",
]
ROUTE_FIX = {
    "AUTH.PUSH_NOT_AUTHORIZED": "Ask the user for commit and push authorization, then rerun the same command with --auth commit --auth push.",
    "AUTH.LOCAL_WRITE_REQUIRED": "Ask the user for permission to write the project, then rerun with --auth local_write.",
    "INPUT.PROJECT_ROOT_REQUIRED": "Rerun with --project-root <absolute path>.",
    "INPUT.V1_SOURCE_REQUIRED": "Rerun with --v1-source <absolute directory>.",
    "ROUTE.CONFLICTING_PRODUCERS": "Rerun with exactly one of CONVERT, CREATE or UPGRADE in --goals.",
    "ROUTE.UNSUPPORTED_EXISTING_V2_SYNC": "Unsupported: the project_root is non-empty. Choose a new empty --project-root; existing-V2 sync has no fallback.",
    "WORKSPACE.TARGET_NOT_EMPTY": "Fresh creation needs an absent or empty --project-root; pick another directory.",
    "WORKSPACE.EXISTING_PROJECT_REQUIRED": "Upgrade, review or publication needs an existing non-empty --project-root.",
    "INPUT.REVIEW_HANDOFF_NOT_FOUND": "The supplied --review-handoff file does not exist; fix the path or drop the flag to insert a review first.",
    "INPUT.GOALS_REQUIRED": "Rerun with --goals (one or more of CONVERT, CREATE, UPGRADE, REVIEW, PUBLISH).",
}


def emit(value: dict[str, Any], code: int) -> int:
    payload = dict(value)
    payload.setdefault("next_command", None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def hide_path(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(["attrib", "+h", str(path)], capture_output=True, check=False)


def cleanup_run_dir(run_root: Path) -> None:
    """Remove one run directory, clearing the Windows hidden attribute first."""
    if os.name == "nt":
        subprocess.run(["attrib", "-h", str(run_root), "/S", "/D"], capture_output=True, check=False)
    shutil.rmtree(run_root, ignore_errors=True)


def leaf_reference(workflow: str) -> str:
    return (SKILL_ROOT / "references" / "workflows" / LEAF_FILES[workflow]).as_posix()


def build_context(work_root: Path, request: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    paths = request.get("paths", {}) if isinstance(request, dict) else {}
    authorizations = run.get("authorizations", {}) if isinstance(run.get("authorizations"), dict) else {}
    run_root = work_root / ".mindplus-agent" / "runs" / str(run.get("run_id", ""))
    upstream = None
    for workflow in reversed(run.get("workflows", [])):
        if workflow != "PUBLISH_GITEE":
            candidate = run_root / "handoffs" / f"{workflow}.json"
            if candidate.is_file():
                upstream = candidate.as_posix()
                break
    if not any(w != "PUBLISH_GITEE" for w in run.get("workflows", [])):
        upstream = paths.get("review_handoff")
    return {
        "work_root": work_root.as_posix(),
        "v1_source": paths.get("v1_source"),
        "project_root": paths.get("project_root"),
        "review_handoff": upstream,
        "review_profile": request.get("review_profile", "BASIC"),
        "authorizations": authorizations,
        "create_repository": authorizations.get("create_repository") is True,
        "preflight_output": (run_root / "evidence" / "publish-preflight.json").as_posix(),
    }


def next_command_for(workflow: str, ctx: dict[str, Any]) -> str:
    skill = SKILL_ROOT.as_posix()
    header = f"Read {leaf_reference(workflow)} fully, then run:"
    if workflow == "REVIEW_EXISTING":
        header = f"Use review profile {ctx.get('review_profile', 'BASIC')}. " + header
    if workflow == "CONVERT_FRESH":
        command = f"python {quote(skill + '/scripts/switch/init_run.py')} --work-root {quote(ctx['work_root'])} --v1-source {quote(ctx['v1_source'])}"
        if ctx.get("project_root"):
            command += f" --project-root {quote(ctx['project_root'])}"
    elif workflow == "CREATE_FRESH":
        command = f"python {quote(skill + '/scripts/switch/check_reference_release.py')} --skill-root {quote(skill)} --offline"
    elif workflow in {"REVIEW_EXISTING", "UPGRADE_EXISTING"}:
        command = f"python {quote(skill + '/scripts/hash_project.py')} --project-root {quote(ctx['project_root'])}"
    elif workflow == "PUBLISH_GITEE":
        command = (
            f"python {quote(skill + '/scripts/prepare_gitee_publish.py')}"
            f" --project-root {quote(ctx['project_root'])}"
            f" --output {quote(ctx['preflight_output'])}"
        )
        if ctx.get("review_handoff"):
            command += f" --review-handoff {quote(ctx['review_handoff'])}"
        for auth in ("commit", "push", "create_repository"):
            if ctx.get("authorizations", {}).get(auth):
                command += f" --auth {auth}"
        if ctx.get("review_profile") == "HOST_READY":
            command += " --require-host-ready"
        if ctx.get("create_repository"):
            command += " --create-repo"
    else:
        command = ""
    return f"{header} {command}"


def load_run(work_root: Path, run_id: str) -> tuple[dict[str, Any], Path]:
    run_file = work_root / ".mindplus-agent" / "runs" / run_id / "run.json"
    if not run_file.is_file():
        raise RunError(f"run not found: {run_file}")
    return read_object(run_file), run_file.parent


def read_request(run_root: Path) -> dict[str, Any]:
    request_path = run_root / "request.json"
    if not request_path.is_file():
        return {}
    try:
        return read_object(request_path)
    except RunError:
        return {}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# start


def cmd_start(args: argparse.Namespace) -> int:
    work_root = args.work_root.expanduser().resolve(strict=False)
    if not work_root.is_dir():
        return emit(
            {"status": "BLOCKED", "reason_code": "WORKSPACE.WORK_ROOT_MISSING", "error": f"work_root does not exist: {work_root}"},
            2,
        )

    goals = [goal.strip().upper() for goal in args.goals.split(",") if goal.strip()]
    authorizations = {field: False for field in AUTHORIZATION_FIELDS}
    for name in args.auth or []:
        normalized = name.strip().lower()
        if normalized not in authorizations:
            return emit(
                {
                    "status": "BLOCKED",
                    "reason_code": "INPUT.UNKNOWN_AUTHORIZATION",
                    "error": f"unknown --auth value: {name}",
                    "valid_values": sorted(AUTHORIZATION_FIELDS),
                },
                2,
            )
        authorizations[normalized] = True

    paths: dict[str, str] = {"project_root": str(args.project_root.expanduser().resolve(strict=False))}
    for flag in ("v1_source", "extension_spec", "review_handoff"):
        value = getattr(args, flag)
        if value is not None:
            paths[flag] = str(value.expanduser().resolve(strict=False))
    request = {"goals": goals, "paths": paths, "authorizations": authorizations, "review_profile": args.review_profile}

    run_id = args.run_id or uuid.uuid4().hex
    if not RUN_ID_RE.fullmatch(run_id):
        return emit({"status": "BLOCKED", "reason_code": "WORKSPACE.RUN_INIT", "error": "run_id contains unsafe characters"}, 2)
    existing_root = work_root / ".mindplus-agent" / "runs" / run_id
    if (existing_root / "run.json").is_file():
        existing_run = read_object(existing_root / "run.json")
        saved_request = read_request(existing_root)
        saved_request.setdefault("review_profile", "BASIC")
        if saved_request != request:
            return emit({"status": "BLOCKED", "reason_code": "WORKSPACE.RUN_REQUEST_MISMATCH", "error": "run-id already belongs to another request; resume it or choose a new run-id"}, 2)
        return emit({"status": "PASS_IDEMPOTENT", "run_id": run_id, "run_root": str(existing_root),
                     "current_workflow": existing_run.get("current_workflow"), "workflows": existing_run.get("workflows"),
                     "next_command": f"python {quote(Path(__file__).resolve().as_posix())} resume --work-root {quote(work_root.as_posix())} --run-id {quote(run_id)}"}, 0)

    try:
        registry = read_route_json(REGISTRY_PATH)
        routed = route_request_fn(request, registry)
    except Exception as exc:  # noqa: BLE001 - surface any contract failure verbatim
        return emit({"status": "BLOCKED", "reason_code": "INPUT.INVALID_ROUTE_REQUEST", "error": str(exc)}, 2)

    if routed.get("status") != "PASS":
        reason = routed.get("reason_code")
        return emit(
            {
                "status": routed.get("status"),
                "state": routed.get("state"),
                "reason_code": reason,
                "message": routed.get("message"),
                "facts": routed.get("facts"),
                "next_command": ROUTE_FIX.get(reason, "Fix the reported fact and rerun the same mpa.py start command."),
            },
            3,
        )

    run_root = work_root / ".mindplus-agent" / "runs" / run_id
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        hide_path(run_root.parent)
        hide_path(run_root)
        request_path = run_root / "request.json"
        route_path = run_root / "route.json"
        with request_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(json.dumps(request, ensure_ascii=False, indent=2) + "\n")
        with route_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(json.dumps(routed, ensure_ascii=False, indent=2) + "\n")
        if "UPGRADE_EXISTING" in routed["workflows"]:
            baseline_project = Path(paths["project_root"])
            baseline = {"project_root": str(baseline_project), "sha256": compute_project_hash(baseline_project)[0]}
            (run_root / "upgrade-baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        output = initialize_run(
            work_root,
            request,
            routed,
            run_id,
            request_path=request_path,
            route_path=route_path,
            allow_staging=True,
            keep_evidence=args.keep_evidence,
        )
    except (OSError, RunError, HashError) as exc:
        return emit({"status": "BLOCKED", "reason_code": "WORKSPACE.RUN_INIT", "error": str(exc)}, 2)

    current = output.get("current_workflow") or (routed.get("workflows") or [None])[0]
    ctx = build_context(work_root, request, {"run_id": run_id, "authorizations": authorizations, "workflows": routed["workflows"]})
    return emit(
        {
            "status": output.get("status"),
            "run_id": output.get("run_id"),
            "run_root": output.get("run_root"),
            "workflows": routed.get("workflows"),
            "current_workflow": current,
            "leaf_reference": leaf_reference(current),
            "next_command": next_command_for(current, ctx),
        },
        0,
    )


# ---------------------------------------------------------------------------
# handoff


def parse_pairs(values: list[str] | None, label: str, errors: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values or []:
        key, separator, rest = value.partition("=")
        if not separator or not key.strip() or not rest.strip():
            errors.append(f"invalid --{label} value (expected name=value): {value}")
            continue
        pairs.append((key.strip(), rest.strip()))
    return pairs


def cmd_handoff(args: argparse.Namespace) -> int:
    work_root = args.work_root.expanduser().resolve(strict=False)
    workflow = args.workflow.strip().upper()
    status = args.status.strip().upper()
    if workflow not in WORKFLOW_PRODUCER:
        return emit(
            {
                "status": "FAIL",
                "error": f"unknown workflow: {workflow}",
                "valid_workflows": sorted(WORKFLOW_PRODUCER),
            },
            1,
        )
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        return emit({"status": "FAIL", "error": "--status must be PASS, FAIL, or BLOCKED"}, 1)
    if status == "PASS" and args.reason_code:
        return emit({"status": "FAIL", "error": "a PASS handoff takes no --reason-code"}, 1)
    if status in {"FAIL", "BLOCKED"} and not args.reason_code:
        return emit({"status": "FAIL", "error": f"--reason-code is required for status {status}"}, 1)

    try:
        run, run_root = load_run(work_root, args.run_id)
    except RunError as exc:
        return emit({"status": "FAIL", "error": str(exc)}, 2)
    if run.get("state") == "TERMINAL":
        return emit({"status": "FAIL", "error": "run is already TERMINAL; start a new run"}, 1)
    if workflow != run.get("current_workflow"):
        return emit(
            {
                "status": "FAIL",
                "error": f"handoff can only be written for the current workflow {run.get('current_workflow')}; got {workflow}",
                "next_command": f"python {quote(Path(__file__).resolve().as_posix())} transition --work-root {quote(work_root.as_posix())} --run-id {quote(args.run_id)}",
            },
            1,
        )

    request = read_request(run_root)
    paths = request.get("paths", {}) if isinstance(request, dict) else {}
    errors: list[str] = []

    checks: list[dict[str, Any]] = []
    results_by_id: dict[str, str] = {}
    for check_id, result in parse_pairs(args.check, "check", errors):
        normalized = result.upper()
        if normalized not in CHECK_RESULTS:
            errors.append(f"invalid check result for {check_id}: {result}")
            continue
        results_by_id[check_id] = normalized
    optional = {value.strip() for value in args.optional or []}
    priorities = {}
    for check_id, priority in parse_pairs(args.priority, "priority", errors):
        priority = priority.upper()
        if check_id not in results_by_id or priority not in {"P0", "P1", "P2"} or check_id in priorities:
            errors.append(f"invalid or duplicate priority for check: {check_id}")
            continue
        priorities[check_id] = priority
        if priority in {"P1", "P2"}:
            optional.add(check_id)
        elif check_id in optional:
            errors.append(f"P0 check cannot be optional: {check_id}")
    if errors:
        return emit({"status": "FAIL", "errors": errors}, 1)
    confirmed = {value.strip() for value in args.confirmed or []}
    evidence_by_id: dict[str, list[str]] = {}
    for check_id, joined in parse_pairs(args.evidence, "evidence", errors):
        evidence_by_id[check_id] = [part.strip() for part in joined.split(",") if part.strip()]

    forgery: list[str] = []
    for check_id, result in results_by_id.items():
        if result == "PASS" and check_id not in optional and not evidence_by_id.get(check_id):
            forgery.append(f"required check {check_id} is PASS without --evidence; add --evidence {check_id}=<path>")
        if result == "PASS" and check_id in USER_CONFIRMED_CHECKS and check_id not in confirmed:
            forgery.append(f"Mind+ host GUI check {check_id} is PASS without user confirmation; add --confirmed {check_id} only after the user observed it")
    if forgery:
        return emit(
            {
                "status": "FAIL",
                "reason_code": "REVIEW.USER_EVIDENCE_REQUIRED",
                "errors": forgery,
                "user_checklist": USER_EVIDENCE_CHECKLIST,
                "next_command": "Ask the user to perform the checklist. After explicit confirmation rerun adding --confirmed <check_id>; otherwise record the check as NOT_RUN with --status BLOCKED.",
            },
            1,
        )

    for check_id, result in sorted(results_by_id.items()):
        checks.append(
            {
                "id": check_id,
                "layer": "HOST_BUILD" if check_id in HOST_READY_CHECKS else "STATIC",
                "claim": check_id.replace("_", " "),
                **({"priority": priorities[check_id]} if check_id in priorities else {}),
                "required": check_id not in optional,
                "result": result,
                "evidence": evidence_by_id.get(check_id, []),
                "owner": None,
                "trigger": None,
                "confirmed_by": "user" if check_id in confirmed else None,
            }
        )

    project_raw = paths.get("project_root")
    if not project_raw:
        return emit({"status": "FAIL", "error": "the run request recorded no project_root"}, 1)
    project = Path(project_raw).expanduser().resolve(strict=False)

    provenance: dict[str, Any]
    if workflow == "CONVERT_FRESH":
        source = paths.get("v1_source")
        if not source or not Path(source).is_dir():
            return emit({"status": "FAIL", "error": "the run request recorded no existing v1_source"}, 1)
        try:
            source_sha256 = compute_project_hash(Path(source))[0]
        except (OSError, HashError) as exc:
            return emit({"status": "FAIL", "reason_code": "REVIEW.PROJECT_HASH_FAILED", "error": f"cannot hash the V1 source: {exc}"}, 1)
        provenance = {"type": "V1_SOURCE", "path": source, "manifest": None, "sha256": source_sha256, "commit": None}
    elif workflow == "CREATE_FRESH":
        spec = paths.get("extension_spec") or str(run_root / "extension-spec.json")
        if not spec or not Path(spec).is_file():
            return emit({"status": "FAIL", "error": "the run request recorded no existing extension_spec"}, 1)
        provenance = {"type": "EXTENSION_SPEC", "path": spec, "manifest": None, "sha256": file_sha256(Path(spec)), "commit": None}
    elif workflow == "UPGRADE_EXISTING":
        baseline_path = run_root / "upgrade-baseline.json"
        if not baseline_path.is_file():
            return emit({"status": "FAIL", "error": "upgrade baseline is missing; do not reconstruct it from modified content"}, 1)
        baseline = read_object(baseline_path)
        provenance = {"type": "EXISTING_V2", "path": str(project), "manifest": str(baseline_path), "sha256": baseline["sha256"], "commit": None}
    elif workflow == "REVIEW_EXISTING":
        upstream = None
        for producer in ("CONVERT_FRESH", "CREATE_FRESH", "UPGRADE_EXISTING"):
            producer_handoff = run_root / "handoffs" / f"{producer}.json"
            if producer_handoff.is_file():
                upstream = load_handoff(producer_handoff).get("input_provenance")
                break
        if upstream:
            provenance = upstream
        else:
            try:
                existing_sha256 = compute_project_hash(project)[0]
            except (OSError, HashError) as exc:
                return emit({"status": "FAIL", "reason_code": "REVIEW.PROJECT_HASH_FAILED", "error": f"cannot hash the project (was the leaf executed?): {exc}"}, 1)
            provenance = {"type": "EXISTING_V2", "path": str(project), "manifest": None, "sha256": existing_sha256, "commit": None}
    else:  # Publication can run without a separate review.
        upstream = build_context(work_root, request, run).get("review_handoff")
        if upstream:
            upstream_path = Path(upstream)
            if not upstream_path.is_file():
                return emit({"status": "FAIL", "reason_code": "INPUT.INVALID_HANDOFF", "error": "upstream handoff is missing"}, 1)
            provenance = {"type": "PRODUCER_HANDOFF", "path": str(upstream_path), "manifest": None, "sha256": file_sha256(upstream_path), "commit": None}
        else:
            provenance = {"type": "EXISTING_V2", "path": str(project), "manifest": None, "sha256": compute_project_hash(project)[0], "commit": None}

    try:
        project_sha256 = compute_project_hash(project)[0]
    except (OSError, HashError) as exc:
        return emit(
            {
                "status": "FAIL",
                "reason_code": "REVIEW.PROJECT_HASH_FAILED",
                "error": f"cannot hash the project (was the leaf executed?): {exc}",
            },
            1,
        )

    workflows = run.get("workflows") or []
    index = workflows.index(workflow) if workflow in workflows else -1
    next_entries = (
        [{"workflow": workflows[index + 1], "condition": NEXT_CONDITIONS.get(workflows[index + 1], "")}]
        if 0 <= index < len(workflows) - 1
        else []
    )
    run_authorizations = run.get("authorizations") if isinstance(run.get("authorizations"), dict) else {}
    authorizations = {field: run_authorizations.get(field) is True for field in AUTHORIZATION_FIELDS}

    artifacts = []
    for kind, path_text in parse_pairs(args.artifact, "artifact", errors):
        artifacts.append({"kind": kind, "path": str(Path(path_text).expanduser().resolve(strict=False)), "sha256": None})
    if errors:
        return emit({"status": "FAIL", "errors": errors}, 1)

    state = args.state.strip().upper() if args.state else ("TERMINAL" if status in {"PASS", "FAIL"} else "WAITING_USER")
    handoff = {
        "schema_version": "mindplus-agent.handoff/v1",
        "run_id": f"{run.get('run_id')}:{workflow}",
        "parent_run_id": str(run.get("run_id")),
        "workflow": workflow,
        "producer": WORKFLOW_PRODUCER[workflow],
        "state": state,
        "status": status,
        "outcome": args.outcome.strip(),
        "reason_code": args.reason_code.strip() if args.reason_code else None,
        "input_provenance": provenance,
        "project_root": str(project),
        "project_sha256": project_sha256,
        "artifacts": artifacts,
        "checks": checks,
        "authorizations": authorizations,
        "next": next_entries,
    }

    required_outcome = "REVIEWED_HOST_READY" if workflow == "REVIEW_EXISTING" and status == "PASS" and request.get("review_profile") == "HOST_READY" else None
    validation_errors = validate_handoff_data(handoff, required_outcome, True)
    if validation_errors:
        return emit(
            {
                "status": "FAIL",
                "reason_code": "INPUT.INVALID_HANDOFF",
                "errors": validation_errors,
                "next_command": "Fix each listed field and rerun the same mpa.py handoff command.",
            },
            1,
        )

    handoff_path = run_root / "handoffs" / f"{workflow}.json"
    with handoff_path.open("w", encoding="utf-8", newline="\n") as output_handle:
        output_handle.write(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n")
    mpa = Path(__file__).resolve().as_posix()
    return emit(
        {
            "status": "PASS",
            "handoff_path": handoff_path.as_posix(),
            "workflow": workflow,
            "state": state,
            "status_outcome": args.outcome.strip(),
            "next_command": f"python {quote(mpa)} transition --work-root {quote(work_root.as_posix())} --run-id {quote(args.run_id)}",
        },
        0,
    )


# ---------------------------------------------------------------------------
# transition


def cmd_transition(args: argparse.Namespace) -> int:
    work_root = args.work_root.expanduser().resolve(strict=False)
    try:
        run, run_root = load_run(work_root, args.run_id)
    except RunError as exc:
        return emit({"status": "FAIL", "error": str(exc)}, 2)

    if run.get("state") == "TERMINAL":
        return emit(
            {
                "status": "PASS",
                "message": "run is already complete",
                "run_root": str(run_root),
                "next_command": None,
            },
            0,
        )

    workflows = run.get("workflows") or []
    current = run.get("current_workflow")
    handoff_path = run_root / "handoffs" / f"{current}.json"
    if not handoff_path.is_file():
        return emit(
            {
                "status": "FAIL",
                "reason_code": "TRANSITION.NO_HANDOFF",
                "error": f"current workflow {current} has no handoff; execute the leaf first",
                "next_command": next_command_for(current, build_context(work_root, read_request(run_root), run)),
            },
            1,
        )

    handoff = load_handoff(handoff_path)
    required_outcome = "REVIEWED_HOST_READY" if current == "REVIEW_EXISTING" and handoff.get("status") == "PASS" and read_request(run_root).get("review_profile") == "HOST_READY" else None
    errors = validate_handoff_data(handoff, required_outcome, True)
    if errors:
        return emit(
            {
                "status": "FAIL",
                "reason_code": "TRANSITION.INVALID_HANDOFF",
                "errors": errors,
                "next_command": f"Rerun the affected checks in {current}, then record a valid handoff.",
            },
            1,
        )

    mpa = Path(__file__).resolve().as_posix()
    if handoff.get("state") == "WAITING_USER":
        return emit(
            {
                "status": "WAITING_USER",
                "reason_code": handoff.get("reason_code"),
                "message": f"{current} is waiting on the user: {handoff.get('outcome')}",
                "next_command": "Resolve the recorded user action, rerun the affected checks, then record the new result for this workflow.",
            },
            3,
        )
    if handoff.get("status") != "PASS":
        return emit(
            {
                "status": "FAIL",
                "reason_code": "TRANSITION.PRODUCER_NOT_PASSING",
                "errors": [f"{current} handoff status is {handoff.get('status')} / {handoff.get('outcome')}"],
                "next_command": "Resolve the finding, rerun the affected checks or requested review, then record the new result. Do not mark stale evidence PASS.",
            },
            1,
        )

    if current not in workflows:
        return emit(
            {
                "status": "FAIL",
                "reason_code": "TRANSITION.CURRENT_NOT_IN_WORKFLOWS",
                "errors": [f"current_workflow {current!r} is not one of the routed workflows {workflows}"],
            },
            1,
        )

    index = workflows.index(current)
    if index == len(workflows) - 1:
        run["state"] = "TERMINAL"
        run["status"] = "PASS"
        with (run_root / "run.json").open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
        handoff_names = [p.name for p in sorted((run_root / "handoffs").glob("*.json"))]
        keep_evidence = bool(getattr(args, "keep_evidence", False)) or bool(run.get("keep_evidence"))
        evidence_cleaned = False
        if not keep_evidence:
            # Records are retained only on explicit request; successful runs clean up.
            cleanup_run_dir(run_root)
            evidence_cleaned = True
        return emit(
            {
                "status": "PASS",
                "message": "run complete" + ("" if keep_evidence else "; run evidence cleaned (--keep-evidence retains it)"),
                "run_root": None if evidence_cleaned else str(run_root),
                "evidence_cleaned": evidence_cleaned,
                "project_root": handoff.get("project_root"),
                "handoffs": handoff_names,
                "external_actions_performed": ["push"] if handoff.get("outcome") == "PUSHED" else [],
                "next_command": None,
            },
            0,
        )

    next_workflow = workflows[index + 1]
    registry = read_route_json(REGISTRY_PATH)
    if next_workflow not in registry["workflows"][current]["allowed_next"]:
        return emit({"status": "FAIL", "reason_code": "TRANSITION.NOT_ALLOWED", "error": "transition is not registered"}, 1)
    if next_workflow == "PUBLISH_GITEE":
        profile = read_request(run_root).get("review_profile", "BASIC")
        gate_errors = validate_handoff_data(handoff, "REVIEWED_HOST_READY" if profile == "HOST_READY" else None, True)
        if gate_errors:
            return emit({"status": "FAIL", "reason_code": "REVIEW.HANDOFF_INVALID", "errors": gate_errors,
                         "next_command": "Rerun the requested checks and write a current handoff."}, 1)
        project = Path(handoff.get("project_root", "")).expanduser()
        try:
            fresh_hash = compute_project_hash(project)[0]
        except (OSError, HashError) as exc:
            return emit({"status": "FAIL", "reason_code": "REVIEW.PROJECT_HASH_FAILED", "errors": [str(exc)]}, 1)
        if fresh_hash != handoff.get("project_sha256"):
            return emit(
                {
                    "status": "FAIL",
                    "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF",
                    "errors": ["The project changed after the recorded checks; refresh the affected checks."],
                    "next_command": "Rerun the affected checks in the current leaf and write a new handoff.",
                },
                1,
            )
        handoff_auth = handoff.get("authorizations", {})
        if not (handoff_auth.get("commit") is True and handoff_auth.get("push") is True):
            return emit(
                {
                    "status": "WAITING_USER",
                    "reason_code": "AUTH.PUSH_NOT_AUTHORIZED",
                    "errors": ["The review handoff does not carry commit+push authorization."],
                    "next_command": "Restart from an authorized mpa.py start request with --auth commit --auth push.",
                },
                3,
            )

    run["current_workflow"] = next_workflow
    with (run_root / "run.json").open("w", encoding="utf-8", newline="\n") as output_handle:
        output_handle.write(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    ctx = build_context(work_root, read_request(run_root), run)
    return emit(
        {
            "status": "PASS",
            "advanced_to": next_workflow,
            "leaf_reference": leaf_reference(next_workflow),
            "next_command": next_command_for(next_workflow, ctx),
        },
        0,
    )


# ---------------------------------------------------------------------------
# clean


def cmd_clean(args: argparse.Namespace) -> int:
    work_root = args.work_root.expanduser().resolve(strict=False)
    mpa = Path(__file__).resolve().as_posix()
    report: list[dict[str, Any]] = []

    runs_root = work_root / ".mindplus-agent" / "runs"
    run_ids = [args.run_id] if args.run_id else (
        [p.parent.name for p in runs_root.glob("*/run.json")] if not args.run_id and args.all else []
    )
    for run_id in run_ids:
        run_root = runs_root / run_id
        if not run_root.is_dir():
            report.append({"run_id": run_id, "removed": False, "note": "not found"})
            continue
        state = "UNKNOWN"
        run_file = run_root / "run.json"
        if run_file.is_file():
            try:
                state = read_object(run_file).get("state", "UNKNOWN")
            except RunError:
                pass
        if state != "TERMINAL" and not args.force:
            report.append({"run_id": run_id, "removed": False, "note": f"state is {state}; use --force to remove anyway"})
            continue
        cleanup_run_dir(run_root)
        report.append({"run_id": run_id, "removed": True, "note": f"state was {state}"})

    ms_root = work_root / ".ms"
    if args.all and ms_root.is_dir():
        for run_dir in sorted(ms_root.iterdir()):
            if not run_dir.is_dir():
                continue
            log = run_dir / "log.md"
            status_text = ""
            if log.is_file():
                for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("- status:"):
                        status_text = line.split(":", 1)[1].strip()
                        break
            if "RUNNING" in status_text and not args.force:
                report.append({"run_id": f".ms/{run_dir.name}", "removed": False, "note": f"switch log is {status_text}; use --force"})
                continue
            cleanup_run_dir(run_dir)
            report.append({"run_id": f".ms/{run_dir.name}", "removed": True, "note": f"switch log was {status_text or 'unknown'}"})
    elif args.run_id and not run_ids and ms_root.is_dir():
        report.append({"run_id": args.run_id, "removed": False, "note": "use resume to list parent runs; .ms run ids differ"})

    removed = sum(1 for item in report if item["removed"])
    skipped = len(report) - removed
    return emit(
        {
            "status": "PASS",
            "removed": removed,
            "skipped": skipped,
            "report": report,
            "next_command": None if removed or not report else f"python {quote(mpa)} clean --work-root {quote(work_root.as_posix())} --all --force to override",
        },
        0,
    )


# ---------------------------------------------------------------------------


def cmd_resume(args: argparse.Namespace) -> int:
    work_root = args.work_root.expanduser().resolve(strict=False)
    runs_root = work_root / ".mindplus-agent" / "runs"
    mpa = Path(__file__).resolve().as_posix()

    if not args.run_id:
        runs = []
        if runs_root.is_dir():
            for run_file in sorted(runs_root.glob("*/run.json")):
                try:
                    record = read_object(run_file)
                except RunError:
                    continue
                runs.append(
                    {
                        "run_id": record.get("run_id"),
                        "state": record.get("state"),
                        "current_workflow": record.get("current_workflow"),
                        "workflows": record.get("workflows"),
                    }
                )
        return emit({"status": "PASS", "runs": runs, "next_command": f"python {quote(mpa)} resume --work-root {quote(work_root.as_posix())} --run-id <id>" if runs else None}, 0)

    try:
        run, run_root = load_run(work_root, args.run_id)
    except RunError as exc:
        return emit({"status": "FAIL", "error": str(exc)}, 2)

    workflows = run.get("workflows") or []
    summaries = []
    for workflow in workflows:
        handoff_path = run_root / "handoffs" / f"{workflow}.json"
        if handoff_path.is_file():
            record = load_handoff(handoff_path)
            summaries.append({"workflow": workflow, "handoff": True, "state": record.get("state"), "status": record.get("status"), "outcome": record.get("outcome")})
        else:
            summaries.append({"workflow": workflow, "handoff": False})

    current = run.get("current_workflow")
    if run.get("state") == "TERMINAL":
        next_command = None
    elif not (run_root / "handoffs" / f"{current}.json").is_file():
        next_command = next_command_for(current, build_context(work_root, read_request(run_root), run))
    else:
        next_command = f"python {quote(mpa)} transition --work-root {quote(work_root.as_posix())} --run-id {quote(args.run_id)}"

    return emit(
        {
            "status": "PASS",
            "run_id": run.get("run_id"),
            "run_root": str(run_root),
            "state": run.get("state"),
            "current_workflow": current,
            "workflows": summaries,
            "next_command": next_command,
        },
        0,
    )


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="route a request and open a parent run")
    start.add_argument("--goals", required=True, help="comma-separated: CONVERT, CREATE, UPGRADE, REVIEW, PUBLISH")
    start.add_argument("--project-root", required=True, type=Path)
    start.add_argument("--v1-source", type=Path)
    start.add_argument("--extension-spec", type=Path)
    start.add_argument("--review-handoff", type=Path, help="optional prior evidence for direct publication")
    start.add_argument("--review-profile", choices=["BASIC", "HOST_READY"], default="BASIC", help="HOST_READY explicitly adds full Mind+ acceptance; BASIC is the default")
    start.add_argument("--work-root", required=True, type=Path)
    start.add_argument("--run-id")
    start.add_argument("--auth", action="append", help="authorization to grant; repeatable")
    start.add_argument("--keep-evidence", action="store_true", help="retain the run directory after the run completes (default: cleaned on success)")
    start.set_defaults(handler=cmd_start)

    handoff = subparsers.add_parser("handoff", help="assemble and validate the current workflow's handoff")
    handoff.add_argument("--work-root", required=True, type=Path)
    handoff.add_argument("--run-id", required=True)
    handoff.add_argument("--workflow", required=True)
    handoff.add_argument("--status", required=True, help="PASS, FAIL, or BLOCKED")
    handoff.add_argument("--outcome", required=True)
    handoff.add_argument("--reason-code")
    handoff.add_argument("--state", help="override the derived state (RUNNING, WAITING_USER, TERMINAL)")
    handoff.add_argument("--check", action="append", help="check result as id=RESULT; repeatable")
    handoff.add_argument("--evidence", action="append", help="evidence paths as id=path[,path]; repeatable")
    handoff.add_argument("--confirmed", action="append", help="check id confirmed by the user; repeatable")
    handoff.add_argument("--optional", action="append", help="check id to mark not required; repeatable")
    handoff.add_argument("--artifact", action="append", help="artifact as kind=path; repeatable")
    handoff.add_argument("--priority", action="append", help="check_id=P0|P1|P2; P1/P2 are advisory, P0 cannot be optional")
    handoff.set_defaults(handler=cmd_handoff)

    transition = subparsers.add_parser("transition", help="validate the current handoff and advance the run")
    transition.add_argument("--work-root", required=True, type=Path)
    transition.add_argument("--run-id", required=True)
    transition.add_argument("--keep-evidence", action="store_true", help="retain the run directory even on completion")
    transition.set_defaults(handler=cmd_transition)

    resume = subparsers.add_parser("resume", help="report run position after an interruption")
    resume.add_argument("--work-root", required=True, type=Path)
    resume.add_argument("--run-id")
    resume.set_defaults(handler=cmd_resume)

    clean = subparsers.add_parser("clean", help="remove finished run records (skips RUNNING unless --force)")
    clean.add_argument("--work-root", required=True, type=Path)
    clean.add_argument("--run-id", help="remove this parent run only")
    clean.add_argument("--all", action="store_true", help="remove all finished parent runs and .ms conversion records")
    clean.add_argument("--force", action="store_true", help="also remove runs that are not TERMINAL")
    clean.set_defaults(handler=cmd_clean)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
