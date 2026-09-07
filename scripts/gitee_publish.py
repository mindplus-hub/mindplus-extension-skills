#!/usr/bin/env python3
"""Deterministic Gitee publication stages: PLAN -> COMMIT -> REMOTE -> PUSH(+VERIFY).

Implements the PUBLISH_GITEE leaf contract. Every stage requires a passing
prepare_gitee_publish.py preflight output and re-checks the token, the handoff
authorizations, and the reviewed project hash before acting. The token reaches
git only through a process-local GIT_ASKPASS shim fed by environment variables
(HTTPS transport) or through SSH with BatchMode options (--ssh transport);
it never enters URLs, arguments, logs, or files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from check_gitee_token import resolve_token
from validate_handoff import validate as validate_handoff
from hash_project import IGNORED_DIRECTORIES, HashError, compute_project_hash

SKILL_ROOT = Path(__file__).resolve().parent.parent
API_BASE = "https://gitee.com/api/v5"
USER_AGENT = "mindplus-agent-skill/publication"
TIMEOUT = 30
PUBLISH_IGNORED_DIRECTORIES = IGNORED_DIRECTORIES | {".vscode", ".idea", "dist"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".zip", ".7z", ".rar", ".mp3", ".wav", ".mp4", ".ttf", ".woff", ".woff2", ".eot", ".pdf", ".mpext", ".exe", ".dll"}
MAX_SCAN_BYTES = 1_000_000
SECRET_PATTERNS = [
    ("private_key_block", r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ("credential_assignment", r"(?i)\b(gitee_token|gitee_access_token|api[_-]?key|apikey|secret|passwd|password)\b\s*[=:]\s*['\"][^'\"\s]{8,}"),
    ("authorization_header", r"(?i)authorization\s*:\s*(basic|token|bearer)\s+[A-Za-z0-9._\-]{8,}"),
]


class StageBlocked(RuntimeError):
    def __init__(self, payload: dict[str, Any], code: int = 2):
        super().__init__(payload.get("reason_code") or payload.get("error") or "blocked")
        self.payload = payload
        self.code = code


def emit(value: dict[str, Any], code: int) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.PREFLIGHT_INVALID", "error": f"cannot read {path}: {exc}"})
    if not isinstance(value, dict):
        raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.PREFLIGHT_INVALID", "error": f"{path} is not an object"})
    return value


def write_state(state_dir: Path, name: str, value: dict[str, Any]) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / name
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]


def is_ssh_url(url: str) -> bool:
    return url.startswith("git@") or url.startswith("ssh://")


def write_askpass_shim(state_dir: Path) -> Path:
    """Write a process-local askpass shim that answers from the environment only.

    A credential.helper spec like `python <path>` is misread by git as the
    `git-credential-python` subcommand (first word without a slash), which broke
    the previous bridge and fell back to the GUI askpass dialog. The shim is
    addressed by absolute path so git executes it directly; it contains no
    secret (both values come from the child-process environment).
    """
    if os.name == "nt":
        shim = state_dir / "askpass.cmd"
        shim.write_text(
            '@echo off\n'
            'echo %~1 | findstr /C:"assword" >nul && (echo %GITEE_TOKEN%) || (echo %GITEE_AUTH_USER%)\n',
            encoding="ascii", newline="\r\n",
        )
    else:
        shim = state_dir / "askpass.sh"
        shim.write_text(
            '#!/bin/sh\ncase "$1" in *assword*) printf \'%s\\n\' "$GITEE_TOKEN" ;; '
            '*) printf \'%s\\n\' "$GITEE_AUTH_USER" ;; esac\n',
            encoding="utf-8", newline="\n",
        )
        shim.chmod(0o755)
    return shim


def probe_ssh() -> tuple[bool, str]:
    """Non-interactive SSH authentication probe against gitee.com."""
    try:
        result = subprocess.run(
            ["ssh", *SSH_OPTIONS, "-T", "git@gitee.com"],
            text=True, capture_output=True, check=False, timeout=30,
        )
    except FileNotFoundError:
        return False, "ssh client not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "ssh probe timed out (the key may need a passphrase or is not registered with Gitee)"
    combined = (result.stdout + result.stderr).strip()
    # Gitee's greeting colorizes words ("successfully" is green), so ANSI SGR
    # sequences sit between the words of the success marker. Strip them first.
    plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", combined)
    if "successfully authenticated" in plain:
        return True, plain[:200]
    return False, (plain or f"ssh exited with {result.returncode}")[:300]


def auth_environment(remote_record: dict[str, Any], token: str, state_dir: Path) -> dict[str, str]:
    """Git environment for fetch/push over the recorded transport (ssh or https)."""
    url = str(remote_record.get("clone_url", ""))
    if remote_record.get("transport") == "ssh" or is_ssh_url(url):
        return {"GIT_SSH_COMMAND": "ssh " + " ".join(SSH_OPTIONS)}
    shim = write_askpass_shim(state_dir)
    return {
        "GIT_ASKPASS": str(shim),
        "GITEE_TOKEN": token,
        "GITEE_AUTH_USER": str(remote_record.get("auth_user") or ""),
    }


def decide_create_privacy(create: bool, public: bool) -> tuple[bool, bool]:
    """Return (initial_private, promote_public_after_push).

    Gitee refuses to create an empty public repository (HTTP 422), so a
    requested-public repository is created private and promoted after the
    push is verified — a failed publish then never leaves a public repo.
    """
    if not create:
        return False, False
    return True, public


def select_transport(mode: str, ssh_ok: bool) -> tuple[str, str | None]:
    """Return (transport, fallback_reason) for mode auto|ssh|https.

    Default (auto) prefers SSH push and falls back to HTTPS+token with the
    reason recorded; "ssh" is strict (the caller stops on probe failure);
    "https" skips probing entirely.
    """
    if mode == "https":
        return "https", None
    if ssh_ok:
        return "ssh", None
    if mode == "auto":
        return "https", "SSH probe failed; fell back to HTTPS+token"
    return "ssh", None


def git(project: Path, *arguments: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        environment.update(env_extra)
    return subprocess.run(
        ["git", "-c", f"safe.directory={project.as_posix()}", "-C", str(project), *arguments],
        text=True, capture_output=True, check=False, env=environment,
    )


def gitee_api(method: str, path: str, token: str, params: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"token {token}", "Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        # Gitee v5 only parses a JSON body when the JSON content type is declared;
        # without it the request is read as an empty form and fields are "missing".
        headers["Content-Type"] = "application/json;charset=UTF-8"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise StageBlocked({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.NETWORK", "error": f"Gitee request failed: {exc}"})


def context(args: argparse.Namespace, need_authorizations: tuple[str, ...] = ()) -> dict[str, Any]:
    state_dir = args.state_dir.expanduser().resolve(strict=False)
    token_source, token = resolve_token()
    if not token_source:
        raise StageBlocked(
            {
                "status": "WAITING_USER", "state": "WAITING_USER", "reason_code": "AUTH.GITEE_TOKEN_MISSING",
                "message": "Expose a Gitee personal access token locally as GITEE_TOKEN or GITEE_ACCESS_TOKEN, or as a single-line file ~/.gitee-token, then rerun. Nothing was read or modified.",
                "application_url": "https://gitee.com/profile/personal_access_tokens",
            },
            3,
        )
    preflight_path = args.preflight.expanduser().resolve(strict=False)
    preflight = read_json(preflight_path)
    if preflight.get("status") != "PASS" or preflight.get("outcome") != "PUBLISH_PREPARE_READY":
        raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.PREFLIGHT_INVALID", "error": f"{preflight_path} is not a passing publication preflight"})

    handoff = read_json(Path(preflight["review_handoff"])) if preflight.get("review_handoff") else {}
    if handoff:
        errors = validate_handoff(handoff, "REVIEWED_HOST_READY" if preflight.get("require_host_ready") else None, True)
        if handoff.get("status") != "PASS" or handoff.get("state") != "TERMINAL" or handoff.get("workflow") not in {"CONVERT_FRESH", "CREATE_FRESH", "REVIEW_EXISTING"}:
            errors.append("upstream handoff is not a passing producer or review")
        if handoff.get("project_sha256") != preflight.get("project_sha256") or Path(handoff.get("project_root", "")).resolve() != Path(preflight["project_root"]).resolve():
            errors.append("upstream evidence no longer matches the publication snapshot")
        if errors:
            raise StageBlocked({"status": "BLOCKED", "reason_code": "REVIEW.HANDOFF_INVALID", "errors": errors})
    elif preflight.get("require_host_ready"):
        raise StageBlocked({"status": "BLOCKED", "reason_code": "REVIEW.HOST_READY_HANDOFF_INVALID", "error": "HOST_READY evidence is missing"})
    authorizations = preflight.get("authorizations", handoff.get("authorizations", {}))
    missing = [name for name in need_authorizations if authorizations.get(name) is not True]
    if missing:
        raise StageBlocked(
            {
                "status": "WAITING_USER", "state": "WAITING_USER",
                "reason_code": "AUTH." + "_".join(name.upper() for name in missing) + "_NOT_AUTHORIZED",
                "message": f"The publication request does not authorize: {', '.join(missing)}. Restart from an authorized route request; do not edit the handoff.",
            },
            3,
        )

    project = Path(preflight["project_root"]).expanduser().resolve(strict=False)
    try:
        fresh_hash = compute_project_hash(project)[0]
    except (OSError, HashError) as exc:
        raise StageBlocked({"status": "BLOCKED", "reason_code": "REVIEW.PROJECT_HASH_FAILED", "error": str(exc)})
    if fresh_hash != preflight.get("project_sha256"):
        raise StageBlocked(
            {
                "status": "BLOCKED", "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF",
                "error": "The project changed after publication preflight; refresh the affected checks and publication plan.",
            }
        )
    return {
        "state_dir": state_dir, "token": token, "token_source": token_source, "preflight": preflight,
        "preflight_path": preflight_path, "handoff": handoff, "project": project, "project_sha256": fresh_hash,
    }


def walk_manifest(project: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for root, directories, filenames in os.walk(project, topdown=True, followlinks=False):
        root_path = Path(root)
        directories[:] = sorted(d for d in directories if d not in PUBLISH_IGNORED_DIRECTORIES)
        for name in sorted(filenames):
            path = root_path / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(project).as_posix()
            entries.append({"path": relative, "size": path.stat().st_size})
    return entries


def scan_secrets(project: Path, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in manifest:
        path = project / entry["path"]
        if path.suffix.casefold() in BINARY_SUFFIXES or entry["size"] > MAX_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in re.finditer(pattern, text):
                findings.append(
                    {
                        "pattern": label,
                        "file": entry["path"],
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
    return findings


def load_stage(state_dir: Path, name: str) -> dict[str, Any]:
    path = state_dir / name
    if not path.is_file():
        raise StageBlocked(
            {
                "status": "BLOCKED", "reason_code": "INPUT.STAGE_STATE_MISSING",
                "error": f"{path} not found; run the earlier stage first",
            }
        )
    record = read_json(path)
    if record.get("status") != "PASS":
        raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.STAGE_STATE_MISSING", "error": f"{path} is not a passing stage record"})
    return record


def manifest_paths(project: Path) -> list[str]:
    return [entry["path"] for entry in walk_manifest(project)]


def drift_check(project: Path, plan: dict[str, Any]) -> None:
    current = manifest_paths(project)
    planned = [entry["path"] for entry in plan.get("manifest", [])]
    if sorted(current) != sorted(planned):
        raise StageBlocked(
            {
                "status": "BLOCKED", "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF",
                "error": "Project file set changed after the plan was written; rerun the plan stage (and review if content changed).",
            }
        )


# --------------------------------------------------------------------------- plan


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        ctx = context(args)
    except StageBlocked as blocked:
        return emit(blocked.payload, blocked.code)

    manifest = walk_manifest(ctx["project"])
    findings = scan_secrets(ctx["project"], manifest)
    tracked = git(ctx["project"], "ls-tree", "-r", "--name-only", "-z", "HEAD")
    deleted_paths = sorted(
        path for path in tracked.stdout.split("\0")
        if path and not (ctx["project"] / path).exists()
        and not any(part in PUBLISH_IGNORED_DIRECTORIES for part in Path(path).parts)
    )
    plan = {
        "deleted_paths": deleted_paths,
        "schema_version": 1,
        "stage": "plan",
        "status": "PASS" if not findings else "FAIL",
        "reason_code": None if not findings else "SECURITY.CREDENTIAL_MATERIAL_FOUND",
        "project_root": str(ctx["project"]),
        "project_sha256": ctx["project_sha256"],
        "reviewed_file_count": len(manifest),
        "reviewed_total_bytes": sum(entry["size"] for entry in manifest),
        "excluded_directories": sorted(PUBLISH_IGNORED_DIRECTORIES),
        "manifest": manifest,
        "secret_scan": {"scanned_patterns": [label for label, _ in SECRET_PATTERNS], "findings": findings},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = write_state(ctx["state_dir"], "publish-plan.json", plan)
    return emit(
        {
            "status": plan["status"],
            "reason_code": plan["reason_code"],
            "plan_file": str(path),
            "reviewed_file_count": len(manifest),
            "secret_findings": findings,
            "message": "Review the manifest; every listed path belongs to the reviewed project hash.",
        },
        0 if plan["status"] == "PASS" else 2,
    )


# --------------------------------------------------------------------------- commit


def git_identity(project: Path) -> tuple[str | None, str | None]:
    name = git(project, "config", "user.name").stdout.strip() or None
    email = git(project, "config", "user.email").stdout.strip() or None
    return name, email


def cmd_commit(args: argparse.Namespace) -> int:
    try:
        ctx = context(args, need_authorizations=("commit",))
        plan = load_stage(ctx["state_dir"], "publish-plan.json")
        drift_check(ctx["project"], plan)
    except StageBlocked as blocked:
        return emit(blocked.payload, blocked.code)

    project = ctx["project"]
    probe = git(project, "rev-parse", "--is-inside-work-tree")
    initialized = probe.returncode == 0 and probe.stdout.strip().casefold() == "true"
    branch = args.branch
    if not initialized:
        branch = branch or "main"
        if git(project, "init", "-b", branch).returncode != 0:
            init = git(project, "init")
            if init.returncode != 0 or git(project, "checkout", "-b", branch).returncode != 0:
                return emit({"status": "BLOCKED", "reason_code": "GIT.INIT_FAILED", "errors": [init.stderr or "git init failed"]}, 2)
    else:
        current = git(project, "branch", "--show-current").stdout.strip()
        branch = branch or (current or "main")
        if current and args.branch and current != args.branch:
            return emit({"status": "BLOCKED", "reason_code": "INPUT.GITEE_TARGET_REQUIRED", "error": f"repo is on {current}, plan requested {args.branch}"}, 2)

    name, email = git_identity(project)
    if not name or not email:
        return emit(
            {
                "status": "WAITING_USER", "state": "WAITING_USER", "reason_code": "GIT.IDENTITY_REQUIRED",
                "message": "Git author identity is unavailable. Configure user.name/user.email or pass --author-name/--author-email (stored repo-locally only).",
            },
            3,
        )
    if args.author_name:
        git(project, "config", "user.name", args.author_name)
    if args.author_email:
        git(project, "config", "user.email", args.author_email)

    paths = [entry["path"] for entry in plan["manifest"]]
    deletions = plan.get("deleted_paths", [])
    existing_index = git(project, "ls-files", "-z")
    if existing_index.returncode:
        return emit({"status": "BLOCKED", "reason_code": "GIT.INSPECTION_FAILED", "error": "cannot read index paths"}, 2)
    indexed_paths = set(filter(None, existing_index.stdout.split("\0")))
    stage_paths = paths + [path for path in deletions if path in indexed_paths]
    for start in range(0, len(stage_paths), 100):
        chunk = stage_paths[start : start + 100]
        result = git(project, "--literal-pathspecs", "add", "-A", "--", *chunk)
        if result.returncode != 0:
            return emit({"status": "BLOCKED", "reason_code": "GIT.STAGE_FAILED", "errors": [result.stderr.strip() or "git add failed"]}, 2)

    staged = [path for path in git(project, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if path]
    outside = sorted(set(staged) - set(paths + deletions))
    if outside:
        return emit({"status": "BLOCKED", "reason_code": "GIT.PUBLICATION_SET_MISMATCH", "errors": [f"staged paths outside the reviewed manifest: {outside}"]}, 2)

    indexed = git(project, "ls-files", "-z")
    if indexed.returncode or set(filter(None, indexed.stdout.split("\0"))) != set(paths):
        return emit({"status": "BLOCKED", "reason_code": "GIT.PUBLICATION_SET_MISMATCH", "error": "index tree differs from the reviewed publication manifest"}, 2)
    approved_tree = git(project, "write-tree")
    if approved_tree.returncode:
        return emit({"status": "BLOCKED", "reason_code": "GIT.PUBLICATION_SET_MISMATCH", "error": "cannot capture the staged tree"}, 2)

    # Advisory only: reviewed third-party content is published verbatim, so
    # trailing-whitespace findings must not block (the session-verified escape
    # hatch was hand-editing git config, which this replaces).
    check = git(project, "diff", "--cached", "--check")
    whitespace_warnings = [line for line in (check.stdout or "").splitlines() if line.strip()][:50]

    after_hash = compute_project_hash(project)[0]
    if after_hash != ctx["project_sha256"]:
        return emit({"status": "BLOCKED", "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF", "error": "staging changed the project hash"}, 2)

    head = git(project, "rev-parse", "HEAD")
    reused = False
    if head.returncode != 0:
        commit = git(project, "commit", "-m", args.message)
        if commit.returncode != 0:
            return emit({"status": "BLOCKED", "reason_code": "GIT.COMMIT_FAILED", "errors": [commit.stderr.strip() or "git commit failed"]}, 2)
    elif git(project, "rev-parse", "HEAD^{tree}").stdout.strip() == approved_tree.stdout.strip():
        reused = True  # exact reviewed tree is already HEAD
    else:
        commit = git(project, "commit", "-m", args.message)
        if commit.returncode != 0:
            return emit({"status": "BLOCKED", "reason_code": "GIT.COMMIT_FAILED", "errors": [commit.stderr.strip() or "git commit failed"]}, 2)

    committed_tree = git(project, "rev-parse", "HEAD^{tree}")
    if committed_tree.returncode or committed_tree.stdout.strip() != approved_tree.stdout.strip():
        return emit({"status": "BLOCKED", "reason_code": "GIT.PUBLICATION_SET_MISMATCH", "error": "committed tree differs from the approved index; commit was created but publication must stop"}, 2)
    sha = git(project, "rev-parse", "HEAD").stdout.strip()
    record = {
        "schema_version": 1,
        "stage": "commit",
        "status": "PASS",
        "project_root": str(project),
        "branch": branch,
        "commit_sha": sha,
        "reused_existing_commit": reused,
        "staged_file_count": len(staged),
        "manifest_file_count": len(paths),
        "whitespace_check": "PASS" if check.returncode == 0 else "WARN",
        "whitespace_warnings": whitespace_warnings,
        "commit_message": args.message,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = write_state(ctx["state_dir"], "publish-commit.json", record)
    return emit(
        {
            "status": "PASS", "commit_sha": sha, "branch": branch,
            "reused_existing_commit": reused, "commit_file": str(path),
            "whitespace_check": record["whitespace_check"],
            "whitespace_warnings": whitespace_warnings,
        },
        0,
    )


# --------------------------------------------------------------------------- remote


def cmd_remote(args: argparse.Namespace) -> int:
    try:
        ctx = context(args, need_authorizations=("push",) + (("create_repository",) if args.create else ()))
        plan = load_stage(ctx["state_dir"], "publish-plan.json")
        commit_record = load_stage(ctx["state_dir"], "publish-commit.json")
        if args.create and not (args.private or args.public):
            raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.GITEE_TARGET_REQUIRED", "error": "--private or --public is required when creating a repository"})
        if args.create and args.description is None:
            raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.GITEE_TARGET_REQUIRED", "error": "--description is required when creating a repository (may be an explicit empty string)"})
        if not args.owner or not args.repo_name:
            raise StageBlocked({"status": "BLOCKED", "reason_code": "INPUT.GITEE_TARGET_REQUIRED", "error": "--owner and --repo-name are required; never infer them"})
    except StageBlocked as blocked:
        return emit(blocked.payload, blocked.code)

    project = ctx["project"]
    token = ctx["token"]
    owner = args.org or args.owner
    status, payload = gitee_api("GET", "/user", token)
    if status != 200 or not isinstance(payload, dict) or not payload.get("login"):
        return emit(
            {
                "status": "BLOCKED", "reason_code": "GITEE.AUTH_FAILED",
                "error": f"Gitee rejected the local token (HTTP {status}) while resolving the token account; no Git or remote change was made.",
            },
            2,
        )
    auth_user = str(payload["login"])

    mode = getattr(args, "transport", "auto")
    ssh_ok, ssh_detail = (False, "not probed")
    if mode in ("auto", "ssh"):
        ssh_ok, ssh_detail = probe_ssh()
        if mode == "ssh" and not ssh_ok:
            return emit(
                {
                    "state": "WAITING_USER", "status": "WAITING_USER",
                    "reason_code": "AUTH.SSH_KEY_NOT_USABLE",
                    "error": f"SSH authentication to gitee.com is not available non-interactively: {ssh_detail}",
                    "message": "Add your public key to the Gitee account (keys must be passphrase-free for non-interactive push), or rerun with --https to use the token transport.",
                },
                3,
            )
    transport, fallback_reason = select_transport(mode, ssh_ok)

    created = False
    initial_private, promote_after_push = decide_create_privacy(args.create, bool(args.public))
    if args.create:
        body = {"name": args.repo_name, "private": initial_private, "description": args.description or "", "auto_init": False}
        path = f"/orgs/{args.org}/repos" if args.org else "/user/repos"
        status, payload = gitee_api("POST", path, token, body=body)
        if status not in (200, 201):
            message = str(payload.get("message") or payload) if isinstance(payload, dict) else str(payload)
            reason = "GITEE.REPO_COLLISION" if "exist" in message.casefold() else "GITEE.CREATE_FAILED"
            return emit({"status": "BLOCKED", "reason_code": reason, "http_status": status, "error": message}, 2)
        created = True
    else:
        status, payload = gitee_api("GET", f"/repos/{owner}/{args.repo_name}", token)
        if status == 404:
            return emit({"status": "BLOCKED", "reason_code": "GITEE.REPO_NOT_FOUND", "error": f"{owner}/{args.repo_name} does not exist; use --create only if explicitly requested"}, 2)
        if status != 200 or not isinstance(payload, dict):
            return emit({"status": "BLOCKED", "reason_code": "GITEE.VERIFY_FAILED", "http_status": status, "error": "could not verify the existing repository"}, 2)

    full_name = str(payload.get("full_name") or f"{owner}/{args.repo_name}")
    html_url = str(payload.get("html_url") or f"https://gitee.com/{owner}/{args.repo_name}")
    private_flag = bool(payload.get("private"))
    clone_url = (
        f"git@gitee.com:{full_name}.git" if transport == "ssh"
        else f"https://gitee.com/{full_name}.git"
    )

    remote_name = args.remote_name
    existing_url = git(project, "remote", "get-url", remote_name)
    if existing_url.returncode != 0:
        added = git(project, "remote", "add", remote_name, clone_url)
        if added.returncode != 0:
            return emit({"status": "BLOCKED", "reason_code": "GIT.REMOTE_ADD_FAILED", "errors": [added.stderr.strip() or "git remote add failed"]}, 2)
    elif existing_url.stdout.strip() != clone_url:
        return emit(
            {
                "status": "BLOCKED", "reason_code": "GIT.REMOTE_MISMATCH",
                "error": f"remote {remote_name} already points to {existing_url.stdout.strip()}; changing it requires explicit user approval",
                "expected_url": clone_url,
            },
            2,
        )

    record = {
        "schema_version": 1,
        "stage": "remote",
        "status": "PASS",
        "created": created,
        "transport": transport,
        "transport_selection": {
            "mode": mode,
            "ssh_probe": ("pass" if ssh_ok else f"fail: {ssh_detail}"),
            "fallback_reason": fallback_reason,
        },
        "owner_or_org": owner,
        "repo_name": args.repo_name,
        "full_name": full_name,
        "private": private_flag,
        "clone_url": clone_url,
        "remote_name": remote_name,
        "branch": commit_record["branch"],
        "auth_user": auth_user,
        "requested_visibility": ("public" if args.public else "private") if args.create else None,
        "pending_visibility_promotion": promote_after_push,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = write_state(ctx["state_dir"], "publish-remote.json", record)
    return emit(
        {
            "status": "PASS", "created": created, "full_name": full_name,
            "private": private_flag, "clone_url": clone_url, "remote_file": str(path),
            "transport": transport, "fallback_reason": fallback_reason,
        },
        0,
    )


# --------------------------------------------------------------------------- push


def cmd_push(args: argparse.Namespace) -> int:
    try:
        ctx = context(args, need_authorizations=("push",))
        load_stage(ctx["state_dir"], "publish-plan.json")
        commit_record = load_stage(ctx["state_dir"], "publish-commit.json")
        remote_record = load_stage(ctx["state_dir"], "publish-remote.json")
        drift_check(ctx["project"], read_json(ctx["state_dir"] / "publish-plan.json"))
    except StageBlocked as blocked:
        return emit(blocked.payload, blocked.code)

    project = ctx["project"]
    token = ctx["token"]
    branch = commit_record["branch"]
    remote_name = remote_record["remote_name"]
    owner = remote_record["owner_or_org"]
    repo_name = remote_record["repo_name"]
    head = git(project, "rev-parse", "HEAD").stdout.strip()

    if remote_record.get("transport") == "ssh" or is_ssh_url(remote_record.get("clone_url", "")):
        ssh_ok, ssh_detail = probe_ssh()
        if not ssh_ok:
            return emit(
                {
                    "status": "BLOCKED", "reason_code": "AUTH.SSH_KEY_NOT_USABLE",
                    "errors": [f"SSH probe failed before push: {ssh_detail}"],
                },
                2,
            )
        auth_env = auth_environment(remote_record, token, ctx["state_dir"])
    else:
        auth_env = auth_environment(remote_record, token, ctx["state_dir"])

    status, payload = gitee_api("GET", f"/repos/{owner}/{repo_name}/branches/{branch}", token)
    already_current = False
    if status == 200 and isinstance(payload, dict):
        remote_sha = (payload.get("commit") or {}).get("sha")
        if remote_sha == head:
            already_current = True
        else:
            fetch = git(project, "fetch", remote_name, branch, env_extra=auth_env)
            if fetch.returncode != 0:
                return emit({"status": "BLOCKED", "reason_code": "GIT.FETCH_FAILED", "errors": [fetch.stderr.strip() or "git fetch failed"]}, 2)
            ancestor = git(project, "merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD")
            if ancestor.returncode != 0:
                return emit(
                    {
                        "status": "BLOCKED", "reason_code": "GIT.NON_FAST_FORWARD",
                        "error": "remote branch is not an ancestor of the reviewed commit; merging or forcing is outside this leaf",
                        "remote_sha": remote_sha, "local_sha": head,
                    },
                    2,
                )
    elif status != 404:
        return emit({"status": "BLOCKED", "reason_code": "GITEE.VERIFY_FAILED", "http_status": status, "error": "could not probe the remote branch"}, 2)

    if not already_current:
        push = git(project, "push", remote_name, f"{branch}:{branch}", env_extra=auth_env)
        if push.returncode != 0:
            combined = (push.stderr + push.stdout).casefold()
            if "non-fast-forward" in combined:
                reason = "GIT.NON_FAST_FORWARD"
            elif "403" in combined or "authentication" in combined or "denied" in combined or "access" in combined:
                reason = "GITEE.PUSH_AUTH_FAILED"
            else:
                reason = "GIT.PUSH_FAILED"
            return emit({"status": "BLOCKED", "reason_code": reason, "errors": [push.stderr.strip() or push.stdout.strip() or "git push failed"]}, 2)

    status, payload = gitee_api("GET", f"/repos/{owner}/{repo_name}/branches/{branch}", token)
    remote_sha = (payload.get("commit") or {}).get("sha") if isinstance(payload, dict) else None
    if status != 200 or remote_sha != head:
        return emit(
            {
                "status": "BLOCKED", "reason_code": "GITEE.VERIFY_FAILED",
                "error": f"remote ref does not match the approved local commit after push (HTTP {status}, remote {remote_sha}, local {head})",
            },
            2,
        )
    after_hash = compute_project_hash(project)[0]
    if after_hash != ctx["project_sha256"]:
        return emit({"status": "BLOCKED", "reason_code": "REVIEW.STALE_HOST_READY_HANDOFF", "error": "project hash changed during publication"}, 2)

    visibility_promotion = None
    if remote_record.get("pending_visibility_promotion"):
        try:
            status, payload = gitee_api("PATCH", f"/repos/{owner}/{repo_name}", token, body={"private": False})
        except StageBlocked:
            status, payload = None, {"message": "visibility request failed; verify repository visibility before resuming"}
        if status == 200 and isinstance(payload, dict) and payload.get("private") is False:
            visibility_promotion = {"status": "PROMOTED_TO_PUBLIC"}
        else:
            message = str(payload.get("message") or payload) if isinstance(payload, dict) else str(payload)
            visibility_promotion = {
                "status": "FAILED",
                "http_status": status,
                "error": f"public visibility was not confirmed; check it in the Gitee web UI ({message[:200]})",
            }

    visibility_failed = bool(visibility_promotion and visibility_promotion["status"] == "FAILED")
    record = {
        "schema_version": 1,
        "stage": "push",
        "status": "BLOCKED" if visibility_failed else "PASS",
        "outcome": "PUSHED_VISIBILITY_PENDING" if visibility_failed else "PUSHED",
        "reason_code": "GITEE.VISIBILITY_UPDATE_FAILED" if visibility_failed else None,
        "already_current": already_current,
        "branch": branch,
        "verified_remote_sha": remote_sha,
        "local_commit_sha": head,
        "clone_url": remote_record["clone_url"],
        "transport": remote_record.get("transport", "https"),
        "visibility_promotion": visibility_promotion,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = write_state(ctx["state_dir"], "publish-push.json", record)
    if visibility_failed:
        return emit({**record, "push_file": str(path), "next_command": None}, 2)
    mpa = SKILL_ROOT / "scripts" / "mpa.py"
    evidence = ctx["state_dir"]
    next_command = (
        f'python "{mpa.as_posix()}" handoff --work-root <work-root> --run-id <run-id> --workflow PUBLISH_GITEE '
        f'--status PASS --outcome PUSHED '
        f'--check publication_snapshot_current=PASS --evidence publication_snapshot_current="{ctx["preflight_path"]}" '
        f'--check publication_set_reviewed=PASS --evidence publication_set_reviewed="{evidence / "publish-plan.json"}" '
        f'--check git_commit=PASS --evidence git_commit="{evidence / "publish-commit.json"}" '
        f'--check gitee_repository=PASS --evidence gitee_repository="{evidence / "publish-remote.json"}" '
        f'--check remote_ref_verified=PASS --evidence remote_ref_verified="{evidence / "publish-push.json"}"'
    )
    return emit(
        {
            "status": "PASS", "outcome": "PUSHED", "already_current": already_current,
            "branch": branch, "verified_remote_sha": remote_sha, "push_file": str(path),
            "visibility_promotion": visibility_promotion,
            "next_command": next_command,
        },
        0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(stage: argparse.ArgumentParser) -> None:
        stage.add_argument("--preflight", required=True, type=Path, help="passing prepare_gitee_publish.py output")
        stage.add_argument("--state-dir", required=True, type=Path, help="publication evidence directory outside project_root")

    plan = subparsers.add_parser("plan", help="explicit file manifest + secret scan (read-only)")
    add_common(plan)
    plan.set_defaults(handler=cmd_plan)

    commit = subparsers.add_parser("commit", help="stage the manifest and create exactly one commit")
    add_common(commit)
    commit.add_argument("--message", required=True)
    commit.add_argument("--branch")
    commit.add_argument("--author-name")
    commit.add_argument("--author-email")
    commit.set_defaults(handler=cmd_commit)

    remote = subparsers.add_parser("remote", help="verify or create the named Gitee repository")
    add_common(remote)
    remote.add_argument("--owner", required=True)
    remote.add_argument("--repo-name", required=True)
    remote.add_argument("--org", help="create under this organization instead of the token account")
    remote.add_argument("--create", action="store_true")
    remote.add_argument("--private", action="store_true")
    remote.add_argument("--public", action="store_true")
    remote.add_argument("--description")
    remote.add_argument("--remote-name", default="origin")
    transport_group = remote.add_mutually_exclusive_group()
    transport_group.add_argument("--ssh", dest="transport", action="store_const", const="ssh", help="SSH transport strictly: probe failure stops instead of falling back")
    transport_group.add_argument("--https", dest="transport", action="store_const", const="https", help="HTTPS+token transport without SSH probing")
    remote.set_defaults(transport="auto")
    remote.set_defaults(handler=cmd_remote)

    push = subparsers.add_parser("push", help="push over the recorded transport and verify the remote ref")
    add_common(push)
    push.set_defaults(handler=cmd_push)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
