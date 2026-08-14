# Mission <M01> — <owned outcome>

> Generated from `context-hub.sqlite3`. The authoritative context is the recorded checkout view.

- Specialist: `<specialist>`
- Relationship: `<lead | advisor | parallel-owner | independent-challenger>`
- Effort: `<Lean | Standard | Deep>`
- Write mode: `<read-only | writer>`
- Responsibility surface: <concrete paths/modules/state>
- Distinct decision value: <why this mission changes the result>
- Dependencies: <mission IDs or None>
- Required entries: <canonical IDs or None>
- Topic subscriptions: <topics or None>

## Objective

<Observable owned outcome>

## Intent

<Why this specialist is assigned>

## Success conditions

```json
["<observable success>"]
```

## Hard constraints

```json
["<constraint>"]
```

## Verification expectations

```json
["<required check>"]
```

## Known risks

```json
["<risk>"]
```

## Checked-out context view

- View ID: `<view-id>`
- Revision delivered: `<revision>`
- Canonical snapshot SHA-256: `<sha256>`
- Context-view SHA-256: `<sha256>`
- Snapshot file: `<checkout-json>`

## Authority and communication

- Work end to end inside the declared authority envelope.
- Do not edit canonical SQLite state or generated Hub views.
- Submit decision-relevant findings as proposals with evidence.
- Return a structured result against the exact checkout hash.
- Temporary clarification may be direct; accepted facts, decisions, ownership, and risk dispositions must be recorded through the Hub.
