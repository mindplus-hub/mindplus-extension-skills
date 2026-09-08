#!/usr/bin/env python3
"""Check local Gitee token presence without printing or validating the secret value."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_ENV_NAMES = ("GITEE_TOKEN", "GITEE_ACCESS_TOKEN")
DEFAULT_TOKEN_FILE = Path.home() / ".gitee-token"
CREDENTIAL_HOST = "gitee.com"
CREDENTIAL_SOURCE = "windows-credential-manager:git:https://gitee.com"
CREDENTIAL_TIMEOUT_SECONDS = 10
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _valid_token(value: str) -> bool:
    return bool(value) and "\n" not in value and "\r" not in value and len(value) <= 256


def resolve_windows_credential() -> tuple[str | None, str]:
    """Read the Gitee PAT from Git Credential Manager on Windows.

    Git for Windows delegates this helper to Windows Credential Manager when
    ``credential.helper=manager`` is configured. The password is captured
    only in this process; it is never printed, written to a file, or put in a
    command argument. Non-Windows hosts deliberately return no result here.
    """
    if os.name != "nt":
        return None, ""
    request = f"protocol=https\nhost={CREDENTIAL_HOST}\n\n"
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    # Do not open a GUI/browser prompt while checking presence.
    environment["GCM_INTERACTIVE"] = "Never"
    try:
        completed = subprocess.run(
            ["git", "credential", "fill"],
            input=request,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
            timeout=CREDENTIAL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    if completed.returncode != 0:
        return None, ""

    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"username", "password"}:
            fields[key] = value
    token = fields.get("password", "").strip()
    if _valid_token(token):
        return CREDENTIAL_SOURCE, token
    return None, ""


def checked_sources(env_names) -> list[str]:
    sources = list(env_names)
    if os.name == "nt":
        sources.append(CREDENTIAL_SOURCE)
    else:
        sources.append("file:" + str(Path(os.environ.get("GITEE_TOKEN_FILE") or DEFAULT_TOKEN_FILE)))
    return sources


def resolve_token(env_names=DEFAULT_ENV_NAMES):
    """Return (source, token) without persisting or logging the token.

    Explicit environment variables are checked first for CI/test overrides.
    On Windows, Git Credential Manager is then queried for the password stored
    in Windows Credential Manager under ``git:https://gitee.com``. A local
    token file remains available only on non-Windows hosts.
    """
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if _valid_token(value):
            return f"env:{name}", value

    source, token = resolve_windows_credential()
    if source:
        return source, token

    if os.name == "nt":
        return None, ""
    file_path = Path(os.environ.get("GITEE_TOKEN_FILE") or DEFAULT_TOKEN_FILE).expanduser()
    try:
        value = file_path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        value = ""
    if _valid_token(value):
        return f"file:{file_path}", value
    return None, ""


def emit(value: dict, output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = output.expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(encoded)
    print(encoded, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", action="append", dest="env_names", help="Environment variable name to check; may repeat")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    env_names = tuple(args.env_names or DEFAULT_ENV_NAMES)
    invalid = [name for name in env_names if not ENV_NAME_RE.fullmatch(name)]
    if invalid:
        emit(
            {
                "state": "TERMINAL",
                "status": "BLOCKED",
                "outcome": "TOKEN_CHECK_INVALID",
                "reason_code": "INPUT.INVALID_ENV_NAME",
                "token_present": False,
                "checked_sources": list(env_names),
                "message": f"Invalid environment variable names: {invalid}",
            },
            args.output,
        )
        return 2

    source, _ = resolve_token(env_names)
    if source:
        emit(
            {
                "state": "RUNNING",
                "status": "PASS",
                "outcome": "TOKEN_PRESENT",
                "reason_code": None,
                "token_present": True,
                "source": source,
                "checked_sources": checked_sources(env_names),
                "message": "A local Gitee token is present. Its value was not read into output or printed.",
            },
            args.output,
        )
        return 0

    emit(
        {
            "state": "WAITING_USER",
            "status": "BLOCKED",
            "outcome": "TOKEN_REQUIRED",
            "reason_code": "AUTH.GITEE_TOKEN_MISSING",
            "token_present": False,
            "checked_sources": checked_sources(env_names),
            "message": "No local Gitee token was detected. On Windows, save the personal access token as the password for git:https://gitee.com in Windows Credential Manager and configure Git Credential Manager. On non-Windows hosts, use GITEE_TOKEN, GITEE_ACCESS_TOKEN, or a single-line ~/.gitee-token file. Do not paste it into chat.",
            "application_url": "https://gitee.com/profile/personal_access_tokens",
        },
        args.output,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
