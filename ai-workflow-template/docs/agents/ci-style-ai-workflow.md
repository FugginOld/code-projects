# CI-Style AI Workflow

## Purpose

This workflow makes AI-assisted changes predictable, reviewable, and safe across repos while reducing Claude, ChatGPT, Codex, and Copilot session usage.

Required flow:

```text
Context → Plan → Issue → Branch → Test → Change → Diagnose → Review → Merge
```

## Gate 0 — Repo Setup

Run once per repo:

```text
/setup-matt-pocock-skills
```

Confirm these files exist:

```text
AGENTS.md
CONTEXT.md
docs/agents/
docs/adr/
.github/pull_request_template.md
.github/ISSUE_TEMPLATE/ai-task.md
```

Pass condition:

- repo has agent instructions
- repo has domain context
- repo has PR and issue templates

## Gate 1 — Context

Use Claude or ChatGPT:

```text
/caveman lite
/grill-with-docs
/zoom-out
```

Required result:

- affected files identified
- domain terms checked against `CONTEXT.md`
- relevant architecture decisions reviewed
- smallest useful change identified

Pass condition:

- scope is clear
- no unknown domain terms remain
- no architecture conflict ignored

## Gate 2 — Issue

For non-trivial work:

```text
/to-prd
/to-issues
```

Each issue must include:

- problem
- acceptance criteria
- likely files touched
- tests expected
- risk level
- rollback note

Pass condition:

- issue is independently completable
- issue is small enough for one branch

## Gate 3 — Branch

Create a branch:

```bash
git checkout -b agent/<issue-number>-short-name
```

Pass condition:

- branch is tied to one issue
- working tree was clean before starting

## Gate 4 — Test-Driven Implementation

Use Codex/ChatGPT for implementation:

```text
/caveman full
/tdd
```

Required loop:

1. write or identify failing test
2. run test and confirm failure when practical
3. implement smallest fix
4. run test and confirm pass
5. refactor only if tests stay green

Pass condition:

- tests added or reason documented
- no unrelated rewrite
- no unrelated formatting churn

## Gate 5 — Diagnose

Use Codex/ChatGPT first:

```text
/diagnose
```

Check:

- bug reproduced or feature verified
- edge cases considered
- assumptions listed
- regression tests exist where practical
- command output reviewed

Pass condition:

- no unresolved blocker
- no untested critical path

## Gate 6 — Architecture Check

Use only for medium or large changes:

```text
/improve-codebase-architecture
```

Ask:

```text
Did this change improve structure, preserve behavior, avoid duplication, and follow CONTEXT.md vocabulary?
```

Pass condition:

- no unnecessary abstraction
- no duplicated core logic
- no ADR conflict

## Gate 7 — Local CI

Run all relevant checks.

Common examples:

```bash
git status
npm test
npm run lint
npm run typecheck
pytest
ruff check .
mypy .
go test ./...
cargo test
```

Pass condition:

- all available checks pass
- failures are fixed or documented

## Gate 8 — Review

Use Claude only for final high-value review when possible:

```text
/caveman lite
/diagnose
```

Review prompt:

```text
Review this diff only. Block the PR for correctness issues, missing tests, risky assumptions, unnecessary complexity, or architecture conflicts. Do not re-read the whole repo unless required.
```

Pass condition:

- review findings resolved
- remaining risks documented in PR

## Gate 9 — Pull Request

Create PR:

```bash
gh pr create --fill
```

PR must include:

- linked issue
- summary
- tests run
- risks
- rollback plan

## Gate 10 — Merge

Before merge:

```bash
git status
git pull --rebase
```

Merge only when:

- issue acceptance criteria are met
- tests pass
- no unresolved review comments remain
- branch has one focused change
