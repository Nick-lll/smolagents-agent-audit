# smolagents audit: failure disguised as success

**简体中文一句话摘要**：本仓库是一份可离线复现的开源审计，检查 `huggingface/smolagents` 在固定提交上是否存在「失败被当成成功返回」的缺陷；仓库自带的测试框架本身可被验证，四项判据中四项获得复现，且本文明确列出这些检查**不能**证明什么。

---

## What this is

An offline, keyless, CPU-only verification harness and its recorded results. It audits one
defect class in one pinned revision of one public framework:

> **a failure that is presented to the caller as a success.**

The target is `huggingface/smolagents` at commit
`c30b115286e000e98711fae5e85993547b73d826`. Four claims were written and all four
reproduced; seven further candidate defects were examined and rejected with evidence. The
harness audits itself first, so a control that fails to run can never be reported as a
finding about the target.

The full write-up of each finding is in `findings/`. The method is in `REPRODUCE.md`.

## Who this is for

- **Maintainers of the audited project**, who want a reproduction they can run themselves
  before deciding whether to act. `REPRODUCE.md` is written for you and needs no
  cooperation from us.
- **Security and reliability engineers** evaluating whether an agent framework tells them
  the truth when a model call dies mid-run.
- **Anyone building a control or CI check on top of an agent framework**, who needs to know
  which run outcomes are distinguishable from which.
- **Readers of the finding briefs**, who want the raw artifact behind each claim rather
  than a summary of it.

## Run everything with one command

```sh
python scripts/fetch_targets.py   # once: clones the audited revision (needs network)
python run.py                     # every time: runs the audit, writes artifacts, prints verdicts
```

Then read `harness/runs/<timestamp>/RESULTS.md`, or the rendered copy kept at
`findings/raw/`.

**Environment: no network, no API key, no GPU required.** Only the one-time clone needs
network. The audit itself uses a stub `Model` subclass that raises instead of calling a
provider, so no paid endpoint is ever contacted. Requirements are Python 3.10+, git, and
about 200 MB of disk.

## What these checks do NOT prove

This section is the point of the repository. Read it before quoting any number here.

- **A finding is claimed only when a reproduction ran.** Every claim below is backed by
  recorded output from an executed run, kept verbatim in `findings/raw/`. Nothing here is
  inferred from reading code and presented as measured. Where a step is a convention rather
  than a measurement, the finding says so in its own "what this does not prove" section.
- **This does not prove the absence of other defects.** The harness walked the syntax tree
  of the shipped package and found 89 `except` handlers, 37 of which do not re-raise. Eleven
  of those 37 were exercised with an executable check; the rest were read, not run. Any of
  the unexercised ones could hide a defect this harness cannot see.
- **This does not rank severity, and does not claim these are the worst issues in the
  project.** One defect class was targeted. Nothing here should be read as a security
  rating or a severity score.
- **No real model provider was ever contacted.** Every scenario drives the genuine
  framework loop with a stub model that raises `ConnectionError`. The control flow under
  test is real; the provider's own retry and error taxonomy is not exercised. A provider
  that retries internally could change how often the audited path is reached — though not
  whether it swallows.
- **The corrected variants are our corrections, not the project's patches.** They exist to
  prove each check can fail, and they are applied in memory only. They have not been
  submitted upstream and are not proposals.
- **Two of the four claims rest on judgement, not only measurement.** The claim that a
  `None` answer should never be labelled `success` is a convention. The zero-step-budget
  configuration is a boundary, not the documented default of 20 steps; a maintainer could
  reasonably call it out of contract. Both are flagged in the relevant finding.
- **Large parts of the project were out of reach offline**: remote executors (e2b, docker,
  modal), the MCP client, hub push/pull, the Gradio UI and the vision-browser examples.
  None of them were tested, and none of them is covered by any claim here.
- **The harness's own results can move if the target moves.** `harness/_setup.py` refuses to
  run unless the checkout is at the pinned commit, because a control measured against one
  revision cannot report a verdict about another.
- **A published result is a snapshot, not a standing guarantee.** If the pinned revision is
  superseded, the recorded artifacts still describe that revision and nothing later.

## Repository layout

```
README.md              this file
REPRODUCE.md           exact commands, pinned commits, expected output, reproduction rate
DISCLOSURE.md          responsible-disclosure stance, timeline, dispute handling
PUBLISH_RUNBOOK.md     the operator's procedure for publishing this repository (Chinese)
LICENSE                Apache-2.0 (see the note at the end of the file for why)
verify_package.py      offline self-containment check; run it before publishing
run.py                 the one command
scripts/fetch_targets.py   clones the audited revision at its pinned commit
harness/               the runnable harness (core.py, mutants.py, three_state_audit.py, _setup.py)
harness/runs/          artifacts written by your own runs (not committed)
findings/briefs/       one document per finding, plus the authored full report
findings/raw/          the recorded artifacts, copied verbatim, with PROVENANCE.md
findings/slots/        what is still missing, stated precisely rather than invented
```

`verify_package.py` asserts that every file here is offline-runnable, that none of them
contains an absolute path to the authoring machine, and that none requires a credential. It
fails loudly if any of that stops being true.
