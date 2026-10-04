"""Deliberately corrected variants ("mutants") of the pinned smolagents revision.

Method
------
Every mutant is a pair of LITERAL text replacements against the pristine in-memory
source of one method, obtained with `inspect.getsource` at run time. The procedure is:

  1. take the pristine source of the audited method;
  2. assert the replacement source text occurs exactly once (0 or >1 matches is
     refused, so a drifting target can never silently produce the unmutated program);
  3. assert the injected text really appears in the corrected source;
  4. `exec` the corrected method and bind it onto the class, recording the
     `file:line` range actually replaced.

The result is a program that differs from the pinned revision in exactly the audited
behaviour and nothing else: all other code is the pristine file's own source, including
its imports and helper calls. `mutate.py` restores the original method afterwards.

Each mutant also states the observable truth it asserts, so the audit report can name
exactly what correction was tested against each defect claim.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


class MutantError(RuntimeError):
    """The mutant could not be applied unambiguously."""


@dataclass
class MethodEdit:
    """One method's literal edit inside a corrected variant."""

    method: str
    replacements: list[tuple[str, str]]


@dataclass
class Mutant:
    """One corrected variant plus the provenance needed to re-verify it."""

    key: str
    summary: str
    method: str
    replacements: list[tuple[str, str]]
    asserts: str
    #: text that must appear in the corrected source once the replacement is applied
    must_contain: list[str] = field(default_factory=list)
    #: extra methods edited by the same corrected variant (keyed by method name)
    extra_methods: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def _edits(self) -> list[MethodEdit]:
        edits = [MethodEdit(self.method, self.replacements)]
        for method, replacements in self.extra_methods.items():
            edits.append(MethodEdit(method, replacements))
        return edits

    def apply_to(self, cls: type) -> dict[str, Any]:
        """Bind the corrected method(s) on `cls`, returning provenance.

        The corrected sources are re-compiled inside a scratch class that inherits the
        target class, so the pristine imports and helper calls resolve exactly as they do
        in the audited file. The caller restores the originals inside a `finally` block
        (`restore`).
        """
        originals: dict[str, Any] = {}
        blocks: list[str] = []
        locations: list[str] = []
        line_counts: list[tuple[int, int]] = []

        for edit in self._edits():
            original = getattr(cls, edit.method)
            originals[edit.method] = original
            try:
                source_lines, first_line = inspect.getsourcelines(original)
                source = "".join(source_lines)
            except OSError as exc:  # pragma: no cover - only if the audited file vanished
                raise MutantError(
                    f"mutant {self.key}: cannot read source of {cls.__name__}.{edit.method}: {exc}"
                )
            corrected = source
            for old, new in edit.replacements:
                count = corrected.count(old)
                if count != 1:
                    raise MutantError(
                        f"mutant {self.key}: the text to replace occurs {count} times in "
                        f"{cls.__name__}.{edit.method}; refusing to produce an ambiguous mutant. "
                        f"First 140 chars of the pattern: {old[:140]!r}"
                    )
                line = first_line + corrected[: corrected.index(old)].count("\n")
                locations.append(f"{inspect.getsourcefile(original)}:{line}")
                corrected = corrected.replace(old, new, 1)
            for required in self.must_contain:
                if required in corrected.replace(edit.replacements[0][1], ""):
                    continue
                if required not in corrected:
                    raise MutantError(
                        f"mutant {self.key}: the corrected source of {edit.method} does not "
                        f"contain the required marker {required!r}; the edit did not take effect"
                    )
            blocks.append(corrected)
            line_counts.append((len(source.splitlines()), len(corrected.splitlines())))

        namespace: dict[str, Any] = dict(getattr(getattr(cls, self.method), "__globals__", {}))
        namespace.setdefault("__name__", f"_mutant_{self.key}")
        scratch_lines = [f"class _Scratch({cls.__name__}):"]
        for block in blocks:
            scratch_lines.extend(
                ("    " + ln) if ln.strip() else ln for ln in block.splitlines()
            )
        try:
            exec(compile("\n".join(scratch_lines) + "\n", "<mutant>", "exec"), namespace)
        except SyntaxError as exc:
            raise MutantError(f"mutant {self.key}: the corrected source does not compile: {exc}") from exc
        scratch = namespace.get("_Scratch")
        if scratch is None:  # pragma: no cover - the compile above would have failed first
            raise MutantError(f"mutant {self.key}: corrected source did not define the scratch class")

        for method in originals:
            corrected_fn = scratch.__dict__.get(method)
            if corrected_fn is None:
                raise MutantError(f"mutant {self.key}: corrected source did not define {method}")
            setattr(cls, method, corrected_fn)
        return {
            "mutant": self.key,
            "summary": self.summary,
            "asserts": self.asserts,
            "class": cls.__name__,
            "methods": list(originals),
            "edit_locations": locations,
            "source_lines_before": sum(before for before, _ in line_counts),
            "source_lines_after": sum(after for _, after in line_counts),
        }


def restore(cls: type, method: str, original: Callable) -> None:
    """Put the pinned revision's method back after a mutant has been exercised."""
    setattr(cls, method, original)


# ── The mutants ───────────────────────────────────────────────────────────────
# The `old` text is copied verbatim from the pinned revision (see PINS.json for the
# commit and the per-edit line numbers computed at run time).

MUTANT_A = Mutant(
    key="A",
    summary=(
        "MultiStepAgent.provide_final_answer: re-raise a model failure instead of "
        "returning the error text as the user-visible answer"
    ),
    method="provide_final_answer",
    replacements=[
        (
            """        except Exception as e:
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": f"Error in generating final LLM output: {e}"}],
            )""",
            """        except Exception as e:
            # MUTANT A: a generation failure on the fallback answer is a generation
            # failure. The framework already treats that failure class as fatal on
            # ordinary action steps (_run_stream re-raises AgentGenerationError), so a
            # corrected implementation surfaces it here as well instead of turning the
            # error text into the answer the caller receives.
            raise AgentGenerationError(f"Error in generating final LLM output:\\n{e}", self.logger) from e""",
        )
    ],
    asserts=(
        "an AgentGenerationError raised by provide_final_answer() reaches the caller of "
        "run() instead of a ChatMessage whose text is the error"
    ),
    must_contain=["raise AgentGenerationError(f\"Error in generating final LLM output:"],
)

MUTANT_C = Mutant(
    key="C",
    summary="MultiStepAgent.run: a run whose final answer is None is not labelled success",
    method="run",
    replacements=[
        (
            """            if self.memory.steps and isinstance(getattr(self.memory.steps[-1], "error", None), AgentMaxStepsError):
                state = "max_steps_error"
            else:
                state = "success"
""",
            """            if self.memory.steps and isinstance(getattr(self.memory.steps[-1], "error", None), AgentMaxStepsError):
                state = "max_steps_error"
            elif output is None:
                # MUTANT C: a run that ends without an answer is not a successful run,
                # whatever the step bookkeeping says.
                state = "incomplete"
            else:
                state = "success"
""",
        )
    ],
    asserts='RunResult.state is not "success" when RunResult.output is None',
    must_contain=["state = \"incomplete\""],
)

MUTANT_D = Mutant(
    key="D",
    summary=(
        "MultiStepAgent._run_stream: with a zero step budget, do not re-yield an "
        "action_step that was never bound"
    ),
    method="_run_stream",
    replacements=[
        (
            "            final_answer = self._handle_max_steps_reached(task)\n            yield action_step\n",
            "            final_answer = self._handle_max_steps_reached(task)\n"
            "            if self.step_number <= 1:\n"
            "                # MUTANT D: no action step ever ran, so there is no action_step\n"
            "                # to re-yield; the fallback answer is still produced.\n"
            "                action_step = None\n"
            "            yield action_step\n",
        )
    ],
    asserts="a zero step budget produces a final answer instead of UnboundLocalError",
    must_contain=["action_step = None"],
)

MUTANT_E = Mutant(
    key="E",
    summary=(
        "MultiStepAgent.provide_final_answer plus _handle_max_steps_reached: record the "
        "generation failure on the step that consumed the remaining budget, and report it "
        "in the run state, so the reason for the fallback answer survives in the run's own "
        "bookkeeping instead of only inside the answer text"
    ),
    method="provide_final_answer",
    replacements=[
        (
            """        try:
            chat_message: ChatMessage = self.model.generate(messages)
            return chat_message
        except Exception as e:
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": f"Error in generating final LLM output: {e}"}],
            )""",
            """        try:
            chat_message: ChatMessage = self.model.generate(messages)
            return chat_message
        except Exception as e:
            # MUTANT E: the caller needs to learn that the fallback answer is not an
            # answer. Keep the same returned message, but mark it so the step that
            # consumed the remaining budget can carry the reason.
            error_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": f"Error in generating final LLM output: {e}"}],
            )
            error_message.generation_failure = f"{type(e).__name__}: {e}"
            return error_message""",
        )
    ],
    asserts="when the fallback answer could not be generated, a step error identifies the failure",
    must_contain=["generation_failure"],
    extra_methods={
        "_handle_max_steps_reached": [
            (
                """        final_memory_step.action_output = final_answer.content
        self._finalize_step(final_memory_step)""",
                """        final_memory_step.action_output = final_answer.content
        _generation_failure = getattr(final_answer, "generation_failure", None)
        if _generation_failure:
            # MUTANT E: the step that consumed the remaining budget carries the reason
            # the fallback answer could not be generated.
            final_memory_step.error = AgentError(_generation_failure, self.logger)
        self._finalize_step(final_memory_step)""",
            )
        ]
    },
)


ALL_MUTANTS: dict[str, Mutant] = {m.key: m for m in (MUTANT_A, MUTANT_C, MUTANT_D, MUTANT_E)}
