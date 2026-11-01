# Preflight — 2026-11-01 · Hostinger VPS (linux x64)

Command: `dev/arm-check.sh <arm>` for each arm, in the agreed order (cheapest and already-installed
first). **A red result is host-scoped** — it says this machine cannot run the arm, not that the arm is
generally unviable.

| Order | Arm | Exit | Verdict |
|---|---|---|---|
| 1 | **A2** DSH headless | 0 | **ok** — `dsh 0.2.0-rc.2` at `/data/.npm-global/bin/dsh` |
| 2 | **A1** native OpenClaw | 0 | **ok** — `OpenClaw 2026.10.3 (59cb447)` |
| 3 | **A6** Claude Code + DeepSeek | 1 | **fail (2)** — `claude` not on PATH on this host; run it on the Mac |
| 4 | **A4** OpenCode | 1 | **fail (2)** — `opencode` not on PATH; needs an install |
| 5 | **A3** DSH-CC | 3 | **partial** — components present, **composition unproven** |
| 6 | **A5** hybrid | 3 | **partial** — components present, **composition unproven** |

## What this establishes

- **A2 is ready to spend money on.** Binary, version, model declaration, worktree, write and fence all
  green.
- **A1 is runnable**, but preflight only proves the binary. The agent-session path — a clean context,
  no durable memory carried in — is a Phase 0 question, not a preflight one.
- **A6 and A4 are not viable on this host.** That is not a verdict on the arms; A6 belongs on the Mac
  and A4 needs an install before it can be checked anywhere.
- **A3 and A5 are partial by construction.** Their declared `BIN` was a *component*, so the first
  version of this check passed them green — a false positive, and worse than a failure because it
  reads as approval. The check now exits 3 for composite arms with "composition unproven".

## Correction made during this run

`A3.conf` declared `BIN=dsh` and `A5.conf` declared `BIN=native`. Both passed checks 2 and 3 by
checking a part and calling the whole viable. Composite arms now declare `KIND=composite` and
`COMPONENTS`, and the script reports `partial` with a non-zero exit. The unproven thing for A3 is the
DSH-CC plugin surface; for A5 it is the handoff between lead and worker.

## Next

Phase 0 smoke (the nine checks in the proposal, §3) for A1 and A2 — the two green arms — while A4 is
installed and A6 is checked on the Mac. A3 and A5 stay unproven until their composition is exercised.
