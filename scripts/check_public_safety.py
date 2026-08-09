# -*- coding: utf-8 -*-
"""Fail when public project files contain common local or secret material."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DENYLIST = PROJECT_ROOT / ".privacy.local.txt"
TEXT_SUFFIXES = {
    ".bat", ".cmd", ".css", ".csv", ".html", ".js", ".json", ".jsonl",
    ".md", ".ps1", ".py", ".toml", ".txt", ".yaml", ".yml",
}
BUILTIN_PATTERNS = (
    ("Windows user path", re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)),
    ("local knowledge-base path", re.compile(r"[A-Za-z]:\\知识库\\", re.IGNORECASE)),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("API secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
)


def candidate_files() -> list[Path]:
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
    files = []
    for relative in result.stdout.splitlines():
        path = PROJECT_ROOT / relative
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return files


def custom_terms() -> list[str]:
    if not LOCAL_DENYLIST.exists():
        return []
    return [
        line.strip() for line in LOCAL_DENYLIST.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def scan() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    terms = custom_terms()
    for path in candidate_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, 1):
            for label, pattern in BUILTIN_PATTERNS:
                if label == "email address" and "git@github.com:" in line:
                    continue
                if pattern.search(line):
                    findings.append({"file": relative, "line": line_number, "rule": label})
            for term in terms:
                if term.casefold() in line.casefold():
                    findings.append({"file": relative, "line": line_number, "rule": "local denylist"})
    for path in (PROJECT_ROOT / "data").rglob("*"):
        if "知识星球" in path.name:
            findings.append({"file": path.relative_to(PROJECT_ROOT).as_posix(), "line": 0, "rule": "excluded data layer"})
    demo_dashboard = PROJECT_ROOT / "data" / "demo" / "dashboard-normalized" / "self_media_dashboard.json"
    if demo_dashboard.exists():
        payload = json.loads(demo_dashboard.read_text(encoding="utf-8-sig"))
        encoded = json.dumps(payload, ensure_ascii=False)
        if re.search(r"[A-Za-z]:\\", encoded):
            findings.append({"file": demo_dashboard.relative_to(PROJECT_ROOT).as_posix(), "line": 0, "rule": "absolute demo source path"})
        if payload.get("dataMode") != "demo":
            findings.append({"file": demo_dashboard.relative_to(PROJECT_ROOT).as_posix(), "line": 0, "rule": "missing demo marker"})
    return findings


def main() -> int:
    findings = scan()
    print(json.dumps({"ok": not findings, "checked_files": len(candidate_files()), "findings": findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
