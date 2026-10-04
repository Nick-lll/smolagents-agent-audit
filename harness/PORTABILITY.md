# What was changed to make the harness portable

The harness in this directory is the audit's own code, mirrored from the authoring tree and
then changed in exactly the ways listed below. Nothing about the criteria, the controls, the
corrected variants or the verdicts was touched. The purpose of the changes is that a stranger
can clone this repository and run it without knowing anything about the machine it was
written on.

## The changes

| file | change | why |
|---|---|---|
| `_setup.py` | new file | resolves the audited checkout relative to this repository and enforces the pinned commit |
| `three_state_audit.py` | the module docstring's run instructions now name `python run.py` instead of an absolute path on the authoring machine | a reader must not need the author's directory layout |
| `three_state_audit.py` | one import of `_setup` plus a call to `_setup.activate()` inserted **before** the audited package is imported | the audited clone's `src` has to be first on `sys.path` or a stale installed copy would be audited instead |
| `three_state_audit.py` | removed the hardcoded `REPO_ROOT` default that pointed at the authoring tree | that path is replaced by `_setup`'s resolution |
| `three_state_audit.py` | `git_pin()` now also records `pinned_commit_required`, `pinned_commit_found` and the upstream repository URL | a reader can see the pin and the checkout agree from the artifact itself, without trusting the console |
| `three_state_audit.py` | two `print` lines state the audited checkout and the commit before anything runs | so a pasted log says which revision produced it |
| `core.py` | docstring rewritten to describe the verdict vocabulary and the design rules without referencing the authoring project | the schema was described in terms of the tool that wrote it, which is exactly what a stranger cannot decode |
| `mutants.py` | **unchanged, byte for byte** | the corrected variants are the substance of the should-fail controls |

Measured difference against the authoring copies: `mutants.py` identical; `core.py` differs on
27 lines, all inside the module docstring and one control docstring; `three_state_audit.py`
differs on 35 lines, all of them the additions above.

## What was deliberately not changed

- **The criteria, the controls, the populations and the verdict rules.** Editing a control to
  make it run on a different machine would invalidate every recorded artifact.
- **The text of observations.** The recorded artifacts quote them.
- **The `SMOLAGENTS_ALLOW_ANY_COMMIT=1` escape hatch**, which is the only way to run against
  an unpinned checkout. It exists so that the pin check can be bypassed deliberately; a result
  produced with it must never be published, because the controls were measured against the
  pinned revision. This is stated in `_setup.py` and in `REPRODUCE.md`.
- **The decorative box-drawing characters in the original's comment banners**, which arrive
  mangled as mojibake in the original's encoding. They are cosmetic, inside comments, and
  regenerating them would change bytes that carry no meaning. Cosmetic cleanup of someone
  else's evidence is not worth a byte-level difference from the audited artifact.

## How the audit target is found

`_setup.locate_target_root()` tries, in order:

1. `$SMOLAGENTS_ROOT`, when set;
2. `hub/smolagents` next to this repository, which is the layout `scripts/fetch_targets.py`
   produces;
3. the current working directory, when it is itself a clone of the target.

A directory counts as a usable target only when it contains the audited package's source, not
merely a checkout of the repository. If none matches, the harness exits with the list of paths
it tried and the two commands that fix the problem, rather than failing later with an import
error.

## How the pin is enforced

`_setup.activate()` compares the checkout's `HEAD` against
`PINNED_SMOLAGENTS_COMMIT` and exits with the exact `git fetch` / `git checkout` commands
when they differ. This exists because a control is a statement about one revision: the STATE
controls re-assert their preconditions at run time precisely so that a control that no longer
applies says so instead of contributing a meaningless result. Running against an unpinned
revision would do exactly what that design forbids.

## Verified in this package

`python run.py` was run from this directory on the pinned revision and reproduced all four
claims: 4 criteria, 11 controls, 0 broken controls, schema self-test passing. The artifact of
that run is `findings/raw/RESULTS.json`, whose SHA-256 is pinned in
`findings/raw/PROVENANCE.md`. The same run was also verified to work with no environment
variable set, resolving the target through `hub/smolagents`, and the whole package was verified
to run from a fresh copy in a different directory with the fetched clone absent.

Two failures were also verified, because a check that has never been seen to fail is not
evidence:

- with the target absent, `run.py` exits 1 and prints the checkout locations it tried plus the
  two commands that fix the problem, instead of failing later with an import error;
- with the forbidden authoring-tree token reintroduced into `harness/_setup.py`, the package
  check reports it as an `authoring-tree reference` and an `absolute local path`, and exits 1.
  `verify_package.py --self-test` performs the equivalent injection into a throwaway copy on
  every run.
