#!/usr/bin/env python3
"""Check local Gitee token presence without printing or validating the secret value."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


DEFAULT_ENV_NAMES = ("GITEE_TOKEN", "GITEE_ACCESS_TOKEN")
DEFAULT_TOKEN_FILE = Path.home() / ".gitee-token"
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def resolve_token(env_names=DEFAULT_ENV_NAMES):
    """Return (source, token): process env first, then the local token file.

    The value is never logged or printed; callers may pass it to a child
    process environment only. The file must be a single non-empty line.
    """
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return f"env:{name}", value
    file_path = Path(os.environ.get("GITEE_TOKEN_FILE") or DEFAULT_TOKEN_FILE).expanduser()
    try:
        value = file_path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        value = ""
    if value and "\n" not in value and "\r" not in value and len(value) <= 256:
        return f"file:{file_path}", value
    return None, ""


def emit(value: dict, output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = output.expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8", newline="\n")
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
                "checked_sources": list(env_names) + ["file:" + str(Path(os.environ.get("GITEE_TOKEN_FILE") or DEFAULT_TOKEN_FILE))],
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
            "checked_sources": list(env_names) + ["file:" + str(Path(os.environ.get("GITEE_TOKEN_FILE") or DEFAULT_TOKEN_FILE))],
            "message": "No local Gitee token was detected. Apply for a personal access token while signed in to Gitee, expose it locally as GITEE_TOKEN or GITEE_ACCESS_TOKEN, or as a single-line file ~/.gitee-token, then resume. Do not paste it into chat.",
            "application_url": "https://gitee.com/profile/personal_access_tokens",
        },
        args.output,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
