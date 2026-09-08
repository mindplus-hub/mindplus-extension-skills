#!/usr/bin/env python3
"""Initialize a secret-free MindPlus Agent parent run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SECRET_KEY_PARTS = {"password", "secret", "cookie", "credential", "token"}


class RunError(RuntimeError):
    pass


def hide_path(path: Path) -> None:
    """Hide run-record directories on Windows so work roots stay uncluttered."""
    if os.name == "nt":
        subprocess.run(["attrib", "+h", str(path)], capture_output=True, check=False)


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RunError(f"cannot read {path}: {exc}") from exc


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_bytes(path).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunError(f"JSON root must be an object: {path}")
    return value


def find_secret_key(value: Any, prefix: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            if any(part in normalized for part in SECRET_KEY_PARTS):
                return f"{prefix}.{key}"
            found = find_secret_key(child, f"{prefix}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = find_secret_key(child, f"{prefix}[{index}]")
            if found:
                return found
    return None


def initialize_run(
    work_root: Path,
    request: dict[str, Any],
    route: dict[str, Any],
    run_id: str,
    *,
    request_path: Path | None = None,
    route_path: Path | None = None,
    allow_staging: bool = False,
    keep_evidence: bool = False,
) -> dict[str, Any]:
    """Create (or idempotently return) one parent run directory.

    Raises RunError on invalid input. An existing run.json makes the call
    idempotent: the recorded run is returned with status PASS_IDEMPOTENT and
    nothing is modified. allow_staging tolerates a pre-created run directory
    without run.json (the wizard entry stages request/route evidence files
    there before calling this function).
    """
    if not work_root.is_absolute() or not work_root.is_dir():
        raise RunError("work_root must be an existing absolute directory")
    secret_path = find_secret_key(request)
    if secret_path:
        raise RunError(f"route request contains a secret-like key at {secret_path}")
    if route.get("status") != "PASS" or route.get("state") != "RUNNING":
        raise RunError("route result must be RUNNING/PASS before a parent run is initialized")
    if not RUN_ID_RE.fullmatch(run_id):
        raise RunError("run_id contains unsafe characters")

    run_root = work_root / ".mindplus-agent" / "runs" / run_id
    run_file = run_root / "run.json"
    if run_root.exists():
        if run_file.is_file():
            try:
                existing = json.loads(run_file.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RunError(f"existing run is unreadable: {run_file}: {exc}") from exc
            return {
                "status": "PASS_IDEMPOTENT",
                "run_id": existing.get("run_id", run_id),
                "run_root": str(run_root),
                "run_file": str(run_file),
                "state": existing.get("state"),
                "current_workflow": existing.get("current_workflow"),
            }
        if not allow_staging:
            raise RunError(f"run directory exists without run.json: {run_root}")
    else:
        run_root.mkdir(parents=True)
    for name in ("handoffs", "evidence", "children"):
        (run_root / name).mkdir(exist_ok=True)

    if request_path is not None:
        request_sha256 = hashlib.sha256(request_path.read_bytes()).hexdigest()
    else:
        request_sha256 = hashlib.sha256(
            json.dumps(request, ensure_ascii=False, indent=2).encode("utf-8")
        ).hexdigest()

    run = {
        "schema_version": "mindplus-agent.run/v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "state": "RUNNING",
        "status": "NOT_RUN",
        "keep_evidence": keep_evidence,
        "request_sha256": request_sha256,
        "request_path": str(request_path) if request_path is not None else None,
        "route_result_path": str(route_path) if route_path is not None else None,
        "workflows": route.get("workflows", []),
        "current_workflow": route.get("workflows", [None])[0] if route.get("workflows") else None,
        "authorizations": request.get("authorizations", {}),
    }
    with run_file.open("w", encoding="utf-8", newline="\n") as output_handle:
        output_handle.write(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    hide_path(run_root.parent)
    hide_path(run_root)
    return {"status": "PASS", "run_id": run_id, "run_root": str(run_root), "run_file": str(run_file)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--route-result", required=True, type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    try:
        work_root = args.work_root.expanduser().resolve(strict=False)
        request_path = args.request.expanduser().resolve(strict=False)
        route_path = args.route_result.expanduser().resolve(strict=False)
        request = read_object(request_path)
        route = read_object(route_path)
        run_id = args.run_id or uuid.uuid4().hex
        output = initialize_run(
            work_root,
            request,
            route,
            run_id,
            request_path=request_path,
            route_path=route_path,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RunError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "WORKSPACE.RUN_INIT", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
