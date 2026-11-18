import { test } from '@playwright/test';

/** Visual QA captures (not assertions) — reviewed by the engineer. */
test.describe('visual QA', () => {
  test('dashboard desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard');
    await page.waitForTimeout(4000);
    await page.screenshot({ path: 'test-results/qa-dashboard.png' });
  });

  test('stock candlestick desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/stocks/AAPL?exchange=NASDAQ');
    await page.waitForTimeout(6000);
    await page.screenshot({ path: 'test-results/qa-stock.png', fullPage: false });
  });

  test('stock mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/stocks/AAPL?exchange=NASDAQ');
    await page.waitForTimeout(6000);
    await page.screenshot({ path: 'test-results/qa-stock-mobile.png' });
  });

  test('markets desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/markets');
    await page.waitForTimeout(4000);
    await page.screenshot({ path: 'test-results/qa-markets.png' });
  });
});
