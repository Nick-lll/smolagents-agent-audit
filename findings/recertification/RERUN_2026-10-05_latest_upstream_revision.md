# Re-run at the latest upstream revision: all four findings still `reproduced`

**Measured 2026-10-05 (UTC).** This file exists because the audit's public notice to the
maintainer states, in the sent body, that *"One finding is a real defect at one call site;
two are contract questions we flag as such."* That sentence was measured against the pinned
revision `c30b115286e000e98711fae5e85993547b73d826`. A claim measured against one revision
does not stay true if upstream moves, so the checks were re-run against upstream's current
tip. Nothing here is a new criterion, a new control, or a new mutant: the harness, the four
criteria, the eleven controls, the four corrected variants and the false-alarm examinations
are exactly those shipped in this repository at `3f4e6080`.

## Headline

**Upstream `main` has not moved since the audit. The pinned commit `c30b1152` *is* the
current tip of `origin/main`, verified against the public remote on 2026-10-05.** All four
findings reproduce at the latest upstream revision, because the latest upstream revision is
the revision that was audited. The public sentence above is therefore still true, word for
word, and no finding's status changes.

## The two revisions, with dates

| what | commit | date |
|---|---|---|
| pinned revision audited and published (`REPRODUCE.md`) | `c30b115286e000e98711fae5e85993547b73d826` | commit date `2026-09-30T07:07:22+02:00` |
| latest upstream `main`, queried 2026-10-05 | `c30b115286e000e98711fae5e85993547b73d826` | same commit |
| latest released tag, queried 2026-10-05 | `v1.26.0` = `12c1bc820eca50ace6f80a21d90426d41d74f845` | commit date `2026-05-29T07:08:24+02:00` |

How "latest upstream `main`" was established, so a reader can repeat it:

```sh
git ls-remote --symref https://github.com/huggingface/smolagents HEAD
# ref: refs/heads/main	HEAD
# c30b115286e000e98711fae5e85993547b73d826	HEAD
git ls-remote https://github.com/huggingface/smolagents refs/heads/main
# c30b115286e000e98711fae5e85993547b73d826	refs/heads/main
git ls-remote --tags https://github.com/huggingface/smolagents | grep 'refs/tags/v1\.2[4-9]'
# ... v1.24.0, v1.25.0, v1.26.0  (no newer tag exists)
```

Two facts about the tag that belong with the numbers, because they are not what the word
"latest" suggests:

- **There is no tag newer than `v1.26.0`, and `v1.26.0` is not an ancestor of `main`.** The
  two histories diverged: `main` contains `406520d` *Bump dev version: v1.27.0.dev0* and
  twelve further commits, while the `v1.26.0` release commit `12c1bc8` sits on
  `origin/v1.26-release` and is the single commit reachable from the tag but not from `main`.
  So "the latest released tag" is **not** a newer revision than the pin; it is an older,
  divergent one, and re-running the audit there would be an audit of a *different, older*
  revision rather than of "latest". It was therefore not run.
- `main` is the development line: `pyproject.toml` at the pin declares
  `version = "1.27.0.dev0"`, which is what the sent notice's parenthetical `(v1.27.0.dev0)`
  refers to.

## What was re-run, and on what

The audited project was checked out **twice, in two separate clones**, and the harness was
run against both **in the same Python interpreter, in the same session, one immediately after
the other**, so that any difference between the two runs could only be attributed to the
checkout. Both clones were created for this re-run; the auditor's other working repository
and the published repository's own checkout were left untouched.

| | run A | run B |
|---|---|---|
| audited checkout | the original audit clone | a fresh clone made 2026-10-05, checked out with `git checkout --detach c30b115286e…` |
| worktree cleanliness | `?? audit/` (a gitignored scratch dir that predates this work) | clean |
| `git rev-parse HEAD` | `c30b115286e000e98711fae5e85993547b73d826` | `c30b115286e000e98711fae5e85993547b73d826` |
| `git describe --tags --always` | `v1.0.0-936-gc30b115` | `v1.0.0-936-gc30b115` |
| harness | `3f4e608015d80a12121dfc46e571389edfe1a5b0` (a clone of the published repo, `findings/raw/` untouched) | the same |
| interpreter | the recorded run's own venv, Python 3.13.13 | the same |

Local filesystem paths are deliberately not printed here, for the same reason
`raw/PROVENANCE.md` gives: a public repository should not carry the author's layout.

The two working trees are **the same tree**: `git rev-parse HEAD^{tree}` returns
`a90b244d123ec44f27d04ea3d5f0f65051e14528` for both, and the seven audited files hash
identically in both, e.g. `src/smolagents/agents.py` = `d4f40408e0e55dc4…` in each. Run B's
checkout carries no untracked `audit/` directory, so it is the cleaner of the two witnesses;
run A is the one whose environment is byte-identical to the recorded run, since it is the
same checkout and the same interpreter.

Artifacts (one directory per run, nothing overwritten; both under the audit workspace's
re-run directory, which is not part of this published repository):

```
runA_pinned_original_clone_20261005T090830Z/{RESULTS.json,RESULTS.md,CONSOLE_stdout.txt,CONSOLE_stderr.txt}
runB_pinned_freshclone_20261005T090830Z/{RESULTS.json,RESULTS.md,CONSOLE_stdout.txt,CONSOLE_stderr.txt}
```

## Result, per finding

Both runs are identical in every verdict, every control status and every measured value. The
harness's own summary is the same in both, and it is the same summary `REPRODUCE.md`
documents:

```json
{"criteria": 4, "controls": 11, "criteria_passed": 4, "criteria_failed": [],
 "broken_controls": [], "false_alarms": 7, "schema_self_test_passed": true}
```

| finding | criterion | status at the latest revision | the observation, re-measured 2026-10-05 |
|---|---|---|---|
| `F1` fallback answer swallows a model failure | `C1_model_failure_during_fallback_answer_is_swallowed` | **`reproduced`** | `run()` returns normally with `output` = `[{"type": "text", "text": "Error in generating final LLM output: Connection reset by peer (simulated endpoint death)"}]`, `state` = `max_steps_error`, `generate_calls` = 2 with purposes `["action_step_prompt", "fallback_answer_prompt"]`; with corrected variant A the same scenario raises `AgentGenerationError` and yields no output |
| `F2` fallback failure reported as a step limit | `C2_fallback_failure_is_reported_as_a_step_limit_error` | **`reproduced`** | `state` = `max_steps_error` with `failure_reason_in_state` = `false` and `failure_reason_in_step_errors` = `false`; the reason survives only in the answer text. With corrected variant E the reason becomes reachable in a step error (`AgentError: ConnectionError: Connection reset by peer…`) |
| `F3` empty answer reported as success | `C3_run_without_an_answer_reports_success` | **`reproduced`** | `output` = `None`, `output_is_none` = `true`, `state` = `success`, `step_errors` = `[null, null]`; the contrast control still labels a real answer (`"5"`) `success` with the answer kept, so this is not a generic "the run was broken" signal |
| `F4` zero step budget crashes | `C4_zero_step_budget_crashes_the_run` | **`reproduced`** | `max_steps=0` raises `UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value` after one `generate()` call whose purpose is `fallback_answer_prompt`; with corrected variant D the run returns the text the model actually produced (`"Let me keep working."`) |

No finding moved to `not reproduced`, `disputed` or `withdrawn`. The vocabulary is the one
`findings/README.md` fixes, and the reason no status changed is not that the re-run agreed
with the old one — it is that **there was nothing new to disagree with: the revision is the
same revision.**

Supporting detail, identical in both runs:

- 11 of 11 controls `PASS`; `C1c`, `C2b`, `C2c`, `C3c`, `C4b` (the corrected-variant controls)
  all bound and fired; `broken_controls` empty; 6 of 6 schema self-test criteria pass.
- The corrected variants were applied in memory against the same method lines in both runs:
  `src/smolagents/agents.py:849`, `:846`, `:634`, `:523`, `:607`.
- The population census is identical: 18 Python files scanned, 89 `except` handlers, 37 that
  do not re-raise — the same 37 line numbers in both runs.
- The discrimination test still goes red when the F1 guard is replaced by a transparent
  re-raise, which is what makes `C1` a measurement rather than a code reading.

## What this re-run does not prove

- **It does not prove the findings hold on any revision other than the pin**, because the pin
  is still upstream's tip. It proves the claim has not *lapsed*. If upstream pushes a commit
  tomorrow, this file becomes a record about `c30b1152` again and the sentence below needs the
  same treatment again.
- **It does not audit the `v1.26.0` tag**, deliberately: that tag is not an ancestor of `main`
  and is four months older than the pin, so it is not "the latest revision" by any reading.
- **It does not claim upstream has read or accepted anything.** No maintainer contact,
  issue, or pull request was made for this re-run, and none is claimed.
- The provider's own retry and error taxonomy remains unexercised, exactly as `README.md`
  §"What these checks do NOT prove" says. Nothing about that changed.
