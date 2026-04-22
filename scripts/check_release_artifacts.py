from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"

BLOCKED_ARTIFACT_PATTERNS = (
    "/.claude/",
    "/.claude-plugin/",
    "/.agents/",
    "/.github/",
    "/docs/",
    "/dist/",
    "/extension/.claude/",
    "/extension/dist/",
    "/extension/node_modules/",
    "/benchmarks/results/",
    "/.env",
    "/cert_key",
    "/uv.lock",
    "/package-lock.json",
)


def _artifact_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(path, "r:gz") as archive:
            return archive.getnames()
    raise ValueError(f"Unsupported artifact: {path}")


def _has_blocked_member(member: str) -> bool:
    normalized = f"/{member.lstrip('./')}"
    return any(pattern in normalized for pattern in BLOCKED_ARTIFACT_PATTERNS)


def main() -> int:
    artifacts = sorted(DIST_DIR.glob("*"))
    if not artifacts:
        print("No build artifacts found in dist/")
        return 1

    failed = False
    for artifact in artifacts:
        if artifact.name == ".gitignore":
            continue
        members = _artifact_members(artifact)
        violations = [member for member in members if _has_blocked_member(member)]
        if violations:
            failed = True
            print(f"{artifact.name}: blocked members detected")
            for member in violations:
                print(f" - {member}")

    if failed:
        return 1

    print("Release artifacts OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
