# Collecting and storing a run's statistics

A run produces one JSON file. This is where each number comes from, and what to do when a harness will
not tell you.

Schema: `results/schema.json`. Example: `results/example.json`. Path:
`results/<YYYY-MM-DD>/<arm>-<n>.json`.

## Two classes of number

| Class | Who fills it | Trust |
|---|---|---|
| **Runner-collected** | the person driving the run, from the harness's own reports | authoritative |
| **Agent-declared** | the arm, in `.run/REPORT.md` | advisory — cross-check, never copy blindly |

The arm cannot see its own token usage. If it reports a number anyway, it is a guess wearing a
number's clothes.

## Field by field

| Field | Class | Source | If unavailable |
|---|---|---|---|
| `task.tag`, `task.commit` | runner | `git rev-parse task/v1` and the peeled commit | required — a run without these is void |
| `arm.id`, `arm.label` | runner | the plan | required |
| `harness.name`, `harness.version` | runner | the harness's own version command | required; `"unreported"` voids the run |
| `model.requested` | runner | what you asked for | required |
| `model.served` | runner | the provider's response or the harness's model line | **`"unreported"` voids the run** — an alias is not a model |
| `model.reasoning` | runner | the harness setting | required; `max` is not the same experiment as `high` |
| `environment.date/os/python` | runner | the run host | required |
| `outcome.acceptance` | runner | `./dev/gate.sh` on the final tree | required |
| `outcome.held_out.passed/total` | runner | the scorer's suite, run **after** the arm has stopped | required |
| `economy.turns` | runner | harness session report | null + note |
| `economy.wall_clock_s` | runner | start to final gate | required |
| `economy.model_spend_usd` | runner | provider invoice, else harness figure, else rate table | null + `cost.source` |
| `economy.context.*` | runner | harness usage report | null — **never estimate a split** |
| `review.defects_found` | runner | independent reviewer | required |
| `review.rework_files/lines` | runner | the patch after review | required |
| `operator_score` | Owner | blind, after the run | null until scored |
| `void` | runner | the rules below | required |

## Rules

1. **Null is a value; a guess is not.** A missing field stays `null` with a note saying why. An
   estimated token split is worse than an absent one, because it looks comparable.
2. **Cost carries its source.** `provider-invoice` > `harness-report` > `rate-table`. Never compare a
   billed figure from one arm against an estimated figure from another without saying so in `notes`.
3. **Collect before you reset.** Turns, tokens and cost come from a session that is still open. Reset
   the worktree first and the numbers are gone.
4. **One file per run, never edited.** A correction is a new record with `"supersedes"`.
5. **The patch travels with the record.** `results/<date>/<arm>-<n>.patch` — `git diff task/v1` taken
   before the worktree is removed. A score without its diff is not reproducible.
6. **Held-out runs after the arm stops.** Never while it is still working; it would become feedback.

## Void conditions

Record the run, do not score it, if any of these hold:

- `model.served` is `"unreported"` or cannot be tied to a provider response;
- `harness.version` is absent;
- the process brief was not given verbatim (say what changed);
- the arm modified or deleted an existing test;
- the arm read the build spec, another branch, or anything outside its worktree;
- the run exceeded the per-run spend ceiling;
- the gate was run on a different tree from the one the patch came from.

A void run is still data — it tells you the protocol was not followed. It just does not go in the
comparison.

## Where it lands

```
results/2026-11-02/A5-01.json      the record
results/2026-11-02/A5-01.patch     the diff
results/2026-11-02/A5-01.gate.log  the gate line(s), verbatim
```

Commit them together, one commit per run, message `results: <arm>-<n>`. Never bundle several runs into
one commit — a run is the unit of evidence.
