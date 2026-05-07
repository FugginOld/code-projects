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

## ASI Brand System (Source of Truth)

All style decisions must trace back to these values extracted directly from the 2025 ASI Brand Book, Color Palette, and template files.

### Color Palette

**Primary Colors**
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Sky Blue | `#9DAFCD` | 157, 175, 205 | Primary backgrounds, accents |
| Aviator Blue | `#7787AA` | 119, 135, 170 | Secondary backgrounds |
| Naval | `#030F40` | 3, 15, 64 | Headers, dark backgrounds, primary text on light |
| Dress White | `#FFFFFF` | 255, 255, 255 | Backgrounds, text on dark |
| Tarmac Gray | `#BEC1C7` | 190, 193, 199 | Dividers, secondary elements |
| Gunmetal | `#4A4D54` | 74, 77, 84 | Secondary text, borders |

**Accent Colors** *(limited use — never large fields of color)*
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| ASI Red | `#A7010A` | 167, 1, 10 | Accent only — title bars, highlights |
| Garnet | `#89080F` | 137, 8, 15 | Deeper red accent |
| Jet Black | `#000000` | 0, 0, 0 | Typography, icons |

**Color Contrast Rules**
- Jet Black text on: Sky Blue, Aviator Blue, Dress White, Tarmac Gray backgrounds
- Dress White text on: Naval, Gunmetal backgrounds
- Naval text on: Dress White, Tarmac Gray, Sky Blue backgrounds

### Typography

**Branded Fonts**
- **Bebas Neue Regular** — marketing materials, graphics, website display
- **Segoe UI Regular** — all titles, headers, subheads, body text in documents

**Print Size Scale**
| Role | Size |
|------|------|
| H1 / Titles | 20–24pt |
| H2 / Subheads | 15–18pt |
| Body text | 10–12pt |
| Business cards | 8–10pt (7pt absolute min) |

> **Note:** Technical documentation and proposals follow government formatting guidelines, not these typography guidelines.

### Logo Rules
- Standard: Full color (red mark + navy "ASI") on white backgrounds
- Reversed: All white on dark backgrounds — never reverse to color
- Never stretch, condense, rotate, or modify the logo
- Minimum height: 8px
- Placement: Always left or right margin — top-left, top-right, bottom-left, or bottom-right
- Clear space: Equal to cap-height of the "A" in "Aero" on all sides; 1.5x at top/bottom
- Use triangle icon alone only when space is too small for full logo and company name is written elsewhere

---

## ASI Templates

Four templates govern all document output. These files live in the repo at `templates/` but are **gitignored** — they exist locally only and are loaded into the app via localStorage or manual import.

### Template 1 — ASI Letterhead (`asi_letterhead.json`)
**Use for:** RFPs, SOWs, company communications, formal correspondence

Extracted from `New_ASI_Letterhead.docx`:
- **Page size:** US Letter (12,240 × 15,840 DXA)
- **Margins:** Top 1", Right 0.75", Bottom 1", Left 0.75" (1080 DXA = 0.75")
- **Header:** ASI logo image (`word/media/image1.png`) — right-aligned
- **Header distance:** 720 DXA (0.5")
- **Footer distance:** 720 DXA (0.5")
- **Font:** Segoe UI
- **Body font size:** 11pt (22 half-pts)
- **Logo contrast rule:** Full color on white; reverse to white on dark backgrounds

```json
{
  "name": "ASI Letterhead",
  "type": "docx",
  "page": { "width_dxa": 12240, "height_dxa": 15840, "orient": "portrait" },
  "margins": { "top": 1440, "right": 1080, "bottom": 1440, "left": 1080, "header": 720, "footer": 720 },
  "fonts": { "heading": "Segoe UI", "body": "Segoe UI" },
  "sizes_halfpt": { "h1": 32, "h2": 26, "body": 22 },
  "colors": { "heading": "#030F40", "body": "#000000", "accent": "#A7010A" },
  "header": { "logo": true, "logo_align": "right", "logo_file": "asi_logo_standard.png" },
  "footer": { "text": "", "page_numbers": false }
}
```

---

### Template 2 — ASI Work Instruction (`asi_wi.json`)
**Use for:** ISO 9001 Work Instructions (WI-xx series)

Extracted from `ASI_WI_Template.docx`:
- **Page size:** US Letter portrait (12,240 × 15,840 DXA)
- **Margins:** Top 1", Right 1", Bottom 1.25", Left 1" (gutter 0)
- **Header distance:** 720 DXA; **Footer distance:** 504 DXA
- **Font:** Arial throughout (all weights)
- **Font sizes:** Body 11pt, H1 16pt, H2 14pt, H3 13pt, small text 9pt
- **Header content:** "Work Instruction | [TITLE] | Rev: — | Date: ___/___/______ | Page X of Y"
- **Footer content:** "Controlled Information [tab] For Internal Use Only" + disclaimer line
- **Footer note:** "This document should be considered UNCONTROLLED if: 1) it is a .pdf file, or 2) it is hardcopy. Verify revision status on the ASI Wiki repository."
- **Colors in use:** `#1F4D78` (dark blue headings), `#666666` (subtitle gray), `#999999` (light gray), `#2E74B5` (link blue)
- **No logo in header** — header is text-only with structured metadata fields

**WI Document Structure (required sections in order):**
1. Cover page — WI number, title, revision, date, approval signatures
2. Change Record table
3. Distribution List table
4. Purpose
5. Scope
6. References
7. Definitions
8. Responsibilities
9. Procedure
10. Records
11. Related Documents
12. Non-Conformance

```json
{
  "name": "ASI Work Instruction",
  "type": "docx",
  "page": { "width_dxa": 12240, "height_dxa": 15840, "orient": "portrait" },
  "margins": { "top": 1440, "right": 1440, "bottom": 1800, "left": 1440, "header": 720, "footer": 504 },
  "fonts": { "heading": "Arial", "body": "Arial" },
  "sizes_halfpt": { "h1": 32, "h2": 28, "h3": 26, "body": 22, "small": 18 },
  "colors": { "heading": "#1F4D78", "subtitle": "#666666", "muted": "#999999", "link": "#2E74B5" },
  "header": {
    "logo": false,
    "fields": ["Work Instruction", "[TITLE]", "Rev: —", "Date: ___/___/______", "Page X of Y"]
  },
  "footer": {
    "left": "Controlled Information",
    "right": "For Internal Use Only",
    "disclaimer": "This document should be considered UNCONTROLLED if: 1) it is a .pdf file, or 2) it is hardcopy. Verify revision status on the ASI Wiki repository.",
    "page_numbers": true
  }
}
```

---

### Template 3 — ASI PowerPoint (`asi_slide.json`)
**Use for:** All ASI slide decks and presentations

Extracted from `ASI_Slide_Template_2025.pptx`:
- **Slide size:** 12,192,000 × 6,858,000 EMU = 16:9 widescreen (13.33" × 7.5")
- **Master background:** scheme color `bg1` (Dress White / `#FFFFFF`)
- **Master fonts:** Arial (Latin), with theme minor/major font fallbacks
- **Master colors:** Naval `#040F40`, accent `#F26B43` (orange-red — use sparingly)
- **Theme accent colors:** `#4472C4`, `#ED7D31`, `#A5A5A5`, `#FFC000`, `#5B9BD5`, `#70AD47`
- **Media files:** `image1.png` (logo), `image2.png` (secondary graphic)
- **Chrome pattern** (`addChrome()` — apply to every slide):
  - Header: ASI logo, top-right or top-left per layout
  - Footer bar: Naval `#030F40` background, Dress White text
  - Footer Y position: `FOOTER_Y = 5.2"` from top
  - Header height: `HEADER_H = 0.82"`
  - Title bar: `y = HEADER_H`, `h = 0.55"`, background `#030F40` (Naval), left accent strip `#A7010A` (ASI Red)
  - Page numbers: bottom-right in footer bar

```json
{
  "name": "ASI Slide Template",
  "type": "pptx",
  "slide_size_emu": { "cx": 12192000, "cy": 6858000 },
  "slide_size_inches": { "w": 13.33, "h": 7.5 },
  "aspect": "16:9",
  "fonts": { "heading": "Arial", "body": "Segoe UI" },
  "colors": {
    "background": "#FFFFFF",
    "naval": "#030F40",
    "red_accent": "#A7010A",
    "text_on_dark": "#FFFFFF",
    "text_on_light": "#030F40"
  },
  "chrome": {
    "header_height_in": 0.82,
    "footer_y_in": 5.2,
    "title_bar_h_in": 0.55,
    "title_bar_bg": "#030F40",
    "title_bar_accent": "#A7010A",
    "footer_bg": "#030F40",
    "footer_text_color": "#FFFFFF",
    "logo_file": "asi_logo_standard.png",
    "page_numbers": true
  }
}
```

---

## Template Asset Files (gitignored, local only)

```
templates/                          # .gitignored except blank.json
├── asi_letterhead.json
├── asi_wi.json
├── asi_slide.json
├── blank.json                      # Safe to commit — no brand assets
└── assets/
    ├── asi_logo_standard.png       # Full color logo (red + navy on white)
    ├── asi_logo_reverse.png        # All-white logo for dark backgrounds
    ├── asi_logo_triangle_red.png   # Icon-only for tight spaces
    └── asi_color_palette.json      # Machine-readable color reference
```

`asi_color_palette.json`:
```json
{
  "primary": {
    "sky_blue":     { "hex": "#9DAFCD", "rgb": [157,175,205] },
    "aviator_blue": { "hex": "#7787AA", "rgb": [119,135,170] },
    "naval":        { "hex": "#030F40", "rgb": [3,15,64] },
    "dress_white":  { "hex": "#FFFFFF", "rgb": [255,255,255] },
    "tarmac_gray":  { "hex": "#BEC1C7", "rgb": [190,193,199] },
    "gunmetal":     { "hex": "#4A4D54", "rgb": [74,77,84] }
  },
  "accent": {
    "asi_red":   { "hex": "#A7010A", "rgb": [167,1,10] },
    "garnet":    { "hex": "#89080F", "rgb": [137,8,15] },
    "jet_black": { "hex": "#000000", "rgb": [0,0,0] }
  }
}
```

---

## Notes from Prior Work

- `pptxgenjs` already proven in ASI real estate deck builds (`addChrome()` pattern, `HEADER_H=0.82"`, `FOOTER_Y=5.2"`)
- **Corrected brand colors** from 2025 Brand Book: primary is Naval `#030F40` (not `#2A2A2A`), red accent is ASI Red `#A7010A` (not `#C0392B`), green `#27AE60` is NOT an ASI brand color — remove from all templates
- PPTX master confirms Naval as `#040F40` (1-digit rounding diff from `#030F40` — use `#030F40` per Brand Book)
- LibreOffice `.doc`→`.docx` conversions inject Liberation Serif/FreeSans font artifacts into `styles.xml` — correct manually on ingest
- Logo must always be added as a new image file, never overwrite `image1.png` in existing ZIPs
- WI template header is text-only (no logo) — logo lives in the Letterhead header only
- Technical documents (WI series, proposals) follow government formatting guidelines per Brand Book note — Arial is correct for WI, Segoe UI for general comms
- Letterhead margins are 0.75" left/right (1080 DXA), not 1" — tighter than WI template