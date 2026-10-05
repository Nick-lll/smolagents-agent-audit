# Reproduction

Everything here was measured on the pinned revision and can be re-measured from a fresh
clone. No step needs an API key, a GPU, or network access after the initial clone.

## Requirements

| requirement | value |
|---|---|
| Python | 3.10 or newer (measured on 3.13.13) |
| git | needed once, to obtain the pinned revision |
| disk | about 200 MB for the clone |
| network | needed once, for the clone only |
| API key | none |
| GPU | none |

Runtime dependencies are the audited package's own: `huggingface-hub`, `requests`, `rich`,
`jinja2`, `pillow`, `python-dotenv`. The harness itself imports only the standard library
plus the package under test. Measured versions at the time of the recorded run are in
`findings/raw/PIP_FREEZE.txt`.

## Pinned upstream revisions

| project | commit | date | `git describe` |
|---|---|---|---|
| `huggingface/smolagents` | `c30b115286e000e98711fae5e85993547b73d826` | 2026-09-30T07:07:22+02:00 | `v1.0.0-936-gc30b115` |
| `crewAIInc/crewAI` (cloned, set aside, not audited) | `738c8e19e35c2888d8e0663bc5cc45c5acf6ac2d` | — | — |

**This pin was still upstream's tip on 2026-10-05.** `git ls-remote --symref
https://github.com/huggingface/smolagents HEAD` resolves to `refs/heads/main` at
`c30b115286e000e98711fae5e85993547b73d826`, so the revision audited here is the latest upstream
revision as of that date and the four findings were re-verified there rather than only assumed
to hold; the record is `findings/recertification/RERUN_2026-10-05_latest_upstream_revision.md`.
The latest released tag is `v1.26.0` (`12c1bc8`, 2026-05-29), which is **not** an ancestor of
`main` and is older than this pin, so it was deliberately not audited. If upstream moves, this
pin becomes a historical revision and the recorded artifacts describe it and nothing later.

`crewAI` was cloned while choosing a target and then set aside, because every crew or flow
run needs a live LLM provider and stubbing enough to avoid that would stop the audited path
from being the real one. Nothing in this repository claims anything about `crewAI`.

## Commands

```sh
python scripts/fetch_targets.py   # clones the audited revision and checks the commit out
python run.py                     # runs the audit; prints verdicts; writes artifacts
```

`run.py` writes `harness/runs/run_<UTC timestamp>/RESULTS.json` and `RESULTS.md`. It never
overwrites an existing artifact: a run pointed at an already-populated `--outdir` exits
non-zero with "refusing to overwrite existing artifact" rather than destroying evidence.

To audit a clone you already have instead of fetching a new one:

```sh
SMOLAGENTS_ROOT=/path/to/your/smolagents python run.py      # POSIX
$env:SMOLAGENTS_ROOT='<path to your clone>'; python run.py  # PowerShell
```

The commit is checked either way. `SMOLAGENTS_ALLOW_ANY_COMMIT=1` bypasses the check for
exploration; a result produced that way must never be published, because the controls were
measured against the pinned revision.

## Expected output

A successful run prints six sections: schema self-test, pristine check, criteria, the
discrimination test, the false-alarm examinations, and a summary. The summary for the
recorded run is:

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

`broken_controls` must be empty for a published result. A non-empty `broken_controls` means
a check failed to run, which is a fact about the harness and not about the target; treat any
such run as void and fix the harness first. Exit status is 0 when the harness ran to
completion whatever the verdicts were, 1 when it could not run at all (missing checkout,
wrong commit, corrected variant still bound), and 2 when it refused to overwrite an
artifact.

## Measured reproduction rate

| quantity | measured value |
|---|---|
| criteria written | 4 |
| criteria reproduced (defect shown on the pinned revision **and** the correction flips the check) | 4 of 4 |
| controls executed | 11 |
| controls broken (`CONTROL_ERROR` / `CONTROL_PRECONDITION_FAILED`) | 0 |
| candidate `except` handlers that do not re-raise (population, measured from the syntax tree) | 37 |
| of those, exercised with an executable check | 11 |
| of those 11, reproduced as defects | 4 |
| of those 11, rejected as false alarms with evidence | 7 |
| schema self-test criteria passed | 6 of 6 |
| reproduction rate of the four claims over repeated runs | **4 of 4 in each recorded run** |

The reproduction rate is stated as a full pass because repeated runs reproduced all four
claims every time, with the artifacts kept under `findings/raw/`. Two honest qualifications
belong with that number:

- **The four claims are not equally strong.** Two of them (`F3`, `F4`) rest partly on a
  judgement about intended behaviour rather than on measurement alone. Their finding
  directories say so explicitly.
- **A run recorded during this work did report `C4` as NOT PASS.** That run overlapped with
  an unrelated process that was rewriting the audited file on disk, which moved the method
  the corrected variant is compiled from and made the mutant report a different outcome.
  The instability was investigated, not explained away: the same scenario was then run six
  consecutive times in a fresh process and produced the identical result every time. The
  practical consequence for a reproducer is that the audited checkout must not be modified
  while the audit runs. The harness already refuses to grade when a corrected variant is
  still bound, but it cannot detect a concurrent editor.

## Cost

Zero. No paid model call is made anywhere in this repository, and the recorded run's spend
is 0.0. The stub `Model` subclasses raise instead of contacting a provider.

## What a reproducer should check first

1. `harness/runs/<...>/RESULTS.json` → `pinned_revision.commit` equals the pin above.
2. `pinned_revision.packages_audited` → the seven SHA-256 values match the table in
   `findings/raw/REPORT_public_audit_final.md` §10, so the audited text is the text here.
3. `summary.broken_controls` is empty.
4. `schema_self_test.all_passed` is `true`, so the verdict vocabulary discriminated in this
   run and not only on the author's machine.
