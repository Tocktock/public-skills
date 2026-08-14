#!/usr/bin/env python3
"""Fail closed when public GPT Squad source contains private or secret-like data."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "engineering"
EXPECTED_COUNTS = {
    "gpt-squad-installer": 26,
    "gpt-squad-orchestrator": 27,
}

FORBIDDEN_LITERALS = (
    "Tocktock/" + "private-skills",
    "Ven" + "ditz",
    "Sendy" + "Core",
    "/home/" + "oai/",
    "/" + "Users/",
    "rollout-" + "20",
    "qnfmtm" + "666",
    "@naver" + ".com",
)

FORBIDDEN_PATTERNS = (
    ("GitHub token", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key", re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
    (
        "credential-bearing URL",
        re.compile(r"\b(?:postgres(?:ql)?|https?)://[^\s:@/]+:[^\s@/]+@", re.IGNORECASE),
    ),
    ("Slack or API token", re.compile(r"\b(?:xox[baprs]|sk)-[A-Za-z0-9_-]{16,}")),
)

RUNTIME_SUFFIXES = {".sqlite3", ".sqlite", ".db", ".jsonl"}
IGNORED_PARTS = {".git", "__pycache__"}


def fail(message: str) -> None:
    raise SystemExit(f"public-source verification failed: {message}")


def text_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in RUNTIME_SUFFIXES:
            fail(f"runtime state file is forbidden: {path.relative_to(ROOT)}")
        result.append(path)
    return result


def main() -> int:
    for skill, expected in EXPECTED_COUNTS.items():
        directory = SKILL_ROOT / skill
        if not directory.is_dir():
            fail(f"missing skill directory: {directory.relative_to(ROOT)}")
        actual = sum(
            1
            for path in directory.rglob("*")
            if path.is_file() and not any(part in IGNORED_PARTS for part in path.parts)
        )
        if actual != expected:
            fail(f"{skill} contains {actual} files; expected {expected}")

    for path in text_files():
        relative = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            fail(f"non-text file is forbidden: {relative}")
            raise AssertionError from exc
        for literal in FORBIDDEN_LITERALS:
            if literal in text:
                fail(f"forbidden literal found in {relative}")
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                fail(f"{label} found in {relative}")

    print("public-source verification: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
