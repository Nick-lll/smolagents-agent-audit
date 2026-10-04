# Executable audit: huggingface/smolagents, failure-disguised-as-success

- pinned commit: `c30b115286e000e98711fae5e85993547b73d826` (2026-09-30T07:07:22+02:00)
- commit subject: fix(ci): harden GitHub Actions workflows (#2558) (#2868)
- audited revision dirty worktree: True
- python: 3.13.13 (tags/v3.13.13:01104ce, Apr  7 2026, 19:25:48) [MSC v.1944 64 bit (AMD64)]
- smolagents 1.27.0.dev0 from `E:\zeus_public_audit\smolagents\src\smolagents\__init__.py`
- network used: no. API key used: no. GPU used: no.

## Verdicts

| criterion | defect shown on pinned revision | correction removes it | verdict | broken controls |
|---|---|---|---|---|
| C1_model_failure_during_fallback_answer_is_swallowed | True | True | PASS | 0 |
| C2_fallback_failure_is_reported_as_a_step_limit_error | True | True | PASS | 0 |
| C3_run_without_an_answer_reports_success | True | True | PASS | 0 |
| C4_zero_step_budget_crashes_the_run | True | True | PASS | 0 |

## Controls

### C1_model_failure_during_fallback_answer_is_swallowed

claim: When the model endpoint fails on the call that produces the fallback final answer, run() returns normally with the error text as the answer instead of raising, and no part of the returned result identifies a generation failure.

verdict rule: PASS requires both: (a) on the pinned revision the run returns without raising and its output contains the raw error text; (b) on the corrected variant the same failure raises out of run().

- **C1a_pinned_run_returns_error_text_as_the_answer** [demonstrates_the_defect / state] -> `PASS`
  - checked: on the pinned revision, the dead endpoint produces a normal return whose output is the error text
  - expected assertion result: True; expectation: assertion is True on the pinned revision (defect reproduces)
  - precondition: the pinned revision still reaches provide_final_answer() and still swallows the failure there (run raises nothing and generate() was called twice) (held: True)
  - observed: `{"raised": null, "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]", "state": "max_steps_error", "call_purposes": ["action_step_prompt", "fallback_answer_prompt"]}`
- **C1b_pinned_run_records_no_machine_readable_failure** [demonstrates_the_defect / state] -> `PASS`
  - checked: no field of the returned RunResult names the generation failure
  - expected assertion result: True; expectation: the assertion's result must be True
  - precondition: same precondition as C1a (held: True)
  - observed: `{"failure_reason_in_state": false, "failure_reason_in_step_errors": false, "failure_reason_in_output": true, "step_errors": [null, null, {"type": "AgentMaxStepsError", "message": "Reached max steps."}]}`
- **C1c_correction_raises_instead_of_answering** [rejects_the_defect / reader] -> `PASS`
  - checked: with mutant A the same dead endpoint raises out of run() and yields no output
  - expected assertion result: True; expectation: assertion is True with the correction in place
  - mutation: MultiStepAgent.provide_final_answer: re-raise a model failure instead of returning the error text as the user-visible answer
  - edited at: edited E:\zeus_public_audit\smolagents\src\smolagents\agents.py:849
  - observed: `{"raised": "AgentGenerationError: Error in generating final LLM output:\nConnection reset by peer (simulated endpoint death)", "output": null, "output_is_none": true}`

### C2_fallback_failure_is_reported_as_a_step_limit_error

claim: The returned RunResult.state cannot distinguish 'the step budget ran out' from 'the model never answered': both are reported as max_steps_error while the failure reason survives only inside the answer text.

verdict rule: PASS requires both: (a) on the pinned revision state is max_steps_error and no step error names the failure; (b) on the corrected variant the failure becomes visible in state or in a step error.

- **C2a_state_says_step_limit_and_nothing_else** [demonstrates_the_defect / state] -> `PASS`
  - checked: on the pinned revision the run reports max_steps_error with the failure only inside the answer text
  - expected assertion result: True; expectation: the assertion's result must be True
  - precondition: the pinned revision still reports max_steps_error for this scenario (held: True)
  - observed: `{"state": "max_steps_error", "failure_reason_in_state": false, "failure_reason_in_step_errors": false, "step_errors": [null, null, {"type": "AgentMaxStepsError", "message": "Reached max steps."}]}`
- **C2b_correction_makes_the_failure_reachable** [rejects_the_defect / reader] -> `PASS`
  - checked: with mutant A the failure reason reaches the caller in the raised exception
  - expected assertion result: True; expectation: assertion is True with the correction in place
  - mutation: MultiStepAgent.provide_final_answer: re-raise a model failure instead of returning the error text as the user-visible answer
  - observed: `{"raised": "AgentGenerationError: Error in generating final LLM output:\nConnection reset by peer (simulated endpoint death)", "no_longer_silent": true}`
- **C2c_correction_makes_the_reason_reachable** [rejects_the_defect / reader] -> `PASS`
  - checked: with mutant E the failure reason appears in the returned state or in a step error
  - expected assertion result: True; expectation: assertion is True with the correction in place
  - mutation: MultiStepAgent.provide_final_answer plus _handle_max_steps_reached: record the generation failure on the step that consumed the remaining budget, and report it in the run state, so the reason for the fallback answer survives in the run's own bookkeeping instead of only inside the answer text
  - observed: `{"state_with_correction": "success", "step_errors_with_correction": [null, null, {"type": "AgentError", "message": "ConnectionError: Connection reset by peer (simulated endpoint death)"}], "failure_visible_with_correction": true}`

### C3_run_without_an_answer_reports_success

claim: A run whose final answer carries nothing (final_answer with no usable payload, or a None answer) returns output=None together with state='success', so a caller that trusts the status has no way to learn that the agent answered nothing.

verdict rule: PASS requires both: (a) on the pinned revision the None-answer run has output None and state success; (b) on the corrected variant such a run is not labelled success.

- **C3a_pinned_success_label_with_none_answer** [demonstrates_the_defect / state] -> `PASS`
  - checked: on the pinned revision output None comes with state success and no step error
  - expected assertion result: True; expectation: the assertion's result must be True
  - precondition: the pinned revision still returns state='success' for a None answer (held: True)
  - observed: `{"agent_class": "ToolCallingAgent", "output_repr": "None", "state": "success", "step_errors": [null, null], "is_final_answer_flags": [null, true], "code_agent_same": {"output_repr": "None", "state": "success"}}`
- **C3b_control_the_label_does_track_a_real_answer** [demonstrates_the_defect / reader] -> `PASS`
  - checked: CONTROL: the same machinery labels a real answer success and keeps the answer, so the harness is not simply seeing a broken run
  - expected assertion result: True; expectation: the assertion's result must be True
  - observed: `{"real_answer_output": "'5'", "real_answer_state": "success", "empty_string_output": "''", "empty_string_state": "success"}`
- **C3c_correction_stops_calling_it_success** [rejects_the_defect / reader] -> `PASS`
  - checked: with mutant C the None-answer run is no longer labelled success
  - expected assertion result: True; expectation: assertion is True with the correction in place
  - mutation: MultiStepAgent.run: a run whose final answer is None is not labelled success
  - observed: `{"state_with_correction": "incomplete", "output_with_correction": "None"}`

### C4_zero_step_budget_crashes_the_run

claim: A zero step budget makes run() raise UnboundLocalError instead of producing the fallback answer, so the caller receives an internal variable name rather than an answer or an explicit error.

verdict rule: PASS requires both: (a) on the pinned revision max_steps=0 raises UnboundLocalError naming action_step, after the fallback model call already happened; (b) on the corrected variant the same configuration returns the fallback answer.

- **C4a_pinned_zero_budget_raises_UnboundLocalError** [demonstrates_the_defect / state] -> `PASS`
  - checked: on the pinned revision max_steps=0 raises UnboundLocalError naming action_step
  - expected assertion result: True; expectation: the assertion's result must be True
  - precondition: the pinned revision still crashes with UnboundLocalError on action_step (held: True)
  - observed: `{"raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value", "generate_calls": 1, "call_purposes": ["fallback_answer_prompt"], "note": "the fallback model call already happened before the crash"}`
- **C4b_correction_returns_the_fallback_answer** [rejects_the_defect / reader] -> `PASS`
  - checked: with mutant D the zero-budget run returns the answer the model produced instead of crashing
  - expected assertion result: True; expectation: assertion is True with the correction in place
  - mutation: MultiStepAgent._run_stream: with a zero step budget, do not re-yield an action_step that was never bound
  - edited at: edited E:\zeus_public_audit\smolagents\src\smolagents\agents.py:849
  - observed: `{"raised_with_correction": null, "output_with_correction": "\"Let me keep working.\"", "is_the_model_answer": true, "call_purposes_with_correction": ["fallback_answer_prompt"], "state_with_correction": "max_steps_error"}`

## Discrimination test (guard replaced by transparent re-raise)

- guards examined: 1
- any check went red: True
- sites with no discriminating check: []
- G1 at src/smolagents/agents.py: provide_final_answer
  - guard: `except Exception as e: return ChatMessage(... error text ...)`
  - replaced by: a transparent re-raise (mutant A: the failure is no longer converted into a value)
  - check: C1a/C1b (pinned run returns the error text as the answer)
  - green with the guard in place: True
  - red with the guard replaced: True
  - verdict: the guard is load-bearing: replacing it flips at least one check from green to red, so the check set discriminates this guard

## False alarms (examined and rejected)

- **a dead model on an ordinary action step is swallowed**
  - verdict: rejected: the framework raises AgentGenerationError out of run()
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nConnection reset by peer (simulated endpoint death)", "generate_calls": 1}`
- **a TypeError wiring bug in a model adapter is absorbed**
  - verdict: rejected: it is wrapped into AgentGenerationError and raised
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nfalse_alarms.<locals>.WrongSignature.generate() got an unexpected keyword argument 'stop_sequences'"}`
- **malformed JSON in tool-call arguments corrupts the answer**
  - verdict: rejected: parse_json_if_needed returns unparsed text by design, and the docs plus tests/test_models.py::test_parse_json_if_needed pin that behaviour ('abc' -> 'abc'). The truncated fragment therefore arrives as a plain string, which the framework accepts as an answer because a bare string is a documented argument form for final_answer.
  - evidence: `{"parse_json_if_needed('{\"answer\": \"5')": "'{\"answer\": \"5'", "documented": "docs/source/en/guided_tour.md plus the tool-calling prompt examples", "test": "tests/test_models.py:312 test_parse_json_if_needed"}`
- **a tool failure is invisible and the run reports success anyway**
  - verdict: rejected: the tool failure is recorded on the step that hit it (AgentToolExecutionError), and feeding a failed tool call back to the model so it can retry is the ReAct design. The run state therefore describes the recovery, which is legitimate.
  - evidence: `{"state": "success", "step_errors": [null, {"type": "AgentToolExecutionError", "message": "Error executing tool 'boom' with arguments {}: RuntimeError: backend unavailable\nPlease try again or use another tool"}, null]}`
- **a boolean final_answer_check is inert, because the implementation wraps it in `assert` (a first code reading suggested assert would not fire on a False return)**
  - verdict: rejected by execution: assert fires on a False return, the guard's rejection is recorded as an AgentError on the step, and the run ends max_steps_error. The documented behaviour (log and continue the run) is what happens.
  - evidence: `{"guard_returns_false_for_bad_value": true, "guard_errors_recorded": [{"type": "AgentError", "message": "Check boolean_guard failed with error: "}], "guard_error_count": 4, "state": "max_steps_error"}`
- **an interpreter timeout is silently absorbed and the run reports success**
  - verdict: rejected as a swallowed failure: the timeout becomes a step observation (AgentExecutionError 'Code execution exceeded the maximum execution time'), so the model sees it and the caller can read it from steps[].error. The residual issue is real but is not this defect class: the run-level state still says success, and the abandoned interpreter thread cannot be stopped (documented in local_python_executor.timeout).
  - evidence: `{"state": "success", "output": "answered after a timeout", "wall_seconds": 2.51, "step_errors": [null, {"type": "AgentExecutionError", "message": "Code execution exceeded the maximum execution time of 1 seconds"}, null], "observations": ["None", "Execution logs:\ntick 0\ntick 1\n", "Execution logs:\nLast output from code snippet:\nanswered after a timeout"], "timed_out_code_wrote_its_marker": false}`
- **a mid-run endpoint death is swallowed as long as steps remain**
  - verdict: rejected: it raises AgentGenerationError out of run(). Only the fallback-answer call converts the same failure into a value.
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nConnection reset by peer (simulated endpoint death)", "generate_calls": 2}`

See REPORT_public_audit.md next to this file for the full write-up, including what this audit does not prove.
