import { test, expect } from "@playwright/test";
import path from "node:path";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const API_URL = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";
const SCREENSHOTS = path.resolve(process.cwd(), "../../docs/screenshots/brand-ui");

for (const viewport of [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
]) {
  test(`login visual — ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`${BASE_URL}/login`);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await page.waitForTimeout(450);
    await page.screenshot({
      path: path.join(SCREENSHOTS, `login-${viewport.width}.png`),
      fullPage: true,
    });
  });
}

test("wrong password exposes an accessible inline error", async ({ page }) => {
  const email = `returning-${Date.now()}@example.com`;
  const password = "LaunchReady!2026";
  const registration = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "Returning Operator" }),
  });
  expect(registration.ok).toBeTruthy();

  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("Incorrect!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOTS, "wrong-password.png"), fullPage: true });
});

test("expired or malformed session redirects gracefully", async ({ context, page }) => {
  await context.addCookies([{
    name: "heliox_session",
    value: "expired.session.token",
    url: BASE_URL,
    httpOnly: true,
    sameSite: "Lax",
  }]);
  await page.goto(`${BASE_URL}/`);
  await expect(page).toHaveURL(/\/login\?redirect=%2F/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("signup validation and long input remain usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${BASE_URL}/signup`);
  await page.getByLabel("Full name").fill("A".repeat(140));
  await page.getByLabel("Work email").fill("not-an-email");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await page.getByLabel("Confirm password").fill("different");
  await page.getByLabel("Confirm password").blur();
  await expect(page.getByText("Passwords do not match.")).toBeVisible();
  await expect(page.getByText("Enter a valid work email.")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOTS, "signup-validation-mobile.png"), fullPage: true });
});
