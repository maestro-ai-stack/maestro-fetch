from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BLOCKED_TRACKED_PATTERNS = (
    ".claude/",
    ".agents/",
    ".env",
    "cert_key",
    "extension/node_modules/",
    "extension/package-lock.json",
)


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    violations = [
        path
        for path in tracked
        if any(pattern in path or path.startswith(pattern) for pattern in BLOCKED_TRACKED_PATTERNS)
    ]

    if violations:
        print("Blocked tracked files detected:")
        for path in violations:
            print(f" - {path}")
        return 1

    print("Repo hygiene OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
