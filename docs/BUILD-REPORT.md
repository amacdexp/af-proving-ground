# Base program — build report

**Repository:** `amacdexp/af-proving-ground` · **Spec:** `docs/BASE-PROGRAM-SPEC.md`
**Built:** 2026-11-01 · **Status:** built, not yet frozen or tagged

---

## Result

- Visible suite: **164 tests**, all passing.
- Cold runtime: **0.7 s** end-to-end through the gate (pytest itself reports 0.44 s).
- Gate exits 0 and stdout is exactly one line:

```
RESULT: total=164 passed=164 failed=0 duration=0.7s
```

- `./dev/spec-check.sh` exits 0; every check prints `ok`.
- Tests checksum: `tests/CHECKSUM` covers the ten `.py` files in `tests/`.
  Verify from the `tests/` directory:

```bash
cd tests && shasum -a 256 -c CHECKSUM
```

`tests/CHECKSUM` itself hashes to:

```
2303214f9fde81b10da931e5703b64c0aa9fd9f069c548e483d6a6cc9e5e5507  tests/CHECKSUM
```

---

## Size

| Path | Files | Lines (`wc -l`) | Non-blank |
|---|---:|---:|---:|
| `src/` | 17 | 1,578 | 1,263 |
| `tests/` | 11 (10 `.py` + `CHECKSUM`) | 1,451 | 1,047 |
| **total** | **28** | **3,029** | **2,310** |

That is inside the 3,000–4,000 line target across `src/` and `tests/`.

---

## Seeded defects

| # | Defect | Location | Lines |
|---|---|---|---|
| **D-A** | Duplicate enforcement is partial: `validate_record` implements the rule, but only the CLI resolves `strict` to true. `api/routes.py` calls it with the settings default (`false`); `queue/consumer.py` does not validate at all. | `src/ledger/validation.py`<br>`src/ledger/api/routes.py`<br>`src/ledger/queue/consumer.py`<br>`src/ledger/cli.py` | 53–65<br>39<br>27–30<br>41 |
| **D-B** | Acknowledge before commit: `drain` calls `mark_done` before `handle`, so a failed insert leaves the row `done` and the record lost. | `src/ledger/queue/consumer.py` | 14–24 (ack at 18, handle at 20, insert at 30) |
| **D-C** | The env override is honoured by `store.py` but ignored by the exporter and the projections, which read the settings directory directly. | `src/ledger/sync/exporter.py`<br>`src/ledger/reports/projections.py`<br>(control: `src/ledger/store.py`) | 36<br>96<br>63–65 |
| **D-D** | The projection only moves forward: `apply()` handles `insert` and returns early for `update` and `delete`, so totals drift. | `src/ledger/reports/projections.py` | 21–29 (early return 27–28) |
| **D-E** | The writable namespace is documented and unenforced: README and `settings.toml` name `data_dir` as the only writable location; nothing checks. | `README.md`<br>`settings.toml` | 90–105<br>1–4 |

No comment, docstring or test names any of these defects.

---

## §16 expected repros

Run from the repo root with the venv on `PATH`, `PYTHONPATH=src` and
`LEDGER_DATA_DIR=$PWD/data-run`:

| Recipe | Expected | Observed |
|---|---|---|
| D-A HTTP duplicate | `201 201` | `201 201` |
| D-A queue duplicate | `2` | `2` |
| D-A CLI control | `1` | `1` (first run `inserted=1`, second `inserted=0 skipped=1`) |
| D-B failed insert after ack | `0` | `0` |
| D-C report ignores the override | files under `data/` | `data/export.json`, `data/totals.json` |
| D-D totals after `update_status` | two identical dicts | `{'GBP': 500}` twice |

Runtime artefacts from the recipes were removed afterwards; `data/` and `data-run/` are
gitignored, and only the empty `data-run/` directory remains.

---

## Deviations and decisions

1. **Visible suite size.** The build has 164 visible tests rather than the spec's ~60 estimate.
   The extra coverage fills repeated query, reporting, validation and error paths and is part of
   reaching the size target without filler. `tests/conftest.py` and `tests/test_utils.py` are not
   listed in §4's map; both are ordinary test infrastructure. No visible test asserts the behaviour
   of D-A–D-E.
2. **`LEDGER_SETTINGS`.** An optional environment variable, added beyond §5, that points
   `config.load()` at an alternative settings file. The visible suite uses it to keep settings and
   storage inside each test's temp directory. When it is unset, discovery is unchanged
   (`settings.toml` at the repo root), and it does not change `LEDGER_DATA_DIR` precedence.
3. **Producer dedupe.** `queue/producer.enqueue` drops byte-identical records within a single call
   using a SHA-256 fingerprint. This is what makes §16's two `enqueue([r, r])` calls produce two
   records rather than four. It never consults stored records or validation, so H2 ("same batch
   enqueued twice → one record") still fails through the consumer path.
4. **Totals semantics.** The projection counts `open` and `paid` records and excludes `void`.
   `rebuild()` implements that rule from the record table. README states the rule. The D-D early
   return is untouched.
5. **Gate details.** `dev/gate.sh` prefers `.venv/bin/python`, falls back to `python3`, exports
   `PYTHONPATH=src` and `PYTHONDONTWRITEBYTECODE=1`, sends all pytest output to stderr and prints
   exactly one `RESULT:` line. Duration is measured around the pytest call, to one decimal place.
   The exit code is 0 only when pytest exits 0 and `failed=0`.
6. **Checksum scope.** `tests/CHECKSUM` covers all ten `.py` files in `tests/` (including
   `conftest.py`); entries are filenames relative to `tests/`, so verification is
   `cd tests && shasum -a 256 -c CHECKSUM`. H7 should use the same command.
7. **Additional application features.** `store.search` supports date spans and stable ordering;
   the reporting module provides `monthly`, `supplier_totals`, `outstanding` and `aging`; the export
   snapshot carries those summaries. They are ordinary application functionality and do not touch
   the seeded defect paths, the HTTP contract or the CLI contract.
8. **Runtime state.** `data-run/` was added to `.gitignore` for the §16 workflow; `data/` was
   already ignored.

Nothing forced a change of stack: Python 3.12.4 venv, Flask 3.1.3, pytest 9.2.0, sqlite from the
standard library. No network at test time, no ports, no containers, no extra dependencies.

---

## Verification

From the repo root:

```bash
./dev/spec-check.sh
./dev/gate.sh
cd tests && shasum -a 256 -c CHECKSUM
```
