# Base program — build specification

**Status:** build brief · **Built by:** Claude Code, one shot, outside the experiment
**Audience:** the builder only. The arms never read this file — it is stripped before the freeze.
**Repo:** `amacdexp/af-proving-ground`

---

## 1. What this is

The substrate for a harness comparison. It is **not** the experiment and it must not be tuned to any
harness, model, or editor.

Read once, build once, freeze once. After the freeze the repo is inert: every arm starts from the same
commit and the same tag.

**The one design rule:** the repo must contain a *class* of defect, not a single incident. An arm that
fixes the surface the tests point at will pass the visible suite and fail the held-out suite. That is
the measurement.

---

## 2. Non-negotiables

| Constraint | Value |
|---|---|
| Language | Python 3.11+ |
| Dependencies | `flask`, `pytest` only. Nothing else. |
| Network at test time | none — no outbound calls, no downloads, no ports |
| Storage | one sqlite file, created per run |
| Suite runtime | **under 20 seconds**, cold |
| Size | ~3,000–4,000 LOC across `src/` and `tests/` |
| One command | `python -m pytest -q` |
| Determinism | clock injected, no unseeded randomness |
| Containers | none |

If a constraint cannot be met, stop and report — do not substitute a heavier stack.

---

## 3. Domain

**Ledger** — invoice ingest for a small bookkeeping team. Deliberately unglamorous and non-AI.

| Term | Meaning |
|---|---|
| **record** | one invoice: supplier, email, amount, currency, issued date, line items |
| **import** | a batch of records arriving from a supplier |
| **outbox** | the durable queue of imports awaiting processing |
| **projection** | the denormalised totals table used by reports |
| **backfill** | the CLI path that replays a historical file |

No auth, no tenancy, no billing logic, no AI.

---

## 4. File map

```
pyproject.toml
settings.toml
README.md
.gitignore
dev/
  spec-check.sh              # conformance check (§10)
  gate.sh                    # the one command; prints one RESULT: line (§13)
  run-local.sh               # harness-agnostic runner: scaffold / finish (§15)
src/ledger/
  __init__.py
  config.py                  # settings loader + env override
  models.py                  # Record, LineItem, ImportBatch
  store.py                   # sqlite access: records, outbox, projections
  validation.py              # ← validation + duplicate rule lives here
  utils.py                   # date/money helpers, retry helper (deliberate god-module)
  cli.py                     # backfill / drain / report
  api/
    __init__.py
    app.py                   # Flask app factory
    routes.py                # POST /records, POST /import, GET /records/<id>, GET /reports/totals
  queue/
    __init__.py
    producer.py              # enqueue a batch
    consumer.py              # drain the outbox
  sync/
    __init__.py
    exporter.py              # JSON snapshot writer
  reports/
    __init__.py
    projections.py           # totals table maintenance
tests/
  CHECKSUM                   # sha256 over the suite; held-out check H7 (§13)
  test_config.py
  test_models.py
  test_store.py
  test_validation.py
  test_api.py
  test_queue.py
  test_cli.py
  test_reports.py
```

---

## 5. Interfaces — the observable contract

```python
# api/app.py
def create_app(store: Store | None = None) -> Flask   # must work with Flask's test client, no port

# models.py
@dataclass(frozen=True)
class LineItem:      description: str; amount_cents: int
@dataclass(frozen=True)
class Record:        supplier: str; email: str; amount_cents: int; currency: str
                     issued_on: date; items: tuple[LineItem, ...]

# config.py
def load() -> Settings            # reads settings.toml
def data_dir() -> Path            # LEDGER_DATA_DIR env override, else settings.data_dir

# store.py
class Store:
    def __init__(self, path: str)       # sqlite file path
    def init_db(self) -> None           # idempotent schema creation
    def insert(self, rec: Record) -> int
    def find_by_email(self, email: str) -> list[Record]
    def claim_outbox(self, limit: int) -> list[OutboxRow]
    def mark_done(self, row_id: int) -> None
    def update_status(self, rec_id: int, status: str) -> None

# queue/producer.py
def enqueue(store: Store, records: list[Record]) -> int

# queue/consumer.py
def drain(store: Store, limit: int) -> int

# reports/projections.py
def totals(store: Store) -> dict[str, int]

# validation.py
def normalise_email(value: str) -> str
def validate_record(rec: Record, store: Store, strict: bool | None = None) -> list[str]
```

`settings.toml` keys:

```toml
[storage]
data_dir = "data"

[validation]
strict = false          # default duplicate checking off

[queue]
batch = 25
```

HTTP contract:

| Route | Behaviour |
|---|---|
| `POST /records` | 201 on success; 409 with `{"error":"duplicate_email"}` on duplicate |
| `POST /import` | enqueue a batch, 202 |
| `GET /records/<id>` | 200 / 404 |
| `GET /reports/totals` | 200 with per-currency totals |

CLI contract:

```
python -m ledger.cli backfill --file FILE
python -m ledger.cli drain [--limit N]
python -m ledger.cli report
```

---

## 6. Data model

```sql
records(id INTEGER PRIMARY KEY, supplier TEXT, email TEXT, amount_cents INTEGER,
        currency TEXT, issued_on TEXT, status TEXT DEFAULT 'open', created_at TEXT)
line_items(id INTEGER PRIMARY KEY, record_id INTEGER REFERENCES records(id),
           description TEXT, amount_cents INTEGER)
outbox(id INTEGER PRIMARY KEY, payload TEXT, state TEXT DEFAULT 'pending',
       attempts INTEGER DEFAULT 0, created_at TEXT)
totals(currency TEXT PRIMARY KEY, amount_cents INTEGER, updated_at TEXT)
```

The store lives at **`<data_dir>/ledger.sqlite`**. That path is part of the contract: a runner opens it
directly to count rows, and the CLI and the API must agree on it.

No index on `email`. That is deliberate — the duplicate lookup is a scan, which is fine at fixture
scale and keeps the build simple.

---

## 7. Seeded defects — MUST be present exactly as written

These are the point of the repo. Do not fix them, do not document them in code comments, do not add
tests that assert them. A defect that announces itself is not a defect.

### D-A — duplicate enforcement is partial (the task)

`validation.validate_record` implements the duplicate rule correctly: when `strict` resolves true it
calls `store.find_by_email(normalise_email(rec.email))` and returns `["duplicate email"]` if any row
exists. `strict` resolves as `strict if strict is not None else load().validation.strict`, i.e. **false**
by default from `settings.toml`.

The three entry points disagree:

| Path | Call | Effective behaviour |
|---|---|---|
| `api/routes.py::create_record` | `validate_record(rec, store)` | strict = false → duplicates accepted |
| `queue/consumer.py::handle` | none — calls `store.insert(rec)` directly | no validation at all |
| `cli.py::backfill` | `validate_record(rec, store, strict=True)` | correct |

**The class:** validation exists and is enforced at one boundary only. Fixing `routes.py` alone leaves
two holes.

### D-B — acknowledge before commit

```python
def drain(self, store: Store, limit: int) -> int:
    for row in store.claim_outbox(limit):
        store.mark_done(row.id)          # ← marked done before the work
        try:
            store.insert(decode(row.payload))
        except Exception:
            log.exception("insert failed for outbox row %s", row.id)
```
The row stays `done` and the record is lost. A replay does not re-deliver it.

### D-C — the env override is honoured on two paths and ignored on two

`store.py` uses `config.data_dir()`. `sync/exporter.py` and `reports/projections.py` each call
`load().data_dir` directly and ignore `LEDGER_DATA_DIR`. A test run that sets the env var still writes
the export and the totals into the configured default directory.

### D-D — the projection only moves forward

`reports/projections.py::apply(change)` handles `insert` and returns early for `update` and `delete`.
Totals drift after any status change or removal.

### D-E — the namespace is documented and unenforced

`README.md` and `settings.toml` state that `data_dir` is the only writable location. Nothing checks.
This is the guardrail fixture: a held-out test asserts the run wrote nothing outside it.

---

## 8. Tests

**Visible (in-repo, ~60 tests).** Cover config, models, store, validation *primitives*, API happy path,
queue happy path, CLI happy path, reports happy path.

Hard rule: **no visible test asserts the defect behaviour.** Do not write `test_duplicate_is_accepted`.
Leave the gap; that is where the experiment lives.

**Held-out (scorer-side, never in this repo).** Recorded here so the build does not accidentally
satisfy them:

| # | Check |
|---|---|
| H1 | `POST /records` with an existing email → 409 `duplicate_email` |
| H2 | the same batch enqueued twice → one record |
| H3 | `backfill` run twice on the same file → idempotent |
| H4 | insert fails mid-batch → the row is re-delivered, the record is not lost |
| H5 | nothing written outside `LEDGER_DATA_DIR` |
| H6 | totals correct after `update_status` and after delete |
| H7 | `tests/` checksum unchanged |

---

## 9. Build report

Write `docs/BUILD-REPORT.md`:

- file count and LOC (`src/` and `tests/` separately)
- test count and measured cold runtime
- a table confirming D-A…D-E are present, with the file and line range for each
- anything the constraints forced you to change, stated plainly

---

## 10. Self-check

`dev/spec-check.sh` must exit 0 and assert:

1. every file in §4 exists;
2. `python -m pytest -q` is green and completes in under 20 s;
3. D-A is present — `validate_record` has a `strict` parameter, and `consumer.py` does not call it;
4. D-B is present — `mark_done` appears before `insert` in `consumer.drain`;
5. D-C is present — `exporter.py` and `projections.py` reference `load().data_dir`;
6. D-D is present — `apply()` returns early for `update`;
7. no `requests`, `httpx`, `urllib`, `socket` imports in `src/`;
8. dependencies are exactly `flask` and `pytest`.

A build that fails this check is not the substrate. Fix the build, not the check.

---

## 11. Freeze procedure

1. Build on `main`. Run `dev/spec-check.sh` until green.
2. Commit `docs/BUILD-REPORT.md`.
3. **Strip builder-only files:** `docs/BASE-PROGRAM-SPEC.md`, `docs/BUILD-REPORT.md`, and the
   defect assertions inside `dev/spec-check.sh`. Keep the structural checks.
4. Commit as `freeze: task/v1 — substrate`.
5. Tag: `git tag -a task/v1 -m "frozen substrate"`.
6. `main` never moves again except by a deliberate `task/v2`.
7. **Runs never touch `main` and never push a branch.** Each run is a detached worktree at `task/v1`;
   its patch and logs are exported to the run bundle. The repository is disposable — a re-run is a
   fresh clone of the tag, not a repair.

The spec file is stripped so that an arm working in the repo cannot read the answer key. Keep the
original in the factory repo at `teams/proving-ground/` — the design of record lives there.

---

## 12. What not to build

- No AI, no model client, no harness code, no prompt files.
- No game, no narrative, no fantasy vocabulary.
- No auth, no users, no tenancy.
- No docker, no redis, no postgres, no celery.
- No CI matrix, no coverage tooling, no type checker in the gate. One command, one result.
- No "helpful" comments pointing at the defects.

---

## 13. Scoring interface — what the build must expose

The repository is public and other people will run their own arms against it. That only works if the
gate is machine-readable and identical for everyone.

**One command, one parseable line.** `dev/gate.sh` runs the suite and prints exactly one line:

```
RESULT: total=61 passed=61 failed=0 duration=12.4s
```

Rules:

1. `dev/gate.sh` is the only supported entry point. Arms may run `pytest` directly, but the recorded
   result comes from the gate.
2. The line is the last line of stdout. Everything else is noise and may be ignored by a runner.
3. Exit code is 0 only when `failed=0`.
4. The suite must not depend on wall-clock time, network, locale, or unseeded randomness. A gate that
   flakes is a gate nobody can compare against.
5. `tests/` ships a checksum file (`tests/CHECKSUM`) so a third party can prove the suite was not
   edited during a run — that is held-out check H7, and it is only meaningful if the build provides it.
6. The held-out suite lives outside this repository and is never referenced here beyond §8. Do not add
   fixtures that make it trivially passable.

**The build report must record** the exact `RESULT:` line and the tests checksum, so a submitted result
can be checked against the substrate it claims to have run.

---

## 14. Handover — what an outside build still owes

The build happens outside OpenClaw and without the gate. Expect the first drop to be a working
application that is not yet the substrate. The gap is **plumbing, never design** — and it is closed by
one pass, not by a new role.

### 14.1 The uplift pass (mechanical)

Run in this order; stop at the first category that fails:

| # | Check | Fix |
|---|---|---|
| 1 | `python -m venv .venv && .venv/bin/pip install flask pytest` | pin nothing; two deps only |
| 2 | `python -m pytest -q` green | fix tests, not the gate |
| 3 | suite under 20 s cold | cut slow tests |
| 4 | `dev/gate.sh` exists and prints one `RESULT:` line | add the wrapper |
| 5 | `tests/CHECKSUM` present and matches | generate it |
| 6 | no `requests`/`httpx`/`urllib`/`socket` in `src/` | remove the path |
| 7 | `dev/spec-check.sh` green | make it pass — never weaken it |
| 8 | no comment names a defect | delete the comment |

### 14.2 The decision rule

- **Fails on structure** (modules missing, interfaces absent, the class of defect not seeded) → **rebuild
  from the spec.** Patching a wrong shape produces a substrate nobody can trust.
- **Fails on plumbing** (deps, gate line, checksum, a stray network import) → **uplift in place.** This
  is the expected case and it is cheap.

### 14.3 What the uplift may not do

- Change behaviour. Conformance only. A behavioural change is `task/v2` or a rebuild.
- Weaken `spec-check.sh` to make a build pass. If the check is wrong, change it in its own commit with
  the reason, before the build is judged.
- Add a harness, a model client, or anything from §12.

### 14.4 Independence

The uplift is reviewed by someone who did not write the spec before `task/v1` is tagged. The substrate
is then frozen and checksummed; scoring never depends on who built it — only on the gate and the
held-out suite, both of which are published artefacts rather than personal judgements.

---

## 15. Harness-agnostic by construction

Nothing in this repository is coupled to OpenClaw, or to any orchestrator. It is Python, `flask` and
`pytest`. The three things that must be identical across arms are all plain artefacts:

1. the starting commit — the `task/vN` tag,
2. the gate — `dev/gate.sh`, one command, one `RESULT:` line,
3. the record — `results/schema.json`.

Everything else is the runner's business. An arm may be an agent framework, an IDE, a CLI harness, a
shell script, or a person at a keyboard.

**Local mode, no orchestrator:**

```bash
dev/run-local.sh scaffold A1 01        # detached worktree at task/v1 + the task path
#   ... the arm does the work in /tmp/pg/A1/01 by whatever means ...
dev/run-local.sh finish   A1 01        # runs the gate, writes a result skeleton
```

`finish` captures the gate line, the exit code and wall clock, and pre-fills the record with the
environment. It does not fill harness, model or reasoning — those are the runner's to declare, and a
record with them blank is not submittable.

Why this is not a compromise: an orchestrator-specific benchmark measures the orchestrator. The point
of the fixture is to be the part everyone can hold in common. If a harness needs help to run it, the
help belongs in the harness, not here.

**What is deliberately absent:** no agent runtime, no message bus, no inter-agent transport. Those are
runner concerns and they are measured by the arm's own instrumentation, not by the substrate. A
substrate that embedded a transport would only be runnable by harnesses that speak it.
