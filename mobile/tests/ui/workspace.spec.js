import { test, expect } from "@playwright/test";

async function signIn(page) {
  await page.goto("/");
  await expect(page.locator("#login-form")).toBeVisible();
  await page.locator("#username").fill("mobile-tester");
  await page.locator("#password").fill("Local-mobile-test-only-123!");
  await page.locator("#login-button").click();
  await expect(page).toHaveURL("http://127.0.0.1:5174/");
  await expect(page.locator(".stage-workspace")).toBeAttached();
  await expect(page.locator("body")).toHaveClass(/mobile-ready/);
}

test("sign-in, mobile navigation, reload and sign-out use the bundled pages", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signIn(page);
  await page.locator("#sidebar-toggle").click();
  await page.locator('.primary-nav a[href="/project-dashboard"]').click();
  await expect(page.locator(".topbar h1")).toHaveText("Project dashboard");
  await page.reload();
  await expect(page.locator(".topbar h1")).toHaveText("Project dashboard");
  await page.locator("#sidebar-toggle").click();
  await page.locator('.primary-nav a[href="/documentation"]').click();
  await expect(page).toHaveURL(/\/documentation$/);
  await expect(page.locator("body")).toHaveClass(/mobile-ready/);
  await page.reload();
  await expect(page.locator("body")).toHaveClass(/mobile-ready/);
  await page.goto("/");
  await expect(page.locator("body")).toHaveClass(/mobile-ready/);
  // The profile menu controls sign-out on a small screen.
  await page.locator("#profile-toggle").click();
  await page.locator("#logout").click();
  await expect(page.locator("#login-form")).toBeVisible();
  await page.goto("/");
  await expect(page.locator("#login-form")).toBeVisible();
  expect(errors).toEqual([]);
});

test("bundled mobile UI keeps file selection and browser export working", async ({ page }) => {
  await signIn(page);
  await page.locator("#requirement-file").setInputFiles({
    name: "mobile-requirements.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(
      "%PDF-1.4\n% File-picker selection fixture; not submitted for ingestion.\n%%EOF",
    ),
  });
  await expect(page.locator("#file-name")).toHaveText("mobile-requirements.pdf");
  const download = page.waitForEvent("download");
  await page.evaluate(() => window.BrdPdf.download("Mobile preview export", "mobile-preview.pdf"));
  expect((await download).suggestedFilename()).toBe("mobile-preview.pdf");
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth + 1,
  );
  expect(horizontalOverflow).toBe(false);
});

test("connection loss is visible without clearing the requirements draft", async ({
  page,
  context,
}) => {
  await signIn(page);
  await page.locator("#description").fill("Review quotation test execution results.");
  await context.setOffline(true);
  await expect(page.locator(".native-notice")).toContainText("offline");
  await context.setOffline(false);
  await expect(page.locator(".native-notice")).toContainText("Connection restored");
  await expect(page.locator("#description")).toHaveValue(
    "Review quotation test execution results.",
  );
});
