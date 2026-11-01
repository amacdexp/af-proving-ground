#!/bin/sh
# Run one arm locally — no orchestrator, no OpenClaw, no network.
#
#   dev/run-local.sh scaffold <arm> <n> [tag]   create the worktree, print the task path
#   dev/run-local.sh finish   <arm> <n> [tag]   run the gate, write a result skeleton
#
# The arm does the work in the worktree by whatever means it likes: an agent, an IDE,
# a human, a shell script. This wrapper only owns the parts that must be identical
# across arms: the starting commit, the gate command, and the record shape.
set -eu

cmd=${1:?usage: run-local.sh scaffold|finish <arm> <n> [tag]}
arm=${2:?arm, e.g. A1}
n=${3:?run number, e.g. 01}
tag=${4:-task/v1}

root=$(git rev-parse --show-toplevel)
wtroot=${PG_WORKTREE_ROOT:-$(cd "$root/.." && pwd)/pg-runs}
wt="$wtroot/$arm/$n"
out="$root/results/$(date -u +%Y-%m-%d)"

case "$cmd" in
  scaffold)
    git -C "$root" rev-parse -q --verify "refs/tags/$tag" >/dev/null 2>&1 || {
      echo "no tag $tag — freeze the substrate first (spec §11)" >&2; exit 1; }
    [ -e "$wt" ] && { echo "$wt already exists — a run is never reused" >&2; exit 1; }
    git -C "$root" worktree add --detach "$wt" "$tag" >/dev/null
    echo "worktree: $wt"
    echo "task:     $wt/docs/TASK.md   (if absent, the ticket is issued separately)"
    echo "gate:     $wt/dev/gate.sh"
    echo
    echo "Do the work in $wt. Do not touch the parent checkout."
    echo "When done: dev/run-local.sh finish $arm $n $tag"
    ;;

  finish)
    [ -d "$wt" ] || { echo "no worktree at $wt — run scaffold first" >&2; exit 1; }
    [ -x "$wt/dev/gate.sh" ] || { echo "missing $wt/dev/gate.sh" >&2; exit 1; }
    mkdir -p "$out" "$wtroot/$arm/$n" 2>/dev/null || true

    start=$(date +%s)
    set +e
    line=$(cd "$wt" && ./dev/gate.sh 2>&1 | tail -n 1)
    rc=$?
    set -e
    end=$(date +%s)

    echo "$line"
    echo "exit=$rc  wall_clock_s=$((end - start))"

    python3 - "$out/$arm-$n.json" "$arm" "$n" "$tag" "$line" "$rc" "$((end - start))" <<'PY'
import json, sys, subprocess, datetime, os
path, arm, n, tag, line, rc, secs = sys.argv[1:8]
sha = subprocess.run(["git", "-C", os.path.dirname(path) or ".", "rev-parse", "HEAD"],
                     capture_output=True, text=True).stdout.strip() or "unknown"
rec = {
  "schema": "af-proving-ground/result/v1",
  "task":   {"tag": tag, "commit": sha},
  "arm":    {"id": arm, "label": ""},
  "harness":{"name": "", "version": "", "config": ""},
  "model":  {"requested": "", "served": "", "reasoning": "off"},
  "environment": {"date": datetime.date.today().isoformat(),
                  "os": f"{os.uname().sysname.lower()}-{os.uname().machine}",
                  "python": sys.version.split()[0]},
  "outcome": {"acceptance": "fail", "held_out": {"passed": 0, "total": 0}},
  "economy": {"turns": 0, "wall_clock_s": int(secs), "model_spend_usd": 0,
              "context": {"prompt_tokens": 0, "cache_read": 0, "cache_write": 0,
                          "output": 0, "compactions": 0}},
  "review":  {"defects_found": 0, "rework_files": 0, "rework_lines": 0},
  "operator_score": None, "void": False, "void_reason": None,
  "notes": f"gate: {line.strip()} (exit {rc}) — fill every empty field before submitting"
}
json.dump(rec, open(path, "w"), indent=2)
print(f"wrote {path} (skeleton — fill the blanks)")
PY
    ;;

  *)
    echo "unknown command: $cmd" >&2; exit 2 ;;
esac
