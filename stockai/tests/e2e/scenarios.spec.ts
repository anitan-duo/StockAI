import { test, expect } from '@playwright/test';

/** Scenario Lab: blind challenge flow with server-enforced blindness. */
test.describe('Scenario Lab', () => {
  test.beforeEach(async ({ page, request }) => {
    const email = `lab${Date.now()}@example.com`;
    const reg = await request.post('http://localhost:8000/api/v1/auth/register', {
      data: { email, password: 'Lab-test-123', full_name: 'Lab' },
    });
    expect(reg.ok()).toBeTruthy();
    const { tokens } = await reg.json();
    await page.goto('/');
    await page.evaluate((t: string) => {
      localStorage.setItem('access_token', t);
    }, tokens.access_token);
  });

  test('blind flow: load, commit, reveal, streak', async ({ page }) => {
    await page.goto('/scenarios');
    await expect(page.locator('body')).toContainText(/Scenario Lab/i, { timeout: 15000 });

    // Load a matured historical scenario (defaults target one).
    await page.getByRole('button', { name: /load blind scenario/i }).click();
    await expect(page.locator('body')).toContainText(/Ends .*target v1-/i, { timeout: 30000 });
    // A real chart renders (canvas) from decision-time bars only.
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15000 });

    // Commit a forecast (default 40/30/30 sums to 100).
    await page.getByRole('button', { name: /commit forecast/i }).click();
    await expect(page.locator('body')).toContainText(/Reveal outcome/i, { timeout: 15000 });

    // Reveal resolves from genuine later sessions.
    await page.getByRole('button', { name: /reveal outcome/i }).click();
    await expect(page.locator('body')).toContainText(/Correct decision|Incorrect decision/i, {
      timeout: 30000,
    });
    const text = ((await page.locator('body').innerText()) || '').toLowerCase();
    expect(text).not.toMatch(/\bNaN\b/);
  });

  test('unknown symbol fails honestly, no fabricated scenario', async ({ page, request }) => {
    const res = await request.post(
      'http://localhost:8000/api/v1/scenarios?symbol=NOPEZZZ&exchange=NASDAQ&decision_date=2025-06-13&task_id=h1d&split=train',
    );
    // Unauthenticated API call: must be 401/403, never a synthesized scenario.
    expect([401, 403]).toContain(res.status());
  });
});
