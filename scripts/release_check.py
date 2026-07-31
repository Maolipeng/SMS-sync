#!/usr/bin/env python3
"""Fail closed on common SMS Bridge release hygiene mistakes."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "README.md",
    "README.en.md",
    "SECURITY.md",
    "LICENSE",
    "docs/USER_GUIDE.zh-CN.md",
    "docs/USER_GUIDE.en.md",
    "docs/THREAT_MODEL.zh-CN.md",
    "docs/THREAT_MODEL.en.md",
    "docs/RELEASING.md",
}
FORBIDDEN_NAMES = {
    ".env",
    "state.sqlite3",
    "sms-bridge.log",
    "sms-bridge.error.log",
}
SECRET_PATTERNS = {
    "Telegram Bot Token": re.compile(rb"\b\d{7,12}:AA[A-Za-z0-9_-]{20,}\b"),
    "Discord Webhook URL": re.compile(
        rb"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/"
        rb"\d{6,24}/[A-Za-z0-9._-]{20,}"
    ),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def project_files() -> list[Path]:
    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]
    ignored_directories = {"__pycache__", "build", "dist", ".venv"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not ignored_directories.intersection(path.relative_to(ROOT).parts)
    ]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    missing = sorted(name for name in REQUIRED if not (ROOT / name).is_file())
    if missing:
        fail("missing release documentation: " + ", ".join(missing))

    files = project_files()
    forbidden = sorted(str(path.relative_to(ROOT)) for path in files if path.name in FORBIDDEN_NAMES)
    if forbidden:
        fail("runtime/private files would be released: " + ", ".join(forbidden))

    for path in files:
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            content = path.read_bytes()
        except OSError as exc:
            fail(f"cannot inspect {path.relative_to(ROOT)}: {exc}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                fail(f"possible {label} in {path.relative_to(ROOT)}")

    commands = [
        [sys.executable, "-m", "py_compile", "sms_bridge.py", "sms_bridge_ui.py"],
        ["/bin/zsh", "-n", "SMS Bridge.command"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)

    if (ROOT / ".git").exists():
        subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(f"Release check passed: {len(files)} files inspected; tests and syntax checks passed.")


if __name__ == "__main__":
    main()
