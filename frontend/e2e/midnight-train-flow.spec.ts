/**
 * e2e/midnight-train-flow.spec.ts
 * ================================
 * Smoke test: R1 finding → correct → rerun → resolved.
 *
 * Single-test end-to-end flow; state is shared within the test via
 * page navigation. Each "step" is logged with test.step().
 *
 * Prerequisites:
 *   - Backend  : http://localhost:8000  (uvicorn)
 *   - Frontend : http://localhost:5173  (vite)
 */

import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __e2eDir = path.dirname(__filename);

const SYNTHETIC = path.resolve(
  __e2eDir,
  '../../data/synthetic/scenario_01_midnight_train_unclaimed',
);

const CASE_NAME = `Smoke-${Date.now()}`;

test.setTimeout(180_000);

test('Midnight Train: create → upload → map → analyze → correct → rerun → resolved', async ({ page }) => {

  // ── Step 1: Create case ────────────────────────────────────────────────
  await test.step('create case', async () => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('SoundDue');
    await page.fill('input[placeholder*="Midnight"]', CASE_NAME);
    await page.getByRole('button', { name: 'Create Case' }).click();
    await expect(page.getByText(CASE_NAME).first()).toBeVisible({ timeout: 8000 });
  });

  // ── Step 2: Open case ──────────────────────────────────────────────────
  await test.step('open case', async () => {
    const row = page.locator('tr', { hasText: CASE_NAME }).first();
    await row.getByRole('button', { name: /Open/i }).click();
    await expect(page.getByText('1. Upload files')).toBeVisible({ timeout: 8000 });
  });

  // ── Step 3: Upload files ───────────────────────────────────────────────
  await test.step('upload four Midnight Train CSV files', async () => {
    const uploads = [
      { name: 'recordings.csv', kind: 'recordings' },
      { name: 'ownership.csv',  kind: 'ownership'  },
      { name: 'works.csv',      kind: 'works'       },
      { name: 'mappings.csv',   kind: 'mappings'    },
    ];

    for (const f of uploads) {
      // Set the kind dropdown first — the first <select> is the file-kind dropdown
      await page.locator('select').first().selectOption(f.kind);
      // Let React commit the state update for defaultKind
      await page.waitForTimeout(300);

      // Trigger file input (hidden behind label) — fires React onChange → setStaged
      await page.locator('input[type="file"]').setInputFiles(
        path.join(SYNTHETIC, f.name),
      );

      // Wait for the staged file entry to appear (the upload button becomes visible)
      const uploadBtn = page.locator('[data-testid="upload-submit-btn"]');
      await expect(uploadBtn).toBeVisible({ timeout: 8000 });

      // Extra safety: wait for button text to confirm staged state is reflected
      await expect(uploadBtn).toContainText('Upload', { timeout: 5000 });

      await uploadBtn.click();

      // Wait for the preview card (file name appears in the uploaded entries section)
      await expect(page.getByText(f.name).first()).toBeVisible({ timeout: 15_000 });

      // Wait for uploading state to clear before next iteration
      await expect(uploadBtn).not.toBeVisible({ timeout: 8000 });
    }

    // After all uploads the Analyze button should be enabled
    // (gate: uploadedFiles.length > 0, no mapping confirmation required)
    await expect(page.getByRole('button', { name: 'Analyze' })).toBeEnabled({ timeout: 8000 });
  });

  // ── Step 4: Confirm mappings ───────────────────────────────────────────
  await test.step('confirm column mappings', async () => {
    await page.getByRole('button', { name: '2. Map columns' }).click();
    await page.waitForTimeout(1500);

    // Click any panels that still need confirming (idempotent if already done)
    const btns = await page.getByRole('button', { name: 'Confirm mappings' }).all();
    for (const btn of btns) {
      if (await btn.isVisible()) {
        await btn.click();
        await page.waitForTimeout(400);
      }
    }

    // Analyze must remain enabled (mapping step is advisory)
    await expect(page.getByRole('button', { name: 'Analyze' })).toBeEnabled({ timeout: 5000 });
  });

  // ── Step 5: Analyze ────────────────────────────────────────────────────
  await test.step('run Analyze', async () => {
    const analyzeBtn = page.getByRole('button', { name: 'Analyze' });
    await expect(analyzeBtn).toBeEnabled({ timeout: 8000 });
    await analyzeBtn.click();

    // Auto-switches to Findings, at least one row
    await expect(page.getByText('4. Findings')).toBeVisible();
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 15_000 });
  });

  // ── Step 6: Finding detail — six sections ─────────────────────────────
  await test.step('open finding detail — six sections visible', async () => {
    // Use the explicit "View →" button rather than row click
    await page.getByRole('button', { name: /View/ }).first().click();
    await page.waitForTimeout(800);

    // Sections render uppercase in the DOM (via .toUpperCase() in Section component)
    for (const s of ['ISSUE', 'EVIDENCE', 'RULE', 'UNCERTAINTY', 'NEXT STEP', 'REVIEW HISTORY']) {
      await expect(page.getByText(s, { exact: true })).toBeVisible({ timeout: 8000 });
    }
    await expect(page.getByRole('button', { name: 'Accept' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reject' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Correct record' })).toBeVisible();
    await expect(page.getByText(/leads for human review/i)).toBeVisible();
  });

  // ── Step 7: Correct the finding ────────────────────────────────────────
  await test.step('correct the record', async () => {
    await page.getByRole('button', { name: 'Correct record' }).click();
    // Visible hint text that appears when correction form opens
    await expect(page.getByText('Explain what was incorrect')).toBeVisible({ timeout: 5000 });

    // Add a correction field
    await page.fill('input[placeholder="field name"]', 'share_status');
    await page.fill('input[placeholder="corrected value"]', 'claimed');
    await page.getByRole('button', { name: 'Add' }).click();
    await expect(page.getByText('share_status')).toBeVisible();

    // Required note — only one textarea when correction form is open
    await page.fill('textarea', 'Registration confirmed — share is now claimed.');

    await page.getByRole('button', { name: 'Confirm' }).click();
    await expect(page.getByText(/Decision recorded/i)).toBeVisible({ timeout: 8000 });

    // Status badge shows resolved on the detail page
    await expect(page.getByText('resolved').first()).toBeVisible({ timeout: 6000 });
  });

  // ── Step 8: Rerun ──────────────────────────────────────────────────────
  await test.step('rerun — finding appears under Resolved', async () => {
    // Back to findings list
    await page.getByRole('button', { name: '← Back to findings' }).click();
    await page.waitForTimeout(500);

    // Click ↻ Rerun
    await page.getByRole('button', { name: '↻ Rerun' }).click();
    await expect(page.getByText('Rerun analysis')).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: '↻ Run now' }).click();

    // Wait for diff results
    await expect(page.getByText(/✓ Resolved/)).toBeVisible({ timeout: 25_000 });

    // Resolved count ≥ 1
    const resolvedPill = page.locator('div', { hasText: /✓ Resolved:/ }).first();
    await expect(resolvedPill).toBeVisible();
    const txt = await resolvedPill.textContent() ?? '';
    const n = parseInt(txt.match(/Resolved:\s*(\d+)/)?.[1] ?? '0', 10);
    expect(n).toBeGreaterThanOrEqual(1);
  });
});
