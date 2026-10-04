"""Executable audit harness: huggingface/smolagents, failure-disguised-as-success.

One command, no API key, no GPU, no network:

    python run.py

`run.py` at the repository root is a thin wrapper over this file. Call this module
directly only when you need a specific `--outdir`:

    python harness/three_state_audit.py --outdir harness/runs/<a-name-not-used-before>

The audited checkout is found automatically: `$SMOLAGENTS_ROOT` when set, otherwise
`hub/smolagents` next to this file (the layout `scripts/fetch_targets.py` creates). The
harness refuses to start unless that checkout is at the pinned commit, because controls
measured against one revision cannot report verdicts about another. `REPRODUCE.md` records
the pin and the measured reproduction rate.

The harness never writes outside its artifact directory (a fresh
`harness/runs/audit_run_<timestamp>_pid<pid>` unless `--outdir` says otherwise), refuses to
overwrite existing artifact files, and mutates nothing on disk: every "corrected variant"
is applied in memory and restored in a `finally` block.

Sections
--------
1. schema self-test      - proves the three-state machinery discriminates
2. pristine check        - proves no corrected variant is left bound before grading
3. criteria C1..C4       - each with a defect-demonstrating and a should-fail control
4. discrimination test   - replaces each swallowing guard with a transparent re-raise
5. false alarms          - candidate defects examined and rejected, with the evidence
6. population census     - how many candidate sites exist, measured from the syntax tree
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import inspect
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    Audit,
    Criterion,
    CtlRole,
    reader_control,
    state_control,
    self_test,
)
from mutants import ALL_MUTANTS, MutantError, restore  # noqa: E402

import _setup  # noqa: E402

#: Put the audited clone's `src` at the front of sys.path BEFORE smolagents is imported, so
#: the harness audits the checkout under test and not whatever copy of the package happens
#: to be installed in the running interpreter. `_setup` also refuses to start unless that
#: checkout is at the pinned commit these controls were measured against.
REPO_ROOT, PINNED_COMMIT_FOUND = _setup.activate(
    require_pinned_commit=os.environ.get("SMOLAGENTS_ALLOW_ANY_COMMIT") != "1"
)

print(f"audited checkout: {REPO_ROOT}")
print(f"commit:           {PINNED_COMMIT_FOUND} (pinned)")

import smolagents  # noqa: E402
from smolagents import CodeAgent, ToolCallingAgent, tool  # noqa: E402
from smolagents.agents import MultiStepAgent  # noqa: E402
from smolagents.models import (  # noqa: E402
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
    Model,
)
from smolagents.monitoring import (  # noqa: E402
    AgentLogger,
    LogLevel,
)
from smolagents.utils import AgentGenerationError  # noqa: E402

SWALLOWED_REASON = "Connection reset by peer (simulated endpoint death)"
#: the text the healthy stub model returns, used to prove that a returned answer really
#: came from the model rather than from an error path
FALLBACK_MODEL_TEXT = "Let me keep working."


# ══════════════════════════════════════════════════════════════════════════════
# Stub models: no network, no credentials. Each models one failure a real user hits.
# ══════════════════════════════════════════════════════════════════════════════
class BreakableModel(Model):
    """Healthy for the first `healthy_calls` generate() calls, then fails on every later
    call, which is what an endpoint that dies mid-run looks like (quota exhausted,
    credential expired, upstream restarted).

    The failure point is fixed by the constructor rather than flipped from outside: an
    earlier version of this harness set the flag before run() and thereby made the FIRST
    call fail, which is a different scenario that the framework handles correctly.
    """

    def __init__(self, healthy_calls: int, reason: str = SWALLOWED_REASON):
        super().__init__(model_id="stub-breakable")
        self.healthy_calls = healthy_calls
        self.reason = reason
        self.calls = 0
        #: which prompt each call carried, so a control can prove WHICH call site answered
        self.purposes: list[str] = []

    @staticmethod
    def _purpose(messages) -> str:
        text = str(messages)
        if "Error in generating final LLM output" in text:  # pragma: no cover - defensive
            return "unknown"
        if "stuck and failed to do so" in text:
            return "fallback_answer_prompt"
        return "action_step_prompt"

    def generate(self, messages, tools_to_call_from=None, stop_sequences=None):
        self.calls += 1
        self.purposes.append(self._purpose(messages))
        if self.calls > self.healthy_calls:
            raise ConnectionError(self.reason)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Let me keep working.",
            tool_calls=[
                ChatMessageToolCall(
                    id=f"call_{self.calls}",
                    type="function",
                    function=ChatMessageToolCallFunction(name="add", arguments={"a": 1, "b": 1}),
                )
            ],
        )


class CodeBreakableModel(Model):
    """CodeAgent variant: emits a healthy code action, then the endpoint dies."""

    def __init__(self, healthy_calls: int, reason: str = SWALLOWED_REASON):
        super().__init__(model_id="stub-code-breakable")
        self.healthy_calls = healthy_calls
        self.reason = reason
        self.calls = 0

    def generate(self, messages, stop_sequences=None, **kwargs):
        self.calls += 1
        if self.calls > self.healthy_calls:
            raise ConnectionError(self.reason)
        return ChatMessage(role=MessageRole.ASSISTANT, content="Thought: count\n<code>\nx = 1 + 1\n</code>\n")


class EmptyAnswerModel(Model):
    """Finalizes with a payload that carries no answer at all."""

    def __init__(self, payload: Any):
        super().__init__(model_id="stub-empty-answer")
        self.payload = payload
        self.calls = 0

    def generate(self, messages, tools_to_call_from=None, stop_sequences=None):
        self.calls += 1
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="done",
            tool_calls=[
                ChatMessageToolCall(
                    id=f"call_{self.calls}",
                    type="function",
                    function=ChatMessageToolCallFunction(name="final_answer", arguments={"answer": self.payload}),
                )
            ],
        )


class CodeNoneAnswerModel(Model):
    """CodeAgent emitting final_answer(None)."""

    def __init__(self):
        super().__init__(model_id="stub-code-none-answer")
        self.calls = 0

    def generate(self, messages, stop_sequences=None, **kwargs):
        self.calls += 1
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Thought: done\n<code>\nfinal_answer(None)\n</code>\n",
        )


@tool
def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: first addend
        b: second addend
    """
    return a + b


def _silent_logger() -> AgentLogger:
    """A logger whose console output goes nowhere, so artifacts stay machine readable."""
    from rich.console import Console

    return AgentLogger(level=LogLevel.OFF, console=Console(file=io.StringIO(), width=200))


# ══════════════════════════════════════════════════════════════════════════════
# The audited scenarios. Each returns a plain dict: raw observations only.
# ══════════════════════════════════════════════════════════════════════════════
def scenario_dead_endpoint_at_fallback_answer() -> dict[str, Any]:
    """ToolCallingAgent with max_steps=1: one healthy step, then the endpoint dies on
    the very call that would produce the user-visible answer."""
    model = BreakableModel(healthy_calls=1)
    agent = ToolCallingAgent(
        tools=[add], model=model, max_steps=1, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    if model.healthy_calls < 1:
        raise ValueError("this scenario needs at least one healthy action step before the endpoint dies")
    observed: dict[str, Any] = {"agent_class": "ToolCallingAgent", "max_steps": 1}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            result = agent.run("What is 2 + 3?", return_full_result=True)
        observed["raised"] = None
        observed["output"] = result.output
        observed["output_repr"] = repr(result.output)
        observed["output_type"] = type(result.output).__name__
        observed["state"] = result.state
        observed["token_usage_is_none"] = result.token_usage is None
        observed["step_errors"] = [s.get("error") for s in result.steps]
        observed["is_final_answer_flags"] = [s.get("is_final_answer") for s in result.steps]
        observed["failure_reason_in_state"] = SWALLOWED_REASON in str(result.state)
        observed["failure_reason_in_step_errors"] = SWALLOWED_REASON in json.dumps(
            observed["step_errors"], default=str
        )
        observed["failure_reason_in_output"] = SWALLOWED_REASON in json.dumps(result.output, default=str)
    except BaseException as exc:  # noqa: BLE001 - what escapes is itself the observation
        observed["raised"] = f"{type(exc).__name__}: {exc}"
        observed["output"] = None
        observed["output_repr"] = None
        observed["output_type"] = None
        observed["state"] = None
        observed["failure_reason_in_state"] = False
        observed["failure_reason_in_step_errors"] = False
        observed["failure_reason_in_output"] = False
    observed["generate_calls"] = model.calls
    observed["call_purposes"] = list(model.purposes)
    return observed


def scenario_dead_endpoint_code_agent() -> dict[str, Any]:
    """Same shape through CodeAgent, the class the README uses first."""
    model = CodeBreakableModel(healthy_calls=1)
    agent = CodeAgent(tools=[], model=model, max_steps=1, verbosity_level=LogLevel.OFF, logger=_silent_logger())
    observed: dict[str, Any] = {"agent_class": "CodeAgent", "max_steps": 1}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            result = agent.run("count to two", return_full_result=True)
        observed["raised"] = None
        observed["output"] = result.output
        observed["output_repr"] = repr(result.output)
        observed["state"] = result.state
        observed["step_errors"] = [s.get("error") for s in result.steps]
        observed["failure_reason_in_output"] = SWALLOWED_REASON in json.dumps(result.output, default=str)
    except BaseException as exc:  # noqa: BLE001
        observed["raised"] = f"{type(exc).__name__}: {exc}"
        observed["output"] = None
        observed["output_repr"] = None
        observed["state"] = None
        observed["step_errors"] = None
        observed["failure_reason_in_output"] = False
    observed["generate_calls"] = model.calls
    return observed


def scenario_empty_answer(payload: Any, agent_class: str = "ToolCallingAgent") -> dict[str, Any]:
    """A run that completes with no answer at all."""
    if agent_class == "ToolCallingAgent":
        model: Model = EmptyAnswerModel(payload)
        agent = ToolCallingAgent(
            tools=[add], model=model, max_steps=2, verbosity_level=LogLevel.OFF, logger=_silent_logger()
        )
    else:
        model = CodeNoneAnswerModel()
        agent = CodeAgent(tools=[], model=model, max_steps=2, verbosity_level=LogLevel.OFF, logger=_silent_logger())
    with contextlib.redirect_stderr(io.StringIO()):
        result = agent.run("What is 2 + 3?", return_full_result=True)
    return {
        "agent_class": agent_class,
        "payload": repr(payload),
        "output": result.output,
        "output_repr": repr(result.output),
        "output_is_none": result.output is None,
        "state": result.state,
        "step_errors": [s.get("error") for s in result.steps],
        "is_final_answer_flags": [s.get("is_final_answer") for s in result.steps],
        "run_steps": len(result.steps),
    }


def scenario_zero_step_budget(healthy_calls: int = 0) -> dict[str, Any]:
    """max_steps=0: the loop body never executes, so the fallback answer path runs
    before any action step has been created.

    `healthy_calls` controls whether that fallback model call itself succeeds:
    0 = the endpoint is dead too (the run crashes on the crash path either way),
    1 = the endpoint answers the fallback call, which is what a working fallback
    answer looks like and therefore what the corrected variant must produce.
    """
    model = BreakableModel(healthy_calls=healthy_calls)
    agent = ToolCallingAgent(
        tools=[add], model=model, max_steps=0, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    observed: dict[str, Any] = {"max_steps": 0, "healthy_calls": healthy_calls}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            result = agent.run("What is 2 + 3?", return_full_result=True)
        observed["raised"] = None
        observed["output"] = result.output
        observed["output_repr"] = repr(result.output)
        observed["output_is_none"] = result.output is None
        observed["state"] = result.state
    except BaseException as exc:  # noqa: BLE001
        observed["raised"] = f"{type(exc).__name__}: {exc}"
        observed["output"] = None
        observed["output_repr"] = None
        observed["output_is_none"] = True
        observed["state"] = None
    observed["generate_calls"] = model.calls
    observed["call_purposes"] = list(model.purposes)
    return observed


# ══════════════════════════════════════════════════════════════════════════════
# Mutation guard: apply a corrected variant, run, restore, always report what happened.
# ══════════════════════════════════════════════════════════════════════════════
def with_mutant(mutant_key: str, fn: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    """Run `fn` with one corrected variant bound, restoring the pinned revision after.

    Returns (observation, provenance). If the mutant cannot be applied unambiguously,
    provenance carries the refusal and the observation is None: the harness then reports
    a broken control rather than silently grading the unmutated program.
    """
    mutant = ALL_MUTANTS[mutant_key]
    originals = {name: getattr(MultiStepAgent, name) for name in {mutant.method}}
    try:
        provenance = mutant.apply_to(MultiStepAgent)
    except MutantError as exc:
        return None, {"mutant": mutant_key, "applied": False, "refusal": str(exc)}
    try:
        observation = fn()
    finally:
        for name, original in originals.items():
            restore(MultiStepAgent, name, original)
    provenance["applied"] = True
    return observation, provenance


def mutant_is_live(mutant_key: str) -> tuple[bool, str]:
    """Confirm a corrected variant differs from the pinned revision in the expected way."""
    mutant = ALL_MUTANTS[mutant_key]
    original = getattr(MultiStepAgent, mutant.method)
    try:
        provenance = mutant.apply_to(MultiStepAgent)
    except MutantError as exc:
        return False, f"mutant refused: {exc}"
    finally:
        restore(MultiStepAgent, mutant.method, original)
    return True, f"edited {', '.join(provenance['edit_locations'])}"


def pristine_revision_check() -> dict[str, Any]:
    """Verify that no correction is currently bound on the class under audit.

    Every mutant is restored in a `finally` block, but if a restore ever failed, a later
    "pinned revision" measurement would silently be taken against a corrected program and
    the audit would report a false green. This check makes that failure visible: it looks
    for the text each mutant injects inside the live source of the audited methods.
    """
    injected = {
        "A_re_raise_in_provide_final_answer": ('provide_final_answer', "raise AgentGenerationError(f\"Error in generating final"),
        "C_incomplete_state": ("run", 'state = "incomplete"'),
        "D_zero_budget_guard": ("_run_stream", "action_step = None"),
        "E_generation_failure_attribute": ("provide_final_answer", "generation_failure"),
    }
    findings = {}
    clean = True
    for label, (method, marker) in injected.items():
        fn = getattr(MultiStepAgent, method, None)
        if fn is None:
            findings[label] = "method missing"
            clean = False
            continue
        try:
            source = inspect.getsource(fn)
        except OSError:
            findings[label] = "source unavailable (a mutant may be bound)"
            clean = False
            continue
        present = marker in source
        findings[label] = "mutant text present" if present else "clean"
        clean = clean and not present
    return {"pristine": clean, "methods_checked": findings}


# ══════════════════════════════════════════════════════════════════════════════
# Criteria
# ══════════════════════════════════════════════════════════════════════════════
def build_criteria() -> Audit:
    audit = Audit(subject="huggingface/smolagents, failure-disguised-as-success audit")

    # ── C1 ────────────────────────────────────────────────────────────────────
    c1 = audit.add(
        Criterion(
            name="C1_model_failure_during_fallback_answer_is_swallowed",
            claim=(
                "When the model endpoint fails on the call that produces the fallback "
                "final answer, run() returns normally with the error text as the answer "
                "instead of raising, and no part of the returned result identifies a "
                "generation failure."
            ),
            verdict_rule=(
                "PASS requires both: (a) on the pinned revision the run returns without "
                "raising and its output contains the raw error text; (b) on the corrected "
                "variant the same failure raises out of run()."
            ),
            measured={},
            inferred=(
                "Not inferred: both the swallowed outcome and its disappearance under the "
                "correction are executed. The claim that a caller cannot distinguish this "
                "from a real answer follows from the measured output text alone."
            ),
            correct_implementation=(
                "provide_final_answer() should let the generation failure out of the "
                "framework the same way an action-step generation failure does "
                "(_run_stream re-raises AgentGenerationError, and tests/test_agents.py::"
                "test_generation_errors_are_raised asserts that). A caller must be able to "
                "tell 'the agent used its remaining budget' from 'the model never answered'."
            ),
            evidence_sites=[
                "src/smolagents/agents.py: provide_final_answer (except Exception -> ChatMessage with error text)",
                "src/smolagents/agents.py: _handle_max_steps_reached (the only caller)",
                "src/smolagents/agents.py: _run_stream (re-raises AgentGenerationError for action steps)",
            ],
        )
    )

    pinned_c1 = scenario_dead_endpoint_at_fallback_answer()
    c1.measured["pinned_revision"] = pinned_c1
    c1.measured["pinned_revision_code_agent"] = scenario_dead_endpoint_code_agent()

    def c1_precondition() -> bool:
        """The audited code path must still exist: the fallback answer must be the call that
        failed, and the failure must still be swallowed there."""
        purposes = pinned_c1.get("call_purposes") or []
        return (
            pinned_c1.get("raised") is None
            and pinned_c1.get("generate_calls") == 2
            and purposes[:1] == ["action_step_prompt"]
            and purposes[1:2] == ["fallback_answer_prompt"]
        )

    def dem_returns_normally_with_error_text():
        observed = pinned_c1
        assertion = (
            observed.get("raised") is None
            and SWALLOWED_REASON in json.dumps(observed.get("output"), default=str)
        )
        return {
            "raised": observed.get("raised"),
            "output_repr": observed.get("output_repr"),
            "state": observed.get("state"),
            "call_purposes": observed.get("call_purposes"),
        }, assertion

    def dem_no_machine_readable_failure():
        observed = pinned_c1
        assertion = not (
            observed.get("failure_reason_in_state") or observed.get("failure_reason_in_step_errors")
        )
        return {
            "failure_reason_in_state": observed.get("failure_reason_in_state"),
            "failure_reason_in_step_errors": observed.get("failure_reason_in_step_errors"),
            "failure_reason_in_output": observed.get("failure_reason_in_output"),
            "step_errors": observed.get("step_errors"),
        }, assertion

    c1.controls.append(
        state_control(
            "C1a_pinned_run_returns_error_text_as_the_answer",
            "on the pinned revision, the dead endpoint produces a normal return whose "
            "output is the error text",
            "the pinned revision still reaches provide_final_answer() and still swallows "
            "the failure there (run raises nothing and generate() was called twice)",
            c1_precondition,
            dem_returns_normally_with_error_text,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
            expectation="assertion is True on the pinned revision (defect reproduces)",
        )
    )
    c1.controls.append(
        state_control(
            "C1b_pinned_run_records_no_machine_readable_failure",
            "no field of the returned RunResult names the generation failure",
            "same precondition as C1a",
            c1_precondition,
            dem_no_machine_readable_failure,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
        )
    )

    live_ok, live_note = mutant_is_live("A")
    mutated_c1: dict[str, Any] = {"applied": live_ok, "note": live_note}

    def c1_correction_rejects_claim():
        observation, provenance = with_mutant("A", scenario_dead_endpoint_at_fallback_answer)
        mutated_c1.update(provenance)
        if observation is None:
            raise RuntimeError(f"mutant A could not be applied: {provenance.get('refusal')}")
        mutated_c1["observed"] = observation
        assertion = observation.get("raised") is not None and observation.get("output") is None
        return {
            "raised": observation.get("raised"),
            "output": observation.get("output_repr"),
            "output_is_none": observation.get("output") is None,
        }, assertion

    c1.controls.append(
        reader_control(
            "C1c_correction_raises_instead_of_answering",
            "with mutant A the same dead endpoint raises out of run() and yields no output",
            c1_correction_rejects_claim,
            role=CtlRole.REJECTS_THE_DEFECT,
            expected_result=True,
            mutation=ALL_MUTANTS["A"].summary,
            mutation_locations=[live_note] if live_ok else [],
            expectation="assertion is True with the correction in place",
        )
    )
    c1.measured["mutant A"] = mutated_c1

    # ── C2 ────────────────────────────────────────────────────────────────────
    c2 = audit.add(
        Criterion(
            name="C2_fallback_failure_is_reported_as_a_step_limit_error",
            claim=(
                "The returned RunResult.state cannot distinguish 'the step budget ran out' "
                "from 'the model never answered': both are reported as max_steps_error "
                "while the failure reason survives only inside the answer text."
            ),
            verdict_rule=(
                "PASS requires both: (a) on the pinned revision state is max_steps_error "
                "and no step error names the failure; (b) on the corrected variant the "
                "failure becomes visible in state or in a step error."
            ),
            measured={},
            inferred=(
                "The step-limit label itself is intended behaviour. The audited property is "
                "that the label is the only machine-readable signal and it does not mention "
                "the failure that actually prevented an answer."
            ),
            correct_implementation=(
                "state should be derived from whether the run produced an answer, or the "
                "generation failure should be recorded on the step that consumed the "
                "remaining budget; either way a consumer reading only state/step errors "
                "must be able to learn that the model failed."
            ),
            evidence_sites=[
                "src/smolagents/agents.py: run() state computation reads only the last step's error",
                "src/smolagents/agents.py: _handle_max_steps_reached records only AgentMaxStepsError",
            ],
        )
    )
    c2.measured["pinned_revision"] = pinned_c1

    def c2_precondition() -> bool:
        return pinned_c1.get("state") == "max_steps_error" and pinned_c1.get("raised") is None

    def dem_state_misleading():
        observed = pinned_c1
        assertion = observed.get("state") == "max_steps_error" and not (
            observed.get("failure_reason_in_state") or observed.get("failure_reason_in_step_errors")
        )
        return {
            "state": observed.get("state"),
            "failure_reason_in_state": observed.get("failure_reason_in_state"),
            "failure_reason_in_step_errors": observed.get("failure_reason_in_step_errors"),
            "step_errors": observed.get("step_errors"),
        }, assertion

    c2.controls.append(
        state_control(
            "C2a_state_says_step_limit_and_nothing_else",
            "on the pinned revision the run reports max_steps_error with the failure only "
            "inside the answer text",
            "the pinned revision still reports max_steps_error for this scenario",
            c2_precondition,
            dem_state_misleading,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
        )
    )

    mutated_c2: dict[str, Any] = {"applied": live_ok, "note": live_note}

    def c2_correction_rejects_claim():
        observation, provenance = with_mutant("A", scenario_dead_endpoint_at_fallback_answer)
        mutated_c2.update(provenance)
        if observation is None:
            raise RuntimeError(f"mutant A could not be applied: {provenance.get('refusal')}")
        mutated_c2["observed"] = observation
        raised = observation.get("raised") or ""
        assertion = SWALLOWED_REASON in raised
        return {"raised": raised, "no_longer_silent": assertion}, assertion

    c2.controls.append(
        reader_control(
            "C2b_correction_makes_the_failure_reachable",
            "with mutant A the failure reason reaches the caller in the raised exception",
            c2_correction_rejects_claim,
            role=CtlRole.REJECTS_THE_DEFECT,
            expected_result=True,
            mutation=ALL_MUTANTS["A"].summary,
            expectation="assertion is True with the correction in place",
        )
    )

    def c2_correction_rejects_claim():
        observation, provenance = with_mutant("E", scenario_dead_endpoint_at_fallback_answer)
        mutated_c2.update(provenance)
        if observation is None:
            raise RuntimeError(f"mutant E could not be applied: {provenance.get('refusal')}")
        mutated_c2["observed"] = observation
        state = observation.get("state")
        step_errors = observation.get("step_errors") or []
        failure_visible = (state not in (None, "success")) or any(
            SWALLOWED_REASON in json.dumps(step, default=str) for step in step_errors
        )
        return {
            "state_with_correction": state,
            "step_errors_with_correction": step_errors,
            "failure_visible_with_correction": failure_visible,
        }, failure_visible

    c2.controls.append(
        reader_control(
            "C2c_correction_makes_the_reason_reachable",
            "with mutant E the failure reason appears in the returned state or in a step error",
            c2_correction_rejects_claim,
            role=CtlRole.REJECTS_THE_DEFECT,
            expected_result=True,
            mutation=ALL_MUTANTS["E"].summary,
            expectation="assertion is True with the correction in place",
        )
    )
    c2.measured["mutants"] = mutated_c2

    # ── C3 ────────────────────────────────────────────────────────────────────
    c3 = audit.add(
        Criterion(
            name="C3_run_without_an_answer_reports_success",
            claim=(
                "A run whose final answer carries nothing (final_answer with no usable "
                "payload, or a None answer) returns output=None together with "
                "state='success', so a caller that trusts the status has no way to learn "
                "that the agent answered nothing."
            ),
            verdict_rule=(
                "PASS requires both: (a) on the pinned revision the None-answer run has "
                "output None and state success; (b) on the corrected variant such a run is "
                "not labelled success."
            ),
            measured={},
            inferred=(
                "That None is never a legitimate answer is a judgement about the library's "
                "contract, not a measurement: an agent could in principle answer None. What "
                "is measured is the conjunction output=None with state='success' and no step "
                "error, which is what makes the status uninformative."
            ),
            correct_implementation=(
                "run() should decide its completion state from whether an answer was "
                "produced (for example state='incomplete' when output is None), or the "
                "framework should refuse a final_answer call with no payload; a status "
                "field must not read 'success' when nothing was answered."
            ),
            evidence_sites=[
                "src/smolagents/agents.py: run() state computation ignores the answer",
                "src/smolagents/default_tools.py: FinalAnswerTool.forward returns its argument unchanged",
                "src/smolagents/agents.py: ToolCallingAgent._step_stream marks is_final_answer purely by tool name",
            ],
        )
    )
    empty_tool = scenario_empty_answer(None, "ToolCallingAgent")
    empty_code = scenario_empty_answer(None, "CodeAgent")
    empty_string = scenario_empty_answer("", "ToolCallingAgent")
    real_answer = scenario_empty_answer("5", "ToolCallingAgent")
    c3.measured["tool_none_answer"] = empty_tool
    c3.measured["code_none_answer"] = empty_code
    c3.measured["tool_empty_string_answer"] = empty_string
    c3.measured["control_real_answer"] = real_answer

    def c3_precondition() -> bool:
        return (
            empty_tool.get("output_is_none") is True
            and empty_tool.get("state") == "success"
            and all(step is None for step in empty_tool.get("step_errors") or [])
        )

    def dem_success_with_no_answer():
        assertion = empty_tool.get("output_is_none") is True and empty_tool.get("state") == "success"
        return {
            "agent_class": empty_tool.get("agent_class"),
            "output_repr": empty_tool.get("output_repr"),
            "state": empty_tool.get("state"),
            "step_errors": empty_tool.get("step_errors"),
            "is_final_answer_flags": empty_tool.get("is_final_answer_flags"),
            "code_agent_same": {
                "output_repr": empty_code.get("output_repr"),
                "state": empty_code.get("state"),
            },
        }, assertion

    def dem_real_answer_is_contrast():
        assertion = (
            real_answer.get("state") == "success"
            and real_answer.get("output_is_none") is False
            and empty_string.get("output_is_none") is False
        )
        return {
            "real_answer_output": real_answer.get("output_repr"),
            "real_answer_state": real_answer.get("state"),
            "empty_string_output": empty_string.get("output_repr"),
            "empty_string_state": empty_string.get("state"),
        }, assertion

    c3.controls.append(
        state_control(
            "C3a_pinned_success_label_with_none_answer",
            "on the pinned revision output None comes with state success and no step error",
            "the pinned revision still returns state='success' for a None answer",
            c3_precondition,
            dem_success_with_no_answer,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
        )
    )
    c3.controls.append(
        reader_control(
            "C3b_control_the_label_does_track_a_real_answer",
            "CONTROL: the same machinery labels a real answer success and keeps the answer, "
            "so the harness is not simply seeing a broken run",
            dem_real_answer_is_contrast,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
            notes="this control forbids reading C3a as a generic 'the run was broken' signal",
        )
    )

    mutated_c3: dict[str, Any] = {"applied": live_ok, "note": live_note}

    def c3_correction_rejects_claim():
        observation, provenance = with_mutant("C", lambda: scenario_empty_answer(None, "ToolCallingAgent"))
        mutated_c3.update(provenance)
        if observation is None:
            raise RuntimeError(f"mutant C could not be applied: {provenance.get('refusal')}")
        mutated_c3["observed"] = observation
        assertion = not (
            observation.get("output_is_none") is True and observation.get("state") == "success"
        )
        return {
            "state_with_correction": observation.get("state"),
            "output_with_correction": observation.get("output_repr"),
        }, assertion

    c3.controls.append(
        reader_control(
            "C3c_correction_stops_calling_it_success",
            "with mutant C the None-answer run is no longer labelled success",
            c3_correction_rejects_claim,
            role=CtlRole.REJECTS_THE_DEFECT,
            expected_result=True,
            mutation=ALL_MUTANTS["C"].summary,
            expectation="assertion is True with the correction in place",
        )
    )
    c3.measured["mutant C"] = mutated_c3

    # ── C4 ────────────────────────────────────────────────────────────────────
    c4 = audit.add(
        Criterion(
            name="C4_zero_step_budget_crashes_the_run",
            claim=(
                "A zero step budget makes run() raise UnboundLocalError instead of producing "
                "the fallback answer, so the caller receives an internal variable name "
                "rather than an answer or an explicit error."
            ),
            verdict_rule=(
                "PASS requires both: (a) on the pinned revision max_steps=0 raises "
                "UnboundLocalError naming action_step, after the fallback model call "
                "already happened; (b) on the corrected variant the same configuration "
                "returns the fallback answer."
            ),
            measured={},
            inferred=(
                "Whether a zero budget should be rejected at construction time is a design "
                "choice; not inferred is the crash itself, which is executed."
            ),
            correct_implementation=(
                "Either validate max_steps >= 1 where the agent is constructed, or do not "
                "re-yield an action_step that was never created; a caller must never see "
                "UnboundLocalError from the framework's own bookkeeping."
            ),
            evidence_sites=[
                "src/smolagents/agents.py: _run_stream yields action_step after the loop",
                "src/smolagents/agents.py: run() declares max_steps = max_steps or self.max_steps",
            ],
        )
    )
    zero_budget = scenario_zero_step_budget(healthy_calls=0)
    zero_budget_live_model = scenario_zero_step_budget(healthy_calls=1)
    c4.measured["pinned_revision"] = zero_budget
    c4.measured["pinned_revision_with_a_live_fallback_model"] = zero_budget_live_model

    def c4_precondition() -> bool:
        raised = zero_budget.get("raised") or ""
        return (
            raised.startswith("UnboundLocalError")
            and "action_step" in raised
            and zero_budget.get("call_purposes", [])[:1] == ["fallback_answer_prompt"]
        )

    def dem_crash():
        raised = zero_budget.get("raised") or ""
        assertion = raised.startswith("UnboundLocalError") and zero_budget.get("generate_calls") == 1
        return {
            "raised": raised,
            "generate_calls": zero_budget.get("generate_calls"),
            "call_purposes": zero_budget.get("call_purposes"),
            "note": "the fallback model call already happened before the crash",
        }, assertion

    c4.controls.append(
        state_control(
            "C4a_pinned_zero_budget_raises_UnboundLocalError",
            "on the pinned revision max_steps=0 raises UnboundLocalError naming action_step",
            "the pinned revision still crashes with UnboundLocalError on action_step",
            c4_precondition,
            dem_crash,
            role=CtlRole.DEMONSTRATES_THE_DEFECT,
            expected_result=True,
        )
    )

    mutated_c4: dict[str, Any] = {"applied": live_ok, "note": live_note}

    def c4_correction_rejects_claim():
        observation, provenance = with_mutant("D", lambda: scenario_zero_step_budget(healthy_calls=1))
        mutated_c4.update(provenance)
        if observation is None:
            raise RuntimeError(f"mutant D could not be applied: {provenance.get('refusal')}")
        mutated_c4["observed"] = observation
        output = observation.get("output")
        answer_text = json.dumps(output, default=str) if output is not None else ""
        # The fallback answer must be the text the model actually produced, not an error
        # string: asserting only `output is not None` would accept exactly the
        # "failure disguised as an answer" outcome this audit is about.
        assertion = (
            observation.get("raised") is None
            and observation.get("call_purposes", [])[:1] == ["fallback_answer_prompt"]
            and FALLBACK_MODEL_TEXT in answer_text
        )
        return {
            "raised_with_correction": observation.get("raised"),
            "output_with_correction": answer_text[:200],
            "is_the_model_answer": FALLBACK_MODEL_TEXT in answer_text,
            "call_purposes_with_correction": observation.get("call_purposes"),
            "state_with_correction": observation.get("state"),
        }, assertion

    c4.controls.append(
        reader_control(
            "C4b_correction_returns_the_fallback_answer",
            "with mutant D the zero-budget run returns the answer the model produced "
            "instead of crashing",
            c4_correction_rejects_claim,
            role=CtlRole.REJECTS_THE_DEFECT,
            expected_result=True,
            mutation=ALL_MUTANTS["D"].summary,
            mutation_locations=[live_note] if live_ok else [],
            expectation="assertion is True with the correction in place",
            notes=(
                "this control deliberately asserts the CONTENT of the answer, not merely that "
                "something was returned; an earlier version accepted the error text and would "
                "have passed for the wrong reason"
            ),
        )
    )
    c4.measured["mutant D"] = mutated_c4

    return audit


# ══════════════════════════════════════════════════════════════════════════════
# Discrimination test: every guard that could hide a failure becomes a transparent
# re-raise, then the check set must go red somewhere.
# ══════════════════════════════════════════════════════════════════════════════
GUARD_SITES = [
    {
        "id": "G1",
        "location": "src/smolagents/agents.py: provide_final_answer",
        "guard": "except Exception as e: return ChatMessage(... error text ...)",
        "check_name": "C1a/C1b (pinned run returns the error text as the answer)",
        "run": lambda: scenario_dead_endpoint_at_fallback_answer(),
        "check_goes_red_when": lambda observation: observation.get("raised") is not None,
        "why": (
            "on the pinned revision the guard converts a dead endpoint into an ordinary "
            "answer value, so there is nothing for the caller to catch"
        ),
    },
]


def discrimination_test() -> dict[str, Any]:
    """Replace each guard that converts a failure into a value with a transparent
    re-raise, then re-run the same natural entry point and see whether any check
    changes colour.

    The replacement is mutant A, which is exactly that mutation for the one guard whose
    swallowing is load-bearing in the check set. If no check went red, the audit must
    report that its checks have no discriminating power over that guard.
    """
    results = []
    for site in GUARD_SITES:
        baseline = site["run"]()
        with_correction, provenance = with_mutant("A", site["run"])
        red_with_guard = site["check_goes_red_when"](baseline)
        green_with_correction = with_correction is not None and site["check_goes_red_when"](with_correction)
        results.append(
            {
                "id": site["id"],
                "location": site["location"],
                "guard": site["guard"],
                "check": site["check_name"],
                "guard_replaced_by": "a transparent re-raise (mutant A: the failure is no longer converted into a value)",
                "mutation": provenance,
                "baseline_observation": {
                    "raised": baseline.get("raised"),
                    "output_repr": str(baseline.get("output_repr"))[:200],
                    "state": baseline.get("state"),
                },
                "corrected_observation": (
                    None
                    if with_correction is None
                    else {
                        "raised": with_correction.get("raised"),
                        "output_repr": str(with_correction.get("output_repr"))[:200],
                        "state": with_correction.get("state"),
                    }
                ),
                "check_green_with_guard_in_place": not red_with_guard,
                "check_red_with_guard_replaced": green_with_correction,
                "verdict": (
                    "the guard is load-bearing: replacing it flips at least one check from "
                    "green to red, so the check set discriminates this guard"
                    if green_with_correction and not red_with_guard
                    else "NO check discriminates this guard: the check set is blind here"
                ),
            }
        )
    return {
        "definition": (
            "For each guard that converts a failure into an ordinary value, replace it with "
            "a transparent re-raise and require at least one check to go red. A guard no check "
            "reacts to is a guard the audit cannot defend."
        ),
        "guards_examined": len(GUARD_SITES),
        "sites": results,
        "any_check_went_red": any(r["check_red_with_guard_replaced"] for r in results),
        "sites_with_no_discrimination": [
            r["id"] for r in results if not r["check_red_with_guard_replaced"]
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# False alarms: candidate defects examined and rejected, with the evidence that
# rejected them. Recorded so the report can be honest about what was NOT a finding.
# ══════════════════════════════════════════════════════════════════════════════
def false_alarms() -> list[dict[str, Any]]:
    alarms: list[dict[str, Any]] = []

    # FA1: a dead model on an ORDINARY action step.
    model = BreakableModel(healthy_calls=0)
    agent = ToolCallingAgent(
        tools=[add], model=model, max_steps=3, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            agent.run("What is 2 + 3?", return_full_result=True)
        raised = None
    except BaseException as exc:  # noqa: BLE001
        raised = f"{type(exc).__name__}: {exc}"
    alarms.append(
        {
            "candidate": "a dead model on an ordinary action step is swallowed",
            "verdict": "rejected: the framework raises AgentGenerationError out of run()",
            "evidence": {"raised": raised, "generate_calls": model.calls},
        }
    )

    # FA2: a wiring bug (TypeError) in a user model adapter on an ordinary step.
    class WrongSignature(Model):
        def __init__(self):
            super().__init__(model_id="stub-wrong-signature")

        def generate(self, messages, tools_to_call_from=None):
            raise TypeError("generate() got an unexpected keyword argument 'stop_sequences'")

    agent2 = ToolCallingAgent(
        tools=[add], model=WrongSignature(), max_steps=3, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            agent2.run("What is 2 + 3?", return_full_result=True)
        raised2 = None
    except BaseException as exc:  # noqa: BLE001
        raised2 = f"{type(exc).__name__}: {exc}"
    alarms.append(
        {
            "candidate": "a TypeError wiring bug in a model adapter is absorbed",
            "verdict": "rejected: it is wrapped into AgentGenerationError and raised",
            "evidence": {"raised": raised2},
        }
    )

    # FA3: truncated JSON in tool-call arguments.
    from smolagents.agents import parse_json_if_needed

    alarms.append(
        {
            "candidate": "malformed JSON in tool-call arguments corrupts the answer",
            "verdict": (
                "rejected: parse_json_if_needed returns unparsed text by design, and the "
                "docs plus tests/test_models.py::test_parse_json_if_needed pin that "
                "behaviour ('abc' -> 'abc'). The truncated fragment therefore arrives as a "
                "plain string, which the framework accepts as an answer because a bare "
                "string is a documented argument form for final_answer."
            ),
            "evidence": {
                "parse_json_if_needed('{\"answer\": \"5')": repr(parse_json_if_needed('{"answer": "5')),
                "documented": "docs/source/en/guided_tour.md plus the tool-calling prompt examples",
                "test": "tests/test_models.py:312 test_parse_json_if_needed",
            },
        }
    )

    # FA4: a tool failure followed by model recovery.
    @tool
    def boom() -> str:
        """Always raises.

        Returns:
            nothing, it raises
        """
        raise RuntimeError("backend unavailable")

    class ToolThenAnswer(Model):
        def __init__(self):
            super().__init__(model_id="stub-tool-then-answer")
            self.calls = 0

        def generate(self, messages, tools_to_call_from=None, stop_sequences=None):
            self.calls += 1
            if self.calls == 1:
                return ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content="calling the backend",
                    tool_calls=[
                        ChatMessageToolCall(
                            id="call_0",
                            type="function",
                            function=ChatMessageToolCallFunction(name="boom", arguments={}),
                        )
                    ],
                )
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content="giving up",
                tool_calls=[
                    ChatMessageToolCall(
                        id="call_1",
                        type="function",
                        function=ChatMessageToolCallFunction(name="final_answer", arguments="could not reach it"),
                    )
                ],
            )

    agent3 = ToolCallingAgent(
        tools=[boom], model=ToolThenAnswer(), max_steps=4, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    with contextlib.redirect_stderr(io.StringIO()):
        result3 = agent3.run("ask the backend", return_full_result=True)
    alarms.append(
        {
            "candidate": "a tool failure is invisible and the run reports success anyway",
            "verdict": (
                "rejected: the tool failure is recorded on the step that hit it "
                "(AgentToolExecutionError), and feeding a failed tool call back to the model "
                "so it can retry is the ReAct design. The run state therefore describes the "
                "recovery, which is legitimate."
            ),
            "evidence": {
                "state": result3.state,
                "step_errors": [s.get("error") for s in result3.steps],
            },
        }
    )

    # FA5: final_answer_checks that reject every answer.
    def boolean_guard(final_answer, agent_memory=None, agent=None):
        try:
            int(final_answer)
            return True
        except (ValueError, TypeError):
            return False

    class NonNumeric(Model):
        def __init__(self):
            super().__init__(model_id="stub-non-numeric")
            self.calls = 0

        def generate(self, messages, tools_to_call_from=None, stop_sequences=None):
            self.calls += 1
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content="answer",
                tool_calls=[
                    ChatMessageToolCall(
                        id=f"call_{self.calls}",
                        type="function",
                        function=ChatMessageToolCallFunction(name="final_answer", arguments="about four or so"),
                    )
                ],
            )

    agent4 = ToolCallingAgent(
        tools=[add],
        model=NonNumeric(),
        max_steps=3,
        verbosity_level=LogLevel.OFF,
        logger=_silent_logger(),
        final_answer_checks=[boolean_guard],
    )
    with contextlib.redirect_stderr(io.StringIO()):
        result4 = agent4.run("What is 2 + 3?", return_full_result=True)
    guard_errors = [s.get("error") for s in result4.steps if s.get("error") is not None]
    alarms.append(
        {
            "candidate": (
                "a boolean final_answer_check is inert, because the implementation wraps it "
                "in `assert` (a first code reading suggested assert would not fire on a "
                "False return)"
            ),
            "verdict": (
                "rejected by execution: assert fires on a False return, the guard's rejection "
                "is recorded as an AgentError on the step, and the run ends max_steps_error. "
                "The documented behaviour (log and continue the run) is what happens."
            ),
            "evidence": {
                "guard_returns_false_for_bad_value": boolean_guard("about four or so") is False,
                "guard_errors_recorded": guard_errors[:1],
                "guard_error_count": len(guard_errors),
                "state": result4.state,
            },
        }
    )

    # FA6: an action step that times out and the run still finishes.
    class TimeoutSideEffect(Model):
        def __init__(self, marker: Path):
            super().__init__(model_id="stub-timeout")
            self.marker = marker
            self.calls = 0

        def generate(self, messages, stop_sequences=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                code = (
                    "import time\n"
                    "print('tick 0', flush=True)\n"
                    "time.sleep(2.5)\n"
                    "print('tick 1', flush=True)\n"
                    f"__import__('pathlib').Path({str(self.marker)!r}).write_text('completed')\n"
                )
                return ChatMessage(role=MessageRole.ASSISTANT, content=f"Thought: slow\n<code>\n{code}\n</code>\n")
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content="Thought: done\n<code>\nfinal_answer('answered after a timeout')\n</code>\n",
            )

    marker = Path(tempfile.mkdtemp()) / "marker.txt"
    agent5 = CodeAgent(
        tools=[],
        model=TimeoutSideEffect(marker),
        max_steps=2,
        verbosity_level=LogLevel.OFF,
        logger=_silent_logger(),
        executor_kwargs={"timeout_seconds": 1},
    )
    start = time.time()
    with contextlib.redirect_stderr(io.StringIO()):
        result5 = agent5.run("slow code", return_full_result=True)
    alarms.append(
        {
            "candidate": "an interpreter timeout is silently absorbed and the run reports success",
            "verdict": (
                "rejected as a swallowed failure: the timeout becomes a step observation "
                "(AgentExecutionError 'Code execution exceeded the maximum execution time'), "
                "so the model sees it and the caller can read it from steps[].error. The "
                "residual issue is real but is not this defect class: the run-level state "
                "still says success, and the abandoned interpreter thread cannot be stopped "
                "(documented in local_python_executor.timeout)."
            ),
            "evidence": {
                "state": result5.state,
                "output": result5.output,
                "wall_seconds": round(time.time() - start, 2),
                "step_errors": [s.get("error") for s in result5.steps],
                "observations": [str(s.get("observations"))[:120] for s in result5.steps],
                "timed_out_code_wrote_its_marker": marker.exists(),
            },
        }
    )

    # FA7: a model failure on an ordinary step after a healthy step (max_steps not exhausted).
    model7 = BreakableModel(healthy_calls=1)
    agent7 = ToolCallingAgent(
        tools=[add], model=model7, max_steps=3, verbosity_level=LogLevel.OFF, logger=_silent_logger()
    )
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            agent7.run("What is 2 + 3?", return_full_result=True)
        raised7 = None
    except BaseException as exc:  # noqa: BLE001
        raised7 = f"{type(exc).__name__}: {exc}"
    alarms.append(
        {
            "candidate": "a mid-run endpoint death is swallowed as long as steps remain",
            "verdict": (
                "rejected: it raises AgentGenerationError out of run(). Only the "
                "fallback-answer call converts the same failure into a value."
            ),
            "evidence": {"raised": raised7, "generate_calls": model7.calls},
        }
    )

    return alarms


# ══════════════════════════════════════════════════════════════════════════════
# Pins, artifacts
# ══════════════════════════════════════════════════════════════════════════════
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_pin() -> dict[str, Any]:
    info: dict[str, Any] = {}
    for key, args in (
        ("commit", ["rev-parse", "HEAD"]),
        ("commit_date", ["log", "-1", "--format=%cI"]),
        ("commit_subject", ["log", "-1", "--format=%s"]),
        ("describe", ["describe", "--tags", "--always"]),
        ("dirty", ["status", "--porcelain"]),
    ):
        try:
            completed = subprocess.run(
                ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False
            )
            info[key] = completed.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            info[key] = f"unavailable: {exc}"
    info["packages_audited"] = {}
    #: the revision this harness pins, recorded next to the revision actually found, so a
    #: reader can see the two agree without trusting the console output
    info["pinned_commit_required"] = _setup.PINNED_SMOLAGENTS_COMMIT
    info["pinned_commit_found"] = PINNED_COMMIT_FOUND
    info["upstream_repository"] = _setup.UPSTREAM_REPOSITORY
    for rel in (
        "src/smolagents/agents.py",
        "src/smolagents/models.py",
        "src/smolagents/memory.py",
        "src/smolagents/monitoring.py",
        "src/smolagents/local_python_executor.py",
        "src/smolagents/default_tools.py",
        "src/smolagents/tools.py",
    ):
        path = REPO_ROOT / rel
        info["packages_audited"][rel] = sha256_of(path) if path.exists() else "missing"
    return info


def environment() -> dict[str, Any]:
    packages = {}
    for name in ("smolagents", "huggingface-hub", "requests", "rich", "jinja2", "pillow", "python-dotenv"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor_count": os.cpu_count(),
        "smolagents_module": str(Path(smolagents.__file__).resolve()),
        "repo_root": str(REPO_ROOT),
        "packages": packages,
        "network_used": False,
        "api_key_used": False,
        "gpu_used": False,
    }


def exception_handler_census() -> dict[str, Any]:
    """Measure, rather than estimate, the population that was searched.

    The defect class is "a failure presented as a success", so the code population that
    matters is every `except` handler that does NOT re-raise: those are the places where a
    failure can be turned into a value, a log line, or nothing at all. This walks the
    shipped package's syntax tree and classifies every handler, so the audit can state how
    many candidate sites exist and how many were actually exercised.
    """
    import ast

    package = REPO_ROOT / "src" / "smolagents"
    categories = {
        "re_raises_or_propagates": 0,
        "returns_a_value": 0,
        "swallows_with_pass": 0,
        "logs_only": 0,
        "other": 0,
    }
    sites: list[dict[str, Any]] = []
    files = 0
    handlers = 0
    for path in sorted(package.glob("*.py")):
        files += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                handlers += 1
                body = handler.body
                raises = any(isinstance(sub, ast.Raise) for statement in body for sub in ast.walk(statement))
                returns = any(isinstance(statement, ast.Return) for statement in body)
                only_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
                only_log = all(
                    isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                    for statement in body
                )
                if raises:
                    category = "re_raises_or_propagates"
                elif returns:
                    category = "returns_a_value"
                elif only_pass:
                    category = "swallows_with_pass"
                elif only_log:
                    category = "logs_only"
                else:
                    category = "other"
                categories[category] += 1
                if category != "re_raises_or_propagates":
                    sites.append(
                        {
                            "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                            "line": handler.lineno,
                            "category": category,
                            "except_type": (
                                ast.unparse(handler.type) if handler.type is not None else "bare except"
                            ),
                        }
                    )
    return {
        "definition": (
            "every `except` handler in the shipped package that does not re-raise, because those "
            "are the only places a failure can be converted into a value, a log line or nothing"
        ),
        "python_files_scanned": files,
        "except_handlers_total": handlers,
        "by_category": categories,
        "candidate_sites": len(sites),
        "sites": sites,
    }


def write_unique(path: Path, text: str) -> None:
    """Refuse to overwrite: a verification artifact that silently replaces an earlier
    one destroys the evidence it exists to provide."""
    if path.exists():
        raise SystemExit(
            f"refusing to overwrite existing artifact: {path}\n"
            f"choose a different --outdir or delete the previous run deliberately"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def report_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    pin = payload["pinned_revision"]
    add("# Executable audit: huggingface/smolagents, failure-disguised-as-success")
    add("")
    add(f"- pinned commit: `{pin.get('commit')}` ({pin.get('commit_date')})")
    add(f"- commit subject: {pin.get('commit_subject')}")
    add(f"- audited revision dirty worktree: {bool(pin.get('dirty'))}")
    add(f"- python: {payload['environment']['python'].splitlines()[0]}")
    add(f"- smolagents {payload['environment']['packages'].get('smolagents')} from "
        f"`{payload['environment']['smolagents_module']}`")
    add("- network used: no. API key used: no. GPU used: no.")
    add("")
    add("## Verdicts")
    add("")
    add("| criterion | defect shown on pinned revision | correction removes it | verdict | broken controls |")
    add("|---|---|---|---|---|")
    for crit in payload["audit"]["criteria"]:
        add(
            f"| {crit['name']} | {crit['defect_demonstrated']} | {crit['correction_rejected_claim']} "
            f"| {'PASS' if crit['passed'] else 'NOT PASS'} | {len([c for c in crit['controls'] if c['status'] in ('CONTROL_ERROR', 'CONTROL_PRECONDITION_FAILED')])} |"
        )
    add("")
    add("## Controls")
    add("")
    for crit in payload["audit"]["criteria"]:
        add(f"### {crit['name']}")
        add("")
        add(f"claim: {crit['claim']}")
        add("")
        add(f"verdict rule: {crit['verdict_rule']}")
        add("")
        for ctl in crit["controls"]:
            add(f"- **{ctl['name']}** [{ctl['role']} / {ctl['kind']}] -> `{ctl['status']}`")
            add(f"  - checked: {ctl['checked']}")
            add(f"  - expected assertion result: {ctl['expected_result']}; expectation: {ctl['expectation']}")
            if ctl["precondition"]:
                add(f"  - precondition: {ctl['precondition']} (held: {ctl['precondition_ok']})")
            if ctl["mutation"]:
                add(f"  - mutation: {ctl['mutation']}")
            if ctl["mutation_locations"]:
                add(f"  - edited at: {', '.join(ctl['mutation_locations'])}")
            add(f"  - observed: `{json.dumps(ctl['observed'], ensure_ascii=False, default=str)[:600]}`")
            if ctl["status"] == "CONTROL_ERROR":
                add(f"  - CONTROL_ERROR: {ctl['exception_type']}: {ctl['exception_message']}")
        add("")
    add("## Discrimination test (guard replaced by transparent re-raise)")
    add("")
    add(f"- guards examined: {payload['discrimination']['guards_examined']}")
    add(f"- any check went red: {payload['discrimination']['any_check_went_red']}")
    add(f"- sites with no discriminating check: {payload['discrimination']['sites_with_no_discrimination']}")
    for site in payload["discrimination"]["sites"]:
        add(f"- {site['id']} at {site['location']}")
        add(f"  - guard: `{site['guard']}`")
        add(f"  - replaced by: {site['guard_replaced_by']}")
        add(f"  - check: {site['check']}")
        add(f"  - green with the guard in place: {site['check_green_with_guard_in_place']}")
        add(f"  - red with the guard replaced: {site['check_red_with_guard_replaced']}")
        add(f"  - verdict: {site['verdict']}")
    add("")
    add("## False alarms (examined and rejected)")
    add("")
    for alarm in payload["false_alarms"]:
        add(f"- **{alarm['candidate']}**")
        add(f"  - verdict: {alarm['verdict']}")
        add(f"  - evidence: `{json.dumps(alarm['evidence'], ensure_ascii=False, default=str)[:700]}`")
    add("")
    add("See REPORT_public_audit.md next to this file for the full write-up, including what "
        "this audit does not prove.")
    return "\n".join(lines) + "\n"


def default_outdir() -> Path:
    """A fresh, unique artifact directory for every run.

    The harness refuses to overwrite an artifact, so the default destination must be new
    each time; otherwise the documented one-command reproduction would fail on its second
    use, which is exactly the kind of friction that makes a stranger stop verifying.
    """
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return Path(__file__).resolve().parent / "runs" / f"audit_run_{stamp}_pid{os.getpid()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        default=None,
        help=(
            "directory for artifacts; existing files are never overwritten. "
            "Defaults to a fresh audit/runs/audit_run_<UTC timestamp>_pid<pid> directory."
        ),
    )
    args = parser.parse_args()
    outdir = Path(args.outdir).resolve() if args.outdir else default_outdir()

    print("=" * 100)
    print("three-state audit: huggingface/smolagents - failure disguised as success")
    print("=" * 100)

    payload: dict[str, Any] = {
        "harness": "smolagents/audit/three_state_audit.py",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pinned_revision": git_pin(),
        "environment": environment(),
    }

    print("\n--- 1. schema self-test (audits the harness, not the target) ---")
    st = self_test()
    for crit in st.criteria:
        marks = ", ".join(f"{c.name}={c.status.value}" for c in crit.controls)
        print(f"  {crit.name}: passed={crit.passed}  [{marks}]")
    payload["schema_self_test"] = st.dict()
    print(f"  self-test all_passed = {st.all_passed}")

    print("\n--- 2. criteria ---")
    pristine = pristine_revision_check()
    payload["pristine_revision_check"] = pristine
    print(f"  pinned revision is pristine (no correction left bound): {pristine['pristine']}")
    for label, state in pristine["methods_checked"].items():
        print(f"    {label}: {state}")
    if not pristine["pristine"]:
        raise SystemExit(
            "REFUSING TO GRADE: a corrected variant is still bound on the audited class, so "
            "any 'pinned revision' measurement below would be taken against a corrected "
            "program. This is a broken harness state, not a finding about smolagents."
        )
    audit = build_criteria()
    for crit in audit.criteria:
        print(f"\n  {crit.name}")
        print(f"    claim: {crit.claim}")
        for ctl in crit.controls:
            print(f"    control {ctl.name}: {ctl.status.value} ({ctl.role.value})")
            print(f"      observed: {json.dumps(ctl.observed, ensure_ascii=False, default=str)[:400]}")
            if ctl.status.value == "CONTROL_ERROR":
                print(f"      CONTROL_ERROR: {ctl.exception_type}: {ctl.exception_message}")
        print(f"    -> defect_demonstrated={crit.defect_demonstrated} "
              f"correction_rejected_claim={crit.correction_rejected_claim} passed={crit.passed}")
    payload["audit"] = audit.dict()

    print("\n--- 3. discrimination test ---")
    payload["discrimination"] = discrimination_test()
    for site in payload["discrimination"]["sites"]:
        print(f"  {site['id']} {site['location']}")
        print(f"    check {site['check']} green with guard in place: {site['check_green_with_guard_in_place']}")
        print(f"    check red with guard replaced by re-raise: {site['check_red_with_guard_replaced']}")
        print(f"    verdict: {site['verdict']}")

    print("\n--- 4. false alarms ---")
    payload["false_alarms"] = false_alarms()
    for alarm in payload["false_alarms"]:
        print(f"  candidate: {alarm['candidate']}")
        print(f"    verdict: {alarm['verdict']}")
        print(f"    evidence: {json.dumps(alarm['evidence'], ensure_ascii=False, default=str)[:300]}")

    print("\n--- 5. population census (what was searched, measured not estimated) ---")
    payload["candidate_census"] = exception_handler_census()
    census = payload["candidate_census"]
    print(f"  python files scanned: {census['python_files_scanned']}")
    print(f"  except handlers in total: {census['except_handlers_total']}")
    print(f"  by category: {json.dumps(census['by_category'])}")
    print(f"  candidate sites (handlers that do not re-raise): {census['candidate_sites']}")

    payload["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["summary"] = {
        "criteria": len(audit.criteria),
        "controls": sum(len(c.controls) for c in audit.criteria),
        "criteria_passed": sum(1 for c in audit.criteria if c.passed),
        "criteria_failed": [c.name for c in audit.criteria if not c.passed],
        "broken_controls": [
            {"criterion": name, "control": ctl.name, "status": ctl.status.value}
            for name, ctl in audit.broken
        ],
        "false_alarms": len(payload["false_alarms"]),
        "schema_self_test_passed": st.all_passed,
    }
    print("\n--- 6. summary ---")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))

    write_unique(outdir / "RESULTS.json", json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    write_unique(outdir / "RESULTS.md", report_markdown(payload))
    print(f"\nartifacts written to {outdir}")
    print(f"  {outdir / 'RESULTS.json'}")
    print(f"  {outdir / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
