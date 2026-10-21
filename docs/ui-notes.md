# SoundDue UI Redesign & Architecture Notes

## 1. Overview & Design Direction

SoundDue is an explainable music-record reconciliation workbench built for small publishers and royalty administrators. Unlike "black-box" matching tools, SoundDue operates on **glass-box reasoning**: every discrepancy is exposed with its **Issue**, **Evidence**, **Symbolic Rule Trace**, **Uncertainty**, **Next Step**, and **Review History**.

### Core Design Principles
- **Calm & Evidence-Focused**: Styled as a clean audit workbench rather than a flashy dashboard. Soft neutral slate surfaces (`#f8fafc`, `#f1f5f9`), crisp borders, and purposeful contrast.
- **Strict Information Hierarchy**: Monospace typography for machine identifiers (ISRCs, ISWCs, rule IDs, row coordinates); clear sans-serif typography for explanations and metadata.
- **Glass-Box Reasoning**: Findings are leads for human review, not automated ownership determinations. Every finding exposes all 6 reasoning dimensions without truncation.
- **Accessible & Resilient**: Meets WCAG AA standards. No status is conveyed by color alone (all badges pair icons with text). Keyboard focusable controls, visible focus rings, and zero serious axe-core violations.

---

## 2. Design Tokens

Defined centrally in `frontend/tailwind.config.js` and `frontend/src/index.css`:

| Category | Token / Value | Purpose |
| :--- | :--- | :--- |
| **Brand Primary** | `indigo` (`#4f46e5` primary, `#4338ca` hover, `#e0e7ff` tint) | Primary interactive actions, active stepper state, key highlights |
| **Neutral Surfaces** | `slate-50` (`#f8fafc`), `slate-100` (`#f1f5f9`), `slate-200` (`#e2e8f0`) | Screen background, card interiors, subtle table zebra stripes |
| **Neutral Text** | `slate-900` (headings), `slate-800` (body), `slate-600` (secondary/labels) | High-contrast readable typography (WCAG AA compliant: ≥ 4.5:1 ratio) |
| **Semantic Success**| `emerald-700` (`#047857`) text, `emerald-50` background, `emerald-200` border | Resolved findings, confirmed mappings, accepted matches |
| **Semantic Warning**| `amber-800` (`#92400e`) text, `amber-50` background, `amber-200` border | Uncertainty disclosures, ambiguous mappings, warnings |
| **Semantic Error**  | `rose-800` (`#9f1239`) text, `rose-50` background, `rose-200` border | Rule violations, conflicting claims, validation errors |
| **Semantic Info**   | `sky-800` (`#075985`) text, `sky-50` background, `sky-200` border | Next steps, instructions, method tags |
| **Monospace Font**  | `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas` | Identifiers, file fields, raw data values |
| **Elevation**       | `shadow-subtle` (`0 1px 2px rgba(0,0,0,0.05)`), `shadow-card` | Clean card depth without heavy drop-shadows |
| **Border Radius**   | `rounded-lg` (8px for controls), `rounded-xl` (12px for cards) | Friendly, modern workbench feel |

---

## 3. Reusable Component Primitives

Located in `frontend/src/components/ui/`:

1. **`Button` (`Button.tsx`)**:
   - Variants: `primary`, `secondary`, `outline`, `destructive`, `success`, `ghost`.
   - Sizes: `xs`, `sm`, `md`, `lg`.
   - Built-in loading state with accessible animated spinner.
   - Text colors exceed 4.5:1 contrast ratio against button backgrounds.

2. **`Badge` & `StatusPill` (`Badge.tsx`)**:
   - `SeverityBadge`: Renders `error`, `warning`, `info` with corresponding icons (`AlertCircle`, `AlertTriangle`, `Info`).
   - `StatusPill`: Displays `open`, `resolved`, `accepted`, `rejected`, `pending` with status glyphs and semantic colors.
   - Never relies on color alone.

3. **`Card` Family (`Card.tsx`)**:
   - `Card`, `CardHeader` (with optional title, subtitle, and action slot), `CardBody`, and `CardFooter`.

4. **`Callout` (`Callout.tsx`)**:
   - Callout panels for `info`, `warning`, `error`, and `success`.
   - Used for the required **Uncertainty Disclosure** and validation notices.

5. **`Stepper` (`Stepper.tsx`)**:
   - Horizontal workflow stepper: `1. Upload files` → `2. Map columns` → `3. Validation issues` → `4. Findings` → `5. Match candidates` → `6. Export`.
   - States: `done`, `current`, `upcoming`, `blocked`.
   - Displays tooltips explaining exact prerequisites when a step is blocked.

6. **`EmptyState` (`EmptyState.tsx`)**:
   - Clean empty states with icon, heading, explanatory copy, and optional action.
   - Findings empty state explicitly warns: *"No findings. This does not prove the records are correct."*

7. **`MonospaceValue` & `KeyValueRow` (`KeyValue.tsx`)**:
   - Formatted value display with an integrated one-click copy-to-clipboard button.

8. **`Toast` (`Toast.tsx`)**:
   - Accessible toast notification system via `ToastProvider` and `useToast` hook.
   - Confirms review submissions, uploads, and analysis runs.

---

## 4. Screen-by-Screen Enhancements

### 1. App Shell
- Sticky dark header (`bg-slate-900`) with SoundDue logo and badge: *"Audit Workbench — Explainable Music-Record Reconciliation"*.
- Visible **"Fictional demo data"** chip (`bg-amber-500/10 text-amber-300`).
- Active Case breadcrumb with one-click return to case list.
- Persistent footer banner: *"Findings are leads for human review, not ownership determinations."*

### 2. Workspace Stepper & Navigation
- Interactive 6-step workflow stepper reflecting completion status.
- Primary **Analyze** action in header with status indicator.
- Gated navigation preventing out-of-order execution before files are uploaded.

### 3. File Upload & Staging
- Drag-and-drop file dropzone accepting `.csv`, `.xlsx`, `.xls`.
- Chip selectors for file kinds: `recordings`, `works`, `ownership`, `mappings`.
- Staged file list with per-file kind modification and delete button.
- Preview tables with sticky headers displaying detected columns and sample rows.
- Schema issue count pills on each file.

### 4. Column Mapping Section
- Table mapping each source column to suggested canonical fields.
- Confidence indicators (`high`, `medium`, `low`) with color coding.
- Suggestion method indicators (`exact`, `fuzzy`, `synonym`).
- Warning callout for ambiguous mappings.
- "Confirm mappings" button updating the case status.

### 5. Validation Issues
- Tabular display of schema and data errors across all uploaded files.
- Monospace row and column coordinates.
- "Errors only" toggle to filter out benign warnings.
- Content rule: Replaces any raw "unclaimed" text with *"missing from the supplied records"*.

### 6. Findings Section (Audit Dashboard)
- Summary KPI banner: Total Findings, Open for Review, Resolved, and Errors.
- Live search filter (searching across summary, finding type, or rule ID).
- Multi-select dropdown filters for Rule (`R1`, `R2`, `R3`, `R4`) and Status (`open`, `resolved`, `rejected`).
- Responsive TanStack table with row click navigation to Finding Detail.
- "Rerun analysis" button with change indicators.

### 7. Finding Detail (Hero Screen — 2-Column Audit Workbench)
- **Header**: Finding title, severity badge, status pill, and rule version badge.
- **Left Column ("Why this was flagged")**:
  1. **Issue**: Summary and finding type badge.
  2. **Evidence**: Formatted table of file / sheet / row / field / value with copy buttons.
  3. **Rule**: Symbolic rule trace checklist of matched conditions and supporting record jump-links.
  4. **Uncertainty**: Prominent amber callout ensuring limitations are never missed.
  5. **Next Step**: Actionable procedural recommendation.
  6. **Review History**: Vertical audit timeline with auditor name, timestamp, decision pill, and note.
- **Right Column**:
  - **Conflicting Records Comparison**: Side-by-side view (Source A vs Source B) with difference markers (`≠`) on discrepancies.
  - **Review Action Card**: Form for `Accept`, `Reject` (with notice: *"This rejection will persist across reruns"*), and `Correct record` (with field-level input overrides and required reviewer note).

### 8. Rerun Diff Panel
- Category filter buttons: **Resolved**, **New**, **Changed**, **Unchanged**, **Rejected** with exact counts.
- Highlights why findings changed and displays historical audit decisions.

### 9. Match Candidates
- Cards for fuzzy match pairs with per-field match breakdown: composite score, title similarity, contributor/performer similarity, and duration difference.
- One-click Accept / Reject actions with immediate candidate status updates.

### 10. Export Panel
- 3 export format cards (HTML Report, CSV Spreadsheet, JSON Evidence Payload) with descriptions and direct download triggers.

---

## 5. Accessibility Audit (Axe-Core)

An automated axe-core test suite (`frontend/e2e/accessibility.spec.ts`) verifies WCAG 2.1 AA compliance on both the **Findings List** and **Finding Detail** screens:
- **Findings list violations**: 0 serious, 0 critical.
- **Finding detail violations**: 0 serious, 0 critical.
- **Contrast**: All text and form elements pass ≥ 4.5:1 ratio against background surfaces.
- **Forms**: All inputs and select elements have explicit `aria-label` or `<label>` attributes.
- **Keyboard Navigation**: All interactive elements have visible focus rings (`outline: 2px solid #6366f1; outline-offset: 2px`).

---

## 6. Intentional Shortcuts & Trade-offs

1. **Client-side Diff Correlation**:
   The backend `/cases/{id}/rerun` returns a snapshot diff of findings that currently match or no longer match rule criteria. If a finding was manually marked as `resolved` during review, the client enriches the diff with the previous finding history to ensure the reviewer sees their manual resolution in the **Resolved** tab.
2. **Simplified User Authentication**:
   The audit reviewer is hardcoded to `'demo-user'` for prototype simplicity.
3. **No Heavy UI Component Libraries**:
   To keep bundle size light and avoid dependency lock-in, all components are built using pure Tailwind CSS, TanStack Table v9, and `lucide-react` icons (no Material UI, Shadcn CLI, or Ant Design).

---

## 7. API Gaps Identified

1. **Files List Endpoint for Case Reload**:
   The backend provides `POST /cases/{id}/files` and `GET /files/{id}/preview`, but lacks a dedicated `GET /cases/{id}/files` endpoint to retrieve previously uploaded file metadata when re-opening a case in a new session.
   *Workaround*: The frontend uses `case_.file_count` to detect existing files and unlock stepper tabs.
2. **Rule Trace Missing Information Type**:
   In some backend rules (e.g. R1), `rule_trace.missing_information` is returned as a list of strings (`["..."]`) while in others it is a string. The frontend's `sanitise()` utility normalizes arrays and strings transparently.
