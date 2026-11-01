# Task — v1

The text below is the **whole** of what an arm is given. It names no files, because finding them is the
work.

---

## Duplicate imports are accepted

Support has three tickets this week with the same shape: a supplier sends the invoice file twice, and
the customer ends up with two records for the same invoice.

Re-importing a file should be idempotent. Two records with the same email address should not both
exist — the second one should be refused, whichever way it arrives, with a clear error rather than a
silent overwrite.

Please make that true at every way a record can enter the system, not just the one you find first.
Existing behaviour must keep working.

### Acceptance

- Importing the same batch twice leaves one record.
- A duplicate is refused with `duplicate_email`, and over HTTP that is `409`.
- The existing test suite still passes.
- You may add tests. You may not modify or delete existing ones.

---

## Notes for the runner (not part of the ticket)

- The ticket is deliberately vague about *where*. If it said "edit `validation.py:40`", the run would
  measure instruction-following instead of repository understanding.
- "every way a record can enter the system" is the only hint, and it is fair: there are three, they
  are discoverable from the routes, the queue and the CLI, and a fix that covers one will pass the
  visible suite and fail the held-out one.
