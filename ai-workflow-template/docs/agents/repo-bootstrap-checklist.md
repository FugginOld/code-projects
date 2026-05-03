# Repo Bootstrap Checklist

Use this checklist when adding the AI CI workflow to a repo.

## 1. Install Skills

From repo root:

```bash
npx skills@latest add mattpocock/skills
npx skills add JuliusBrussee/caveman
```

Then run in the agent:

```text
/setup-matt-pocock-skills
```

## 2. Add Workflow Files

Copy these files into the repo:

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

## 3. Fill in Repo Context

Edit `CONTEXT.md`:

- repo purpose
- domain vocabulary
- important directories
- build/test commands
- compatibility rules
- known risks

## 4. First Agent Run

Use Claude or ChatGPT:

```text
/caveman lite
/grill-with-docs
/zoom-out
```

Ask:

```text
Update CONTEXT.md with repo vocabulary, important directories, commands, and compatibility rules. Do not change source code.
```

## 5. First Issue

Use:

```text
/to-issues
```

Ask:

```text
Create the smallest useful issue to improve this repo while following AGENTS.md.
```

## 6. First Implementation

Use Codex/ChatGPT:

```text
/caveman full
/tdd
```

Ask:

```text
Implement only issue #__. Write or update tests first when practical. Run available checks. Summarize changed files and risks.
```
