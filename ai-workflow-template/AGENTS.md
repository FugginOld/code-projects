# AGENTS.md

## Purpose

This repo uses a CI-style AI workflow designed for:

- Claude Pro (planning / review)
- ChatGPT / Codex (implementation)
- GitHub Copilot (inline assistance)

Optimized to minimize session limits and token usage.

---

## Companion Docs

| File | Purpose |
|------|---------|
| `docs/agents/ci-style-ai-workflow.md` | Full gate-by-gate workflow (Context → Merge) |
| `docs/agents/ai-usage-budget.md` | Agent budget rules, session-saving prompts, escalation rules |
| `docs/agents/agent-handoff-template.md` | Handoff template when switching between agents |
| `docs/agents/repo-bootstrap-checklist.md` | Checklist for new repo setup |

---

## Workflow Model

```text
Context → Plan → Issue → Branch → Test → Change → Diagnose → Review → Merge
```

See `docs/agents/ci-style-ai-workflow.md` for full gate definitions and pass conditions.

---

## Quick Start

```text
Claude:
/caveman lite
/zoom-out
/to-issues

Codex:
/caveman full
/tdd
/diagnose

Claude:
review diff only
```

---

## Agent Roles

### Claude (Planner / Reviewer)

Use for: `/zoom-out`, `/grill-with-docs`, `/to-prd`, `/to-issues`, `/diagnose` (unclear issues only), PR review, architecture decisions, architecture review, repo planning, issue breakdown, ADR and design review.

Never use for: multi-file implementation, test/debug/fix loops, large code generation, full repo scans, mechanical refactors.

### Codex / ChatGPT (Builder)

Use for: `/tdd`, writing tests, debugging, scripts, command-line validation, small-to-medium code changes, updating generated files.

Rules: one issue at a time · write tests first when practical · smallest possible change · run local checks · summarize results.

Never: redesign mid-task · modify unrelated files · work across multiple issues.

### GitHub Copilot (Inline Assistant)

Use for: autocomplete, boilerplate, repetitive edits, small refactors.

Do not use for: repo-wide analysis, architecture decisions, replacing Claude or Codex workflows.

---

## Agent Switching

Switch **Claude → Codex** when: issue is clearly defined, implementation begins.

Switch **Codex → Claude** when: implementation is complete, final review needed, or behavior is unclear/risky.

See `docs/agents/agent-handoff-template.md` for the handoff checklist.  
See `docs/agents/ai-usage-budget.md` for escalation rules and session-saving prompts.

---

## Matt Pocock Skills

Run once per repo: `/setup-matt-pocock-skills`

```text
/grill-with-docs            # build repo/domain context
/zoom-out                   # understand architecture and impact
/to-prd                     # define larger work
/to-issues                  # create small actionable issues
/tdd                        # implement one issue at a time
/diagnose                   # verify correctness and regressions
/improve-codebase-architecture  # use only after behavior works
```

---

## Agent Skills

- **Issue tracker** — GitHub Issues via `gh`. See `docs/agents/issue-tracker.md`.
- **Triage labels** — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.
- **Domain docs** — root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

---

## Required Repo Files

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

---

## Caveman Usage

```text
/caveman lite   # planning and review
/caveman full   # implementation
```

Avoid terse compression when writing documentation, PRDs, ADRs, user-facing copy, or README sections.

---

## Non-Negotiable Rules

- One issue at a time · one branch per issue
- Small, reviewable changes
- No redesign during bug fixes
- No abstraction before behavior works
- Tests before implementation when practical
- Run local checks before PR
- Update `CONTEXT.md` when domain changes
- Add ADRs for architecture decisions

---

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
