# Responsible disclosure

## The short version

This repository was **published on 2026-10-04 at 08:37:13 −04:00 (12:37:13 UTC)**, before
its maintainer was notified. That order is a deviation from the stance stated below, and it
is recorded here rather than quietly corrected: the intent was to notify first, the
publication happened first, and the record says so.

No maintainer had been contacted and no issue had been opened at the moment of publication.
The notification was sent **after** publication, on 2026-10-04 at 10:06 −04:00
(14:06 UTC): see "Timeline" for the time, the recipient, the channel, and the hash of the
body that was sent.

**Correction, 2026-10-05.** The notice as sent said *"we are telling you first, because the
repository is already public and you should hear it from us rather than from a search
result."* The publication came first, so "telling you first" was not true, and the sentence is
withdrawn here rather than left standing. What was true is narrower: the maintainer was told
by us as well as by the repository. No email was sent to correct this — a second message would
be noise — and the correction is kept here, where the disclosure record lives.

## Scope self-assessment: why this is not filed as a vulnerability report

`smolagents` publishes a `SECURITY.md` that defines what it does and does not treat as a
vulnerability, and states that reports which are theoretical, scanner- or LLM-generated, or
which restate documented behaviour are closed without detailed review.

Having read it, **we do not claim any of these findings is a vulnerability under that
policy**, and we are deliberately not filing them through the private vulnerability channel:

- the findings are **reliability and error-reporting defects**, not code execution, memory
  corruption, file access, credential exposure, or a bypass of an advertised protection;
- two of the four (`F3`, `F4`) rest partly on a judgement about intended behaviour — we say
  so in the findings themselves and file them as contract questions, not defects;
- `SECURITY.md` places "best-practice or hardening suggestions with no demonstrated impact"
  and "local ... absent a multi-tenant or remote-service impact" out of scope.

Filing a report we expect to be closed as out-of-scope would spend a maintainer's time and
teach them nothing. The honest alternative is what this repository does: **publish the
reproduction, state the scope we think applies, and let the maintainer be the one who
decides** — with a short private notice to the maintainer, sent after publication, so that the
maintainer is told by us and not only by a search result.

This self-assessment is itself falsifiable and we invite correction: a maintainer who reads
`SECURITY.md` differently should say so, and the finding's status will be updated as
described below.

## Stance

1. **Notify the maintainer before publishing, not after.** *This is the intended order and
   it was not followed here; see "The short version".* The reproduction is written so that a
   maintainer can run it without our help and without trusting us. A maintainer who can
   reproduce a finding in one command is in a position to decide, and that is the only
   position from which a report is useful.
2. **Publish the reproduction, not a claim about severity.** Nothing here is a severity
   rating, a CVE request, or a statement that these are the worst issues in the project.
   One defect class was targeted and one revision was audited. Severity is stated per
   finding and two findings are explicitly marked as contract questions.
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
6. **Disclose AI assistance.** The audit was carried out with AI assistance, and that is
   stated here because a report that conceals it is not worth reading. What makes the
   findings checkable is not who or what produced them but that **every one is an executed,
   reproducible check with a control that can fail** — run `python run.py` and judge the
   result, not the author.

## Timeline (actual, not planned)

Times are given with their UTC offset; the local clock at the time of these events was
−04:00, so `−04:00` and UTC are both stated wherever a clock time matters. A date on its own
was not enough to check the order of the events below, so the clock times are recorded here.

| date and time | action |
|---|---|
| 2026-10-04 | audit completed against the pinned revision; artifacts recorded |
| 2026-10-04 08:37:13 −04:00 / 12:37:13 UTC | **repository published** — initial commit `48c6aa1af7`, remote `https://github.com/Nick-lll/smolagents-agent-audit` |
| 2026-10-04 09:33:49 −04:00 / 13:33:49 UTC | this file corrected to state the publication; scope self-assessment added (`4ab8141`) |
| 2026-10-04 09:36:10 −04:00 / 13:36:10 UTC | a verifier note that had become false is itself corrected; remote HEAD becomes `3f4e6080` |
| 2026-10-04 10:06 −04:00 / 14:06 UTC *(the send time is as reported by the sender; it was not observed by the tooling that recorded the other times in this table)* | **short private notice sent**, by email, from `nickchen791@gmail.com` to **`security@huggingface.co`** — the address `huggingface/smolagents`'s own `SECURITY.md` names for private reporting. No vulnerability claim, no demand, no attachment. Body verbatim: 1138 bytes, UTF-8, LF line endings only, SHA-256 `608e25c846a6f6dbc61785bacef178629f55e5579d9f481f6bd6ba8c13e6f256` |
| 2026-10-05 | all four findings re-run in a fresh clone of the audited project and in the recorded environment; the pinned commit `c30b1152` turned out to be upstream's current `main` tip, so all four still `reproduced` at the latest upstream revision. Record: `findings/recertification/RERUN_2026-10-05_latest_upstream_revision.md` |
| +7 days after the notice | if no reply, a single reminder is sent; no second reminder follows |
| +14 days after the notice | any reply from the maintainer is published next to the findings, as given |
| onward | any further correspondence is answered on the publication itself, as a dated erratum |

**The order is publication, then notification.** The notice went out 1 hour 29 minutes after
the repository became public, to the address `SECURITY.md` publishes, and it said so itself
("the repository is already public"). Nothing in this file should be read as a claim that the
maintainer was given advance notice, a private window, or priority of any kind: they were not.

The window is short because nothing here is remotely exploitable and nothing here concerns a
live service: every finding is a local, offline, already-public behaviour of a pinned
revision, reproducible by anyone who clones it. A maintainer can extend it by asking, and a
request for more time moves the timetable to whatever date they ask for.

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

Contact for corrections, disputes, or re-runs: **nickchen791@gmail.com**
