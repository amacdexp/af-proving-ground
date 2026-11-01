#!/bin/sh
# Preflight one arm: can this harness be run here at all?
#
#   dev/arm-check.sh A6
#   PREFLIGHT: A6 ok        (exit 0 — you may spend money)
#   PREFLIGHT: A6 fail (2)  (exit 1 — record the arm as not viable)
#
# Seven checks, no network, no tokens spent. POSIX sh, macOS-safe.
set -u

arm=${1:-}
[ -n "$arm" ] || { echo "usage: arm-check.sh <arm-id>" >&2; exit 2; }

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
run_root=${PG_RUN_ROOT:-$(CDPATH= cd -- "$root/.." && pwd)/pg-runs}
conf="$root/arms/$arm.conf"
tag=${PG_TAG:-task/v1}

fails=0
ok()  { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# 1 — declaration
if [ -f "$conf" ]; then
    # shellcheck disable=SC1090
    . "$conf"
    if [ -n "${LABEL:-}" ] && [ -n "${BIN:-}" ] && [ -n "${VERSION_CMD:-}" ] && [ -n "${START_CMD:-}" ]; then
        ok "1 declaration: $LABEL"
    else
        bad "1 declaration: $conf is missing one of LABEL/BIN/VERSION_CMD/START_CMD"
    fi
else
    bad "1 declaration: no $conf"
    BIN=""
fi

# 2 — executable present
if [ "${BIN:-}" = "native" ]; then
    ok "2 executable: native (in-process, nothing to install)"
elif [ -n "${BIN:-}" ] && command -v "$BIN" >/dev/null 2>&1; then
    ok "2 executable: $(command -v "$BIN")"
else
    bad "2 executable: '${BIN:-?}' not found on PATH — install it or record the arm as not viable"
fi

# 3 — pinned version
if [ -n "${VERSION_CMD:-}" ] && ver=$(eval "$VERSION_CMD" 2>/dev/null | head -n 1) && [ -n "$ver" ]; then
    ok "3 version: $ver"
else
    bad "3 version: '$VERSION_CMD' returned nothing — an unpinned harness cannot be recorded"
fi

# 4 — model selection declared
if [ -n "${MODEL_ENV:-}" ]; then
    ok "4 model: declared via $MODEL_ENV (prove the served id before the run)"
else
    bad "4 model: no MODEL_ENV — say 'unreported' if it cannot be stated, so the record is honest"
fi

# 5–7 need a worktree; skip cleanly if the substrate is absent
if ! git -C "$root" rev-parse -q --verify "refs/tags/$tag" >/dev/null 2>&1; then
    bad "5 worktree: tag $tag not found — freeze the substrate first"
    printf '\nPREFLIGHT: %s fail (%d)\n' "$arm" "$fails"
    exit 1
fi

wt="$run_root/$arm/00-preflight"
rm -rf "$wt" 2>/dev/null
mkdir -p "$run_root/$arm" || { bad "5 worktree: cannot create $run_root/$arm"; exit 1; }

if git -C "$root" worktree add --detach "$wt" "$tag" >/dev/null 2>&1; then
    ok "5 worktree: created from $tag"
else
    bad "5 worktree: could not create a worktree at $wt"
fi

# 6 — the harness can write and read inside its worktree
if [ -d "$wt" ] && ( printf 'probe\n' > "$wt/.preflight" && grep -q probe "$wt/.preflight" ); then
    ok "6 write: worktree is writable"
    rm -f "$wt/.preflight"
else
    bad "6 write: cannot write inside the worktree"
fi

# 7 — the fence: this worktree is its own tree, not the parent checkout
if [ -d "$wt" ] && top=$(git -C "$wt" rev-parse --show-toplevel 2>/dev/null) && [ "$top" = "$wt" ]; then
    ok "7 fence: worktree resolves to itself, not the parent checkout"
else
    bad "7 fence: worktree does not resolve to itself — a run could write into the shared checkout"
fi

[ -d "$wt" ] && git -C "$root" worktree remove --force "$wt" >/dev/null 2>&1

printf '\n'
if [ "$fails" -eq 0 ]; then
    printf 'PREFLIGHT: %s ok\n' "$arm"
    exit 0
fi
printf 'PREFLIGHT: %s fail (%d)\n' "$arm" "$fails"
exit 1
