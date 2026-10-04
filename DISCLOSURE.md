# Responsible disclosure

## The short version

These findings have not been disclosed to anyone. No maintainer has been contacted, no issue
has been opened, no advisory has been filed. As of this writing the repository is local and
unpublished. The first step of publishing, in the operator runbook, is notifying the
maintainer — not pushing the repository.

## Stance

1. **Notify the maintainer before publishing, not after.** The reproduction is written so
   that a maintainer can run it without our help and without trusting us. A maintainer who
   can reproduce a finding in one command is in a position to decide, and that is the only
   position from which a report is useful.
2. **Publish the reproduction, not a claim about severity.** Nothing here is a severity
   rating, a CVE request, or a statement that these are the worst issues in the project.
   One defect class was targeted and one revision was audited.
3. **Correct in public, and never silently.** If a maintainer disputes a finding the
   correction is a dated erratum in the finding's own directory, with the original text
   left in place. See "If a maintainer disputes a finding" below. The history of a
   corrected claim is part of the artifact.
4. **No live service is ever touched.** The audit runs against a local clone at a pinned
   commit, with a stub model that raises instead of calling a provider. Reproducing it
   cannot load a vendor's endpoint, and no reader needs an account to verify anything here.
5. **No personal data, no vendor systems, no credentials.** Nothing in this repository
   contains a token, a key, an account identifier, a private path, or a third party's
   unpublished information.

## Timeline

This is the policy the publication will follow. None of the notification steps has been
carried out yet; the measured facts about the audit itself (dates, commits, artifacts) are
in `REPRODUCE.md`.

| day | action |
|---|---|
| D-0 | the maintainer is notified privately, with the reproduction command and the recorded artifact for each finding |
| D-0 | a maintainer who asks for more time is given it, in writing, and the publication date moves to whatever date they ask for |
| D-7 | if the maintainer has not responded, a single reminder is sent; no second reminder follows |
| D-14 | publication of the repository, including any reply the maintainer gave and any correction they asked for |
| D-14 onward | any further correspondence is answered on the publication itself, as a dated erratum |

The embargo is short because nothing here is remotely exploitable and nothing here concerns
a live service: every finding is a local, offline, already-public behaviour of a pinned
revision, reproducible by anyone who clones it. A long embargo would protect nothing and
would leave a reader running the documented behaviour without knowing it had been
characterised. A maintainer can extend it by asking.

## What happens if a maintainer disputes a finding

Disagreement is the expected outcome for at least two of the four findings, because two of
them rest partly on a judgement about intended behaviour rather than on measurement alone
(`F3`'s claim that a `None` answer should never be labelled `success`, and `F4`'s zero-step
budget, which is a boundary configuration rather than the documented default). The process
for a dispute:

1. **Nothing is edited silently.** The original claim, the original observation, and the
   original artifact stay exactly where they are. A finding is never rewritten to look as
   though it had always been correct, and no finding is deleted.
2. **A dated erratum is added** to the finding's directory as `ERRATUM_<YYYY-MM-DD>.md`,
   stating: what the maintainer disputed, the exact evidence they gave, whether the
   dispute changes the measurement or only its interpretation, and the maintainer's
   position in their own words where they permit quotation.
3. **The finding's status line is updated** to one of `disputed`, `partly disputed`, or
   `withdrawn`, with a link to the erratum. The status vocabulary is fixed:
   - `reproduced` — the recorded artifact shows the defect on the pinned revision and the
     correction flips the check;
   - `not reproduced` — a reproducer could not obtain the recorded observation;
   - `disputed` — the measurement stands and the maintainer contests its meaning or
     severity;
   - `withdrawn` — the maintainer's evidence shows the observation was an artifact of the
     harness, or that the documented behaviour is the intended one and the claim was wrong.
4. **A withdrawn finding stays published as withdrawn.** The value of a corrected claim is
   that the correction is visible. Deleting it would remove the only evidence that the
   dispute process works.
5. **A dispute about measurement triggers a re-run, not an argument.** If a maintainer says
   the observation does not reproduce, the response is a fresh run at the pinned commit
   with the artifact published next to the erratum. If it does not reproduce for them, the
   finding moves to `not reproduced` and the finding's directory records the environment
   difference, since that difference is itself information.
6. **The maintainer's fix is reported as their fix.** When an upstream commit changes the
   audited behaviour, the finding records the commit that changed it and the run that
   confirms the change. The finding is not edited to claim credit for a correction the
   project made, and the pin is not moved to make the finding look as though it still
   applies.

## Credit and contact

The audit asks for no credit and offers no bounty. The pinned commit, the audited file
hashes, and the recorded artifacts are published so that the work can be checked and
re-run independently. A maintainer who wants the raw run logs, a different scenario, or a
re-run at a different revision can have them; nothing here depends on keeping information
back.
