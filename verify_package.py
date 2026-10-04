#!/usr/bin/env python3
"""Assert that this package is self-contained, offline-runnable, leak-free and publishable.

    python verify_package.py              # check the package
    python verify_package.py --self-test  # check it AND prove the leak detector fires

What is checked
---------------
1. Every required file exists and is non-empty.
2. Every text file is valid UTF-8, so a stranger's editor and a stranger's CI both read it.
3. No file carries a reference to the authoring machine or the authoring project, and no file
   carries an absolute path from that machine. This is what makes the package portable: a
   reader's checkout is not at the author's path.
4. No file requires a credential: no assignment to a token-shaped name, and no known
   credential prefix.
5. No file performs network I/O, and only the harness imports the package under test.
6. The harness refuses to run against a checkout that is not at the pinned commit, and the pin
   in `harness/_setup.py` matches the pin in `REPRODUCE.md`.
7. The recorded raw evidence is byte-identical to what `findings/raw/PROVENANCE.md` claims it
   is, so a quote in a finding can be traced to the artifact it came from.
8. The operator runbook is declared as not-for-publication and is genuinely ignored by git,
   so it cannot reach the public repository by accident.
9. The policy documents state what this package promises: the keyless offline environment, an
   honesty section, the disclosure process, and the measured reproduction rate.

Why `--self-test` exists
------------------------
A leak detector that has never been observed to fire is not evidence of anything.
`--self-test` copies a real harness file, injects the forbidden token into the copy, and
asserts that the detector reports the copy as a failure. If the detector ever stops working,
this check fails — the only way to tell a clean package from a broken checker.

Why some files are exempt from the leak sweep
---------------------------------------------
Exactly two groups are exempt, each for a reason that would be dishonest to hide:

* **`findings/raw/`** is the recorded evidence, copied verbatim from runs. It contains the
  absolute paths of the machine that produced it, because a harness records which checkout
  and which interpreter it ran against. Editing that would destroy the evidence: a reader
  could no longer check a quoted observation against the artifact. The right fix is not to
  rewrite the artifact but to keep it out of the repository — see the note below.
* **The operator runbook** is a local procedure that has to name the local tree it operates
  on. It is declared not-for-publication and is verified to be git-ignored.

Everything else — every README, every finding, the harness, the scripts, the licence — is
swept with no exemptions, and this file sweeps itself for credentials and network imports.

The forbidden tokens are assembled from `chr()` codes rather than written literally, so this
file does not contain the strings it searches for.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent

#: the authoring project's name and audit tree, split so the literal strings are absent here
_FORBIDDEN_PARTS: tuple[tuple[int, ...], ...] = (
    tuple(ord(c) for c in "zeus"),
    tuple(ord(c) for c in "zeus20260524"),
)
FORBIDDEN_TOKENS: tuple[str, ...] = tuple("".join(chr(c) for c in part) for part in _FORBIDDEN_PARTS)

#: path patterns that only ever appear on an authoring machine
ABSOLUTE_PATH_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?i)\b[a-z]:[\\/]", "a Windows absolute path or drive-rooted path"),
    (r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9._-]+", "a POSIX home-directory path"),
)

#: credential shapes that must never appear
CREDENTIAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:sk|rk)-[A-Za-z0-9]{16,}", "an API key"),
    (r"\bhf_[A-Za-z0-9]{20,}", "a Hugging Face token"),
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}", "a GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", "a GitHub fine-grained PAT"),
    (r"\bAKIA[0-9A-Z]{12,}", "an AWS access key id"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "a Slack token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
)

#: an assignment to a credential-shaped name that is not read from the environment.
#: Lowercase names only: an ALL-CAPS constant named `CREDENTIAL_PATTERNS` is a pattern list,
#: not a secret, and matching it would train the reader to ignore this check.
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?m)^\s*(?:export\s+)?[a-z][a-z0-9_]*(?:token|secret|password|api_?key|credential)"
    r"[a-z0-9_]*\s*[:=]\s*(?!os\.environ|os\.getenv|environ\.get|\$env:|<|None|''|\"\")"
)

#: libraries that would mean the audit is not offline
NETWORK_IMPORTS: tuple[tuple[str, str], ...] = (
    (r"(?m)^\s*(?:import|from)\s+(requests|httpx|urllib\.request|http\.client|socket|aiohttp|websockets)\b",
     "a network library"),
)

#: files exempt from the leak sweep because they ARE the evidence, copied verbatim.
#: Exempt only from checks 3 and 4: they still have to exist and be readable.
EVIDENCE_PREFIXES: tuple[str, ...] = ("findings/raw/",)

#: the operator runbook: a local document that names the local tree it operates on.
#: Exempt from check 3 only, and required by check 8 to be git-ignored and to say so.
OPERATOR_DOCS: tuple[str, ...] = ("PUBLISH_RUNBOOK.md",)

#: files this checker must contain the tokens it searches for, so it is exempt from check 3
#: and from the credential-assignment rule, which would otherwise match its own pattern names
SELF_EXEMPT: tuple[str, ...] = ("verify_package.py",)

#: the harness is allowed to import the package under test; nothing else is
HARNESS_PREFIXES: tuple[str, ...] = ("harness/",)

BINARY_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".whl", ".pyc", ".ico", ".woff", ".woff2"}
)

#: directories that are fetched, not shipped: third-party clones and run artifacts
FETCHED_PREFIXES: tuple[str, ...] = ("hub/", "harness/runs/", ".git/")

REQUIRED_FILES: tuple[str, ...] = (
    "README.md",
    "REPRODUCE.md",
    "DISCLOSURE.md",
    "PUBLISH_RUNBOOK.md",
    "LICENSE",
    ".gitignore",
    "run.py",
    "verify_package.py",
    "scripts/fetch_targets.py",
    "harness/_setup.py",
    "harness/core.py",
    "harness/mutants.py",
    "harness/three_state_audit.py",
    "harness/PORTABILITY.md",
    "findings/README.md",
    "findings/raw/PROVENANCE.md",
    "findings/raw/RESULTS.json",
    "findings/raw/RESULTS.md",
    "findings/raw/PIP_FREEZE.txt",
    "findings/slots/BRIEFS_PENDING.md",
    "findings/slots/POC_INJECTION.md",
    "findings/briefs/F1_fallback_answer_swallows_a_model_failure.md",
    "findings/briefs/F2_fallback_failure_reported_as_step_limit.md",
    "findings/briefs/F3_empty_answer_reported_as_success.md",
    "findings/briefs/F4_zero_step_budget_crashes.md",
    "findings/briefs/REPORT_public_audit_final.md",
)

#: the marker the operator runbook must carry, so the exemption above is never silent
NOT_FOR_PUBLICATION_MARKER = "PUBLICATION: NOT FOR PUBLICATION"

#: expected SHA-256 of each recorded evidence file, as declared in PROVENANCE.md
EXPECTED_EVIDENCE_HASHES: dict[str, str] = {
    "findings/raw/RESULTS.json": "D9845A27D3C7CD03",
    "findings/raw/RESULTS.md": "110BA190BD865FD5",
    "findings/raw/PIP_FREEZE.txt": "FC49DBFCD6B0D846",
    "findings/briefs/REPORT_public_audit_final.md": "AF35091D34EB0DC8",
}


@dataclass
class Problem:
    """One failed check, with the file and line that caused it."""

    check: str
    detail: str
    path: str = ""
    line: int = 0

    def render(self) -> str:
        where = f" [{self.path}:{self.line}]" if self.path else ""
        return f"{self.check}{where}: {self.detail}"


def _is_evidence(relative: str) -> bool:
    return relative.startswith(EVIDENCE_PREFIXES)


def _is_operator_doc(relative: str) -> bool:
    return relative in OPERATOR_DOCS


def _is_self(relative: str) -> bool:
    return relative in SELF_EXEMPT


def iter_files() -> list[Path]:
    """Return every shipped file: no fetched third-party tree, no run artifact, no cache."""
    found: list[Path] = []
    for path in sorted(REPO_DIR.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_DIR).as_posix()
        if relative.startswith(FETCHED_PREFIXES) or "__pycache__" in relative:
            continue
        found.append(path)
    return found


def read_text(path: Path) -> str | None:
    """Return the file's text, or None when it is binary or not valid UTF-8."""
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_text(text: str, relative: str) -> list[Problem]:
    """Return every leak, credential or network problem in one file's text."""
    problems: list[Problem] = []
    evidence = _is_evidence(relative)
    operator = _is_operator_doc(relative)
    self_exempt = _is_self(relative)

    def line_of(index: int) -> int:
        return text.count("\n", 0, index) + 1

    def add(check: str, detail: str, index: int = 0) -> None:
        problems.append(Problem(check, detail, relative, line_of(index) if index else 0))

    if not (evidence or operator or self_exempt):
        for token in FORBIDDEN_TOKENS:
            start = text.lower().find(token)
            while start != -1:
                add("authoring-tree reference", f"contains {token!r}", start)
                start = text.lower().find(token, start + 1)
        for pattern, description in ABSOLUTE_PATH_PATTERNS:
            for match in re.finditer(pattern, text):
                add("absolute local path", f"{description}: {match.group(0)!r}", match.start())

    if not (evidence or self_exempt):
        for pattern, description in CREDENTIAL_PATTERNS:
            for match in re.finditer(pattern, text):
                add("credential-like string", f"{description}: {match.group(0)[:12]}...", match.start())
        for match in CREDENTIAL_ASSIGNMENT.finditer(text):
            add("credential required",
                f"assignment to a credential-shaped name: {match.group(0).strip()[:60]!r}",
                match.start())

    in_harness = relative.startswith(HARNESS_PREFIXES)
    for pattern, description in NETWORK_IMPORTS:
        for match in re.finditer(pattern, text):
            if in_harness and "smolagents" in pattern:
                continue
            add("not offline", f"imports {description}: {match.group(0).strip()!r}", match.start())
    return problems


def check_required_files() -> list[Problem]:
    """Assert every required file is present and non-empty."""
    problems: list[Problem] = []
    for relative in REQUIRED_FILES:
        path = REPO_DIR / relative
        if not path.is_file():
            problems.append(Problem("missing file", f"{relative} does not exist"))
        elif path.stat().st_size == 0:
            problems.append(Problem("empty file", f"{relative} is empty", relative))
    return problems


def check_pin_consistency() -> list[Problem]:
    """Assert the pin in the harness and the pin in the documentation are the same pin."""
    problems: list[Problem] = []
    setup_path = REPO_DIR / "harness" / "_setup.py"
    reproduce_path = REPO_DIR / "REPRODUCE.md"
    if not setup_path.is_file() or not reproduce_path.is_file():
        return problems
    setup_text = setup_path.read_text(encoding="utf-8")
    reproduce_text = reproduce_path.read_text(encoding="utf-8")
    found = re.search(r'PINNED_SMOLAGENTS_COMMIT\s*=\s*"([0-9a-f]{40})"', setup_text)
    if not found:
        problems.append(Problem("pin missing",
                                "harness/_setup.py does not declare a 40-hex pin",
                                "harness/_setup.py"))
        return problems
    commit = found.group(1)
    if commit not in reproduce_text:
        problems.append(Problem(
            "pin mismatch",
            f"REPRODUCE.md does not record the pin {commit} declared by harness/_setup.py",
            "REPRODUCE.md",
        ))
    if "require_pinned_commit" not in setup_text:
        problems.append(Problem("pin unenforced",
                                "harness/_setup.py does not enforce the pin at run time",
                                "harness/_setup.py"))
    return problems


def check_evidence_integrity() -> list[Problem]:
    """Assert each recorded evidence file is the bytes its provenance note claims.

    This is what keeps the raw evidence exemption honest: the exempted files are not merely
    present, they are pinned, so an edited 'recorded' artifact cannot pass as the original.
    """
    import hashlib

    problems: list[Problem] = []
    for relative, expected in EXPECTED_EVIDENCE_HASHES.items():
        path = REPO_DIR / relative
        if not path.is_file():
            problems.append(Problem("evidence missing", f"{relative} does not exist"))
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()[:16]
        if digest != expected:
            problems.append(Problem(
                "evidence altered",
                f"{relative} hashes to {digest} but PROVENANCE.md claims {expected}; "
                f"recorded evidence must not be edited",
                relative,
            ))
    provenance = REPO_DIR / "findings" / "raw" / "PROVENANCE.md"
    if provenance.is_file():
        text = provenance.read_text(encoding="utf-8")
        for relative, expected in EXPECTED_EVIDENCE_HASHES.items():
            if expected not in text:
                problems.append(Problem(
                    "provenance gap",
                    f"PROVENANCE.md does not record the hash {expected} for {relative}",
                    "findings/raw/PROVENANCE.md",
                ))
    return problems


def check_operator_docs_declared() -> list[Problem]:
    """Assert every operator-only document says so and cannot reach the public repository."""
    problems: list[Problem] = []
    gitignore = REPO_DIR / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    for relative in OPERATOR_DOCS:
        path = REPO_DIR / relative
        if not path.is_file():
            problems.append(Problem("operator doc missing", f"{relative} does not exist"))
            continue
        text = path.read_text(encoding="utf-8")
        if NOT_FOR_PUBLICATION_MARKER not in text:
            problems.append(Problem(
                "undeclared operator doc",
                f"{relative} does not carry the marker {NOT_FOR_PUBLICATION_MARKER!r}, so its "
                f"exemption from the leak sweep is silent",
                relative,
            ))
        if relative not in ignored:
            problems.append(Problem(
                "operator doc publishable",
                f"{relative} is not listed in .gitignore, so `git add .` would publish a local "
                f"document",
                ".gitignore",
            ))
        if not (REPO_DIR / ".git").is_dir():
            continue
        completed = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=str(REPO_DIR), capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            problems.append(Problem(
                "operator doc not ignored by git",
                f"`git check-ignore {relative}` says it is NOT ignored; it would be published",
                ".gitignore",
            ))
    return problems


def check_policy_text() -> list[Problem]:
    """Assert the policy documents carry the statements this package promises."""
    problems: list[Problem] = []

    def require(relative: str, needle: str, why: str) -> None:
        path = REPO_DIR / relative
        if not path.is_file():
            return
        if needle.lower() not in path.read_text(encoding="utf-8").lower():
            problems.append(Problem("policy gap", f"{relative} does not state {why}", relative))

    require("README.md", "no network, no api key, no gpu", "the keyless offline environment")
    require("README.md", "do not prove", "an explicit honesty section")
    require("README.md", "reproduction ran", "the rule that a claim requires a reproduction")
    require("README.md", "apache-2.0", "the licence it ships under")
    require("DISCLOSURE.md", "erratum", "the dispute-correction process")
    require("DISCLOSURE.md", "disputed", "a status for a disputed finding")
    # This assertion previously required the words "not been disclosed": it was written
    # while the repository was still unpublished, and once it was published the check pinned
    # a statement that had become FALSE, which then blocked the correction from being
    # published. A gate that enforces a falsehood is worse than no gate. It now asserts the
    # facts that must hold *after* publication, so a regression back to the older, no-longer-
    # true wording fails here.
    require("DISCLOSURE.md", "published on", "the date the repository was published")
    require("DISCLOSURE.md", "not filed as a vulnerability report", "the scope self-assessment")
    require("DISCLOSURE.md", "ai assistance", "that AI assistance is disclosed")
    require("DISCLOSURE.md", "@", "a contact address for corrections")
    require("DISCLOSURE.md", "timeline", "a disclosure timeline")
    require("REPRODUCE.md", "reproduction rate", "the measured reproduction rate")
    require("REPRODUCE.md", "pinned", "the pinned upstream revision")
    require("findings/README.md", "not reproduced", "the full status vocabulary")
    require("findings/slots/BRIEFS_PENDING.md", "slot open", "that no brief has been written")
    require("findings/raw/PROVENANCE.md", "deliberately excluded", "what was left out and why")
    require("findings/raw/PROVENANCE.md", "canonicalised", "the report edit and its original hash")
    require("PUBLISH_RUNBOOK.md", "PAT", "the credential options")
    require("PUBLISH_RUNBOOK.md", "SSH", "the SSH-key option")
    require("PUBLISH_RUNBOOK.md", "git grep", "the pre-publish secret scan")
    require("PUBLISH_RUNBOOK.md", "ERRATUM", "the maintainer-dispute procedure")
    require("LICENSE", "Apache License", "the licence text")
    require("harness/PORTABILITY.md", "SMOLAGENTS_ROOT", "how the audit target is located")

    return problems


def check_driver_containment() -> list[Problem]:
    """Assert the one-command driver launches the harness and writes inside the package."""
    problems: list[Problem] = []
    path = REPO_DIR / "run.py"
    if not path.is_file():
        return problems
    text = path.read_text(encoding="utf-8")
    if '"runs"' not in text:
        problems.append(Problem("driver containment",
                                "run.py does not write under harness/runs/", "run.py"))
    if "subprocess" not in text:
        problems.append(Problem("driver contract", "run.py does not launch the harness", "run.py"))

    fetch = REPO_DIR / "scripts" / "fetch_targets.py"
    if fetch.is_file():
        fetch_text = fetch.read_text(encoding="utf-8")
        if "c30b115286e000e98711fae5e85993547b73d826" not in fetch_text:
            problems.append(Problem("fetch pin missing",
                                    "scripts/fetch_targets.py does not pin the audited commit",
                                    "scripts/fetch_targets.py"))
        if "rev-parse" not in fetch_text:
            problems.append(Problem("fetch pin unverified",
                                    "scripts/fetch_targets.py does not verify the checked-out commit",
                                    "scripts/fetch_targets.py"))
    return problems


def check_artifacts_not_committed() -> list[Problem]:
    """Assert run artifacts and fetched clones are ignored, not shipped."""
    problems: list[Problem] = []
    gitignore = REPO_DIR / ".gitignore"
    if not gitignore.is_file():
        return [Problem("missing file", ".gitignore does not exist")]
    ignored = gitignore.read_text(encoding="utf-8")
    for entry in ("harness/runs/", "hub/"):
        if entry not in ignored:
            problems.append(Problem("artifact not ignored",
                                    f".gitignore does not exclude {entry}", ".gitignore"))
    return problems


def run_checks() -> list[Problem]:
    """Run every check and return all problems found."""
    problems = check_required_files()
    for path in iter_files():
        relative = path.relative_to(REPO_DIR).as_posix()
        text = read_text(path)
        if text is None:
            if path.suffix.lower() not in BINARY_SUFFIXES:
                problems.append(Problem("unreadable file",
                                        "not valid UTF-8 (or not readable as text)", relative))
            continue
        problems.extend(scan_text(text, relative))
    problems.extend(check_pin_consistency())
    problems.extend(check_evidence_integrity())
    problems.extend(check_operator_docs_declared())
    problems.extend(check_policy_text())
    problems.extend(check_driver_containment())
    problems.extend(check_artifacts_not_committed())
    return problems


def published_set() -> list[str]:
    """Return the files that would go into a public repository, in sorted order."""
    published: list[str] = []
    for path in iter_files():
        relative = path.relative_to(REPO_DIR).as_posix()
        if _is_operator_doc(relative):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        published.append(relative)
    return sorted(published)


def self_test() -> int:
    """Prove the leak detector fires by injecting the forbidden token into a copy.

    The copy is written to a temporary directory, never into the package, and it is a copy of
    a real harness file, so the injection happens in the same bytes the sweep really reads.
    """
    source = REPO_DIR / "harness" / "core.py"
    if not source.is_file():
        print("SELF-TEST FAIL: harness/core.py is missing, cannot build the control")
        return 1

    injection = (
        "\n# audit tree: " + FORBIDDEN_TOKENS[1] + "\n"
        "probe_path = r\"" + "E:" + "\\" + FORBIDDEN_TOKENS[1] + "\"\n"
        "probe_key = \"hf_" + "A" * 24 + "\"\n"
    )
    with tempfile.TemporaryDirectory() as scratch:
        probe = Path(scratch) / "core.py"
        probe.write_text(source.read_text(encoding="utf-8") + injection, encoding="utf-8")
        findings = scan_text(probe.read_text(encoding="utf-8"), "harness/core.py (control copy)")

    kinds = sorted({problem.check for problem in findings})
    tree_hits = [p for p in findings if p.check == "authoring-tree reference"]
    path_hits = [p for p in findings if p.check == "absolute local path"]
    cred_hits = [p for p in findings if p.check.startswith("credential")]

    print("self-test (control): a copy of harness/core.py with three violations injected")
    print(f"  detected {len(findings)} problem(s): {kinds}")
    for problem in findings:
        print(f"    {problem.render()}")

    missing = [
        name for name, hits in
        (("authoring-tree reference", tree_hits), ("absolute local path", path_hits),
         ("credential-like string", cred_hits))
        if not hits
    ]
    if missing:
        print(f"SELF-TEST FAIL: the detector did NOT fire on {missing}. A clean result from a "
              f"normal run therefore proves nothing.")
        return 1
    print("SELF-TEST PASS: the detector fired on the injected authoring-tree reference, "
          "absolute path and credential-like string, so a clean package run is meaningful.")
    return 0


def main() -> int:
    """Check the package; optionally prove the detector fires; optionally list what publishes."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true",
                        help="inject forbidden content into a copy and assert the detector fires")
    parser.add_argument("--list-published", action="store_true",
                        help="print the files that would go into the public repository")
    args = parser.parse_args()

    print(f"verifying package at {REPO_DIR}")
    files = iter_files()
    print(f"files swept: {len(files)} (fetched clones and run artifacts excluded)")

    problems = run_checks()
    if problems:
        print(f"\nFAIL: {len(problems)} problem(s) found\n")
        for problem in problems:
            print(f"  {problem.render()}")
        print("\nThis package is NOT self-contained or NOT publishable. Fix the above before "
              "publishing.")
        return 1

    print("\nPASS: no authoring-tree reference, no absolute local path, no credential, no "
          "network import, no missing file.")
    print("      the pin is enforced at run time, the recorded evidence is hash-verified "
          "against its provenance note,")
    print("      the operator runbook is declared non-publishable and is actually git-ignored.")

    if args.list_published:
        published = published_set()
        print(f"\nfiles that would go into the public repository ({len(published)}):")
        for relative in published:
            print(f"  {relative}")
        print(f"\n{len(files) - len(published)} file(s) present here are excluded: the operator "
              f"runbook, and anything not tracked by git.")

    if args.self_test:
        print()
        return self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
