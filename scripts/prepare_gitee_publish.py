#!/usr/bin/env python3
"""Enforce token-first Gitee publication preflight without making mutations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from check_gitee_token import resolve_token
from hash_project import HashError, compute_project_hash
from validate_handoff import load as load_handoff
from validate_handoff import validate as validate_handoff


def emit(value: dict, output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = output.expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")


def git(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={project.as_posix()}", "-C", str(project), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--review-handoff", required=True, type=Path)
    parser.add_argument(
        "--create-repo",
        action="store_true",
        help="The publication will create a new Gitee repository; requires create_repository authorization.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    # This must remain the first gate. Do not resolve/read paths or invoke Git
    # before token presence has been established.
    token_source, _ = resolve_token()
    if not token_source:
        emit(
            {
                "state": "WAITING_USER",
                "status": "BLOCKED",
                "outcome": "TOKEN_REQUIRED",
                "reason_code": "AUTH.GITEE_TOKEN_MISSING",
                "token_present": False,
                "message": "Apply for a Gitee personal access token, expose it locally as GITEE_TOKEN or GITEE_ACCESS_TOKEN, or as a single-line file ~/.gitee-token, then resume. No project, Git, or Gitee operation was performed.",
                "application_url": "https://gitee.com/profile/personal_access_tokens",
            },
            args.output,
        )
        return 3

    project = args.project_root.expanduser().resolve(strict=False)
    handoff_path = args.review_handoff.expanduser().resolve(strict=False)
    try:
        handoff = load_handoff(handoff_path)
        errors = validate_handoff(handoff, "REVIEWED_HOST_READY", True)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "REVIEW.HOST_READY_HANDOFF_INVALID",
                "token_present": True,
                "token_source": token_source,
                "errors": errors,
            },
            args.output,
        )
        return 2

    handoff_authorizations = handoff.get("authorizations")
    if not isinstance(handoff_authorizations, dict):
        handoff_authorizations = {}
    unauthorized = [
        name for name in ("commit", "push") if handoff_authorizations.get(name) is not True
    ]
    if unauthorized:
        emit(
            {
                "state": "WAITING_USER",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "AUTH.PUSH_NOT_AUTHORIZED",
                "token_present": True,
                "token_source": token_source,
                "errors": [
                    f"The review handoff does not carry explicit authorization for: {', '.join(unauthorized)}.",
                    "Ask the user for commit and push authorization, then restart the run with the authorized request.",
                ],
            },
            args.output,
        )
        return 3
    if args.create_repo and handoff_authorizations.get("create_repository") is not True:
        emit(
            {
                "state": "WAITING_USER",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "AUTH.CREATE_REPOSITORY_NOT_AUTHORIZED",
                "token_present": True,
                "token_source": token_source,
                "errors": [
                    "Creating a new Gitee repository requires explicit create_repository authorization.",
                ],
            },
            args.output,
        )
        return 3

    handoff_project = Path(handoff["project_root"]).expanduser().resolve(strict=False)
    if handoff_project != project:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "REVIEW.PROJECT_MISMATCH",
                "token_present": True,
                "token_source": token_source,
                "errors": [f"handoff project {handoff_project} does not match requested project {project}"],
            },
            args.output,
        )
        return 2

    expected_hash = handoff.get("project_sha256")
    try:
        actual_hash, source_file_count = compute_project_hash(project)
    except (OSError, HashError) as exc:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "REVIEW.PROJECT_HASH_FAILED",
                "token_present": True,
                "token_source": token_source,
                "errors": [str(exc)],
            },
            args.output,
        )
        return 2
    if actual_hash != expected_hash:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF",
                "token_present": True,
                "token_source": token_source,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "errors": ["The project changed after HOST_READY review; run review again."],
            },
            args.output,
        )
        return 2

    try:
        probe = git(project, "rev-parse", "--is-inside-work-tree")
    except OSError as exc:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "PUBLISH_PRECHECK_FAILED",
                "reason_code": "GIT.UNAVAILABLE",
                "token_present": True,
                "token_source": token_source,
                "errors": [str(exc)],
            },
            args.output,
        )
        return 2

    if probe.returncode == 0 and probe.stdout.strip().casefold() == "true":
        branch = git(project, "branch", "--show-current")
        status = git(project, "status", "--porcelain=v1")
        remotes = git(project, "remote")
        if branch.returncode or status.returncode or remotes.returncode:
            errors = [item.strip() for item in (branch.stderr, status.stderr, remotes.stderr) if item.strip()]
            emit(
                {
                    "state": "TERMINAL",
                    "status": "BLOCKED",
                    "outcome": "PUBLISH_PRECHECK_FAILED",
                    "reason_code": "GIT.INSPECTION_FAILED",
                    "token_present": True,
                    "token_source": token_source,
                    "errors": errors or ["Git inspection failed without diagnostics."],
                },
                args.output,
            )
            return 2
        git_facts = {
            "state": "EXISTING_REPOSITORY",
            "branch": branch.stdout.strip() or None,
            "dirty": bool(status.stdout.strip()),
            "changed_entry_count": len([line for line in status.stdout.splitlines() if line.strip()]),
            "remote_names": [line.strip() for line in remotes.stdout.splitlines() if line.strip()],
        }
    else:
        git_facts = {
            "state": "NOT_INITIALIZED",
            "branch": None,
            "dirty": None,
            "changed_entry_count": None,
            "remote_names": [],
        }

    emit(
        {
            "state": "RUNNING",
            "status": "PASS",
            "outcome": "PUBLISH_PREPARE_READY",
            "reason_code": None,
            "token_present": True,
            "token_source": token_source,
            "project_root": str(project),
            "review_handoff": str(handoff_path),
            "project_sha256": actual_hash,
            "source_file_count": source_file_count,
            "git": git_facts,
            "message": "Token and HOST_READY handoff gates passed. Only read-only Git inspection was performed.",
        },
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
