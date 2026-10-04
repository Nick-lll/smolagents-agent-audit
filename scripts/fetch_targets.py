#!/usr/bin/env python3
"""Clone the audited frameworks at their pinned commits into ``hub/``.

The audit is a statement about specific revisions, so this script checks each checkout out
at the recorded commit and verifies it, rather than taking whatever the default branch
happens to contain today.

    python scripts/fetch_targets.py

Network is needed for this step only. The audit itself is offline: once ``hub/smolagents``
exists at the pinned commit, ``python run.py`` needs no network, no API key and no GPU.

The default clone URLs are the public upstream repositories. Set ``SMOLAGENTS_GIT_URL``
to clone from a mirror instead; the commit check is unchanged, so a mirror that has the
pinned commit works exactly as well.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
HUB_DIR = REPO_DIR / "hub"

#: key -> (clone url, pinned commit, directory name under hub/)
TARGETS: dict[str, tuple[str, str, str]] = {
    "smolagents": (
        os.environ.get("SMOLAGENTS_GIT_URL", "https://github.com/huggingface/smolagents"),
        "c30b115286e000e98711fae5e85993547b73d826",
        "smolagents",
    ),
}


def run_git(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    """Run one git command and return its stdout, raising on failure when asked."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if check and completed.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed with status {completed.returncode}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    return completed.stdout.strip()


def fetch_target(name: str, url: str, commit: str, directory: str) -> int:
    """Clone (or reuse) one target checkout and check it out at its pinned commit."""
    destination = HUB_DIR / directory
    if destination.is_dir():
        print(f"{name}: reusing existing checkout at {destination}")
        run_git(["fetch", "--all", "--tags"], cwd=destination, check=False)
    else:
        HUB_DIR.mkdir(parents=True, exist_ok=True)
        print(f"{name}: cloning {url} into {destination}")
        run_git(["clone", "--no-checkout", url, str(destination)])

    print(f"{name}: checking out {commit}")
    run_git(["checkout", "--detach", commit], cwd=destination)
    found = run_git(["rev-parse", "HEAD"], cwd=destination)
    if found != commit:
        print(f"{name}: FAIL, wanted {commit} but HEAD is {found}", file=sys.stderr)
        return 1
    print(f"{name}: OK at {found}")
    return 0


def main() -> int:
    """Fetch every pinned target; return non-zero if any checkout is not at its pin."""
    if not run_git(["--version"], check=False):
        print("FAIL: git is not available on PATH", file=sys.stderr)
        return 1

    status = 0
    for name, (url, commit, directory) in TARGETS.items():
        status |= fetch_target(name, url, commit, directory)

    if status == 0:
        print("\nAll targets are at their pinned commits. Now run:  python run.py")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
