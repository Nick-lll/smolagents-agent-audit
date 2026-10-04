#!/usr/bin/env python3
"""One command that reproduces the whole audit: no network, no API key, no GPU.

    python run.py

What it does, in order:

  1. locates the audited framework checkout and refuses to continue unless it is at the
     pinned commit (see ``harness/_setup.py``);
  2. runs ``harness/three_state_audit.py``, which runs the schema self-test, the four
     criteria, the discrimination test and the false-alarm examinations;
  3. writes ``harness/runs/<timestamp>/RESULTS.json`` and ``RESULTS.md`` and prints a
     short verdict summary.

Exit status is 0 whenever the harness itself ran to completion, whatever the verdicts
were: a NOT PASS criterion is a result, not a crash. Exit status 1 means the harness could
not run (missing checkout, wrong commit, or a broken harness state), and exit status 2
means the harness refused to overwrite an existing artifact.

Standard library only. Nothing here imports the audited framework directly.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
HARNESS_DIR = REPO_DIR / "harness"


def main() -> int:
    """Run the audit harness and report where the artifacts landed."""
    script = HARNESS_DIR / "three_state_audit.py"
    if not script.is_file():
        print(f"FAIL: {script} is missing; this package is incomplete", file=sys.stderr)
        return 1

    outdir = HARNESS_DIR / "runs" / time.strftime("run_%Y%m%dT%H%M%SZ", time.gmtime())
    print(f"audit target checkout: {REPO_DIR / 'hub' / 'smolagents'} (or $SMOLAGENTS_ROOT)")
    print(f"artifacts will go to:  {outdir}")
    print()

    completed = subprocess.run([sys.executable, str(script), "--outdir", str(outdir)])
    if completed.returncode != 0:
        print(
            f"\nthe harness exited with status {completed.returncode}; no verdicts are "
            f"claimed from this run",
            file=sys.stderr,
        )
        return completed.returncode

    print("\nOK: reproduction finished. Read the verdicts with:")
    print(f"    {outdir / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
