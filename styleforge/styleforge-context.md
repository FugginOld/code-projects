# StyleForge — Project Context

## Project Overview

**StyleForge** is a static, client-side web application deployed via GitHub Pages (`fugginold.github.io`). It allows a user to import documents, apply branded style templates, preview the restyled output in-browser, iterate via a Claude-powered change loop, and export the final result.

No backend. No server. Everything runs in the browser via JavaScript.

---

## Deployment Target

- **Repo:** `github.com/FugginOld/styleforge`
- **Live URL:** `fugginold.github.io/styleforge`
- **Host:** GitHub Pages — served from the `main` branch `/docs` folder or repo root
- **Base path:** All internal asset links and API calls must be relative or root-relative (`/styleforge/...`) to work correctly under the `/styleforge` subpath
- **Constraints:** Static files only — no Node server, no Python, no Flask
- **API calls:** Direct from browser to Anthropic API (`claude-sonnet-4-20250514`)
- **API key:** Stored client-side (acceptable for personal use)

---

## Supported Pipelines

### 1. DOCX → HTML Preview → DOCX
- **Ingest:** `mammoth.js` (DOCX → HTML)
- **Export:** `docx.js` (HTML → DOCX)
- **Fidelity:** Highest of the three pipelines

### 2. PPTX → HTML Preview → PPTX
- **Ingest:** `JSZip` unpacks ZIP, custom XML parser extracts slide content
- **Preview:** Slide-deck view (16:9 cards, one per slide)
- **Export:** `pptxgenjs`
- **Limitations:** Animations and SmartArt do not survive round-trip; text, images, shapes, and tables do

### 3. XLSX → HTML Preview → XLSX
- **Ingest:** `SheetJS` (`xlsx.js`)
- **Preview:** HTML table with frozen headers and basic cell styling
- **Export:** `SheetJS`
- **Notes:** Cleanest pipeline — formulas, named ranges, and basic formatting survive round-trip

---

## Architecture

### Core Loop

```
[File Upload] → [Ingest Module] → [Structured JSON] → [Claude API]
     → [HTML Preview] → [User Change Request] → [Claude API]
     → (loop until approved)
     → [Export Module] → [Downloaded File]
```

### Structured JSON Schema (common intermediate format)

All three ingest modules normalize their source into this shared schema so Claude can reason about content regardless of format:

```json
{
  "format": "docx | pptx | xlsx",
  "meta": { "title": "", "author": "", "created": "" },
  "content": [
    {
      "type": "section | slide | sheet",
      "index": 0,
      "heading": "",
      "body": "",
      "tables": [],
      "lists": [],
      "images": []
    }
  ]
}
```

### File Structure

```
FugginOld/styleforge/           # GitHub repo root
├── index.html                  # Single-page app shell
├── style.css                   # App UI styles
├── app.js                      # Main application logic
├── engine/
│   ├── ingest.js               # File reading (docx, pptx, xlsx)
│   ├── restyle.js              # Claude API calls + prompt management
│   ├── export.js               # DOCX / PPTX / XLSX output
│   └── preview.js              # HTML preview generation
├── templates/
│   ├── asi_standard.json       # ASI branded template
│   └── blank.json              # Generic unstyled template
├── assets/
│   ├── logo_asi.b64            # Base64-encoded ASI logo
│   └── favicon.ico
└── styleforge-context.md       # This file — project context for Claude Code
```

> **GitHub Pages config:** Set Pages source to the `main` branch root (not `/docs`). The app will be live at `fugginold.github.io/styleforge` automatically once Pages is enabled on the repo.

---

## Template System

Templates are format-aware JSON files. One template governs all three output formats with shared brand rules and format-specific overrides.

### Template Schema

```json
{
  "name": "ASI Standard",
  "version": "1.0",
  "applies_to": ["docx", "pptx", "xlsx"],
  "brand": {
    "primary":        "#C0392B",
    "secondary":      "#2A2A2A",
    "accent":         "#27AE60",
    "font_heading":   "Arial",
    "font_body":      "Calibri",
    "font_size_body": 11,
    "font_size_h1":   16,
    "font_size_h2":   13,
    "logo_base64":    "data:image/jpeg;base64,..."
  },
  "docx": {
    "margins": { "top": "1in", "bottom": "1in", "left": "1.25in", "right": "1in" },
    "header": { "logo": true, "logo_position": "right", "text": "" },
    "footer": { "text": "ASI Health & Safety Plan", "page_numbers": true }
  },
  "pptx": {
    "slide_size": "16:9",
    "header_height_inches": 0.82,
    "footer_y_inches": 5.2,
    "title_bar": { "bg": "#2A2A2A", "accent": "#C0392B", "height_inches": 0.55 },
    "chrome_fn": "addChrome"
  },
  "xlsx": {
    "header_row_bg":   "#2A2A2A",
    "header_row_font": "#FFFFFF",
    "alt_row_bg":      "#F5F5F5",
    "freeze_top_row":  true,
    "border_style":    "thin"
  }
}
```

---

## Claude API Integration

### Model
`claude-sonnet-4-20250514`

### Endpoint
`https://api.anthropic.com/v1/messages`

### System Prompt Architecture

Each API call receives:
1. The structured JSON of the source document content
2. The full template JSON
3. The conversation history of prior change requests
4. Output format instructions

```
You are a document restyling engine.

You receive:
- SOURCE: structured JSON of document content
- TEMPLATE: JSON object defining all style rules
- HISTORY: array of prior user change requests and your prior responses

Your task:
1. Reflow the SOURCE content into clean, styled HTML matching TEMPLATE rules exactly.
2. Apply all fonts, colors, margins, and layout via inline CSS (sandboxed preview environment).
3. After the HTML, append a <changes> block listing what you applied or changed.
4. If the user's change request is ambiguous, make a reasonable decision and note it in <changes>.

Return format:
<html>...complete styled HTML document...</html>
<changes>
- Applied heading font: Arial 16pt #2A2A2A
- Added ASI logo to header, right-aligned
- ...
</changes>
```

### Conversation History Management

Full history is passed on every call (Claude has no memory between calls):

```javascript
const history = [
  { role: "user",      content: "Initial restyle request + source JSON + template JSON" },
  { role: "assistant", content: "...HTML output + changes block..." },
  { role: "user",      content: "Make the headings larger and move logo to the left" },
  { role: "assistant", content: "...updated HTML + changes block..." }
];
```

---

## UI Layout

```
┌─────────────────────────────────────────────────────────┐
│  StyleForge                               [Templates ▾]  │
├──────────────────┬──────────────────────────────────────┤
│  LEFT PANEL      │  PREVIEW PANEL                       │
│                  │                                      │
│  SOURCE FILE     │  ┌────────────────────────────────┐  │
│  [Drop / Browse] │  │                                │  │
│                  │  │   Rendered HTML document       │  │
│  TEMPLATE        │  │   (iframe, sandboxed)          │  │
│  [Selector ▾]    │  │                                │  │
│  [Upload JSON]   │  └────────────────────────────────┘  │
│                  │                                      │
│  FORMAT OUT      │  Changes applied:                    │
│  ○ DOCX          │  ✓ Fonts  ✓ Header  ✓ Colors        │
│  ○ PPTX          │                                      │
│  ○ XLSX          │  ┌────────────────────────────────┐  │
│                  │  │ Request changes...          [→] │  │
│  [Restyle ▶]     │  └────────────────────────────────┘  │
│                  │                                      │
│                  │  [Save DOCX]  [Save PPTX] [Save XLSX]│
└──────────────────┴──────────────────────────────────────┘
```

---

## Build Order

| Phase | Deliverable |
|-------|-------------|
| 1 | UI shell — file drop, format detection, template selector, preview panel, export buttons |
| 2 | DOCX pipeline — mammoth.js ingest, docx.js export |
| 3 | XLSX pipeline — SheetJS both directions |
| 4 | PPTX pipeline — JSZip ingest, pptxgenjs export |
| 5 | Claude API loop — restyle engine, change request chat, revision history |
| 6 | Template manager — save/load/extract templates from reference files |

---

## CDN Dependencies

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pptxgenjs/3.12.0/pptxgen.bundle.js"></script>
<!-- docx.js loaded as ES module from unpkg -->
```

---

## Key Technical Risks

| Risk | Mitigation |
|------|------------|
| PPTX XML parsing inconsistency | Scope to text, tables, images only; skip SmartArt/animations |
| Claude HTML output drift across turns | Enforce strict output schema with required section IDs |
| HTML → DOCX export fidelity | Best for text-heavy docs; warn user on complex layouts |
| API key exposed in client-side JS | Acceptable for personal GitHub Pages use; add `.gitignore` note |
| CORS on Anthropic API | Anthropic API supports browser-direct calls; no proxy needed |

---

## Testing & CI

### Test Runner — Vitest
- Unit test all ingest, export, and restyle modules in isolation
- Mock Claude API responses — never burn real tokens in CI
- Zero-config, no build system required
- Test files live in `__tests__/` adjacent to each module

### End-to-End — Playwright
- Automates a real headless Chromium browser
- Key scenarios to cover:
  - File upload → correct format detected → preview renders
  - Change request submitted → preview updates
  - Each export format (DOCX, PPTX, XLSX) triggers a download
- Runs on PR to `main` only (slower, not every push)
- Uses a mock API key env var — no real Claude calls in CI

### GitHub Actions Workflows

**`ci.yml`** — triggers on every push and PR
```yaml
steps:
  - ESLint lint check
  - Vitest unit tests
  - Build check (confirm index.html + all assets resolve)
```

**`e2e.yml`** — triggers on PR to `main`
```yaml
steps:
  - Playwright end-to-end tests (headless Chromium)
  - Mock ANTHROPIC_API_KEY injected as GitHub Actions secret
```

**`deploy.yml`** — triggers on push to `main`
```yaml
steps:
  - Must pass ci.yml gate first
  - actions/deploy-pages publishes to fugginold.github.io/styleforge
```

### Code Quality

**ESLint**
- Config: `eslint:recommended` + browser globals
- Include `eslint-plugin-no-unsanitized` — critical for this app since Claude returns raw HTML injected into the preview iframe; this plugin flags unguarded `innerHTML` assignments

**Prettier** — formatting consistency across all JS/HTML/CSS/JSON files

**Husky + lint-staged** — runs ESLint and Prettier on staged files pre-commit; nothing dirty reaches the repo

### Security

**API key handling**
- Never commit the real API key
- Add `config.js` to `.gitignore`
- Commit a `config.example.js` with a placeholder value as the reference
- In CI, inject `ANTHROPIC_API_KEY` as a GitHub Actions secret

**Dependabot** — enable in repo settings; monitors CDN-pinned library versions and opens PRs when security patches are available

### Suggested `package.json` Scripts
```json
{
  "scripts": {
    "test":     "vitest run",
    "test:e2e": "playwright test",
    "lint":     "eslint engine/ app.js",
    "format":   "prettier --write .",
    "prepare":  "husky install"
  }
}
```

### File additions to repo structure
```
FugginOld/styleforge/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── e2e.yml
│       └── deploy.yml
├── .vscode/
│   ├── settings.json           # Workspace editor settings
│   └── extensions.json         # Recommended extensions prompt
├── __tests__/
│   ├── ingest.test.js
│   ├── export.test.js
│   └── restyle.test.js
├── e2e/
│   └── workflows.spec.js
├── config.example.js           # Placeholder — safe to commit
├── config.js                   # Real API key — gitignored
├── .gitignore
├── .eslintrc.json
├── .prettierrc
└── package.json
```

---

## VS Code Configuration

### `.vscode/settings.json`
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.tabSize": 2,
  "eslint.validate": ["javascript", "html"],
  "files.associations": {
    "*.json": "jsonc"
  },
  "vitest.enable": true,
  "playwright.reuseBrowser": true
}
```

### `.vscode/extensions.json`
```json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "eamodio.gitlens",
    "ms-playwright.playwright",
    "vitest.vitest-explorer",
    "github.vscode-github-actions",
    "redhat.vscode-yaml",
    "zainchen.json",
    "redhat.vscode-xml",
    "christian-kohler.path-intellisense",
    "formulahendry.auto-rename-tag",
    "rangav.vscode-thunder-client"
  ]
}
```

### Extension Notes

| Extension | ID | Purpose |
|-----------|-----|---------|
| ESLint | `dbaeumer.vscode-eslint` | Inline lint errors as you type |
| Prettier | `esbenp.prettier-vscode` | Format on save for JS/HTML/CSS/JSON |
| GitLens | `eamodio.gitlens` | Track Claude Code session changes across files |
| Playwright Test | `ms-playwright.playwright` | Run/debug e2e tests in editor |
| Vitest Explorer | `vitest.vitest-explorer` | Run/debug unit tests in editor |
| GitHub Actions | `github.vscode-github-actions` | Validate workflow YAML inline |
| YAML | `redhat.vscode-yaml` | Schema validation for workflow files |
| JSON with Comments | `zainchen.json` | Folding + tolerates comments in template JSON |
| XML | `redhat.vscode-xml` | Readable DOCX/PPTX/XLSX raw XML debugging |
| Path Intellisense | `christian-kohler.path-intellisense` | Autocomplete file paths in imports and src/href |
| Auto Rename Tag | `formulahendry.auto-rename-tag` | Keeps HTML open/close tags in sync |
| Thunder Client | `rangav.vscode-thunder-client` | Test Anthropic API calls before wiring into app |

### Extensions to Avoid
- **GitHub Copilot** — conflicts with Claude Code for autocomplete; redundant
- **Docker** — nothing to containerize
- **Live Share** — solo project

---

## Notes from Prior Work

- `pptxgenjs` already proven in ASI real estate deck builds (`addChrome()` pattern, `HEADER_H=0.82"`, `FOOTER_Y=5.2"`)
- ASI brand colors: primary `#C0392B`, secondary `#2A2A2A`, accent `#27AE60`
- ASI header image stored as base64 extracted from `ASI_Template.pptx ppt/media/image1.jpeg`, cropped to `(0,0,1920,145)`
- LibreOffice `.doc`→`.docx` conversions inject Liberation Serif/FreeSans font artifacts into `styles.xml` — watch for this on DOCX ingest
- Logo should always be added as a new image file, never overwrite `image1.png` in existing ZIPs
