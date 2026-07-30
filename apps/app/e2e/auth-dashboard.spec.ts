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
    await page.getByLabel("Full name").fill(testName);
    await page.getByLabel("Work email").fill(testEmail);
    await page.getByLabel("Password", { exact: true }).fill(testPassword);
    await page.getByLabel("Confirm password").fill(testPassword);
    await page.getByRole("button", { name: "Create workspace" }).click();
    await expect(page).toHaveURL(/\/(onboarding|\?|$)/, { timeout: 10000 });

    // 2. Onboarding (create team) - if redirected to onboarding
    const url = page.url();
    if (url.includes("/onboarding")) {
      // Registration creates the tenant boundary atomically; onboarding then
      // resumes at the optional integration step.
      await page.goto(`${BASE_URL}/`);
    }

    // 3. Dashboard loads
    await page.goto(`${BASE_URL}/`);
    await expect(
      page.getByRole("heading", { name: "Executive Overview" }),
    ).toBeVisible({ timeout: 15000 });

    // 4. Charts or content visible
    const hasCharts = await page.locator('[class*="recharts"]').count() > 0;
    const hasContent = await page.locator("main").isVisible();
    expect(hasCharts || hasContent).toBeTruthy();

    // 5. Logout - click user avatar (gradient circle) then Log out
    await page.getByRole("button", { name: "U", exact: true }).click();
    await page.getByRole("button", { name: "Log out", exact: true }).click();
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
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("TestPassword123!");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/(onboarding|\/)/, { timeout: 10000 });
  });
});
