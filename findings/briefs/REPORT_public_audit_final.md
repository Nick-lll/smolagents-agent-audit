# Public audit: huggingface/smolagents, a three-state verification of "failure disguised as success"

This document is the deliverable of a verification audit. It reports what was executed, what was observed, and what follows from those observations. Every number and every quoted value below is taken from the recorded artifact `RESULTS.json` of the run described in section 9; none of it is transcribed by hand.

## 1. What this is

An executable harness that looks for one specific defect class in a public AI agent framework: **a failure that is presented to the caller as a success**. It runs offline (no network, no API key, no GPU), it has a self-test for its own machinery, and every claim it makes carries a control that can fail.

## 2. The project chosen, and why

**huggingface/smolagents**, pinned at commit `c30b115286e000e98711fae5e85993547b73d826` (2026-09-30T07:07:22+02:00, v1.0.0-936-gc30b115), version `1.27.0.dev0`.

Evidence for the choice, all measured on the audit host:

- **Public and popular**: 29,666 GitHub stars, 7.4 MB of repository, language reported as Python (GitHub REST API, same session as the clone).
- **Python only, small enough for CPU-only work**: the audited tree is 7 files of interest totalling well under 1 MB; the runtime dependencies are huggingface-hub, requests, rich, jinja2, pillow and python-dotenv. Nothing here needs a GPU; the whole audit ran on the CPU of the audit host.
- **A real orchestration loop with error handling worth auditing**: the ReAct loop in `MultiStepAgent._run_stream` decides per step whether an `AgentError` is fed back to the model or raised, has a fallback-answer path when the step budget is exhausted, records per-step errors, and computes a run-level `state` that callers branch on. That is exactly the surface where a failure can be relabelled as a success.
- **Runnable without credentials**: `smolagents.models.Model` is a documented subclass point, and the project's own `tests/test_agents.py` drives the loop with hand-written `Model` subclasses. This audit uses the same technique, so the audited control flow is the real one and no paid API is ever called.

Candidates considered and why they were not chosen:

| project | stars | size | why not chosen |
|---|---|---|---|
| crewAIInc/crewAI | 59,326 | large multi-package monorepo | crew/flow orchestrators; needs an LLM provider for any run |
| microsoft/autogen | 61,250 | 148.7 MB | event-driven multi-agent runtime; Python surface still split across autogen-agentchat/autogen-core |
| langchain-ai/langgraph | 42,680 | 527.7 MB | graph execution engine; heavy dependency set |
| 567-labs/instructor | 13,972 | 79.6 MB | the project's kind of loop is the LLM-output layer: retries and validation, not an agent loop |

`crewAI` was cloned during this session (as a `crewAI` checkout sibling to the smolagents clone, commit `738c8e19e35c2888d8e0663bc5cc45c5acf6ac2d`) and set aside: every crew or flow run requires a live LLM provider, so any audit of its loop would either need a paid key or would have to stub so much that the audited path stops being the real one. smolagents lets a stub model drive the genuine loop.

## 3. Method

Three states, not two. Every control reports exactly one of:

- `PASS` / `FAIL` — the control ran and its assertion matched or contradicted its declared expectation;
- `CONTROL_ERROR` — the control itself raised. The original exception type, message and full traceback are recorded; a broken control is never silently a pass. This matters because a control that fails to run looks exactly like a target that failed;
- `CONTROL_PRECONDITION_FAILED` — a `STATE` control whose precondition no longer holds in this run. It does not execute its body and it is neither a pass nor a fail.

Every claim (a `Criterion`) needs two roles to be `PASS`: at least one control that **demonstrates the defect on the pinned revision**, and at least one control that **rejects the claim when a deliberately corrected variant is substituted in place**. If any control is broken or its precondition failed, the criterion cannot be `PASS`.

The corrected variants ("mutants") are produced by literal single-occurrence edits to the pristine in-memory source of the audited method, read with `inspect.getsourcelines` at run time. A replacement that matches zero times or more than once is refused with an error, and each mutant asserts that its injected text appears in the corrected source. Nothing on disk is modified: the corrected method is bound in memory and restored in a `finally` block, and the harness additionally verifies before grading that no corrected variant is still bound.

## 4. Findings

Four criteria, eleven controls, four reproduced defects. Each entry below gives the claim, the pinned-revision observation, and the correction that flips the control.

### F1. C1_model_failure_during_fallback_answer_is_swallowed

**Claim.** When the model endpoint fails on the call that produces the fallback final answer, run() returns normally with the error text as the answer instead of raising, and no part of the returned result identifies a generation failure.

**What was measured.**

```json
{
  "agent_class": "ToolCallingAgent",
  "max_steps": 1,
  "raised": null,
  "output": [
    {
      "type": "text",
      "text": "Error in generating final LLM output: Connection reset by peer (simulated endpoint death)"
    }
  ],
  "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]",
  "output_type": "list",
  "state": "max_steps_error",
  "token_usage_is_none": true,
  "step_errors": [
    null,
    null,
    {
      "type": "AgentMaxStepsError",
      "message": "Reached max steps."
    }
  ],
  "is_final_answer_flags": [
    null,
    false,
    false
  ],
  "failure_reason_in_state": false,
  "failure_reason_in_step_errors": false,
  "failure_reason_in_output": true,
  "generate_calls": 2,
  "call_purposes": [
    "action_step_prompt",
    "fallback_answer_prompt"
  ]
}
```

*pinned_revision_code_agent*:

```json
{
  "agent_class": "CodeAgent",
  "max_steps": 1,
  "raised": null,
  "output": [
    {
      "type": "text",
      "text": "Error in generating final LLM output: Connection reset by peer (simulated endpoint death)"
    }
  ],
  "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]",
  "state": "max_steps_error",
  "step_errors": [
    null,
    null,
    {
      "type": "AgentMaxStepsError",
      "message": "Reached max steps."
    }
  ],
  "failure_reason_in_output": true,
  "generate_calls": 2
}
```

**Controls.**

| control | role | state | assertion result |
|---|---|---|---|
| `C1a_pinned_run_returns_error_text_as_the_answer` | demonstrates_the_defect | `PASS` | observed: {"raised": null, "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]", "stat |
| `C1b_pinned_run_records_no_machine_readable_failure` | demonstrates_the_defect | `PASS` | observed: {"failure_reason_in_state": false, "failure_reason_in_step_errors": false, "failure_reason_in_output": true, "step_errors": [null, null, {"type": "AgentMaxSteps |
| `C1c_correction_raises_instead_of_answering` | rejects_the_defect | `PASS` | observed: {"raised": "AgentGenerationError: Error in generating final LLM output:\nConnection reset by peer (simulated endpoint death)", "output": null, "output_is_none": |

**Observed wrong-but-plausible outcome.** `{"raised": null, "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]", "state": "max_steps_error", "call_purposes": ["action_step_prompt", "fallback_answer_prompt"]}`

**What would be correct.** provide_final_answer() should let the generation failure out of the framework the same way an action-step generation failure does (_run_stream re-raises AgentGenerationError, and tests/test_agents.py::test_generation_errors_are_raised asserts that). A caller must be able to tell 'the agent used its remaining budget' from 'the model never answered'.

**What is inferred rather than measured.** Not inferred: both the swallowed outcome and its disappearance under the correction are executed. The claim that a caller cannot distinguish this from a real answer follows from the measured output text alone.

**Evidence sites.**

- src/smolagents/agents.py: provide_final_answer (except Exception -> ChatMessage with error text)
- src/smolagents/agents.py: _handle_max_steps_reached (the only caller)
- src/smolagents/agents.py: _run_stream (re-raises AgentGenerationError for action steps)

### F2. C2_fallback_failure_is_reported_as_a_step_limit_error

**Claim.** The returned RunResult.state cannot distinguish 'the step budget ran out' from 'the model never answered': both are reported as max_steps_error while the failure reason survives only inside the answer text.

**What was measured.**

```json
{
  "agent_class": "ToolCallingAgent",
  "max_steps": 1,
  "raised": null,
  "output": [
    {
      "type": "text",
      "text": "Error in generating final LLM output: Connection reset by peer (simulated endpoint death)"
    }
  ],
  "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]",
  "output_type": "list",
  "state": "max_steps_error",
  "token_usage_is_none": true,
  "step_errors": [
    null,
    null,
    {
      "type": "AgentMaxStepsError",
      "message": "Reached max steps."
    }
  ],
  "is_final_answer_flags": [
    null,
    false,
    false
  ],
  "failure_reason_in_state": false,
  "failure_reason_in_step_errors": false,
  "failure_reason_in_output": true,
  "generate_calls": 2,
  "call_purposes": [
    "action_step_prompt",
    "fallback_answer_prompt"
  ]
}
```

**Controls.**

| control | role | state | assertion result |
|---|---|---|---|
| `C2a_state_says_step_limit_and_nothing_else` | demonstrates_the_defect | `PASS` | observed: {"state": "max_steps_error", "failure_reason_in_state": false, "failure_reason_in_step_errors": false, "step_errors": [null, null, {"type": "AgentMaxStepsError" |
| `C2b_correction_makes_the_failure_reachable` | rejects_the_defect | `PASS` | observed: {"raised": "AgentGenerationError: Error in generating final LLM output:\nConnection reset by peer (simulated endpoint death)", "no_longer_silent": true} |
| `C2c_correction_makes_the_reason_reachable` | rejects_the_defect | `PASS` | observed: {"state_with_correction": "success", "step_errors_with_correction": [null, null, {"type": "AgentError", "message": "ConnectionError: Connection reset by peer (s |

**Observed wrong-but-plausible outcome.** `{"state": "max_steps_error", "failure_reason_in_state": false, "failure_reason_in_step_errors": false, "step_errors": [null, null, {"type": "AgentMaxStepsError", "message": "Reached max steps."}]}`

**What would be correct.** state should be derived from whether the run produced an answer, or the generation failure should be recorded on the step that consumed the remaining budget; either way a consumer reading only state/step errors must be able to learn that the model failed.

**What is inferred rather than measured.** The step-limit label itself is intended behaviour. The audited property is that the label is the only machine-readable signal and it does not mention the failure that actually prevented an answer.

**Evidence sites.**

- src/smolagents/agents.py: run() state computation reads only the last step's error
- src/smolagents/agents.py: _handle_max_steps_reached records only AgentMaxStepsError

### F3. C3_run_without_an_answer_reports_success

**Claim.** A run whose final answer carries nothing (final_answer with no usable payload, or a None answer) returns output=None together with state='success', so a caller that trusts the status has no way to learn that the agent answered nothing.

**What was measured.**

*tool_none_answer*:

```json
{
  "agent_class": "ToolCallingAgent",
  "payload": "None",
  "output": null,
  "output_repr": "None",
  "output_is_none": true,
  "state": "success",
  "step_errors": [
    null,
    null
  ],
  "is_final_answer_flags": [
    null,
    true
  ],
  "run_steps": 2
}
```

*code_none_answer*:

```json
{
  "agent_class": "CodeAgent",
  "payload": "None",
  "output": null,
  "output_repr": "None",
  "output_is_none": true,
  "state": "success",
  "step_errors": [
    null,
    null
  ],
  "is_final_answer_flags": [
    null,
    true
  ],
  "run_steps": 2
}
```

*tool_empty_string_answer*:

```json
{
  "agent_class": "ToolCallingAgent",
  "payload": "''",
  "output": "",
  "output_repr": "''",
  "output_is_none": false,
  "state": "success",
  "step_errors": [
    null,
    null
  ],
  "is_final_answer_flags": [
    null,
    true
  ],
  "run_steps": 2
}
```

*control_real_answer*:

```json
{
  "agent_class": "ToolCallingAgent",
  "payload": "'5'",
  "output": "5",
  "output_repr": "'5'",
  "output_is_none": false,
  "state": "success",
  "step_errors": [
    null,
    null
  ],
  "is_final_answer_flags": [
    null,
    true
  ],
  "run_steps": 2
}
```

**Controls.**

| control | role | state | assertion result |
|---|---|---|---|
| `C3a_pinned_success_label_with_none_answer` | demonstrates_the_defect | `PASS` | observed: {"agent_class": "ToolCallingAgent", "output_repr": "None", "state": "success", "step_errors": [null, null], "is_final_answer_flags": [null, true], "code_agent_s |
| `C3b_control_the_label_does_track_a_real_answer` | demonstrates_the_defect | `PASS` | observed: {"real_answer_output": "'5'", "real_answer_state": "success", "empty_string_output": "''", "empty_string_state": "success"} |
| `C3c_correction_stops_calling_it_success` | rejects_the_defect | `PASS` | observed: {"state_with_correction": "incomplete", "output_with_correction": "None"} |

**Observed wrong-but-plausible outcome.** `{"agent_class": "ToolCallingAgent", "output_repr": "None", "state": "success", "step_errors": [null, null], "is_final_answer_flags": [null, true], "code_agent_same": {"output_repr": "None", "state": "success"}}`

**What would be correct.** run() should decide its completion state from whether an answer was produced (for example state='incomplete' when output is None), or the framework should refuse a final_answer call with no payload; a status field must not read 'success' when nothing was answered.

**What is inferred rather than measured.** That None is never a legitimate answer is a judgement about the library's contract, not a measurement: an agent could in principle answer None. What is measured is the conjunction output=None with state='success' and no step error, which is what makes the status uninformative.

**Evidence sites.**

- src/smolagents/agents.py: run() state computation ignores the answer
- src/smolagents/default_tools.py: FinalAnswerTool.forward returns its argument unchanged
- src/smolagents/agents.py: ToolCallingAgent._step_stream marks is_final_answer purely by tool name

### F4. C4_zero_step_budget_crashes_the_run

**Claim.** A zero step budget makes run() raise UnboundLocalError instead of producing the fallback answer, so the caller receives an internal variable name rather than an answer or an explicit error.

**What was measured.**

```json
{
  "max_steps": 0,
  "healthy_calls": 0,
  "raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value",
  "output": null,
  "output_repr": null,
  "output_is_none": true,
  "state": null,
  "generate_calls": 1,
  "call_purposes": [
    "fallback_answer_prompt"
  ]
}
```

*pinned_revision_with_a_live_fallback_model*:

```json
{
  "max_steps": 0,
  "healthy_calls": 1,
  "raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value",
  "output": null,
  "output_repr": null,
  "output_is_none": true,
  "state": null,
  "generate_calls": 1,
  "call_purposes": [
    "fallback_answer_prompt"
  ]
}
```

**Controls.**

| control | role | state | assertion result |
|---|---|---|---|
| `C4a_pinned_zero_budget_raises_UnboundLocalError` | demonstrates_the_defect | `PASS` | observed: {"raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value", "generate_calls": 1, "call_purposes": ["fall |
| `C4b_correction_returns_the_fallback_answer` | rejects_the_defect | `PASS` | observed: {"raised_with_correction": null, "output_with_correction": "\"Let me keep working.\"", "is_the_model_answer": true, "call_purposes_with_correction": ["fallback_ |

**Observed wrong-but-plausible outcome.** `{"raised": "UnboundLocalError: cannot access local variable 'action_step' where it is not associated with a value", "generate_calls": 1, "call_purposes": ["fallback_answer_prompt"], "note": "the fallback model call already happened before the crash"}`

**What would be correct.** Either validate max_steps >= 1 where the agent is constructed, or do not re-yield an action_step that was never created; a caller must never see UnboundLocalError from the framework's own bookkeeping.

**What is inferred rather than measured.** Whether a zero budget should be rejected at construction time is a design choice; not inferred is the crash itself, which is executed.

**Evidence sites.**

- src/smolagents/agents.py: _run_stream yields action_step after the loop
- src/smolagents/agents.py: run() declares max_steps = max_steps or self.max_steps

## 5. The discrimination test (guard replaced by an always-allow mutant)

For each guard that converts a failure into an ordinary value, replace it with a transparent re-raise and require at least one check to go red. A guard no check reacts to is a guard the audit cannot defend.

- guard `except Exception as e: return ChatMessage(... error text ...)` at src/smolagents/agents.py: provide_final_answer
  - replaced by: a transparent re-raise (mutant A: the failure is no longer converted into a value)
  - mutated at: `<smolagents clone>/src/smolagents/agents.py:849`
  - check: C1a/C1b (pinned run returns the error text as the answer)
  - baseline (guard in place): {"raised": null, "output_repr": "[{'type': 'text', 'text': 'Error in generating final LLM output: Connection reset by peer (simulated endpoint death)'}]", "state": "max_steps_error"}
  - after replacement: {"raised": "AgentGenerationError: Error in generating final LLM output:\nConnection reset by peer (simulated endpoint death)", "output_repr": "None", "state": null}
  - green with the guard in place: **True**; red with the guard replaced: **True**
  - verdict: **the guard is load-bearing: replacing it flips at least one check from green to red, so the check set discriminates this guard**

Any check went red: **True**. Guards with no discriminating check: none.

## 6. False alarms: what was examined and rejected

7 candidate defects were examined with an executable check and rejected. They are listed because a negative result is a result, and because each one is a plausible-looking claim that a less careful audit would have published.

- **a dead model on an ordinary action step is swallowed**
  - rejected: the framework raises AgentGenerationError out of run()
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nConnection reset by peer (simulated endpoint death)", "generate_calls": 1}`
- **a TypeError wiring bug in a model adapter is absorbed**
  - rejected: it is wrapped into AgentGenerationError and raised
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nfalse_alarms.<locals>.WrongSignature.generate() got an unexpected keyword argument 'stop_sequences'"}`
- **malformed JSON in tool-call arguments corrupts the answer**
  - rejected: parse_json_if_needed returns unparsed text by design, and the docs plus tests/test_models.py::test_parse_json_if_needed pin that behaviour ('abc' -> 'abc'). The truncated fragment therefore arrives as a plain string, which the framework accepts as an answer because a bare string is a documented argument form for final_answer.
  - evidence: `{"parse_json_if_needed('{\"answer\": \"5')": "'{\"answer\": \"5'", "documented": "docs/source/en/guided_tour.md plus the tool-calling prompt examples", "test": "tests/test_models.py:312 test_parse_json_if_needed"}`
- **a tool failure is invisible and the run reports success anyway**
  - rejected: the tool failure is recorded on the step that hit it (AgentToolExecutionError), and feeding a failed tool call back to the model so it can retry is the ReAct design. The run state therefore describes the recovery, which is legitimate.
  - evidence: `{"state": "success", "step_errors": [null, {"type": "AgentToolExecutionError", "message": "Error executing tool 'boom' with arguments {}: RuntimeError: backend unavailable\nPlease try again or use another tool"}, null]}`
- **a boolean final_answer_check is inert, because the implementation wraps it in `assert` (a first code reading suggested assert would not fire on a False return)**
  - rejected by execution: assert fires on a False return, the guard's rejection is recorded as an AgentError on the step, and the run ends max_steps_error. The documented behaviour (log and continue the run) is what happens.
  - evidence: `{"guard_returns_false_for_bad_value": true, "guard_errors_recorded": [{"type": "AgentError", "message": "Check boolean_guard failed with error: "}], "guard_error_count": 4, "state": "max_steps_error"}`
- **an interpreter timeout is silently absorbed and the run reports success**
  - rejected as a swallowed failure: the timeout becomes a step observation (AgentExecutionError 'Code execution exceeded the maximum execution time'), so the model sees it and the caller can read it from steps[].error. The residual issue is real but is not this defect class: the run-level state still says success, and the abandoned interpreter thread cannot be stopped (documented in local_python_executor.timeout).
  - evidence: `{"state": "success", "output": "answered after a timeout", "wall_seconds": 2.51, "step_errors": [null, {"type": "AgentExecutionError", "message": "Code execution exceeded the maximum execution time of 1 seconds"}, null], "observations": ["None", "Execution logs:\ntick 0\ntick 1\n", "Execution logs:\nLast output from code snippet:\nanswered after a timeout"], "timed_out_code_wrote_its_marker": false}`
- **a mid-run endpoint death is swallowed as long as steps remain**
  - rejected: it raises AgentGenerationError out of run(). Only the fallback-answer call converts the same failure into a value.
  - evidence: `{"raised": "AgentGenerationError: Error while generating output:\nConnection reset by peer (simulated endpoint death)", "generate_calls": 2}`

## 7. What this audit does NOT prove

- **It does not prove the absence of other defects.** Four criteria were written and all four reproduced. The candidate sites not turned into criteria were reviewed by reading, not by execution; any of them could hide a defect this harness does not see.
- **It does not prove these are the highest-severity issues in the project.** Severity was not ranked; the target was one defect class only.
- **It does not test against a real model provider.** Every scenario uses a stub `Model` subclass that raises `ConnectionError`, so the *control flow* is real but the provider's own error taxonomy is not exercised. A provider that retries internally could change how often the audited path is reached, though not whether it swallows.
- **The mutants are corrections in the harness, not in the project.** They are not proposed patches and have not been submitted anywhere; they exist to show that each control can fail.
- **`C3`'s judgement that `None` is never a legitimate answer is a convention, not a measurement.** What is measured is the conjunction `output is None` with `state == "success"` and no step error.
- **`C4` exercises an unusual configuration.** A zero step budget is a boundary, not the documented default of 20; a reviewer could reasonably call it out-of-contract.
- **No coverage of remote executors, MCP clients, the Gradio UI, hub push/pull, or the vision-browser examples.** None of them can be exercised offline.

## 8. What could not be tested, and why

- **Any real LLM call.** No API key was used and no paid endpoint was contacted; that was a hard constraint of the audit.
- **Remote code execution paths** (`e2b`, `docker`, `modal`, `blaxel` executors): they require third-party services.
- **`ToolCollection.from_mcp` and MCP tool loading**: requires an MCP server.
- **The Gradio UI and hub integration** (`push_to_hub`, `from_hub`): require a live Hugging Face Hub token and would constitute outward contact, which this audit deliberately avoided.
- **The project's own test suite was not run as a whole.** The audit depends on the library's public entry points only; running the suite would add third-party dependencies and network tests without strengthening any of the four criteria.
- **Long-running behaviour**: the interpreter-timeout scenario shows that an abandoned interpreter thread cannot be stopped (the project documents this in `local_python_executor.timeout`), but its consequences over minutes or hours were not measured.

## 9. Exact reproduction

Requirements: Windows, Python 3.10+, git, about 200 MB of disk, no GPU, no network access after the clone, no API key.

```powershell
# 1. obtain the pinned revision
git clone https://github.com/huggingface/smolagents.git smolagents
cd smolagents
git checkout c30b115286e000e98711fae5e85993547b73d826

# 2. install the library and its runtime dependencies only
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .

# 3. run the audit (this one command prints the verdicts and writes the artifacts)
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
.venv\Scripts\python.exe audit\three_state_audit.py
```

There is nothing to edit before running: the harness only uses the library's public entry points plus `smolagents.models.Model` subclassing, and its final lines print the directory it wrote. It refuses to overwrite an existing artifact, so the default `--outdir` is a fresh timestamped directory on every run, and passing an already-populated `--outdir` exits non-zero with "refusing to overwrite existing artifact" (verified).

Recorded artifacts of the run reported here (`reproduce_final2`):

| artifact | contents |
|---|---|
| `smolagents/audit/three_state_audit.py` | the harness (one command, no key, no GPU) |
| `smolagents/audit/core.py` | the self-contained three-state control schema |
| `smolagents/audit/mutants.py` | the corrected variants and their verification |
| `smolagents/audit/make_report.py` | renders this report from the recorded artifact |
| `smolagents/audit/runs/reproduce_final2/STDOUT.txt` | raw console output of the run |
| `smolagents/audit/runs/reproduce_final2/STDERR.txt` | raw standard error (empty) |
| `smolagents/audit/runs/reproduce_final2/RESULTS.json` | machine-readable criteria, controls, traces |
| `smolagents/audit/runs/reproduce_final2/RESULTS.md` | the same, rendered as tables |
| `smolagents/audit/runs/reproduce_final2/PIP_FREEZE.txt` | exact dependency versions of the run |
| `smolagents/audit/probe_recon*.py` | the reconnaissance probes, kept because they show which hypotheses were falsified |

## 10. Pins and environment

- commit: `c30b115286e000e98711fae5e85993547b73d826` (2026-09-30T07:07:22+02:00), subject: fix(ci): harden GitHub Actions workflows (#2558) (#2868)
- `git describe`: `v1.0.0-936-gc30b115`
- worktree state at audit time: `?? audit/` (only the untracked `audit/` directory, which this audit added; no tracked file was modified)
- python: `3.13.13 (tags/v3.13.13:01104ce, Apr  7 2026, 19:25:48) [MSC v.1944 64 bit (AMD64)]`
- platform: `Windows-11-10.0.26200-SP0`
- interpreters/processors: 16
- smolagents module under test: `<clone root>/src/smolagents/__init__.py` (the clone under test, not a site-packages copy)
- network used: **False**; API key used: **False**; GPU used: **False**

Dependency versions at run time (also in `PIP_FREEZE.txt`):

```
smolagents==1.27.0.dev0
huggingface-hub==2.1.1
requests==2.34.2
rich==15.0.0
jinja2==3.1.6
pillow==12.3.0
python-dotenv==1.2.4
```

SHA-256 of each audited file at this commit (so a reader can confirm the audited text):

```
d4f40408e0e55dc4ad20b6a92bb166285b6624dfbdce6ef55b511b7bd1e94c33  src/smolagents/agents.py
806c1ec195b56324704cf82cb84b089325a3ce293e13168fc189dbfa2c21751c  src/smolagents/models.py
fab02dbe39b4f1404f4d02403d61d2ef3571bb84010529efb01147cef2425df8  src/smolagents/memory.py
a0e398ec4311c7111756273023ed726bdfa2f011c5abc65529343d739cf411a2  src/smolagents/monitoring.py
78e00312510b2d96fb5265d66d91f35fc7bd49e7c345b1e79f652a92b00a7cfa  src/smolagents/local_python_executor.py
82de8b3999e6d18e6b864109e64c9bf67fb6fe07b45e39f6d0690f9870b3bb54  src/smolagents/default_tools.py
ffaba38a0a4fac36201f22c6278a424cdf6902ea267bfe440c83b13777cf3bd9  src/smolagents/tools.py
```

## 11. Counts

| quantity | value |
|---|---|
| python files scanned in the shipped package | 18 |
| `except` handlers found in total | 89 |
| handlers that re-raise or propagate (structurally out of scope) | 52 |
| **candidate sites** (handlers that do NOT re-raise: return a value, `pass`, or log only) | **37** |
| candidate sites exercised with an executable check | 11 |
| candidate defects reproduced as real defects | 4 |
| candidate defects rejected as false alarms | 7 |
| criteria written | 4 |
| controls executed | 11 |
| criteria PASS (defect reproduced and correction flips the control) | 4 |
| criteria not PASS | none |
| broken controls (`CONTROL_ERROR` / `CONTROL_PRECONDITION_FAILED`) | 0 |
| schema self-test passed | True |
| guards put through the always-allow discrimination test | 1 |

The population figure is measured by walking the syntax tree of every shipped module (`exception_handler_census()` in the harness), not estimated: the defect class can only occur where an `except` handler refuses to re-raise, and there are 37 such handlers. The harness exercised 11 of them with executable checks and the rest were read but not run; the unexercised ones are concentrated in the modules this audit could not run offline (remote executors, the MCP client, hub serialization). The full list is in `RESULTS.json` under `candidate_census.sites`.

Accounting of the 11 exercised candidates: 4 reproduced as defects (F1–F4; F2 shares F1's code site but asserts a separable property about the run's own bookkeeping), 7 were rejected as false alarms and are listed in section 6 above with the evidence that rejected them.

## 12. Contact statement

This audit made **no outward contact of any kind**. Nothing was registered, no account was created, no email was sent, no issue or pull request was opened, and no public or third-party service was contacted other than the single `git clone` of the public repository that the audit is about. Nothing outside the locations the audit was permitted to write was written: the harness and its artifacts live beside the audited clone, and the summary lives in the authoring workspace's reports directory. The audited repository's tracked files are untouched (verified with `git status`: only the untracked `audit/` directory).

