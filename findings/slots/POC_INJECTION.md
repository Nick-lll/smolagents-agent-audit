# Slot: prompt-injection proof of concept

**State of this slot: not included in this package.** The proof of concept is a separate
workstream with its own harness, its own results directory and its own reproduction rate, and
at the time this package was assembled it had not been reviewed or frozen. Nothing from it is
copied, summarised as a finding, or claimed anywhere in this repository.

This file records its actual state, measured from what is on disk, so that a reader of this
package is not left guessing whether an injection finding exists.

## What is recorded

- **What it is:** an offline, keyless proof of concept for indirect prompt injection against
  the same pinned revision of the same project, driven by a harness separate from the
  three-state audit.
- **Its own pinned commit:** the same revision the audit pins. Its own results record the
  target's file digests as unchanged by its runs.
- **What its runs reported when last measured:** 4 scenarios attempted, 2 reproduced, 0 false
  alarms. Reproduced: a local side-effect tool reached by injected text, and a subagent report
  becoming the manager's instruction. Not reproduced: exfiltration through an allowed outbound
  call, and bypassing the `final_answer_checks` guardrail. Both controls that must show no harm
  showed none.
- **How to tell whether that is current:** the authoritative files are that workstream's own
  `RESULTS.md` / `RESULTS.json`. A number repeated here is a copy and can go stale; do not
  cite this file as evidence for a claim about injection.

## Why it is not in this package

1. **It has not been reviewed.** This package's rule is that a finding appears only when a
   reproduction ran *and* the artifact was checked. That check has not happened for this work.
2. **Its reproduction rate is partial by design.** Two of four scenarios reproduced, and the
   two that did not are recorded as such. Presenting that next to four of four fully
   reproduced claims, without the review behind them, would misrepresent both.
3. **Mixing the two defect classes would blur both.** This package is scoped to one defect
   class: a failure presented as a success. Injection is a different class with a different
   threat model, different evidence standard, and different disclosure considerations.

## What would put it here

If that workstream is reviewed and frozen, it becomes a second results set, not an extra
finding in the existing four:

- a finding directory per reproduced scenario, following the same layout and the same status
  vocabulary as `findings/README.md`;
- its recorded artifacts under `findings/raw/`, with a provenance entry stating which run they
  came from;
- a statement of the same two limits every finding here carries: what the proof of concept
  does not prove, and what could not be tested offline;
- a disclosure plan of its own, because a demonstrated injection is a security matter and not
  only a reliability one. `../../DISCLOSURE.md` states the process it would follow.
