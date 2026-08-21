import { expect, test } from "@playwright/test";

const widths = [390, 768, 1024, 1440, 1920];
const site = {
  brand: "Edvatiq",
  support_email: "sales@edvatiq.com",
  contact_phone: "+919787867648",
  legal_ready: true,
  legal_documents: { privacy: { id: "privacy-fixture" } },
};
const catalog = {
  trial_enabled: false,
  payment_available: true,
  plans: [
    {
      id: "growth", name: "Growth", description: "For growing organizations",
      recommended: true, purchasable: true, signup_mode: "paid",
      monthly_quote: { total_paise: 294882, tax_paise: 44982 },
      annual_quote: { total_paise: 2948820, tax_paise: 449820 },
      annual_saving_percent: 17, ai_credits: 2500, location_limit: 3,
      employee_limit: 15, client_limit: 2000,
    },
    {
      id: "enterprise", name: "Enterprise", description: "For complex organizations",
      recommended: false, purchasable: false, signup_mode: "contact",
      monthly_quote: null, annual_quote: null, annual_saving_percent: 0,
      ai_credits: null, location_limit: null, employee_limit: null, client_limit: null,
    },
  ],
};

async function mockPublicApi(page, { siteBody = site, catalogBody = catalog, catalogStatus = 200 } = {}) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) }));
  await page.route("**/api/public/site", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(siteBody) }));
  await page.route("**/api/billing/public/plans", (route) => route.fulfill({ status: catalogStatus, contentType: "application/json", body: JSON.stringify(catalogBody) }));
}

async function revealFullPage(page) {
  await page.evaluate(async () => {
    const pause = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const step = Math.max(500, Math.floor(window.innerHeight * 0.75));
    for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await pause();
    }
    window.scrollTo(0, 0);
    await pause();
  });
}

test.describe.configure({ mode: "serial" });

for (const width of widths) {
  test(`landing page at ${width}px`, async ({ page }) => {
    await mockPublicApi(page);
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /See what matters/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Need software built around your workflow?" })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
    await revealFullPage(page);
    await page.waitForTimeout(150);

    const overflow = await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator('a[href="tel:+919787867648"]').first()).toHaveAttribute("href", "tel:+919787867648");
    await expect(page).toHaveScreenshot(`landing-${width}.png`, {
      animations: "disabled",
      caret: "hide",
      fullPage: true,
    });
  });
}

test("project deep link remains usable while motion features load", async ({ page }) => {
  await mockPublicApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/motionFeatures.js*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.continue();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?inquiry=client_project#contact");
  await expect(page.getByRole("heading", { name: "Tell us what you want to build." })).toBeVisible();
  await expect(page.getByLabel("Organization or venture (optional)")).not.toHaveAttribute("required", "");
  await expect(page.getByRole("button", { name: /Send project enquiry/ })).toBeVisible();
  await expect(page.locator('a[href^="https://wa.me/919787867648"]')).toHaveCount(3);
});

test("interactive landing controls are keyboard operable", async ({ page }) => {
  await mockPublicApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const businessTab = page.getByRole("tab", { name: "Business", exact: true });
  await businessTab.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Business position", { exact: true })).toBeVisible();

  const gymTab = page.getByRole("tab", { name: "Gym and fitness", exact: true });
  await gymTab.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /Run membership around the person/ })).toBeVisible();

  const annual = page.getByRole("button", { name: /Annual/ });
  await annual.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Billed annually / tax included")).toBeVisible();

  const project = page.getByRole("button", { name: /Custom software project/ });
  await project.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Tell us what you want to build." })).toBeVisible();
  await expect(page.getByLabel("Organization or venture (optional)")).not.toHaveAttribute("required", "");
});

test("long plan content and pricing failures remain usable", async ({ page }) => {
  const longCatalog = {
    ...catalog,
    plans: catalog.plans.map((plan, index) => index === 0 ? {
      ...plan,
      name: "Growth workspace for multidisciplinary operating teams",
      description: "For organizations coordinating several locations, responsibilities, integrations, approval paths, and evidence-heavy workflows without losing day-to-day clarity.",
    } : plan),
  };
  await mockPublicApi(page, { catalogBody: longCatalog });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await revealFullPage(page);
  expect(await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth)).toBeLessThanOrEqual(1);
  await expect(page.getByText(/multidisciplinary operating teams/)).toBeVisible();

  const failedPage = await page.context().newPage();
  await mockPublicApi(failedPage, { catalogBody: { detail: "Unavailable" }, catalogStatus: 503 });
  await failedPage.emulateMedia({ reducedMotion: "reduce" });
  await failedPage.goto("/");
  await expect(failedPage.getByText("Pricing is temporarily unavailable.")).toBeVisible();
  await expect(failedPage.getByRole("button", { name: "Try again" })).toBeVisible();
  await failedPage.close();
});
