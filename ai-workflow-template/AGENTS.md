# AGENTS.md

## Purpose

This repo uses a CI-style AI workflow designed for Claude Pro, ChatGPT Plus/Codex, and GitHub Copilot Pro while minimizing session limits and rate limits.

Default workflow:

```text
Context → Plan → Issue → Branch → Test → Change → Diagnose → Review → Merge
```

## Agent Roles

### Claude

Use Claude for high-value reasoning only:

- architecture review
- repo planning
- issue breakdown
- PR review
- diagnosing unclear failures
- ADR and design review

Do not use Claude for:

- long coding sessions
- repeated test/fix loops
- broad repo re-reading
- full file dumps unless required
- mechanical refactors

### Codex / ChatGPT

Use Codex or ChatGPT for implementation work:

- `/tdd`
- writing tests
- debugging
- scripts
- command-line validation
- small-to-medium code changes
- updating generated files

### GitHub Copilot

Use Copilot for local assistance only:

- autocomplete
- small inline edits
- boilerplate
- repetitive code
- simple refactors

Do not use Copilot Chat for large repo scans unless needed.

## Matt Pocock Skills Order

Use this order unless the issue requires a smaller subset:

```text
/setup-matt-pocock-skills   # once per repo
/grill-with-docs            # build repo/domain context
/zoom-out                   # understand architecture and impact
/to-prd                     # define larger work
/to-issues                  # create small actionable issues
/tdd                        # implement one issue at a time
/diagnose                   # verify correctness and regressions
/improve-codebase-architecture # use only after behavior works
```

## Caveman Usage

Use Caveman to reduce context and token usage.

Recommended modes:

```text
/caveman lite   # planning, issue review, PR review
/caveman full   # implementation and debugging
```

Avoid terse compression when writing:

- documentation
- PRDs
- ADRs
- user-facing copy
- README sections

## Required Files

The repo should maintain:

```text
AGENTS.md
CONTEXT.md
docs/agents/ci-style-ai-workflow.md
docs/agents/ai-usage-budget.md
docs/agents/agent-handoff-template.md
docs/adr/0000-template.md
.github/pull_request_template.md
.github/ISSUE_TEMPLATE/ai-task.md
```

## Non-Negotiable Rules

- Work on one issue at a time.
- Create or use a branch per issue.
- Keep changes small and reviewable.
- Do not redesign during a bug fix.
- Do not add abstractions before behavior works.
- Tests come before implementation when practical.
- Run available local checks before PR.
- Update `CONTEXT.md` when repo vocabulary or domain rules change.
- Add an ADR when architecture decisions change.

## Default Prompt for AI Work

```text
Use the CI-style AI workflow from AGENTS.md.
Use Caveman mode unless writing docs.
Work on one small vertical slice only.
Do not redesign unrelated code.
Use existing repo conventions.
Write or update tests first when practical.
Run available checks.
Summarize changed files, commands run, and remaining risks.
```
