#!/usr/bin/env python3
"""Check the converted project README for template placeholders and broken local links."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path


LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDERS = (
    "<扩展标题>",
    "<扩展名称>",
    "<传感器 / 执行器 / 通信模块 / 功能类>",
    "<主要功能1>",
    "<主要功能2>",
    "<主要功能3>",
    "<典型应用场景>",
    "<产品型号1>",
    "<产品型号2>",
    "<产品型号3>",
    "<SKU>",
    "<功能 / 主板 / 模式>",
    "<积木 / 示例程序等>",
)
REQUIRED_HEADINGS = ("## 积木", "## 示例程序", "## 支持列表", "## 更新日志")


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.project_root.expanduser().resolve()
    readme = root / "README.md"
    errors: list[dict] = []
    if not readme.is_file():
        errors.append({"type": "missing_readme", "path": str(readme)})
        text = ""
    else:
        try:
            text = readme.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append({"type": "read_error", "error": str(exc)})
            text = ""
    for placeholder in PLACEHOLDERS:
        if placeholder in text:
            errors.append({"type": "template_placeholder", "value": placeholder})
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append({"type": "missing_section", "value": heading})
    checked_links = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        raw = raw.split(" ", 1)[0]
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme or raw.startswith(("#", "mailto:")):
            continue
        relative = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0])
        if not relative:
            continue
        target = (readme.parent / relative).resolve()
        item = {"link": raw, "target": str(target)}
        if not inside(target, root):
            item.update({"status": "FAIL", "error": "link escapes project root"})
            errors.append({"type": "unsafe_link", **item})
        elif not target.exists():
            item.update({"status": "FAIL", "error": "target does not exist"})
            errors.append({"type": "broken_link", **item})
        else:
            item["status"] = "PASS"
        checked_links.append(item)
    result = {
        "status": "PASS" if not errors else "FAIL",
        "project_root": str(root),
        "readme": str(readme),
        "checked_local_links": checked_links,
        "errors": errors,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8", newline="\n")
    print(encoded)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

