# Arms — the adapter contract

An arm is not code in this repository. It is **a name, an arrangement, a pinned version and a proven
model identity** — plus a declaration file so the harness that runs it does not have to guess.

```
arms/A6.conf          how to invoke it, what to ask for, what to call it
dev/arm-check.sh A6   can we run it here, at all?       → PREFLIGHT: A6 ok
```

## The declaration

A `.conf` is sourced by POSIX `sh`. Five keys:

| Key | Meaning |
|---|---|
| `LABEL` | human name for the record |
| `BIN` | the executable, or `native` for an in-process agent |
| `VERSION_CMD` | command that prints the harness version — this string becomes `harness.version` |
| `START_CMD` | how a run is opened in a worktree |
| `MODEL_ENV` | the environment that selects the model, or `unreported` if it cannot be stated |

## Preflight — before any scored run

`dev/arm-check.sh <arm>` answers one question: **can this harness be run here at all?** Seven checks:

1. the declaration exists and parses;
2. the executable is present (or the arm is `native`);
3. the version command returns a string — an unpinned harness cannot be recorded;
4. the model selection is declared, or explicitly `unreported`;
5. a worktree can be created from `task/v1` under the run root;
6. the harness can write and read a file inside that worktree;
7. the fence holds — a path outside the run root is refused.

Exit 0 is a green light to spend money. Anything else is a finding: record the arm as **not viable**
with the failing check, and move on. A harness that cannot be wired is not a harness that scored badly.

**Why this exists:** installing DSH and wiring ACP harnesses has failed before, at the point of use.
The failure belongs in preflight, where it costs minutes, not in run 7 of 9, where it costs the
comparison.

## Guardrails

- One worktree per run, under the run root (`pg-runs/<arm>/<n>`), created from `task/v1` and removed
  after the record is committed. No reuse, no sharing between arms.
- The arm writes only inside its worktree. `arm-check` proves the fence; the run brief states it.
- Teardown order: gate → collect stats from the live session → write the record and patch → remove the
  worktree. Reverse that order and the numbers are gone.
- An arm that modifies `tests/` is void, not disqualified.

## Adding one

```bash
cp arms/A6.conf arms/A7.conf     # edit five keys
dev/arm-check.sh A7              # iterate until ok
```

Nothing else in the repository changes. That is the point.
