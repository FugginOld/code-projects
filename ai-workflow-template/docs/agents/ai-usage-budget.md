# AI Usage Budget

## Purpose

This file prevents session limits and rate limits by assigning the right work to the right AI tool.

## Default Agent Budget

| Agent | Budget Role | Use For | Avoid |
|---|---|---|---|
| Claude Pro | scarce reasoning | architecture, planning, review | long coding loops |
| ChatGPT Plus / Codex | implementation | tests, code, debugging | repeated broad planning |
| GitHub Copilot Pro | local assist | autocomplete, small edits | full repo analysis |

## Claude Rules

Claude should receive only:

- `AGENTS.md`
- `CONTEXT.md`
- issue text
- changed file list
- selected affected files only when needed
- test output
- `git diff`

Do not give Claude:

- entire repo dumps
- generated files unless relevant
- repeated full context after every change
- long terminal logs without trimming

## Codex / ChatGPT Rules

Use Codex or ChatGPT for:

- implementation
- test writing
- repeated test/fix loops
- scripts
- mechanical cleanup
- local verification

Codex should always summarize:

```text
Changed files:
Commands run:
Tests passing:
Known risks:
Next recommended step:
```

## Copilot Rules

Use Copilot for:

- inline suggestions
- boilerplate
- simple completion
- repetitive edits

Avoid Copilot Chat for:

- architecture decisions
- full repo review
- large context analysis
- PRD creation

## Session-Saving Prompt for Claude

Use this when starting a Claude session:

```text
Use AGENTS.md and CONTEXT.md.
Use /caveman lite.
Do not re-read the whole repo.
Issue: #__
Branch: agent/__
Changed files:
- __
Tests run:
- __
Task:
Review only this diff for correctness, missing tests, architecture conflicts, and merge risk.
```

## Session-Saving Prompt for Codex

```text
Use AGENTS.md and CONTEXT.md.
Use /caveman full.
Work only on issue #__.
Do not redesign unrelated code.
Write or update tests first when practical.
Run available checks.
Return changed files, commands run, and remaining risks.
```

## Escalation Rules

Escalate from Codex to Claude only when:

- architecture is unclear
- tests conflict with expected behavior
- requirements are ambiguous
- a change affects multiple subsystems
- an ADR may be needed

Do not escalate for:

- syntax errors
- normal test failures
- formatting
- import fixes
- boilerplate
