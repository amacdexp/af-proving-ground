# Run brief — v1

Give this to the arm **verbatim**. It is identical for every arm; the only thing that changes between
runs is the worktree and the run id. If you paraphrase it, you are no longer measuring the harness.

---

**Runner fills these three lines before pasting. Nothing else changes.**

```
WORKTREE: <absolute path to the fresh worktree>
ARM:      <A1 | A2 | A3 | A4 | A5 | A6+>
RUN:      <n>
```

You are working in a prepared repository at the path above. Your job is one ticket, given below.

**The ticket**

> Duplicate imports are accepted — re-importing a file should be idempotent, and two records with the
> same email address should not both exist. Refuse the second one at every way a record can enter the
> system, with a clear error rather than a silent overwrite. Existing behaviour must keep working.

**Rules**

1. First write `.run/START.md` with one line: the task, your branch, and the command you will use.
2. Keep `.run/LEDGER.md` updated as you work — one line per step, so the run survives an interruption.
3. One writer. Do not create a second working copy, and do not touch anything outside this directory.
4. Do not modify or delete existing tests. You may add tests.
5. Do not read `builds/` or `results/` — they are records, not inputs.
6. Do not use the network.
7. The deliverable is the change and its evidence. Do not paste large output into your replies.
8. **Done means the gate passes** — not that you believe it does.

**The gate**

```
./dev/gate.sh
```

It prints one line: `RESULT: total=N passed=N failed=N duration=Ns`, and exits 0 only when `failed=0`.
Run it. Report the line you actually got.

**Report**

Write `.run/REPORT.md` with:

- what you changed and why, in a few lines;
- the gate line, verbatim;
- anything you could not do, and what you would need;
- if you know them, your turn count and wall clock — leave them blank if you do not.

**Stop**

When the gate is green and the report is written, stop. Do not push, do not open a pull request, do not
merge. The runner owns git.

---

## Why the rules are here

| Rule | Why |
|---|---|
| `.run/START.md` | declares the task before the work — the first artifact is a commitment, not a summary |
| `.run/LEDGER.md` | makes recovery measurable; a restart either resumes or it does not |
| one writer | a second copy is how two edits diverge and a result becomes unattributable |
| no test edits | otherwise "green" means "the tests were changed" |
| no `builds/` / `results/` | those are the answer key's neighbours; reading them turns a run into a lookup |
| no network | offline is what makes the run reproducible |
| done = gate | the gap between "I believe it works" and "it works" is the measurement |
