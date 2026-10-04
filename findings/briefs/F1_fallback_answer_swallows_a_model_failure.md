# F1 — a model failure on the fallback answer becomes the answer

**Status:** `reproduced`
**Criterion in the harness:** `C1_model_failure_during_fallback_answer_is_swallowed`
**Evidence class:** fully measured — both the wrong outcome and its disappearance under the
correction were executed.
**Upstream repository:** `huggingface/smolagents` at `c30b115286e000e98711fae5e85993547b73d826`

## Claim

When the model endpoint fails on the call that produces the fallback final answer, `run()`
returns normally with the error text as the answer instead of raising, and no part of the
returned result identifies a generation failure.

## What was measured

`max_steps=1`, endpoint healthy for the first call and dead afterwards (a quota exhaustion or
an expired credential, not a first-call failure, which the framework handles correctly):

```json
{
  "raised": null,
  "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]",
  "state": "max_steps_error",
  "step_errors": [null, null, {"type": "AgentMaxStepsError", "message": "Reached max steps."}],
  "failure_reason_in_state": false,
  "failure_reason_in_step_errors": false,
  "failure_reason_in_output": true,
  "generate_calls": 2,
  "call_purposes": ["action_step_prompt", "fallback_answer_prompt"]
}
```

The run does not raise. The only signal that the model never answered is the prose inside the
answer, and the string `"Error in generating final LLM output:"` is not machine-readable
state. `CodeAgent` behaves identically.

## Controls

| control | role | status | what it establishes |
|---|---|---|---|
| `C1a_pinned_run_returns_error_text_as_the_answer` | demonstrates the defect | `PASS` | the run returns normally and its output carries the raw error text |
| `C1b_pinned_run_records_no_machine_readable_failure` | demonstrates the defect | `PASS` | no field of the returned result names the generation failure |
| `C1c_correction_raises_instead_of_answering` | rejects the defect | `PASS` | with the correction, the same failure raises `AgentGenerationError` out of `run()` and yields no output |

`C1c` is the should-fail control: without it, the claim that the failure is *swallowed* would
be unsupported, because the harness would never have shown the failure being raised.

## The correction that flips the check

`MultiStepAgent.provide_final_answer`: re-raise a model failure instead of returning a
`ChatMessage` whose text is the error. This is what the framework already does for an
action-step generation failure — `_run_stream` re-raises `AgentGenerationError`, and the
project's own `tests/test_agents.py::test_generation_errors_are_raised` pins that. The
correction is applied in memory only; it is not a submitted patch.

## What would be correct

`provide_final_answer()` should let the generation failure out of the framework the same way
an action-step generation failure does. A caller must be able to tell "the agent used its
remaining budget" from "the model never answered".

## What this does not prove

- **Not proven: that a provider behaves this way in production.** The endpoint is a stub
  `Model` subclass that raises `ConnectionError`. The framework control flow is real; a
  provider that retries internally could change how often this path is reached, though not
  whether it swallows once reached.
- **Not proven: that the framework intends the error text to be machine-readable.** It
  plainly is not, and nothing in the project documents it as a signal.
- **Not inferred.** Both the swallowed outcome and its disappearance under the correction were
  executed. The conclusion that a caller cannot distinguish this from a real answer follows
  from the measured output text alone.

## Evidence sites

- `src/smolagents/agents.py` — `provide_final_answer` (`except Exception` → `ChatMessage` with
  the error text)
- `src/smolagents/agents.py` — `_handle_max_steps_reached` (the only caller)
- `src/smolagents/agents.py` — `_run_stream` (re-raises `AgentGenerationError` for action
  steps, which is what makes the asymmetry visible)

## Raw evidence

- `../../raw/RESULTS.json` → `audit.criteria[name=C1_...]`
- `REPORT_public_audit_final.md` §4 F1
- Reader-facing brief: `../slots/BRIEFS_PENDING.md`
