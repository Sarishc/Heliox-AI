import { test, expect } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const API_URL = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";

test.describe("Auth and Dashboard E2E", () => {
  const testEmail = `e2e-${Date.now()}@example.com`;
  const testPassword = "TestPassword123!";
  const testName = "E2E Test User";

  test("signup -> login -> create tenant -> load dashboard -> logout", async ({
    page,
    context,
  }) => {
    // 1. Signup
    await page.goto(`${BASE_URL}/signup`);
    await page.fill('input[placeholder="Full name"]', testName);
    await page.fill('input[placeholder="Email"]', testEmail);
    await page.fill('input[placeholder="Password (min 8 chars)"]', testPassword);
    await page.click('button:has-text("Create account")');
    await expect(page).toHaveURL(/\/(onboarding|\?|$)/, { timeout: 10000 });

    // 2. Onboarding (create team) - if redirected to onboarding
    const url = page.url();
    if (url.includes("/onboarding")) {
      await page.fill('input[placeholder="My Team"]', "E2E Test Team");
      await page.click('button:has-text("Create team")');
      // API key modal may appear - click "Continue without copying" or "Copy and continue"
      const modalBtn = page.getByRole("button", { name: /Continue without copying|Copy and continue/ });
      await modalBtn.click({ timeout: 8000 }).catch(() => {});
      await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 5000 });
    }

    // 3. Dashboard loads
    await page.goto(`${BASE_URL}/`);
    await expect(page.locator("text=Executive Overview").or(page.locator("text=Cost Trends"))).toBeVisible({
      timeout: 15000,
    });

    // 4. Charts or content visible
    const hasCharts = await page.locator('[class*="recharts"]').count() > 0;
    const hasContent = await page.locator("main").isVisible();
    expect(hasCharts || hasContent).toBeTruthy();

    // 5. Logout - click user avatar (gradient circle) then Log out
    await page.locator('button:has(div.rounded-full.bg-gradient-to-br)').first().click();
    await page.click('button:has-text("Log out")');
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  });

  test("login with existing user", async ({ page }) => {
    // Create user first via API
    const res = await fetch(`${API_URL}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: `login-${Date.now()}@example.com`,
        password: "TestPassword123!",
        full_name: "Login Test",
      }),
    });
    expect(res.ok).toBeTruthy();

    const email = (await res.json()).email;

    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[placeholder="Email"]', email);
    await page.fill('input[placeholder="Password"]', "TestPassword123!");
    await page.click('button:has-text("Login with Email")');

    await expect(page).toHaveURL(/\/(onboarding|\/)/, { timeout: 10000 });
  });
});
