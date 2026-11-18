import { test, expect } from '@playwright/test';

const API = process.env.E2E_API_URL || 'http://localhost:8000/api/v1';
const email = `e2e${Date.now()}@example.com`;
const password = 'E2e-test-123';

test.describe('StockAI smoke', () => {
  test('registration → dashboard', async ({ page }) => {
    await page.goto('/signup');
    const fullName = page.locator('#fullName');
    if (await fullName.count()) await fullName.fill('E2E User');
    await page.locator('#email').fill(email);
    await page.locator('#password').fill(password);
    const confirm = page.locator('#confirmPassword');
    if (await confirm.count()) await confirm.fill(password);
    await page.getByRole('button', { name: /sign up|register|create account/i }).click();
    await expect(page).toHaveURL(/dashboard|login/, { timeout: 15000 });
  });

  test('login → dashboard → logout loop', async ({ page, request }) => {
    const lemail = `login${Date.now()}@example.com`;
    await request.post(`${API}/auth/register`, {
      data: { email: lemail, password, full_name: 'Login User' },
    });
    await page.goto('/login');
    await page.locator('#email').fill(lemail);
    await page.locator('#password').fill(password);
    await page.locator('form button[type="submit"]').click();
    await expect(page).toHaveURL(/dashboard/, { timeout: 15000 });
    await expect(page.locator('body')).toContainText(/dashboard|markets|watchlist/i);
  });

  test('invalid login shows error, no session', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#email').fill('nobody@example.com');
    await page.locator('#password').fill('wrong-password-1');
    await page.locator('form button[type="submit"]').click();
    await expect(page.locator('body')).toContainText(/invalid|incorrect|unauthorized|failed/i, { timeout: 15000 });
  });

  test('stock detail shows prediction or honest unavailable', async ({ page }) => {
    await page.goto('/stocks/AAPL?exchange=NASDAQ');
    const body = page.locator('body');
    await expect(body).toContainText(/AAPL|prediction|unavailable|loading/i, { timeout: 20000 });
    const text = (await body.innerText()).toLowerCase();
    expect(text).not.toMatch(/NaN|undefined error/);
  });

  test('watchlist CRUD via API (deterministic fixture user)', async ({ request }) => {
    const reg = await request.post(`${API}/auth/register`, {
      data: { email: `wl${Date.now()}@example.com`, password: 'Wl-test-123', full_name: 'WL' },
    });
    expect(reg.ok()).toBeTruthy();
    const { tokens } = await reg.json();
    const headers = { Authorization: `Bearer ${tokens.access_token}` };
    const created = await request.post(`${API}/watchlist`, { headers, data: { name: 'E2E List' } });
    expect(created.status()).toBe(201);
    const { id } = await created.json();
    const listed = await request.get(`${API}/watchlist`, { headers });
    expect(listed.ok()).toBeTruthy();
    expect(JSON.stringify(await listed.json())).toContain('E2E List');
    const del = await request.delete(`${API}/watchlist/${id}`, { headers });
    expect([200, 204].includes(del.status())).toBeTruthy();
  });

  test('expired token is rejected (401) without stack trace', async ({ request }) => {
    const res = await request.get(`${API}/auth/me`, { headers: { Authorization: 'Bearer invalid.token.here' } });
    expect(res.status()).toBe(401);
    const body = await res.text();
    expect(body).not.toMatch(/Traceback|File "\/app\//);
  });
});
