# AI CI Workflow for VS Code

This guide explains how to install and use the AI CI workflow in a new or existing repository using VS Code, Matt Pocock's Skills, Caveman, Claude, Codex, and GitHub Copilot.

## Purpose

This workflow creates a repeatable process for improving repositories with AI while reducing wasted sessions, rate-limit issues, large context dumps, and unstructured agent work.

The workflow follows this order:

```text
Context → Plan → Issue → Branch → Test → Change → Diagnose → Review → Merge
```

## Tools Used

- **VS Code**: main editor
- **Claude Pro**: planning, architecture, final review
- **ChatGPT Plus / Codex**: implementation, tests, validation
- **GitHub Copilot Pro**: inline coding assistance
- **Matt Pocock Skills**: structured AI workflows
- **Caveman**: compressed agent communication
- **GitHub CLI**: issues and pull requests

---

# 1. Prerequisites

Install these before starting:

## Node.js

Check:

```bash
node -v
npm -v
```

## Git

Check:

```bash
git --version
```

## GitHub CLI

Check:

```bash
gh --version
```

Login if needed:

```bash
gh auth login
```

## VS Code

Open your repo in VS Code:

```bash
code .
```

Recommended VS Code extensions:

- GitHub Copilot
- GitHub Copilot Chat
- Claude Code, if used
- GitHub Pull Requests and Issues

---

# 2. Add the AI CI Workflow Files

Copy the workflow markdown files into the root of your repository.

Expected structure:

```text
AGENTS.md
CONTEXT.md
README.md
docs/
  agents/
    ci-style-ai-workflow.md
    ai-usage-budget.md
  adr/
    0000-template.md
.github/
  ISSUE_TEMPLATE/
    ai-task.md
    bug.md
    feature.md
  PULL_REQUEST_TEMPLATE.md
```

If using the ZIP workflow pack, extract it from the repository root:

```bash
unzip ai-ci-workflow-pack.zip -d .
```

Review the files in VS Code before committing.

---

# 3. Install Matt Pocock Skills

From the root of the repo, run:

```bash
npx skills@latest add mattpocock/skills
```

Follow the wizard prompts.

Recommended selections:

```text
Issue tracker: GitHub
Docs location: docs/
ADR location: docs/adr/
Shared context file: CONTEXT.md
```

---

# 4. Install Caveman

From the root of the repo, run:

```bash
npx skills add JuliusBrussee/caveman
```

Caveman is used to keep AI sessions short and focused.

Recommended usage:

```text
/caveman lite
```

Use for planning and review.

```text
/caveman full
```

Use for implementation.

Avoid using highly compressed modes for final documentation, PRDs, user-facing writing, or ADRs.

---

# 5. Run Repo Setup Once

Run this once per repository, not once per AI tool.

In Claude or Codex inside the repo, run:

```text
/setup-matt-pocock-skills
```

Use Claude for this step if possible.

This configures repo-level conventions such as:

- issue workflow
- labels
- documentation locations
- context file usage
- ADR expectations

After setup, Claude, Codex, and Copilot all use the same repo files.

---

# 6. Commit the Baseline Workflow

After installing the files and running setup:

```bash
git status
git add .
git commit -m "Add AI CI workflow and agent rules"
```

Push the branch:

```bash
git push
```

---

# 7. Recommended Agent Roles

## Claude

Use Claude for high-value reasoning only:

- architecture review
- repo planning
- `/zoom-out`
- `/to-prd`
- `/to-issues`
- `/diagnose` on unclear problems
- final PR review

Avoid using Claude for:

- long implementation loops
- repeated test failures
- large repo scans after every change
- mechanical edits

## Codex

Use Codex for execution:

- `/tdd`
- writing tests
- implementation
- debugging
- running commands
- fixing validation failures

## GitHub Copilot

Use Copilot for small inline work:

- autocomplete
- boilerplate
- repetitive edits
- small refactors

Do not use Copilot Chat as the main repo-planning tool.

---

# 8. Standard Workflow in VS Code

## Step 1: Understand the repo

In Claude:

```text
/caveman lite
/zoom-out
```

Prompt:

```text
Review this repo using AGENTS.md, CONTEXT.md, and docs/agents/ci-style-ai-workflow.md. Identify the smallest useful improvement and any architectural risks. Do not read the entire repo unless necessary.
```

## Step 2: Create a small issue

In Claude:

```text
/to-issues
```

Prompt:

```text
Create one small GitHub issue for the highest-value improvement. Include acceptance criteria, likely files touched, tests expected, risk level, and rollback notes.
```

## Step 3: Create a branch

In the VS Code terminal:

```bash
git checkout -b agent/issue-number-short-name
```

Example:

```bash
git checkout -b agent/12-add-service-validation
```

## Step 4: Implement with tests

In Codex:

```text
/caveman full
/tdd
```

Prompt:

```text
Work only on issue #__.
Follow AGENTS.md, CONTEXT.md, and docs/agents/ci-style-ai-workflow.md.
Write tests first, implement the smallest fix, run checks, and summarize changed files.
```

## Step 5: Diagnose the result

In Codex:

```text
/diagnose
```

Prompt:

```text
Check this change for bugs, missing tests, regressions, bad assumptions, and unnecessary complexity. Do not redesign unrelated code.
```

## Step 6: Run local checks

Run only the checks that apply to the repo.

Common examples:

```bash
git status
npm test
npm run lint
npm run typecheck
pytest
ruff check .
mypy .
```

If no checks exist, create or document a minimal validation command before merging.

## Step 7: Final review with Claude

Use Claude only on the diff, not the full repo.

Prompt:

```text
/caveman lite

Repo context: see CONTEXT.md
Workflow: see AGENTS.md
Issue: #__
Branch: agent/#__
Changed files:
- file1
- file2

Tests run:
- command 1
- command 2

Review this diff only for correctness, missing tests, architecture risk, and merge risk. Do not redesign unrelated parts of the repo.
```

## Step 8: Open a pull request

```bash
gh pr create --fill
```

The PR should include:

- linked issue
- summary
- tests run
- risks
- rollback plan

## Step 9: Merge only after checks pass

Before merging:

```bash
git status
git pull --rebase
```

Merge only when:

- acceptance criteria are met
- tests pass
- review comments are resolved
- the change is focused on one issue

---

# 9. Low-Session / Low-Rate-Limit Rules

To avoid hitting Claude, Codex, or Copilot limits:

## Do not paste the whole repo

Use only:

```text
AGENTS.md
CONTEXT.md
docs/agents/ci-style-ai-workflow.md
the issue
affected files
test output
git diff
```

## Use Claude only twice per issue

Recommended:

1. planning / issue creation
2. final review

Use Codex for the middle implementation loop.

## Keep issues small

One issue should touch one focused area.

Avoid prompts like:

```text
Fix the whole repo.
```

Prefer:

```text
Add validation that services are backed by packages for Debian 12 environment files.
```

## Use Caveman by default

Planning:

```text
/caveman lite
```

Implementation:

```text
/caveman full
```

Final docs:

Use normal mode.

---

# 10. Standard Prompts

## Repo review prompt

```text
/caveman lite
/zoom-out

Review this repo using AGENTS.md and CONTEXT.md. Identify the smallest useful improvement, likely files affected, missing tests, and merge risk. Do not perform implementation.
```

## Issue creation prompt

```text
/to-issues

Create one small GitHub issue from the repo review. Include problem, acceptance criteria, likely files touched, tests expected, risk level, and rollback notes.
```

## Implementation prompt

```text
/caveman full
/tdd

Work only on issue #__.
Write tests first.
Implement the smallest fix.
Run available checks.
Summarize changed files and validation results.
Do not redesign unrelated code.
```

## Diagnosis prompt

```text
/diagnose

Check this change for bugs, missing tests, regressions, bad assumptions, unnecessary complexity, and acceptance criteria gaps.
```

## Final review prompt

```text
/caveman lite

Review this diff only.
Check correctness, tests, architecture risk, merge risk, and rollback safety.
Do not redesign unrelated code.
```

---

# 11. Recommended New Repo Startup Sequence

For every new repository:

```bash
code .
unzip ai-ci-workflow-pack.zip -d .
npx skills@latest add mattpocock/skills
npx skills add JuliusBrussee/caveman
```

Then in Claude:

```text
/setup-matt-pocock-skills
```

Then commit:

```bash
git add .
git commit -m "Add AI CI workflow"
```

Then start work:

```text
/caveman lite
/zoom-out
/to-issues
```

---

# 12. Recommended Existing Repo Startup Sequence

For an existing repo:

```bash
git checkout -b setup/ai-ci-workflow
unzip ai-ci-workflow-pack.zip -d .
npx skills@latest add mattpocock/skills
npx skills add JuliusBrussee/caveman
```

Then in Claude:

```text
/setup-matt-pocock-skills
/zoom-out
```

Ask:

```text
Review this existing repo. Identify outdated docs, missing context, missing validation, duplicated logic, missing tests, and the smallest safe improvement. Do not implement yet.
```

Commit setup separately:

```bash
git add .
git commit -m "Add AI CI workflow"
```

Then create issues for improvements.

---

# 13. Maintenance

Review these files periodically:

```text
AGENTS.md
CONTEXT.md
docs/agents/ci-style-ai-workflow.md
docs/agents/ai-usage-budget.md
```

Update them when:

- repo architecture changes
- terminology changes
- issue workflow changes
- validation requirements change
- AI tool usage changes

---

# 14. Key Rule

Do not let AI work directly on large, vague goals.

Always force work into:

```text
One issue → one branch → one tested change → one review → one PR
```
