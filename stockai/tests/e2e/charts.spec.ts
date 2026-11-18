import { test, expect } from '@playwright/test';

/**
 * Chart flows: real backend history rendered through every visualization
 * mode. Fails honestly (UNAVAILABLE/empty states) rather than hanging.
 */
test.describe('StockAI charts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/stocks/AAPL?exchange=NASDAQ');
    // Chart footer proves backend bars arrived and were mapped.
    await expect(page.locator('body')).toContainText(/bars •/, { timeout: 30000 });
  });

  test('candlestick renders real OHLC canvas, no fabrications', async ({ page }) => {
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15000 });
    const text = (await page.locator('body').innerText()) || '';
    // Standalone NaN values (not the substring in "financial").
    expect(text).not.toMatch(/\bNaN\b/);
    expect(text.toLowerCase()).not.toContain('undefined error');
  });

  test('chart-type switching preserves data (no reload of values)', async ({ page }) => {
    const footer = () => page.locator('text=/\\d+ bars •/');
    const before = await footer().first().innerText();
    for (const name of ['OHLC', 'Line', 'Area', 'Baseline', 'Candles']) {
      await page.getByRole('button', { name, exact: true }).click();
      await expect(footer().first()).toContainText(/bars •/);
    }
    const after = await footer().first().innerText();
    // Same bar count across all types: switching never changes the data.
    expect(after.split('bars')[0]).toBe(before.split('bars')[0]);
  });

  test('timeframe switching returns plausible ranges', async ({ page }) => {
    for (const tf of ['5D', '1Y', 'MAX']) {
      await page.getByRole('button', { name: tf, exact: true }).click();
      await expect(page.locator('body')).toContainText(/bars •/, { timeout: 30000 });
    }
    const text = (await page.locator('body').innerText()) || '';
    expect(text).not.toMatch(/2001|1999|1970/);
  });

  test('overlays, oscillator pane, percent view and fullscreen', async ({ page }) => {
    // Overlay toggle
    await page.getByText('SMA 50', { exact: false }).first().click().catch(() => {});
    // Oscillator sub-pane
    const rsi = page.getByText('RSI', { exact: true });
    if (await rsi.count()) await rsi.first().click();
    await expect(page.locator('body')).toContainText(/bars •/);
    // Percent view
    const pct = page.getByText('%-change view');
    if (await pct.count()) await pct.click();
    await expect(page.locator('body')).toContainText(/bars •/);
    // Fullscreen open + esc close
    await page.getByRole('button', { name: /expand/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10000 });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 10000 });
  });

  test('unknown symbol fails honestly', async ({ page }) => {
    await page.goto('/stocks/NOPEZZZ?exchange=NASDAQ');
    await expect(page.locator('body')).toContainText(/no quote available|unable to load|not found|unavailable/i, {
      timeout: 30000,
    });
  });
});
