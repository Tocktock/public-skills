# Context Guard Compatibility Note

The former file-backed Context Guard has been superseded by the transactional Context Hub.

Use [context-hub.md](context-hub.md) for the canonical protocol. The Hub keeps SQLite as the source of truth, records role-specific checkout views, automatically invalidates recorded consumers, seals result versions, and generates Markdown as a derived view.

For an active legacy file-backed run, use `migrate-legacy`. The migration preserves the old files in a timestamped backup and requires every imported mission to receive a fresh checkout before substantive continuation.

Do not start new work with the retired manual ledger-edit and `advance` workflow.
