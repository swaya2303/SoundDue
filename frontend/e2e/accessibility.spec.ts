import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility Audits (WCAG AA)', () => {
  test('Findings list and Finding detail pages meet WCAG AA standards', async ({ page }) => {
    // 1. Navigate to case list
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('SoundDue');

    // 2. Open Midnight Train Demo case which has findings
    const row = page.locator('tr', { hasText: /Midnight Train/i }).first();
    await row.getByRole('button', { name: /Open/i }).click();

    // 3. Navigate to Findings tab
    const findingsTabBtn = page.getByRole('button', { name: /Findings/i });
    await findingsTabBtn.click();
    await page.waitForTimeout(1000);

    // Axe audit on Findings list
    const findingsListScan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const seriousViolationsList = findingsListScan.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );

    console.log('Findings list serious/critical violations count:', seriousViolationsList.length);
    if (seriousViolationsList.length > 0) {
      console.log('Violations on Findings List:', JSON.stringify(seriousViolationsList, null, 2));
    }
    expect(seriousViolationsList).toEqual([]);

    // 4. Click View on the first finding to open Finding Detail (the hero page)
    const viewBtn = page.getByRole('button', { name: /View/i }).first();
    await viewBtn.click();
    await expect(page.getByText('Why this was flagged')).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(500);

    // Axe audit on Finding Detail page
    const findingDetailScan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const seriousViolationsDetail = findingDetailScan.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );

    console.log('Finding detail serious/critical violations count:', seriousViolationsDetail.length);
    if (seriousViolationsDetail.length > 0) {
      console.log('Violations on Finding Detail:', JSON.stringify(seriousViolationsDetail, null, 2));
    }
    expect(seriousViolationsDetail).toEqual([]);
  });
});
