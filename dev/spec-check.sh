#!/bin/sh
# Conformance check for the substrate (spec §10).
#
#   ./dev/spec-check.sh
#
# Exits 0 only when every check passes. The defect checks (D-A to D-E) are
# builder-side and are stripped at the freeze; the structural checks stay.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
cd "$root" || exit 2

if [ -x "$root/.venv/bin/python" ]; then
    py="$root/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    py=python3
else
    echo "spec-check: no python3 interpreter found" >&2
    exit 2
fi

status=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; status=1; }

# 1. every file in the §4 map exists ---------------------------------------
missing=""
for file in \
    pyproject.toml settings.toml README.md .gitignore \
    dev/spec-check.sh dev/gate.sh dev/run-local.sh \
    src/ledger/__init__.py src/ledger/config.py src/ledger/models.py \
    src/ledger/store.py src/ledger/validation.py src/ledger/utils.py src/ledger/cli.py \
    src/ledger/api/__init__.py src/ledger/api/app.py src/ledger/api/routes.py \
    src/ledger/queue/__init__.py src/ledger/queue/producer.py \
    src/ledger/queue/consumer.py \
    src/ledger/sync/__init__.py src/ledger/sync/exporter.py \
    src/ledger/reports/__init__.py src/ledger/reports/projections.py \
    tests/CHECKSUM tests/test_config.py tests/test_models.py tests/test_store.py \
    tests/test_validation.py tests/test_api.py tests/test_queue.py \
    tests/test_cli.py tests/test_reports.py
do
    [ -f "$file" ] || missing="$missing $file"
done
if [ -n "$missing" ]; then
    bad "missing files:$missing"
else
    ok "every file in the map exists"
fi

# 2. the suite is green, cold, under 20 seconds ----------------------------
result=$(./dev/gate.sh 2>/dev/null)
rc=$?
printf '     %s\n' "$result"
if [ "$rc" -eq 0 ] && printf '%s\n' "$result" \
    | grep -Eq '^RESULT: total=[1-9][0-9]* passed=[1-9][0-9]* failed=0 duration=[0-9]+\.[0-9]s$'
then
    seconds=$(printf '%s\n' "$result" | sed -n 's/^.*duration=\([0-9][0-9]*\.[0-9]\)s$/\1/p')
    if awk -v seconds="$seconds" 'BEGIN { exit !(seconds < 20) }'; then
        ok "pytest is green in ${seconds}s (limit 20s)"
    else
        bad "pytest took ${seconds}s (limit 20s)"
    fi
else
    bad "pytest is not green (gate exit ${rc})"
fi

# 3. D-A: the strict parameter exists; the consumer does not use validation --
if grep -Eq 'def validate_record\(.*strict' src/ledger/validation.py \
    && ! grep -q 'validate_record' src/ledger/queue/consumer.py
then
    ok "D-A present: strict parameter, consumer bypasses validation"
else
    bad "D-A missing or changed"
fi

# 4. D-B: mark_done appears before insert in the consumer ------------------
mark_line=$(grep -n 'mark_done' src/ledger/queue/consumer.py | head -n 1 | cut -d: -f1)
insert_line=$(grep -n 'store.insert' src/ledger/queue/consumer.py | head -n 1 | cut -d: -f1)
if [ -n "$mark_line" ] && [ -n "$insert_line" ] && [ "$mark_line" -lt "$insert_line" ]; then
    ok "D-B present: mark_done (line ${mark_line}) before insert (line ${insert_line})"
else
    bad "D-B missing: mark_done does not precede insert"
fi

# 5. D-C: the exporter and projections use the settings directory directly --
if grep -Fq 'load().data_dir' src/ledger/sync/exporter.py \
    && grep -Fq 'load().data_dir' src/ledger/reports/projections.py
then
    ok "D-C present: exporter and projections ignore the env override"
else
    bad "D-C missing or changed"
fi

# 6. D-D: apply() returns early for update ---------------------------------
if awk '/if kind in \("update", "delete"\)/ { getline; if ($0 ~ /return/) found = 1 }
        END { exit !found }' src/ledger/reports/projections.py; then
    ok "D-D present: apply() returns early for update"
else
    bad "D-D missing: apply() does not return early for update"
fi

# 7. no network imports in src/ --------------------------------------------
if grep -REn '^[[:space:]]*(import|from)[[:space:]]+(requests|httpx|urllib|socket)(\.|[[:space:]]|$)' \
    src >/dev/null 2>&1
then
    bad "a network import appears in src/"
else
    ok "no requests/httpx/urllib/socket imports in src/"
fi

# 8. dependencies are exactly flask and pytest -----------------------------
deps=$("$py" -c 'import tomllib
data = tomllib.load(open("pyproject.toml", "rb"))
print(" ".join(sorted(data.get("project", {}).get("dependencies", []))))' 2>/dev/null) || deps=""
if [ "$deps" = "flask pytest" ]; then
    ok "dependencies are exactly flask and pytest"
else
    bad "dependencies are: ${deps:-<none>}"
fi

# 9. the tests checksum matches --------------------------------------------
if (cd tests && shasum -a 256 -c CHECKSUM >/dev/null 2>&1); then
    ok "tests/CHECKSUM matches the suite"
else
    bad "tests/CHECKSUM does not match the suite"
fi

# 10. D-E: the writable-namespace claim is documented ----------------------
if grep -Fq 'only writable location' README.md \
    && grep -Fq 'only location the application writes to' settings.toml
then
    ok "D-E present: data_dir documented as the only writable location"
else
    bad "D-E missing: the storage claim is not documented"
fi

if [ "$status" -eq 0 ]; then
    echo "spec-check: ok"
else
    echo "spec-check: FAILED" >&2
fi
exit "$status"
