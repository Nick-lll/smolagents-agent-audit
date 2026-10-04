# F3 — a run that answers nothing is labelled success

**Status:** `reproduced`
**Criterion in the harness:** `C3_run_without_an_answer_reports_success`
**Evidence class:** the conjunction is measured; the judgement that `None` is never a
legitimate answer is a **convention**, and a maintainer can reasonably dispute it. Read the
"what this does not prove" section before quoting this finding.
**Upstream repository:** `huggingface/smolagents` at `c30b115286e000e98711fae5e85993547b73d826`

## Claim

A run whose final answer carries nothing (`final_answer` with no usable payload, or a `None`
answer) returns `output=None` together with `state='success'`, so a caller that trusts the
status has no way to learn that the agent answered nothing.

## What was measured

Both agent classes, two payloads:

```json
{"agent_class": "ToolCallingAgent", "payload": "None", "output": null, "output_is_none": true,
 "state": "success", "step_errors": [null, null], "is_final_answer_flags": [null, true], "run_steps": 2}
```

```json
{"agent_class": "CodeAgent", "payload": "None", "output": null, "output_is_none": true,
 "state": "success", "step_errors": [null, null], "is_final_answer_flags": [null, true], "run_steps": 2}
```

An empty-string payload gives `output=""` with `state="success"` as well. The step that is
flagged `is_final_answer: true` carries no error.

## Controls

| control | role | status | what it establishes |
|---|---|---|---|
| `C3a_pinned_success_label_with_none_answer` | demonstrates the defect | `PASS` | on the pinned revision `output=None` comes with `state="success"` and no step error |
| `C3b_control_the_label_does_track_a_real_answer` | demonstrates the defect (control clause) | `PASS` | the same machinery labels a real answer `success` and keeps the answer, so the harness is not merely observing a broken run |
| `C3c_correction_stops_calling_it_success` | rejects the defect | `PASS` | with the correction the `None`-answer run reports `state="incomplete"` |

`C3b` is a control in the ordinary sense: it shows the label is not simply always wrong. It
exists because "the state field is broken" and "the state field is wrong for this case" are
different claims, and only the second is made here.

## The correction that flips the check

`MultiStepAgent.run`: a run whose final answer is `None` is not labelled `success`. Applied in
memory only; not a submitted patch.

## What would be correct

A run that produced no answer should say so in its status, or the status vocabulary should
make clear that `success` means only "the loop completed". Either fix is fine; what is wrong
is a status field that a caller cannot use to detect an empty answer.

## What this does not prove

- **This is the weakest of the four claims, on purpose stated plainly.** Whether `None` is a
  legitimate final answer is a **convention, not a measurement**. A framework can argue that
  an agent answering `None` is a successful run of an agent that answered `None`. What *is*
  measured is the conjunction: `output is None` **and** `state == "success"` **and** no step
  error. A maintainer who writes "an empty answer is a legitimate answer" is disagreeing with
  the convention, not with the measurement, and the finding's status should then become
  `disputed` with their position recorded — see `../../DISCLOSURE.md`.
- **Not proven: that a caller cannot detect this another way.** A caller can always inspect
  `output is None`. The claim is that the status field does not do it, not that detection is
  impossible.
- **Not proven: that the empty-string case matters.** It is reported for completeness; the
  claim rests on the `None` case.
- **Not inferred.** The `None`-answer run and its relabelling under the correction were both
  executed.

## Evidence sites

- `src/smolagents/agents.py` — `run()` labels the run from step bookkeeping, not from whether
  an answer exists

## Raw evidence

- `../../raw/RESULTS.json` → `audit.criteria[name=C3_...]`
- `REPORT_public_audit_final.md` §4 F3
- Reader-facing brief: `../slots/BRIEFS_PENDING.md`
