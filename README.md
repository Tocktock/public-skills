# Public Skills

Reusable public agent skills maintained by Tocktock.

## Included skills

- `gpt-squad-installer` — installs and verifies an explicit opt-in GPT Squad with registered specialist profiles.
- `gpt-squad-orchestrator` — coordinates specialist work with lightweight, cooperative, or transactional execution according to the shared-state risk.

The current release also bounds no-progress specialist waiting so repeated timeouts cannot become an unbounded polling loop. It preserves the model, specialist reasoning effort, review behavior, Context Hub integrity, and verification requirements.

## Install

List the available skills:

```bash
npx skills add https://github.com/Tocktock/public-skills --list
```

Install one skill globally for Codex:

```bash
npx skills add https://github.com/Tocktock/public-skills \
  --skill gpt-squad-orchestrator \
  --agent codex \
  --global
```

Install the companion installer in the same way when you need to register or verify the specialist profiles.

## Verify

```bash
./scripts/ci-check.sh
```

The verification suite checks the installer, cooperation planner, runtime backpressure, transactional Context Hub, operational lifecycle, and public-source sanitization.

## Public-source boundary

This repository must not contain credentials, private repository references, internal company identifiers, raw runtime databases, session ledgers, local user paths, or generated agent run artifacts. Pull requests run a fail-closed public-source scan before the behavioral tests.
