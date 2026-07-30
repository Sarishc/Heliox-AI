import { test, expect } from "@playwright/test";

test("recommendations route requires authentication", async ({
  page,
}) => {
  await page.goto("/recommendations");
  await expect(page).toHaveURL(/\/login\?redirect=%2Frecommendations/, {
    timeout: 15000,
  });
});
