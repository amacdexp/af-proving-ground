# af-proving-ground

A fixed substrate for comparing coding harnesses. Same repo, same task, same commit — the harness is
the only variable.

**Status: pre-freeze.** The base program is not built yet. This repository currently holds the build
specification and nothing else; `task/v1` does not exist.

## Why

The build team runs a hybrid: native OpenClaw agents with delegated coding workers. That setup is
being questioned, and nobody has measured it against the alternatives on the same task. This repo is
the measuring stick — deliberately small, deliberately ordinary, and frozen so that two runs are
comparable.

It is not a benchmark suite and it is not a product. It is one repository, one ticket, and a gate.

## The experiment, in one paragraph

Five arms — native, DSH, DSH-CC, OpenCode, and the native+DSH hybrid — each run the same ticket
against the same tagged commit, under a process held identical across arms: declaration at start, a
state ledger, artifact-first output, bounded wait, one writer per worktree, and "done" means the
acceptance gate passes, not that the agent says so. Scoring is acceptance, independent review, rework
and integration; cost and context economics explain the result rather than deciding it.

## Layout

```
docs/BASE-PROGRAM-SPEC.md   the build brief (builder-only; removed at the freeze)
dev/spec-check.sh           conformance check for the build
```
`src/`, `tests/`, `settings.toml` and `pyproject.toml` arrive with the build.

## Reproducing a run

```
git worktree add /tmp/pg/<arm>/<n> task/v1     # one worktree per run, never shared
python -m pytest -q                            # the same command the gate runs
```

One branch per **run**, not per arm: `run/<arm>/<n>`. Branches are receipts and never merge.

## What this repository is not

No AI, no model clients, no harness code, no game, no narrative, no auth, no containers. If a change
adds any of those, it is in the wrong repository.

## Governance

Built once by an outside builder, frozen once, and never tuned afterwards. The design of record lives
in the factory repo under `teams/proving-ground/`. A change to the task is `task/v2` and a new pilot —
never an edit to `v1`.
