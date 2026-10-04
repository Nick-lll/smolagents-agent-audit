# Findings

One directory per finding. Every finding here is backed by a recorded artifact from an
executed run, kept verbatim in `raw/`. Nothing in this directory is inferred from reading
code and presented as measured.

## Status vocabulary

| status | meaning |
|---|---|
| `reproduced` | the recorded artifact shows the behaviour on the pinned revision, and the correction flips the check |
| `not reproduced` | a reproducer could not obtain the recorded observation |
| `disputed` | the measurement stands and the maintainer contests its meaning or its severity |
| `withdrawn` | the observation was an artifact of the harness, or the documented behaviour is the intended one and the claim was wrong |

A correction never edits a finding in place. It adds `ERRATUM_<YYYY-MM-DD>.md` to the
finding's directory and updates the status there; see `../DISCLOSURE.md`.

## Layout

```
briefs/    the finding documents: one per finding, plus the authored full report
raw/       the recorded artifacts, copied verbatim, with PROVENANCE.md saying from where
slots/     what is still missing, stated precisely rather than filled with invention
```

A finding is a `briefs/<F>.md` document plus the `raw/` artifact it quotes. Nothing is
summarised into `briefs/` that `raw/` does not support.

## The findings

| brief | claim in one line | status | evidence class |
|---|---|---|---|
| `briefs/F1_fallback_answer_swallows_a_model_failure.md` | when the endpoint dies on the call that produces the fallback answer, `run()` returns the error text **as the answer** instead of raising | `reproduced` | fully measured |
| `briefs/F2_fallback_failure_reported_as_step_limit.md` | the returned `state` cannot distinguish "the step budget ran out" from "the model never answered"; both are `max_steps_error` | `reproduced` | measured; the step-limit label itself is intended behaviour |
| `briefs/F3_empty_answer_reported_as_success.md` | a run that answers nothing returns `output=None` together with `state='success'` | `reproduced` | measured conjunction; the judgement that `None` is never a legitimate answer is a convention |
| `briefs/F4_zero_step_budget_crashes.md` | `max_steps=0` raises `UnboundLocalError` naming an internal variable instead of producing the fallback answer | `reproduced` | measured crash; whether a zero budget is in contract is a design choice |

Four claims, eleven controls, four reproduced, zero broken controls. Seven further candidate
defects were examined with executable checks and **rejected**; they are listed in
`briefs/REPORT_public_audit_final.md` §6, because a negative result is a result and each one is
a claim a less careful audit would have published.

## Raw evidence

| file | what it is | provenance |
|---|---|---|
| `raw/RESULTS.json` | machine-readable criteria, controls, observations, census | a run of this package, `harness/runs/run_20261004T032929Z` |
| `raw/RESULTS.md` | the same rendered as tables | the same run |
| `raw/PIP_FREEZE.txt` | the recorded run's exact dependency versions | `reproduce_final2`, re-encoded to UTF-8 (see below) |
| `raw/PROVENANCE.md` | where each artifact came from, its SHA-256, and what was deliberately left out | written by hand |

`briefs/REPORT_public_audit_final.md` is the authored full write-up, including its §7 "what this
audit does NOT prove". It is documentation rather than harness output, which is why it lives
under `briefs/`; its bytes are hash-pinned like the rest.

## Slots

- **`slots/BRIEFS_PENDING.md`** — the one-page reader-facing briefs. The four finding documents
  under `briefs/` are evidence records written in full; the short one-page brief for each is
  still open. The slot states exactly what belongs in one; nothing was invented to fill it.
- **`slots/POC_INJECTION.md`** — a separate prompt-injection proof of concept. Its state is
  recorded, not summarised, and it is not claimed as a finding here.

## A dangling filename in the recorded output

`raw/RESULTS.md` ends by telling the reader to see `REPORT_public_audit.md` next to it. That
name never existed: the authored report is `REPORT_public_audit_final.md`, and it lives under
`briefs/`. The raw file is left exactly as the harness wrote it rather than edited to hide the
inconsistency, and the correct filename is recorded here.

## What is claimed, and what is only recorded

`reproduced` in the table above means the recorded artifact shows the behaviour and the
correction removes it. It does **not** mean the behaviour is a bug the maintainer must fix:
for `F3` and `F4` a reasonable maintainer can reply that the behaviour is intended and the
claim is about ergonomics or contract boundaries. `../README.md` lists what none of these
checks prove.
