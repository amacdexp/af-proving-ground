# Build brief — v1

Give this to the harness **verbatim**, in an empty branch, with the spec in front of it. This is the
**E0 build run**: producing a substrate from scratch. It is not the benchmark and never produces a
`results/` entry.

---

**Runner fills these two lines before pasting. Nothing else changes.**

```
REPO:   <absolute path to the empty branch checkout>
BUILD:  <YYYY-MM-DD-harness--model>
```

You are building a small Python application from a written specification.

**The specification** is at `briefs/build/v1/SPEC.md` in this checkout. Read all of it, including §7,
which describes defects the application **must contain**. Those are not bugs to fix — they are the
fixture, and the spec explains why.

**Rules**

1. First write `.build/START.md`: the spec version, your branch, and the command you will use to test.
2. Keep `.build/LEDGER.md` updated — one line per step.
3. Build to the spec's file map exactly. Do not add modules, frameworks, services or containers.
4. Implement every seeded defect **exactly as §7 describes**. Do not improve them, do not comment on
   them, and do not add tests that assert them.
5. Dependencies are `flask` and `pytest`. Nothing else. No network at test time.
6. The suite must run in under 20 seconds and print one `RESULT:` line via `./dev/gate.sh`.
7. Write `docs/BUILD-REPORT.md` with file count, LOC, test count, measured runtime, and a line per
   seeded defect naming where it lives.

**Definition of done**

- `./dev/spec-check.sh` exits 0;
- `./dev/gate.sh` prints `failed=0`;
- the six expected behaviours in §16 reproduce exactly as stated;
- the build report is written.

**Stop**

When those four hold, stop. Do not push, do not tag, do not strip the spec — the runner owns git.

---

## What the runner does next

| # | Step | Why |
|---|---|---|
| 1 | `python3 baseline.py <checkout>` (scorer-side, private) | six checks; a build that quietly fixed a defect fails |
| 2 | 6/6? then strip `docs/BASE-PROGRAM-SPEC.md`, `docs/BUILD-REPORT.md`, and the defect assertions in `dev/spec-check.sh` | the frozen tree must not carry the answer key |
| 3 | `git commit -m "freeze: task/vN — substrate"` + annotated tag | the substrate is now immutable |
| 4 | Write the record in `builds/` and mark exactly one `"official": true` | the build becomes evidence |

A build that fails the baseline is not a substrate. Rebuild from the spec — do not patch the shape.
