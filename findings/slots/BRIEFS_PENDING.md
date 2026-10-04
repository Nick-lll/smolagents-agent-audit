# Slots: reader-facing English briefs

**State of this slot: empty on purpose.** No brief has been written yet, and none has been
invented to fill the space. This file says exactly what belongs here so that the person who
writes them does not have to reconstruct the requirement, and so that a reader can see the
difference between "no brief exists" and "a brief was written and says nothing".

## What belongs here

One brief per finding, at:

```
findings/<finding directory>/BRIEF.md
```

A brief is the short reader-facing document for someone who will not run the harness. It is
not a summary of the README in that directory; the README is the evidence record, and the
brief is the argument. Each brief must contain, in this order:

1. **Title and status** — the finding's status from `findings/README.md`, and the pinned
   commit.
2. **The claim in one paragraph** — what a caller observes, phrased as behaviour a user hits,
   with no harness vocabulary. No control names, no `PASS`/`FAIL`, no criterion identifiers.
3. **Why a reader should care** — the concrete consequence for someone building on the
   framework: what they would get wrong if they trusted the status they were given.
4. **The smallest reproduction** — the shortest code a reader can run, and the observed
   output. Where a full reproduction needs the harness, say so and point at
   `REPRODUCE.md` rather than restating the harness.
5. **The exact limit of the claim** — copied, not paraphrased, from the finding's own "what
   this does not prove" section. A brief that omits this is a brief that overclaims.
6. **What was not tested** — the same sentence the finding uses, kept verbatim, so the brief
   and the evidence record cannot drift apart.

## Rules for writing them

- **English.** These are the reader-facing documents; the repository README carries the
  one-line Chinese summary, and the publish runbook is Chinese. A brief is English.
- **No finding may get a brief before it has a recorded artifact.** All four findings have
  one, so all four slots are open.
- **A brief never states something the finding's README does not support.** If a brief needs a
  fact the README lacks, the README is what gets corrected first.
- **`F3` and `F4` briefs must lead with the convention-shaped caveat**, not bury it: for those
  two, a reasonable maintainer can reply that the behaviour is intended.
- **Do not write a brief for the rejected candidates.** Those are recorded in
  `raw/REPORT_public_audit_final.md` §6 with the evidence that rejected them. They are a
  negative result, and a brief would invite the reader to treat them as findings.

## What is already here

| finding | README (evidence record) | brief |
|---|---|---|
| `F1_fallback_answer_swallows_a_model_failure` | present | **slot open** |
| `F2_fallback_failure_reported_as_step_limit` | present | **slot open** |
| `F3_empty_answer_reported_as_success` | present | **slot open** |
| `F4_zero_step_budget_crashes` | present | **slot open** |
