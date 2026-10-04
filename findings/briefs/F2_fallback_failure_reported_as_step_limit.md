# F2 — the run state cannot distinguish "out of steps" from "the model never answered"

**Status:** `reproduced`
**Criterion in the harness:** `C2_fallback_failure_is_reported_as_a_step_limit_error`
**Evidence class:** measured; the step-limit label itself is intended behaviour, so part of
this finding is about what the label omits, not about the label being wrong.
**Upstream repository:** `huggingface/smolagents` at `c30b115286e000e98711fae5e85993547b73d826`

## Claim

The returned `RunResult.state` cannot distinguish "the step budget ran out" from "the model
never answered": both are reported as `max_steps_error`, while the failure reason survives
only inside the answer text.

## What was measured

```json
{
  "state": "max_steps_error",
  "failure_reason_in_state": false,
  "failure_reason_in_step_errors": false,
  "failure_reason_in_output": true,
  "step_errors": [null, null, {"type": "AgentMaxStepsError", "message": "Reached max steps."}],
  "generate_calls": 2,
  "call_purposes": ["action_step_prompt", "fallback_answer_prompt"]
}
```

This shares F1's code site but asserts a separable property: F1 is about the failure being
turned into a value, F2 is about the run's own bookkeeping being unable to name it. A caller
that branches on `state` alone — which is what the field is for — learns "the budget ran out"
even when the truth is "the model was unreachable".

## Controls

| control | role | status | what it establishes |
|---|---|---|---|
| `C2a_state_says_step_limit_and_nothing_else` | demonstrates the defect | `PASS` | on the pinned revision `state` is `max_steps_error` and no step error names the failure |
| `C2b_correction_makes_the_failure_reachable` | rejects the defect | `PASS` | with the re-raise correction the failure reaches the caller as a raised exception |
| `C2c_correction_makes_the_reason_reachable` | rejects the defect | `PASS` | with the bookkeeping correction the reason becomes reachable in the step errors (`AgentError: ConnectionError: Connection reset by peer (simulated endpoint death)`) |

Two should-fail controls were needed here, because the claim has two halves: that the failure
is invisible in the run's own state, and that a correction can make it visible.

## The corrections that flip the check

1. `MultiStepAgent.provide_final_answer`: re-raise instead of returning the error text
   (shared with F1).
2. `provide_final_answer` plus `_handle_max_steps_reached`: record the generation failure on
   the step that consumed the remaining budget, so `step_errors` names it and `state` can be
   derived from something other than "the last step hit the budget".

Both are applied in memory only and are not submitted patches.

## What would be correct

Either derive `state` from whether the run produced an answer, or record the generation
failure on the step that consumed the remaining budget. Either way, a consumer reading only
`state` and `step_errors` must be able to learn that the model failed.

## What this does not prove

- **The step-limit label itself is not claimed to be a defect.** Ending the run when the
  budget is exhausted is intended. The audited property is that this label is the *only*
  machine-readable signal, and it does not mention the failure that actually prevented an
  answer.
- **Not proven: that providers distinguish these cases for the framework.** Same stub-model
  limitation as F1.
- **Not proven: that every failure class is equally affected.** What was executed is an
  endpoint that dies mid-run; the claim is about how that failure is recorded.

## Evidence sites

- `src/smolagents/agents.py` — `run()` computes `state` from only the last step's error
- `src/smolagents/agents.py` — `_handle_max_steps_reached` records only `AgentMaxStepsError`

## Raw evidence

- `../../raw/RESULTS.json` → `audit.criteria[name=C2_...]`
- `REPORT_public_audit_final.md` §4 F2
- Reader-facing brief: `../slots/BRIEFS_PENDING.md`
