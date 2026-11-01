# af-proving-ground

A frozen repository for comparing **coding-agent harnesses** on the same task, with the same process,
and publishing the result in a form someone else can reproduce.

Most benchmarks ask "how good is the model". This one asks a narrower and more practical question:
*which arrangement of agent, harness and model gets a real change landed, reviewed and merged — at
what cost?* The repository is deliberately ordinary, because the variable under test is the harness,
not the domain.

Anyone can run any harness against `task/v1` and submit a result. Comparisons are only valid within
the same task tag.

---

## Run a test in six steps

| # | Step | What you use |
|---|---|---|
| 1 | Pin the pair you are testing — substrate and question | tag `task/v1` · `briefs/v1/` |
| 2 | Make a fresh worktree; never reuse one | `dev/run-local.sh scaffold <arm> <n>` |
| 3 | Hand the arm the brief **verbatim**; fill only the three header lines | `briefs/v1/RUN-BRIEF.md` |
| 4 | Let it work. No help, no hints, no mid-run answers | — |
| 5 | Run the gate on what it produced | `./dev/gate.sh` |
| 6 | Collect and store the numbers | `briefs/v1/STATS.md` → `results/<date>/<arm>-<n>.{json,patch,gate.log}` |

**Read these three, in this order:**

| File | Answers |
|---|---|
| `briefs/v1/TASK.md` | what the arm is asked to do |
| `briefs/v1/RUN-BRIEF.md` | what the arm is told, word for word, and what "done" means |
| `briefs/v1/STATS.md` | where every number comes from, which missing number voids the run, and where the record lands |

If a number cannot be observed, it is `null` — never an estimate. That single rule is what makes two
results comparable.

---

## The five arms this repo was built for

| Arm | Arrangement | How it is wired |
|---|---|---|
| **A1** | Native agent, skills + tools, no external harness | in-process tool loop |
| **A2** | DSH headless | one-shot delegation wrapper |
| **A3** | DSH-CC (plugin stack, executor profile) | plugin path; capability proven per run |
| **A4** | OpenCode | ACP session (`agentId: opencode`) |
| **A5** | **Hybrid** — native lead + delegated worker | in-process lead, external worker |

A5 is the one the build team actually runs. If you are testing your own setup, A5 is the arm that
matters most, and A1 is its control.

**Adding an arm** is expected: `A6+`, your harness, any model. Nothing in the repo is specific to the
five above — an arm is a name, an arrangement, a version string and a result file.

---

## Harness-agnostic

Nothing here requires OpenClaw, or any orchestrator. The repo is Python, `flask` and `pytest`. Three
artefacts must be identical across arms — the `task/vN` tag, `dev/gate.sh`, and the result schema —
and everything else is your runner's business.

Runs on macOS with a POSIX shell (`zsh` or `bash`), Python 3.11+. No Windows or PowerShell steps — one
platform, one dialect.

No orchestrator? Run it locally:

```bash
dev/run-local.sh scaffold A1 01     # detached worktree at task/v1
#   ... do the work however you like ...
dev/run-local.sh finish   A1 01     # gate + result skeleton
```

An arm can be an agent framework, an IDE, a CLI harness, or a person at a keyboard. There is no agent
runtime, no message bus and no inter-agent transport in this repo, deliberately — a substrate that
embedded one would only be runnable by harnesses that speak it.

---

## Briefs — the prompt each arm gets

`briefs/v1/` holds the three documents that make a run comparable:

| File | What it is |
|---|---|
| `TASK.md` | the ticket — the only thing the arm is told about the question |
| `RUN-BRIEF.md` | the prompt, given **verbatim**; the runner fills three header lines and nothing else |
| `STATS.md` | where each number comes from, and what to do when a harness will not report one |

Briefs version independently of the substrate tag: the code freezes as `task/vN`, the question freezes
as `briefs/vN`. A result cites both, and neither moves underneath the other.

## The task

`task/v1` — one ticket, written the way tickets arrive:

> Importing the same invoice twice creates two records. Re-importing a file should be idempotent, and
> a duplicate should be rejected at every way a record can enter the system, with a `409` and
> `duplicate_email`.

The ticket names **no files**. Finding the enforcement points is the work. The change spans 5–8 files
across two modules.

The repo contains a *class* of defect, not one incident. An arm that fixes the surface the visible
tests point at will pass `pytest` and fail the held-out suite. That gap is the measurement.

---

## Process constant

Every arm, every run, the same rules:

1. One line at start: task, branch, acceptance command.
2. A state ledger file, updated per step, surviving a restart.
3. Artifact-first output — the change and its evidence are the deliverable.
4. Bounded wait, never poll.
5. One writer per worktree; one branch or detached worktree per run.
6. Integration after the gate and after review.
7. **"Done" is the gate passing, not the agent saying so.**

If the process differs between arms, the run measures your process and calls it a harness.

---

## Scoring

A run produces a **0–100 composite** plus the raw metrics it came from. Publish both: a score without
its components is not reproducible.

| Component | Points | Rule |
|---|---|---|
| **Acceptance** | 50 | gate passes: 50 · partial: 25 · fails: 0 |
| **Held-out** | 25 | `passed / total × 25` — the unseen suite (§H1–H7) |
| **Integration** | 15 | merge with no manual repair: 15 · with repair: 7 · cannot: 0 |
| **Economy** | 10 | cheapest run in the batch scores 10; others scale by ratio |

**Reported separately, never folded into the composite:** the operator's 1–5 score on the artefact,
and total model spend. A single number that hides the human judgement is not comparable across
people; a spend number folded into quality rewards doing less.

**Automatic void** (recorded, not scored): served model identity unprovable · harness version not
pinned · per-run spend ceiling exceeded · process constant not given verbatim.

---

## Recording a run

One JSON file per run: `results/<YYYY-MM-DD>/<arm>-<n>.json`, against `results/schema.json`.

```json
{
  "schema": "af-proving-ground/result/v1",
  "task":   { "tag": "task/v1", "commit": "<sha>" },
  "arm":    { "id": "A5", "label": "native lead + DSH worker" },
  "harness":{ "name": "dsh", "version": "<pinned>", "config": "headless, 7200s timeout" },
  "model":  { "requested": "deepseek/deepseek-v4-pro",
              "served": "<id returned by the provider>",
              "reasoning": "high" },
  "environment": { "date": "2026-11-01", "os": "linux-x64", "python": "3.11.9" },
  "outcome": { "acceptance": "pass", "held_out": { "passed": 6, "total": 7 } },
  "economy": { "turns": 41, "wall_clock_s": 905, "model_spend_usd": 1.12,
               "context": { "prompt_tokens": 0, "cache_read": 0, "cache_write": 0,
                            "output": 0, "compactions": 0 } },
  "review":  { "defects_found": 2, "rework_files": 1, "rework_lines": 0 },
  "operator_score": 4,
  "void": false,
  "notes": ""
}
```

**The model field is not optional and not free-form.** Record the model that actually served the
request — an alias is a routing label, not a model — and the reasoning/thinking level, because two
runs at different levels are different experiments. A result whose served model cannot be shown is
void.

## Submitting a result

Pull request with: the JSON above, the patch (`git diff task/v1`), the gate log, and the harness
version. Nothing else. Results are merged as-is; they are not ratified, ranked across tags, or
"adjusted" for fairness. The components are published so a reader can re-weight them.

**Comparability rule:** results are comparable only within one `task/vN` tag. A v1 score and a v2
score are different experiments that happen to share a name.

---

## Fixture rotation — why v1 will not last

This repository is public, so `task/v1` will eventually be in someone's training data. That does not
invalidate it for runs whose models predate it, and it does not make the measurements wrong — it makes
them **dated**.

The rule that follows: **each round publishes a new tag**, with new fixtures and a new seeded defect
class. Cross-tag comparison is invalid, and a run must always state the tag it ran against. Reputation
attaches to a harness's *record across tags*, not to a single number.

Anyone who runs v1 to measure a model newer than this repository should say so — and should expect the
result to flatter the model.

---

## Reproducing a run

```bash
git clone <repo> && cd af-proving-ground
git worktree add --detach ../pg-runs/<arm>/<n> task/v1
cd ../pg-runs/<arm>/<n>
python -m pytest -q                       # the gate, unchanged
git diff task/v1 > ../../results/<date>/<arm>-<n>.patch
```

**Run branches are local and never pushed.** The repo is disposable; a re-run is a fresh clone of the
tag, not a repair. **`main` is never touched after the freeze.**

---

## Build axis (E0) — pilot

The substrate itself was built from this spec in one unattended session. That is a measurable event,
and a different capability from editing a frozen repo:

Numbers live in `builds/`, not here. The current figure set is
`builds/2026-11-01-claude-code--deepseek-v4-1-flash-verified.json`: 62 build turns, 28 m 08 s, max
reasoning, 6.83M prompt tokens (121k fresh / 6.71M cache read), $0.22, 0 human interventions.

This table used to carry a second copy of those numbers. It doesn't any more — two copies of a
measurement drift, and a benchmark that quotes itself is not evidence.

Records live in `builds/` — one JSON per variant, schema in `builds/schema.json`, rules in
`builds/README.md`. Exactly one record is ever `"official": true`, and it must match the commit that
`task/v1` is tagged on.

**This is one data point, not a comparison.** It is a baseline for anyone who builds the fixture
themselves, and the fields above are the ones a build record must carry. Note what the numbers say:
cheap in money, expensive in time, and almost all of the prompt volume is the same context being
re-presented turn after turn — the #557 failure class wearing a different coat.

## What this repository is not

Not a model benchmark, not a leaderboard, not a product. No AI, no harness code, no game, no
containers. One task, one gate, one record format.

## Governance

Built once by an outside builder, frozen once, never tuned afterwards. The design of record and the
build brief live in the build-factory repository. A change to the task is a new tag and a new pilot —
never an edit to a frozen one.
