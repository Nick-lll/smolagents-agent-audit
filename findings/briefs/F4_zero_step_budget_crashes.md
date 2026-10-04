# F4 — a zero step budget raises `UnboundLocalError` from the framework's own bookkeeping

**Status:** `reproduced`
**Criterion in the harness:** `C4_zero_step_budget_crashes_the_run`
**Evidence class:** the crash is measured. Whether a zero budget is inside the documented
contract is a design choice, and this finding does not decide it.
**Upstream repository:** `huggingface/smolagents` at `c30b115286e000e98711fae5e85993547b73d826`

## Claim

A zero step budget makes `run()` raise `UnboundLocalError` instead of producing the fallback
answer, so the caller receives an internal variable name rather than an answer or an explicit
error.

## What was measured

```json
{
  "max_steps": 0,
  "healthy_calls": 0,
  "raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value",
  "output": null,
  "state": null,
  "generate_calls": 1,
  "call_purposes": ["fallback_answer_prompt"]
}
```

With a **live** fallback model (`healthy_calls=1`) the outcome is the same crash:

```json
{"max_steps": 0, "healthy_calls": 1,
 "raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value",
 "output": null, "generate_calls": 1, "call_purposes": ["fallback_answer_prompt"]}
```

The fallback model call already happened before the crash, so the work was done and then
discarded. The exception reaches the caller with a Python-internal variable name, not with a
message about step budgets.

## Controls

| control | role | status | what it establishes |
|---|---|---|---|
| `C4a_pinned_zero_budget_raises_UnboundLocalError` | demonstrates the defect | `PASS` | on the pinned revision `max_steps=0` raises `UnboundLocalError` naming `action_step` |
| `C4b_correction_returns_the_fallback_answer` | rejects the defect | `PASS` | with the correction the same configuration returns the answer the model actually produced (`"Let me keep working."`), not an error string |

`C4b` deliberately asserts that the output is the **model's text**, not merely "not None".
Asserting only `output is not None` would accept exactly the failure-disguised-as-an-answer
outcome this audit is about; the control would then pass for the wrong reason.

## The correction that flips the check

`MultiStepAgent._run_stream`: with a zero step budget, do not re-yield an `action_step` that
was never bound. Applied in memory only; not a submitted patch.

## What would be correct

Either validate `max_steps >= 1` where the agent is constructed, or do not re-yield an
`action_step` that was never created. A caller must never see `UnboundLocalError` from the
framework's own bookkeeping.

## What this does not prove

- **A zero step budget is a boundary, not the documented default.** The default is 20 steps.
  A maintainer can reasonably reply that `max_steps=0` is out of contract and that rejecting
  it at construction is the fix they would choose. That reply does not change the measured
  crash; it changes which fix is appropriate, and the finding's status should then record the
  disagreement as `disputed` per `../../DISCLOSURE.md`.
- **Not proven: that any realistic caller sets a zero budget.** The defect was reached by
  direct configuration. How likely that configuration is in the wild was not measured and is
  not claimed.
- **Not proven: that the same class of crash exists for other boundary values.** Only
  `max_steps=0` was executed.
- **Not inferred.** The crash is executed, and so is its disappearance under the correction.

## Evidence sites

- `src/smolagents/agents.py` — `_run_stream` yields `action_step` after the loop
- `src/smolagents/agents.py` — `run()` declares `max_steps = max_steps or self.max_steps`

## Raw evidence

- `../../raw/RESULTS.json` → `audit.criteria[name=C4_...]`
- `REPORT_public_audit_final.md` §4 F4
- Reader-facing brief: `../slots/BRIEFS_PENDING.md`
