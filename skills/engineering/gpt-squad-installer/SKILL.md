---
name: gpt-squad-installer
description: Safely plan, install, verify, migrate, update, and roll back a session-persistent explicit opt-in GPT-5.6 Sol Chief Engineer with fourteen high-reasoning general elite specialist agents on macOS. Use when registering the dormant specialist catalog, replacing the legacy five process roles, checking compatibility after a Codex update, or restoring a prior configuration.
---

# GPT Squad Installer

Install only after an explicit user request. Treat `plan` and `verify` as read-only. Treat `install`, migration, and `rollback` as user-configuration mutations.

Read [references/installation-guide.md](references/installation-guide.md) completely before the first installation or rollback in a task.

## What this installer creates

The root runs `gpt-5.6-sol` as a Chief Engineer. Its reasoning effort is not pinned by default: the installer preserves an existing supported choice, leaves it unspecified when none exists, and removes the legacy installer-owned forced `high` setting during migration.

It registers fourteen general, model-independent specialist names:

- `product_systems`
- `product_design`
- `experience_design`
- `domain_application`
- `data_systems`
- `distributed_systems`
- `integration_evolution`
- `platform_reliability`
- `security_trust`
- `change_review`
- `quality_falsification`
- `performance_economics`
- `codebase_forensics`
- `technical_communication`

Every specialist runs GPT-5.6 Sol High and can investigate, design, implement, refactor, test, and document an authorized outcome end to end. `change_review` owns holistic change review and a calibrated adversarial pass; `quality_falsification` remains the distinct specialist for executable falsification. Recursive agent creation is disabled.

The catalog is dormant when a new Codex task or conversation session begins. One explicit GPT Squad request activates squad mode for the remainder of that session. Later turns remain active without repeated invocation until the user explicitly opts out or the session ends.

An unscoped opt-out disables GPT Squad for the current session until explicit reactivation. A request-scoped opt-out pauses only that request. A new Codex session always starts dormant.

The installer removes the legacy generic process roles only when they remain installer-owned. It refuses to delete an unmanaged or drifted target.

## Run the workflow

```bash
node <skill-dir>/scripts/gpt-squad.mjs plan --json
node <skill-dir>/scripts/gpt-squad.mjs install --json
node <skill-dir>/scripts/gpt-squad.mjs verify --json
```

Pass `--codex-home <path>` only when the target differs from `CODEX_HOME` or `~/.codex`. Pass `--codex-bin <path>` only when discovery fails. `--root-model` remains fixed to `gpt-5.6-sol`. Omit `--root-effort` to preserve the current supported choice, pass a target-supported effort to pin it, or pass `--root-effort auto` to remove the root-level assignment. Specialist profiles remain pinned to high reasoning.

Report the redacted plan, blocking collisions, `backupId`, changed paths, specialist roster, catalog decision, and prompt-load verification. Keep child identity and actual orchestration behavior `UNRESOLVED` until a fresh Codex task proves them through parent and child runtime metadata.

## Session activation contract

- New Codex sessions begin root-only with the specialist catalog dormant.
- Task complexity alone does not activate GPT Squad.
- A user request that names GPT Squad, `$gpt-squad-orchestrator`, a registered specialist, or delegated/parallel agents activates squad mode.
- Once active, later turns in the same session may use GPT Squad without repeating the name.
- The first activating or reactivating request should delegate at least one suitable specialist when possible.
- Later active turns use the smallest sufficient squad. Trivial or negative-value delegation work may stay root-only without disabling the mode.
- An unscoped opt-out disables squad mode for the session; a request-scoped opt-out pauses only that request.
- Reused specialists must receive a fresh recorded Context Hub checkout when prior context may be stale.
- Dispatch independent missions before waiting, obey the current spawn schema, and avoid busy polling.
- Concurrent writers require disjoint responsibility surfaces or isolation.
- External, production, credential-bearing, destructive, and irreversible actions remain root-controlled.

Use the separate `gpt-squad-orchestrator` skill for mission composition, session continuity, transactional Context Hub checkout and synchronization, sealed results, integration, and evaluation.

## Preserve user state and compatibility

- Preserve approval, sandbox, MCP, notification, personality, project, plugin, skill, and unrelated agent settings.
- Preserve unrelated `config.toml` and `AGENTS.md` content.
- Replace only bounded managed policy and role-registration blocks.
- Refuse unmanaged same-name registrations.
- Back up every managed target before the first install mutation.
- Preserve legacy Sol-Luna files, state, and backups unless explicitly owned by this migration.
- Derive compatibility catalogs from the target runtime and patch only the Sol model's `multi_agent_version` when necessary.
- Never print configuration contents, secrets, credentials, raw subprocess stderr, or model catalog contents.
- Coordinate against GPT Squad, legacy Sol-Sol, and Sol-Luna installer locks.
- Do not restart or terminate Codex Desktop automatically.

## Verify and restart

Structural verification checks exact hashes and modes for installer-owned generated files, managed semantics for shared `config.toml` and `AGENTS.md`, the fixed root model, supported root effort, specialist high reasoning, exact roster parity, the session-persistent opt-in and opt-out contract, all fourteen generated profiles, disabled recursive agents, legacy-role cleanup, and runtime prompt loading.

It does not prove real child execution, model identity, session-state compliance, selection quality, Context Hub checkout delivery, independence, or wave ordering.

After installation, quit Codex Desktop completely, reopen it, start a new task, and run the smoke tests in the installation guide. Inspect parent events, child `session_meta`, and Context Hub records—not final-answer self-report.

## Roll back

```bash
node <skill-dir>/scripts/gpt-squad.mjs rollback \
  --backup-id <backup-id> \
  --json
```

Rollback validates the manifest, restore payloads, target paths, and current installed hashes before the first restore mutation. It creates a pre-rollback safety backup and refuses to overwrite drifted managed targets.
