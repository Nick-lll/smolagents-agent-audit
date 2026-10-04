"""Three-state verification core for the public audit of huggingface/smolagents.

This module is deliberately self-contained: it imports nothing but the standard library,
so a stranger can read it and re-run the audit without any familiarity with the authoring
toolchain. The verdict vocabulary is small on purpose:

  PASS                          the control ran and its assertion held as expected
  FAIL                          the control ran and its assertion did not hold as expected
  CONTROL_ERROR                 the control itself raised, so it says nothing about the target
  CONTROL_PRECONDITION_FAILED   a STATE control no longer applies to this revision

Design rules enforced here, not merely documented:

  * A control never reports PASS because it did not run. A control that raises is
    folded into CONTROL_ERROR with the original exception type, message and full
    traceback. A STATE control whose precondition fails at run time reports
    CONTROL_PRECONDITION_FAILED and does NOT execute its body.
  * Every control declares its kind (READER = pure function on synthetic input,
    STATE = depends on the audited revision still having the defect under test).
  * `expected_result` is mandatory and has no default. A defaulted boolean whose meaning
    can be read both ways is how a control silently stops testing anything: an earlier
    harness lost three criteria to exactly that, so the parameter is required.
  * A defect claim requires TWO controls: one that demonstrates the defect on the
    pinned revision, and one that rejects the claim when a corrected variant is
    substituted in its place. A claim with a missing or broken control can never be
    PASS. A claim with no should-fail control has not been shown to be falsifiable and is
    therefore not PASS either.
  * `self_test()` drives the real factories with bodies whose outcome is known in advance
    and asserts the status the schema must report. It audits the harness, not the target,
    and it runs first in every recorded run.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CtlStatus(str, Enum):
    """The three states, plus the "this control no longer applies" state."""

    PASS = "PASS"
    FAIL = "FAIL"
    CONTROL_ERROR = "CONTROL_ERROR"
    CONTROL_PRECONDITION_FAILED = "CONTROL_PRECONDITION_FAILED"


class CtlKind(str, Enum):
    """READER: pure function on synthetic input, runnable at any time.
    STATE: depends on the audited revision still exhibiting the defect."""

    READER = "reader"
    STATE = "state"


class CtlRole(str, Enum):
    """DEMONSTRATES_THE_DEFECT: passes when the defect reproduces on the pinned revision.
    REJECTS_THE_DEFECT: passes when the same check does NOT reproduce it on a
    deliberately corrected variant (this is the should-fail control)."""

    DEMONSTRATES_THE_DEFECT = "demonstrates_the_defect"
    REJECTS_THE_DEFECT = "rejects_the_defect"


@dataclass
class Control:
    """One typed control record. Field names are explicit; there is no **kwargs sink."""

    name: str
    role: CtlRole
    kind: CtlKind
    status: CtlStatus
    checked: str
    expected_result: bool
    observed: Any = None
    expectation: str = ""
    precondition: str = ""
    precondition_ok: bool | None = None
    mutation: str = ""
    mutation_locations: list[str] = field(default_factory=list)
    notes: str = ""
    exception_type: str = ""
    exception_message: str = ""
    traceback_text: str = ""

    @property
    def decisive(self) -> bool:
        return self.status in (CtlStatus.PASS, CtlStatus.FAIL)

    @property
    def broken(self) -> bool:
        return not self.decisive

    def dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "kind": self.kind.value,
            "status": self.status.value,
            "checked": self.checked,
            "expected_result": self.expected_result,
            "observed": self.observed,
            "expectation": self.expectation,
            "precondition": self.precondition,
            "precondition_ok": self.precondition_ok,
            "mutation": self.mutation,
            "mutation_locations": self.mutation_locations,
            "notes": self.notes,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "traceback_text": self.traceback_text,
        }


def _capture(name, role, kind, checked, exc, **extra) -> Control:
    return Control(
        name=name,
        role=role,
        kind=kind,
        status=CtlStatus.CONTROL_ERROR,
        checked=checked,
        expected_result=extra.pop("expected_result", False),
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback_text="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        notes="the control itself raised; this is a broken control, not a finding about the target",
        **extra,
    )


def reader_control(
    name: str,
    checked: str,
    fn: Callable[[], tuple[Any, bool]],
    *,
    role: CtlRole,
    expected_result: bool,
    expectation: str = "",
    mutation: str = "",
    mutation_locations: list[str] | None = None,
    notes: str = "",
) -> Control:
    """Run a READER control.

    `fn()` returns `(observed, assertion_satisfied)`. The control is decisive when
    `assertion_satisfied == expected_result`. A non-boolean second element is a
    CONTROL_ERROR: a control whose assertion result cannot be interpreted has lost its
    meaning, and reporting PASS or FAIL for it would be a guess.
    """
    try:
        observed, satisfied = fn()
    except BaseException as exc:  # noqa: BLE001 - a broken control must be visible
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _capture(
            name, role, CtlKind.READER, checked, exc,
            expected_result=expected_result, mutation=mutation,
            mutation_locations=mutation_locations or [],
        )
    if not isinstance(satisfied, bool):
        return _capture(
            name, role, CtlKind.READER, checked,
            TypeError(
                f"control returned a non-boolean assertion result "
                f"({type(satisfied).__name__}: {satisfied!r}); the second element must be "
                f"whether the assertion held"
            ),
            expected_result=expected_result, observed=observed,
            mutation=mutation, mutation_locations=mutation_locations or [],
        )
    ok = satisfied is expected_result
    return Control(
        name=name,
        role=role,
        kind=CtlKind.READER,
        status=CtlStatus.PASS if ok else CtlStatus.FAIL,
        checked=checked,
        expected_result=expected_result,
        observed=observed,
        expectation=expectation or f"the assertion's result must be {expected_result}",
        mutation=mutation,
        mutation_locations=mutation_locations or [],
        notes=notes,
    )


def state_control(
    name: str,
    checked: str,
    precondition: str,
    precondition_fn: Callable[[], bool],
    fn: Callable[[], tuple[Any, bool]],
    *,
    role: CtlRole,
    expected_result: bool,
    expectation: str = "",
    mutation: str = "",
    mutation_locations: list[str] | None = None,
    notes: str = "",
) -> Control:
    """Run a STATE control after re-asserting its precondition at run time.

    If the precondition no longer holds, the control reports
    CONTROL_PRECONDITION_FAILED and does NOT run its body: a control that no longer
    applies must say so rather than contribute a meaningless False.
    """
    try:
        pre_ok = bool(precondition_fn())
    except BaseException as exc:  # noqa: BLE001
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _capture(
            name, role, CtlKind.STATE, checked, exc,
            expected_result=expected_result, precondition=precondition,
            precondition_ok=False, mutation=mutation,
            mutation_locations=mutation_locations or [],
        )
    if not pre_ok:
        return Control(
            name=name,
            role=role,
            kind=CtlKind.STATE,
            status=CtlStatus.CONTROL_PRECONDITION_FAILED,
            checked=checked,
            expected_result=expected_result,
            precondition=precondition,
            precondition_ok=False,
            mutation=mutation,
            mutation_locations=mutation_locations or [],
            notes=(
                "precondition no longer holds in this run, so this control does not "
                "apply to the revision under test; it is neither PASS nor FAIL"
            ),
        )
    try:
        observed, satisfied = fn()
    except BaseException as exc:  # noqa: BLE001
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return _capture(
            name, role, CtlKind.STATE, checked, exc,
            expected_result=expected_result, precondition=precondition,
            precondition_ok=True, mutation=mutation,
            mutation_locations=mutation_locations or [],
        )
    if not isinstance(satisfied, bool):
        return Control(
            name=name,
            role=role,
            kind=CtlKind.STATE,
            status=CtlStatus.CONTROL_ERROR,
            checked=checked,
            expected_result=expected_result,
            observed=observed,
            precondition=precondition,
            precondition_ok=True,
            mutation=mutation,
            mutation_locations=mutation_locations or [],
            notes="control returned a non-boolean assertion result",
        )
    return Control(
        name=name,
        role=role,
        kind=CtlKind.STATE,
        status=CtlStatus.PASS if satisfied is expected_result else CtlStatus.FAIL,
        checked=checked,
        expected_result=expected_result,
        observed=observed,
        expectation=expectation or f"the assertion's result must be {expected_result}",
        precondition=precondition,
        precondition_ok=True,
        mutation=mutation,
        mutation_locations=mutation_locations or [],
        notes=notes,
    )


@dataclass
class Criterion:
    """One audited claim, with the controls that back it."""

    name: str
    claim: str
    verdict_rule: str
    measured: dict[str, Any] = field(default_factory=dict)
    inferred: str = ""
    correct_implementation: str = ""
    controls: list[Control] = field(default_factory=list)
    evidence_sites: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Criterion.name must not be empty: artifact keys come from it")
        if not self.claim:
            raise ValueError(f"{self.name}: a criterion without a stated claim cannot be reviewed")
        if not self.verdict_rule:
            raise ValueError(f"{self.name}: verdict_rule must say what counts as PASS")

    @property
    def defect_demonstrated(self) -> bool:
        controls = [c for c in self.controls if c.role is CtlRole.DEMONSTRATES_THE_DEFECT]
        return bool(controls) and all(c.status is CtlStatus.PASS for c in controls)

    @property
    def correction_rejected_claim(self) -> bool:
        controls = [c for c in self.controls if c.role is CtlRole.REJECTS_THE_DEFECT]
        return bool(controls) and all(c.status is CtlStatus.PASS for c in controls)

    @property
    def broken_controls(self) -> list[Control]:
        return [c for c in self.controls if c.broken]

    @property
    def passed(self) -> bool:
        """A criterion is PASS only when at least one control plays each role, every
        control ran (none broken, none with a failed precondition), and both directions
        hold: the defect shows on the pinned revision and disappears under a correction.

        A criterion with only one role is not PASS: a claim with no should-fail control
        has not been shown to be falsifiable. A broken control (CONTROL_ERROR,
        CONTROL_PRECONDITION_FAILED) can never contribute to PASS.
        """
        demonstrates = [c for c in self.controls if c.role is CtlRole.DEMONSTRATES_THE_DEFECT]
        rejects = [c for c in self.controls if c.role is CtlRole.REJECTS_THE_DEFECT]
        if not demonstrates or not rejects:
            return False
        if any(c.broken for c in self.controls):
            return False
        return all(c.status is CtlStatus.PASS for c in demonstrates + rejects)

    def dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "claim": self.claim,
            "verdict_rule": self.verdict_rule,
            "passed": self.passed,
            "defect_demonstrated": self.defect_demonstrated,
            "correction_rejected_claim": self.correction_rejected_claim,
            "measured": self.measured,
            "inferred": self.inferred,
            "correct_implementation": self.correct_implementation,
            "evidence_sites": self.evidence_sites,
            "controls": [c.dict() for c in self.controls],
        }


@dataclass
class Audit:
    """A criteria set, serialized by object rather than by hand-written key paths."""

    subject: str
    criteria: list[Criterion] = field(default_factory=list)

    def add(self, criterion: Criterion) -> Criterion:
        if any(c.name == criterion.name for c in self.criteria):
            raise ValueError(f"duplicate criterion name {criterion.name}")
        self.criteria.append(criterion)
        return criterion

    @property
    def all_passed(self) -> bool:
        return bool(self.criteria) and all(c.passed for c in self.criteria)

    @property
    def broken(self) -> list[tuple[str, Control]]:
        return [(c.name, ctl) for c in self.criteria for ctl in c.broken_controls]

    def dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "all_passed": self.all_passed,
            "criteria_count": len(self.criteria),
            "control_count": sum(len(c.controls) for c in self.criteria),
            "broken_control_count": len(self.broken),
            "criteria": [c.dict() for c in self.criteria],
        }


def self_test() -> Audit:
    """Prove the schema discriminates before it is used to judge anything else.

    Each criterion below drives the real factories with a body whose outcome is known
    in advance and asserts the status the schema must report. If the schema silently
    turned a broken control into PASS, these self-tests would fail.
    """
    audit = Audit(subject="three-state schema self-test: audits the harness, not the target")

    def _raises():
        raise RuntimeError("synthetic control failure")

    def _never_runs():  # pragma: no cover - presence of its effect is the assertion
        raise AssertionError("body must not run when the precondition is false")

    def _probe(kind_name: str, inner_kind: str) -> tuple[Any, bool]:
        def clause():
            if inner_kind == "reader":
                return reader_control(kind_name, "synthetic", _raises,
                                      role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=False)
            return state_control(kind_name, "synthetic", "synthetic precondition that is false",
                                 lambda: False, _never_runs,
                                 role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True)

        inner = clause()
        if inner_kind == "reader":
            assertion = (
                inner.status is CtlStatus.CONTROL_ERROR
                and inner.exception_type == "RuntimeError"
                and "synthetic control failure" in inner.traceback_text
            )
        else:
            assertion = (
                inner.status is CtlStatus.CONTROL_PRECONDITION_FAILED
                and inner.precondition_ok is False
                and inner.observed is None
            )
        return {"inner_status": inner.status.value, "inner_exception": inner.exception_type}, assertion

    audit.add(
        Criterion(
            name="ST1_reader_control_that_raises_is_CONTROL_ERROR",
            claim="a control whose body raises is CONTROL_ERROR and keeps the original traceback",
            verdict_rule="status is CONTROL_ERROR, exception type recorded, traceback retained",
            controls=[
                reader_control("st1", "reader control body raises RuntimeError",
                               lambda: _probe("inner_raises", "reader"),
                               role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True),
                reader_control(
                    "st1b",
                    "the same probe would be False if the schema reported PASS for a raising body",
                    lambda: ({"inner_status_seen": _probe("inner_raises_2", "reader")[0]["inner_status"]},
                             _probe("inner_raises_3", "reader")[0]["inner_status"] != "PASS"),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    audit.add(
        Criterion(
            name="ST2_false_precondition_is_CONTROL_PRECONDITION_FAILED",
            claim="a STATE control with a false precondition reports "
                  "CONTROL_PRECONDITION_FAILED and does not run its body",
            verdict_rule="status is CONTROL_PRECONDITION_FAILED and observed is None",
            controls=[
                reader_control("st2", "STATE control with precondition false",
                               lambda: _probe("inner_stale", "state"),
                               role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True),
                reader_control(
                    "st2b",
                    "the classification is not PASS and not FAIL",
                    lambda: ({"inner_status_seen": _probe("inner_stale_2", "state")[0]["inner_status"]},
                             _probe("inner_stale_3", "state")[0]["inner_status"]
                             not in ("PASS", "FAIL")),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    audit.add(
        Criterion(
            name="ST3_mismatched_expectation_is_FAIL",
            claim="a control whose assertion contradicts its expectation reports FAIL",
            verdict_rule="status is FAIL",
            controls=[
                reader_control(
                    "st3",
                    "assertion says False but expected_result is True",
                    lambda: ("observed", reader_control(
                        "inner_mismatch", "synthetic", lambda: ("o", False),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True).status
                              is CtlStatus.FAIL),
                    role=CtlRole.DEMONSTRATES_THE_DEFECT,
                    expected_result=True,
                ),
                reader_control(
                    "st3b",
                    "the same shape with a matching expectation is not FAIL",
                    lambda: ("observed", reader_control(
                        "inner_mismatch_repaired", "synthetic", lambda: ("o", False),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=False).status
                              is not CtlStatus.FAIL),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    audit.add(
        Criterion(
            name="ST4_matching_expectation_is_PASS",
            claim="a control whose assertion matches its expectation reports PASS",
            verdict_rule="status is PASS",
            controls=[
                reader_control(
                    "st4",
                    "assertion says True and expected_result is True",
                    lambda: ("observed", reader_control(
                        "inner_match", "synthetic", lambda: ("o", True),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True).status
                              is CtlStatus.PASS),
                    role=CtlRole.DEMONSTRATES_THE_DEFECT,
                    expected_result=True,
                ),
                reader_control(
                    "st4b",
                    "flipping the expectation flips the status away from PASS",
                    lambda: ("observed", reader_control(
                        "inner_match_flipped", "synthetic", lambda: ("o", True),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=False).status
                              is not CtlStatus.PASS),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    audit.add(
        Criterion(
            name="ST5_non_boolean_assertion_is_CONTROL_ERROR",
            claim="a control whose second element is not a bool is refused, not interpreted",
            verdict_rule="status is CONTROL_ERROR with a TypeError recorded",
            controls=[
                reader_control(
                    "st5",
                    "second element is a string instead of a bool",
                    lambda: ("observed", reader_control(
                        "inner_not_a_bool", "synthetic", lambda: ("o", "o"),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=False).exception_type
                              == "TypeError"),
                    role=CtlRole.DEMONSTRATES_THE_DEFECT,
                    expected_result=True,
                ),
                reader_control(
                    "st5b",
                    "a genuine bool is not refused",
                    lambda: ("observed", reader_control(
                        "inner_bool_ok", "synthetic", lambda: ("o", True),
                        role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True).exception_type
                              == ""),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    audit.add(
        Criterion(
            name="ST6_PASS_requires_both_roles",
            claim="a criterion holding only defect-demonstrating controls is not PASS: "
                  "without a should-fail control the claim is unsupported",
            verdict_rule="criterion.passed is False and correction_rejected_claim is False",
            controls=[
                reader_control(
                    "st6",
                    "criterion with a single DEMONSTRATES_THE_DEFECT control",
                    lambda: ("observed", (lambda c: (c.passed is False and c.correction_rejected_claim is False))(
                        Criterion(
                            name="sole_control",
                            claim="single-role criterion",
                            verdict_rule="n/a",
                            controls=[reader_control(
                                "only", "synthetic", lambda: ("o", True),
                                role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True)],
                        ))),
                    role=CtlRole.DEMONSTRATES_THE_DEFECT,
                    expected_result=True,
                ),
                reader_control(
                    "st6b",
                    "adding the missing role makes the same criterion PASS",
                    lambda: ("observed", (lambda c: c.passed)(
                        Criterion(
                            name="both_roles",
                            claim="two-role criterion",
                            verdict_rule="n/a",
                            controls=[
                                reader_control("only", "synthetic", lambda: ("o", True),
                                               role=CtlRole.DEMONSTRATES_THE_DEFECT, expected_result=True),
                                reader_control("reject", "synthetic", lambda: ("o", True),
                                               role=CtlRole.REJECTS_THE_DEFECT, expected_result=True),
                            ],
                        ))),
                    role=CtlRole.REJECTS_THE_DEFECT,
                    expected_result=True,
                ),
            ],
        )
    )

    return audit
