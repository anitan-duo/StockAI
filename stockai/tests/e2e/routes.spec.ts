import { test, expect } from '@playwright/test';

/** Every primary route must load without JS crashes or blank screens. */
const ROUTES = [
  '/dashboard',
  '/markets',
  '/predictions',
  '/screener',
  '/watchlist',
  '/alerts',
  '/backtesting',
  '/mlops',
  '/analytics',
  '/scenarios',
  '/research',
  '/settings',
];

for (const route of ROUTES) {
  test(`route ${route} loads without page errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
    await page.goto(route);
    await page.waitForTimeout(5000);
    // Not blank: some real heading or content must render.
    const text = ((await page.locator('body').innerText()) || '').trim();
    expect(text.length).toBeGreaterThan(50);
    expect(errors, `pageerrors on ${route}: ${errors.join(' | ')}`).toEqual([]);
  });
}
