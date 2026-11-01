#!/bin/sh
# The one supported entry point: run the visible suite and print one RESULT line.
#
#   ./dev/gate.sh
#   RESULT: total=61 passed=61 failed=0 duration=12.4s
#
# All pytest output goes to stderr. Stdout carries exactly one line, and the
# exit code is 0 only when every test passed. POSIX sh + bash 3.2 compatible.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
cd "$root" || exit 2

if [ -x "$root/.venv/bin/python" ]; then
    py="$root/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    py=python3
else
    echo "gate: no python3 interpreter found" >&2
    exit 2
fi

export PYTHONPATH="$root/src"
export PYTHONDONTWRITEBYTECODE=1

start=$("$py" -c 'import time; print(f"{time.time():.3f}")') || exit 2
output=$("$py" -m pytest -q 2>&1)
rc=$?
end=$("$py" -c 'import time; print(f"{time.time():.3f}")') || exit 2

printf '%s\n' "$output" >&2

printf '%s\n' "$output" | "$py" -c '
import re
import sys

text = sys.stdin.read()
rc = int(sys.argv[1])
start = float(sys.argv[2])
end = float(sys.argv[3])

lines = [line.strip() for line in text.splitlines() if line.strip()]
summary = lines[-1] if lines else ""
counts = {}
for match in re.finditer(r"(\d+) (passed|failed|errors?|skipped)", summary):
    counts[match.group(2)] = int(match.group(1))

passed = counts.get("passed", 0)
failed = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)
skipped = counts.get("skipped", 0)
if passed + failed + skipped == 0 and rc != 0:
    failed = 1
total = passed + failed + skipped

print(
    f"RESULT: total={total} passed={passed} failed={failed}"
    f" duration={end - start:.1f}s"
)
sys.exit(0 if rc == 0 and failed == 0 else 1)
' "$rc" "$start" "$end"
