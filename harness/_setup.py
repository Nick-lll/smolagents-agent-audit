"""Locate the audited framework checkout and put ITS source first on sys.path.

Every path in this package is resolved relative to this file. There is no absolute
path, no home-directory assumption, and no environment variable that must be set: the
harness runs from wherever the repository was cloned.

Resolution order for the audit target
-------------------------------------
1. ``$SMOLAGENTS_ROOT`` when set: an explicit path to the framework clone.
2. ``<this repo>/hub/smolagents``: the layout ``scripts/fetch_targets.py`` produces.
3. ``$CWD`` when it is itself a clone of the target.

In every case ``<root>/src`` is inserted at the FRONT of ``sys.path`` so the harness
audits the clone under test rather than any other copy of the package that happens to be
installed in the interpreter. Without this, a stale site-packages copy would be audited
and the recorded line numbers and file hashes would not match the pinned commit.

The pinned commit is checked, not merely recorded. If the checkout is at a different
commit the harness refuses to start, because a control that no longer applies must say
so rather than produce a verdict about a revision nobody pinned.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: the revision every control in `three_state_audit.py` was measured against
PINNED_SMOLAGENTS_COMMIT = "c30b115286e000e98711fae5e85993547b73d826"
UPSTREAM_REPOSITORY = "https://github.com/huggingface/smolagents"

AUDIT_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = AUDIT_SCRIPT_DIR.parent


def _is_smolagents_clone(path: Path) -> bool:
    """A usable target has the audited package source, not just a checkout of the repo."""
    return (path / "src" / "smolagents" / "agents.py").is_file()


def locate_target_root() -> Path:
    """Return the framework clone to audit, or exit with an actionable message."""
    candidates: list[tuple[str, Path]] = []
    override = os.environ.get("SMOLAGENTS_ROOT")
    if override:
        candidates.append(("$SMOLAGENTS_ROOT", Path(override).expanduser()))
    candidates.append(("hub/smolagents next to this repo", REPO_DIR / "hub" / "smolagents"))
    candidates.append(("the current directory", Path.cwd()))

    for label, candidate in candidates:
        if _is_smolagents_clone(candidate):
            return candidate.resolve()

    tried = "\n".join(f"    - {label}: {candidate}" for label, candidate in candidates)
    raise SystemExit(
        "cannot find the audited framework checkout; looked at:\n"
        f"{tried}\n\n"
        "Fix it with either:\n"
        f"    python scripts/fetch_targets.py          # clones {UPSTREAM_REPOSITORY}\n"
        f"    set SMOLAGENTS_ROOT=<path to your clone>\n\n"
        f"The clone must be at commit {PINNED_SMOLAGENTS_COMMIT}."
    )


def target_commit(target_root: Path) -> str:
    """Return the checkout's HEAD commit, or an empty string when git cannot answer."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:  # noqa: BLE001 - a missing git is reported through the empty string
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def activate(require_pinned_commit: bool = True) -> tuple[Path, str]:
    """Resolve the target, pin-check it, and prepend its source tree to sys.path.

    @param require_pinned_commit: refuse to run when HEAD is not the pinned revision.
    @returns: the resolved target root and the commit found there.
    """
    target_root = locate_target_root()
    commit = target_commit(target_root)
    source_dir = target_root / "src"
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

    if require_pinned_commit and commit != PINNED_SMOLAGENTS_COMMIT:
        found = commit or "unknown (git unavailable, or the checkout has no history)"
        raise SystemExit(
            f"REFUSING TO RUN: the target checkout is at {found}\n"
            f"but every control in this harness was measured against "
            f"{PINNED_SMOLAGENTS_COMMIT}.\n"
            f"Auditing a different revision would report verdicts nobody pinned.\n"
            f"Check out the pinned commit:\n"
            f"    git -C {target_root} fetch origin && "
            f"git -C {target_root} checkout {PINNED_SMOLAGENTS_COMMIT}\n"
            f"Set SMOLAGENTS_ALLOW_ANY_COMMIT=1 only to explore, never to publish a result."
        )
    return target_root, commit


def resolve_root(require_pinned_commit: bool = True) -> Path:
    """Resolve the target and return the root used for file hashes and git metadata."""
    root, _ = activate(require_pinned_commit=require_pinned_commit)
    return root
