# Build records (E0)

The substrate is built **before** the experiment, so its own numbers are a separate axis: how much did
it cost to produce a conforming repo from the spec?

This directory holds one JSON file per build variant — same spec, different harness or model. It exists
so a build is a record from the first commit, not a memory reconstructed afterwards from a screenshot.

## Rules

1. **One record per variant, never edited.** A correction is a new record with `"supersedes": "<id>"`.
2. **Exactly one `"official": true`** — the build the A1–A5 runs are made from. Its `artefact.commit`
   must equal the commit that `task/v1` is tagged on.
3. **Tokens are split, never totalled.** `cache_read` and `input_fresh` are different products at
   different prices; a single "prompt tokens" number cannot be compared across vendors.
4. **Cost says where it came from.** `billed_usd` only when a provider or harness actually showed a
   bill. Otherwise `estimated_usd` plus `rate_table_date`. Never compare a billed figure to an
   estimated one without saying so.
5. **`human_interventions` is the field that makes builds comparable.** Zero means the harness produced
   it. A non-zero count is not a disqualification — it is a different, more expensive experiment, and
   the record says so.

## Adding one

```bash
cp builds/TEMPLATE.json builds/$(date +%Y-%m-%d)-<harness>--<model>.json
# fill every field; null is honest, a guess is not
git add builds/ && git commit -m "builds: <harness> + <model>"
```

## Why this is not part of the task score

Building a repo from a spec and editing a frozen repo are different capabilities. Folding them into one
number would let a strong builder with a weak editor look average, and vice versa. E0 produces a
baseline for replication; E1 produces the comparison.
