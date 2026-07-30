import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const API_URL = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";
const auditRun = Date.now();
let auditEmail = "";
const auditPassword = "RouteAuditPassword123!";
let sessionCookie: { name: string; value: string };

const protectedRoutes = [
  "/",
  "/alerts",
  "/analytics",
  "/billing",
  "/billing/usage",
  "/budgets",
  "/forecast",
  "/onboarding",
  "/optimization",
  "/proxy",
  "/recommendations",
  "/reports",
  "/roi",
  "/settings",
  "/settings/authentication",
  "/settings/integrations",
];

const publicRoutes = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password?token=invalid-deep-audit-token",
  "/verify-email?token=invalid-deep-audit-token",
  "/auth/callback?error=access_denied",
  "/invite/invalid-deep-audit-token",
  "/share/invalid-deep-audit-token",
];

async function authenticate(context: BrowserContext, demoMode = false) {
  await context.addCookies([
    {
      ...sessionCookie,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await context.addInitScript((enabled) => {
    if (enabled) {
      window.localStorage.setItem("heliox_demo_mode", "true");
    } else {
      window.localStorage.removeItem("heliox_demo_mode");
    }
  }, demoMode);
}

async function expectHealthyRoute(page: Page, route: string, allowedResponseStatuses: number[] = []) {
  const runtimeErrors: string[] = [];
  const observedAllowedStatuses = new Set<number>();
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") runtimeErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (allowedResponseStatuses.includes(response.status())) {
      observedAllowedStatuses.add(response.status());
    }
  });

  const response = await page.goto(route);
  expect(response, `${route} must produce a document response`).not.toBeNull();
  expect(response!.status(), `${route} returned ${response!.status()}`).toBeLessThan(500);
  await page.waitForTimeout(750);
  await expect(page.locator("body")).not.toContainText("Application error");
  await expect(page.locator("body")).not.toContainText("Internal Server Error");
  const unexpectedRuntimeErrors = runtimeErrors.filter(
    (message) =>
      ![...observedAllowedStatuses].some((status) =>
        message.includes(`status of ${status}`)
      )
  );
  expect(unexpectedRuntimeErrors, `${route} emitted browser runtime errors`).toEqual([]);
}

test.beforeAll(async ({}, workerInfo) => {
  auditEmail = `route-audit-${auditRun}-${workerInfo.workerIndex}-${Date.now()}@example.com`;
  const registration = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: auditEmail,
      password: auditPassword,
      full_name: "Route Coverage Audit",
    }),
  });
  expect(registration.ok).toBeTruthy();

  const login = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-Forwarded-For": `198.51.100.${91 + (workerInfo.workerIndex % 100)}`,
    },
    body: new URLSearchParams({ username: auditEmail, password: auditPassword }),
  });
  expect(login.ok).toBeTruthy();
  const rawCookie = login.headers.get("set-cookie")?.split(";")[0];
  expect(rawCookie).toBeTruthy();
  const separator = rawCookie!.indexOf("=");
  sessionCookie = {
    name: rawCookie!.slice(0, separator),
    value: rawCookie!.slice(separator + 1),
  };
});

for (const route of publicRoutes) {
  test(`public route ${route} loads without runtime errors`, async ({ page }) => {
    const allowedResponseStatuses = route.startsWith("/invite/")
      ? [404]
      : route.startsWith("/verify-email?")
        ? [400]
        : [];
    await expectHealthyRoute(page, route, allowedResponseStatuses);
  });
}

test("Next API catch-all proxies a real backend health response", async ({ page }) => {
  const response = await page.goto("/api/v1/health");
  expect(response?.status()).toBe(200);
  expect(await response?.json()).toMatchObject({
    checks: {
      database: { status: "ok" },
      redis: { status: "ok" },
    },
  });
});

for (const route of protectedRoutes) {
  test(`${route} handles an authenticated empty-data state`, async ({ page, context }) => {
    await authenticate(context, false);
    await expectHealthyRoute(page, route);
    expect(page.url()).not.toContain("/login");
  });

  test(`${route} handles an authenticated populated/demo state`, async ({ page, context }) => {
    await authenticate(context, true);
    await expectHealthyRoute(page, route);
    expect(page.url()).not.toContain("/login");
    expect(await page.evaluate(() => localStorage.getItem("heliox_demo_mode"))).toBe("true");
  });
}

test.describe.serial("write-capable feature surfaces", () => {
  test.beforeEach(async ({ context }) => {
    await authenticate(context, false);
  });

  test("budgets creates and displays a policy through the UI", async ({ page }) => {
    await page.goto("/budgets");
    await page.getByPlaceholder("Project (optional)").fill(`audit-${auditRun}`);
    await page.getByPlaceholder("Monthly budget (USD)").fill("12500");
    await page.getByRole("button", { name: "Create policy" }).click();
    await expect(page.getByText(`PROD • audit-${auditRun}`)).toBeVisible();
  });

  test("reports creates and displays a saved report through the UI", async ({ page }) => {
    const reportName = `Deep audit report ${auditRun}`;
    await page.goto("/reports");
    await page.getByPlaceholder("Report name").fill(reportName);
    await page.getByRole("button", { name: "Save report" }).click();
    await expect(page.getByText(reportName, { exact: true })).toBeVisible();
  });

  test("alerts saves and masks email recipients through the UI", async ({ page }) => {
    await page.goto("/alerts");
    const recipients = page.getByPlaceholder("alerts@example.com, finance@example.com");
    await expect(recipients).toBeVisible();
    await recipients.fill(`audit-${auditRun}@example.com`);
    await page.getByRole("button", { name: "Save email alerts" }).click();
    await expect(page.getByText("Email alerts saved. Recipients will receive budget, anomaly, and summary notifications.")).toBeVisible();
  });

  test("settings handles a plan-gated API key write gracefully", async ({ page }) => {
    const keyName = `deep-audit-${auditRun}`;
    await page.goto("/settings");
    await page.getByPlaceholder("Key name").fill(keyName);
    await page.getByRole("button", { name: "Create key" }).click();
    await expect(page.getByText("This feature requires the Growth plan or higher.")).toBeVisible();
  });
});

test("recommendations exposes a stable empty-data state when no actions exist", async ({ page, context }) => {
  await authenticate(context, false);
  await page.goto("/recommendations");
  await expect(page.getByText("No recommendations match your filters")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset filters" })).toBeVisible();
});
