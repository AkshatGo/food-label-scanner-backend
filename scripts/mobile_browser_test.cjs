/* Run with NODE_PATH pointing to an installed Playwright package.
   LABELENS_BASE_URL selects an isolated local test server. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const base = process.env.LABELENS_BASE_URL || "http://127.0.0.1:8010";
(async () => {
  const browser = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base + "/ui");
  await page.waitForSelector("#recentProducts .empty-shelf");
  await page.screenshot({
    path: "/tmp/labelens-mobile-home.png",
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.getByRole("button", { name: "Open profile", exact: true }).click();
  await page
    .getByRole("button", { name: "Sign in / join", exact: true })
    .click();
  await page.locator('[data-auth="signup"]').click();
  await page.locator("#email").fill(`browser-${Date.now()}@example.com`);
  await page.locator("#password").fill("password123");
  await page.locator("#authSubmit").click();
  await page.waitForFunction(() => !document.querySelector("#authDialog").open);
  await page.locator('input[value="sugar"]').check();
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await page.locator('[data-nav="scan"]').click();
  await page
    .locator("#frontImage")
    .setInputFiles("/tmp/labelens-test-front.png");
  await page.locator("#backImage").setInputFiles("/tmp/labelens-test-back.png");
  await page.screenshot({
    path: "/tmp/labelens-mobile-capture.png",
    fullPage: true,
  });
  await page.locator("#scanSubmit").click();
  await page.waitForSelector("#resultScreen:not(.hidden) .nutrition-table", {
    timeout: 90000,
  });
  await page.waitForFunction(
    () =>
      !document
        .querySelector("#guidanceResult")
        .textContent.includes("Loading"),
  );
  await page.screenshot({
    path: "/tmp/labelens-mobile-result.png",
    fullPage: true,
  });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator("#reportButton").click(),
  ]);
  assert.ok(download.suggestedFilename().endsWith(".pdf"));
  await page.reload();
  await page.locator('[data-nav="library"]').click();
  await page.waitForSelector("#libraryProducts .product-card");
  assert.equal(await page.locator("#libraryProducts .product-card").count(), 1);
  await page.locator("#libraryProducts .product-card").click();
  await page.waitForSelector("#resultScreen:not(.hidden) .nutrition-table");
  // Offline cache never contains private API responses.
  await page.evaluate(() => navigator.serviceWorker.ready);
  const cached = await page.evaluate(async () =>
    (
      await Promise.all(
        (await caches.keys()).map(async (name) =>
          (await (await caches.open(name)).keys()).map((r) => r.url),
        ),
      )
    ).flat(),
  );
  assert.ok(cached.length > 0);
  assert.ok(cached.every((url) => !url.includes("/api/")));
  await context.setOffline(true);
  await page.goto(base + "/ui#home");
  await page.waitForSelector("#homeTitle");
  assert.equal(await page.locator("#connection").isVisible(), true);
  await context.setOffline(false);
  await page.reload();
  await page.waitForFunction(
    () => document.querySelector("#avatar").textContent !== "You",
  );
  await page.locator('[data-nav="profile"]').click();
  await page.locator("#logoutButton").click();
  await page.waitForSelector("#accountPanel [data-signin]");
  assert.equal(
    (await context.request.get(base + "/api/v1/products")).status(),
    401,
  );
  const desktop = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await desktop.goto(base + "/ui");
  await desktop.screenshot({
    path: "/tmp/labelens-desktop-home.png",
    fullPage: true,
  });
  assert.equal(errors.length, 0, errors.join("\n"));
  console.log(
    "PASS: mobile account/preferences, real OCR scan, PDF, persisted shelf, offline shell, private-cache exclusion, logout, layout, and JS errors.",
  );
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
