# Provenance of the recorded evidence

This file says exactly where each recorded artifact came from, what its hash is, and what was
changed or left out. It exists so a reader can tell a measurement from a copy of a measurement,
and so nothing is "cleaned up" without saying so.

## What is where

| artifact | location | bytes | SHA-256 (first 16) | copied from | produced by |
|---|---|---|---|---|---|
| `RESULTS.json` | `raw/RESULTS.json` | 60219 | `D9845A27D3C7CD03` | `harness/runs/run_20261004T032929Z/RESULTS.json`, in this package | a run of `run.py` here, on the pinned revision |
| `RESULTS.md` | `raw/RESULTS.md` | 14482 | `110BA190BD865FD5` | `harness/runs/run_20261004T032929Z/RESULTS.md`, in this package | the same run |
| `PIP_FREEZE.txt` | `raw/PIP_FREEZE.txt` | 577 | `FC49DBFCD6B0D846` | the recorded run's `PIP_FREEZE.txt` | the audit environment's `pip freeze` (re-encoded; see below) |
| `REPORT_public_audit_final.md` | `briefs/REPORT_public_audit_final.md` | 31979 | `AF35091D34EB0DC8` | the audit's authored report | the audit's write-up, rendered from a recorded artifact (edited; see below) |

`verify_package.py` checks all four hashes, so an edited "recorded" file cannot pass as the
original.

The two `RESULTS.*` files come from a run of **this package**, so they also demonstrate that the
package as shipped reproduces the findings. Their summary:

```json
{
  "criteria": 4,
  "controls": 11,
  "criteria_passed": 4,
  "criteria_failed": [],
  "broken_controls": [],
  "false_alarms": 7,
  "schema_self_test_passed": true
}
```

## Change 1: `PIP_FREEZE.txt` was re-encoded

It arrived as **UTF-16 with a byte-order mark**, because it was written by a shell redirection on
Windows rather than by `pip` itself. A text file that a stranger's editor reads as mojibake is a
file a stranger cannot check, so it was re-encoded to UTF-8 with LF line endings. **No line of
content was added, removed or reordered**; the 29 package lines are the original lines. Two
hashes are recorded so the transformation is checkable rather than asserted:

| revision | SHA-256 (first 16) |
|---|---|
| as received, UTF-16 with BOM | `89679AD33C1A737D` |
| as shipped here, UTF-8 with LF | `FC49DBFCD6B0D846` |

## Change 2: the authored report's local paths were canonicalised

The authored report referred to the authoring machine in seven places: the paths of the audited
clone, the sibling `crewAI` clone, the reproduction commands' working directory, the module under
test, a mutant location, and the sentence recording where the audit was allowed to write. Those
seven references were replaced with canonical placeholders such as `<smolagents clone>` and
`<clone root>`, or rewritten to be path-free.

**What was NOT changed:** every measurement, every quoted observation, every verdict, every
count, every hash, and every file:line reference. The edit is a substitution of local filesystem
paths only, and the finding documents under `briefs/` quote their observations from
`raw/RESULTS.json`, which is untouched. Two hashes are recorded so the transformation is
checkable:

| revision | SHA-256 (first 16) |
|---|---|
| as authored | `CD0227C2CC9A5A68` |
| as shipped here, local paths canonicalised | `AF35091D34EB0DC8` |

The alternative — shipping the authored bytes and exempting them from the leak scan — was
rejected because a public repository must not carry the author's filesystem layout, and the
alternative of dropping the report entirely would remove the only narrative account of §§7–8
("what this audit does NOT prove", "what could not be tested").

## Deliberately excluded, and why

- **The recorded run's `STDOUT.txt` (21152 bytes, `824F1BCF0846F26B`) and its empty `STDERR.txt`**
  are not copied in. The console log echoes the absolute paths of the machine that produced it,
  and editing a log to remove evidence would make it a different artifact from the one the
  findings cite. Run `run.py` and the equivalent log appears under `harness/runs/` with your own
  paths in it. The two `RESULTS.*` files carry everything the findings actually quote.
- **The authoring machine's own `RESULTS.json`** is not copied in, because its
  `pinned_revision.command` and mutant locations embed absolute local paths and it is superseded
  by this package's own run. Its `RESULTS.md` is byte-identical to the copy kept here, which is
  why that copy is the one kept.
- **No upstream source file is vendored.** The harness imports the audited package and reads
  method source text at run time. No part of the audited project is redistributed here.

## Harness revision behind the recorded artifacts

The authored report was rendered from a slightly earlier revision of the harness than the one
shipped here. The current harness adds a population census over the shipped package and the
portability changes described in `harness/PORTABILITY.md`. Both revisions were run and both
report the same verdicts: 4 of 4 claims reproduced, 11 controls, 0 broken controls, and a passing
6-criteria schema self-test. The difference between the revisions is extra evidence, not a
different result, and the copies under `raw/` are what the findings quote.
