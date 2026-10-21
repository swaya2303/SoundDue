import { chromium } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outDir = path.resolve(__dirname, '../../docs/screenshots');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  console.log('Navigating to http://localhost:5173...');
  await page.goto('http://localhost:5173');
  await page.waitForTimeout(1000);

  // 1. Case list
  console.log('Capturing 01-case-list...');
  await page.screenshot({ path: path.join(outDir, 'before-01-case-list.png'), fullPage: true });

  // Open "Midnight Train Demo" specifically
  const demoRow = page.locator('tr', { hasText: 'Midnight Train Demo' }).first();
  if (await demoRow.count() > 0) {
    await demoRow.getByRole('button', { name: /Open/i }).click();
  } else {
    await page.getByRole('button', { name: /Open/i }).first().click();
  }
  await page.waitForTimeout(1000);

  // 2. Upload tab
  console.log('Capturing 02-upload...');
  await page.screenshot({ path: path.join(outDir, 'before-02-upload.png'), fullPage: true });

  // 3. Mapping tab
  console.log('Capturing 03-mapping...');
  await page.getByRole('button', { name: /Map columns/i }).click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(outDir, 'before-03-mapping.png'), fullPage: true });

  // 4. Findings list
  console.log('Capturing 04-findings-list...');
  await page.getByRole('button', { name: /Findings/i }).click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(outDir, 'before-04-findings-list.png'), fullPage: true });

  // 5. Finding detail
  console.log('Capturing 05-finding-detail...');
  const viewBtn = page.getByRole('button', { name: /View/i }).first();
  await viewBtn.waitFor({ state: 'visible', timeout: 5000 });
  await viewBtn.click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(outDir, 'before-05-finding-detail.png'), fullPage: true });

  // Back to findings
  await page.getByRole('button', { name: /Back to findings/i }).click();
  await page.waitForTimeout(500);

  // 6. Rerun diff
  console.log('Capturing 06-rerun-diff...');
  const rerunBtn = page.getByRole('button', { name: /Rerun/i });
  await rerunBtn.click();
  await page.waitForTimeout(500);
  const runNowBtn = page.getByRole('button', { name: /Run now/i });
  if (await runNowBtn.count() > 0) {
    await runNowBtn.click();
    await page.waitForTimeout(2000);
  }
  await page.screenshot({ path: path.join(outDir, 'before-06-rerun-diff.png'), fullPage: true });

  await browser.close();
  console.log('Done capturing all 6 before screenshots.');
}

run().catch((err) => {
  console.error('Error:', err);
  process.exit(1);
});
