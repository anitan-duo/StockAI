import { test, expect } from '@playwright/test';

/** §15 horizon honesty: the UI must never promise 1w/1m model forecasts. */
test.describe('prediction horizon honesty', () => {
  test('stock page offers only the 1-day model horizon', async ({ page }) => {
    await page.goto('/stocks/AAPL?exchange=NASDAQ');
    await expect(page.locator('body')).toContainText(/bars •/, { timeout: 30000 });
    await expect(page.locator('body')).toContainText(/next trading day/i);
    await expect(page.locator('body')).not.toContainText(/next 1 week|next 1 month/i);
  });

  test('predictions page is 1D-only', async ({ page }) => {
    await page.goto('/predictions');
    await expect(page.locator('body')).toContainText(/next trading day/i, { timeout: 30000 });
    await expect(page.locator('body')).not.toContainText(/1W — Next week|1M — Next month/i);
  });

  test('prediction cards show model age, never timeless forecasts', async ({ page }) => {
    await page.goto('/predictions');
    await expect(page.locator('body')).toContainText(/as of/, { timeout: 30000 });
  });
});
