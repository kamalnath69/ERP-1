import { expect, test } from "@playwright/test";

const widths = [390, 768, 1024, 1440, 1920];
const scenarios = ["empty", "sparse", "dense", "long", "restricted"];
const profiles = {
  college: {
    empty: "overview",
    sparse: "operations",
    dense: "leadership",
    long: "academic_support",
    restricted: "academic_support",
  },
  business: {
    empty: "operations",
    sparse: "operations",
    dense: "leadership",
    long: "operations",
    restricted: "leadership",
  },
};

test.describe.configure({ mode: "serial" });

for (const kind of ["college", "business"]) {
  for (const scenario of scenarios) {
    for (const width of widths) {
      test(`${kind} ${scenario} dashboard at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(`/dashboard-fixtures.html?kind=${kind}&scenario=${scenario}&profile=${profiles[kind][scenario]}`);
        await page.evaluate(() => document.fonts.ready);

        const fixture = page.getByTestId("dashboard-fixture");
        await expect(fixture).toBeVisible();
        await expect(fixture).toHaveScreenshot(`${kind}-${scenario}-${width}.png`, {
          animations: "disabled",
          caret: "hide",
        });

        const horizontalOverflow = await page.evaluate(() => Math.max(
          document.documentElement.scrollWidth,
          document.body.scrollWidth,
        ) - window.innerWidth);
        expect(horizontalOverflow).toBeLessThanOrEqual(1);

        const overlap = await page.locator("[data-dashboard-card]").evaluateAll((cards) => {
          const boxes = cards.map((card) => card.getBoundingClientRect());
          for (let first = 0; first < boxes.length; first += 1) {
            for (let second = first + 1; second < boxes.length; second += 1) {
              const x = Math.min(boxes[first].right, boxes[second].right) - Math.max(boxes[first].left, boxes[second].left);
              const y = Math.min(boxes[first].bottom, boxes[second].bottom) - Math.max(boxes[first].top, boxes[second].top);
              if (x > 1 && y > 1) return { first, second, x, y };
            }
          }
          return null;
        });
        expect(overlap).toBeNull();

        const laneGeometry = await page.locator("[data-dashboard-lane]").evaluateAll((lanes) => lanes.map((lane) => {
          const cards = [...lane.children].map((card) => card.getBoundingClientRect());
          return {
            alignSelf: getComputedStyle(lane).alignSelf,
            gaps: cards.slice(1).map((card, index) => Math.round(card.top - cards[index].bottom)),
          };
        }));
        laneGeometry.forEach((lane) => {
          expect(["start", "auto"]).toContain(lane.alignSelf);
          lane.gaps.forEach((gap) => expect(gap).toBeGreaterThanOrEqual(18));
          lane.gaps.forEach((gap) => expect(gap).toBeLessThanOrEqual(22));
        });

        const inaccessibleActions = await page.locator("a, button").evaluateAll((actions) => actions.filter((action) => {
          const name = (action.getAttribute("aria-label") || action.textContent || "").trim();
          const invalidLink = action.tagName === "A" && !action.getAttribute("href");
          return !name || invalidLink || action.hasAttribute("disabled");
        }).length);
        expect(inaccessibleActions).toBe(0);

        if (scenario === "restricted") {
          await expect(page.getByRole("note")).toContainText("Some evidence is not included");
          await expect(page.getByText(kind === "college" ? "Attendance trend" : "Collections trend", { exact: true })).toHaveCount(0);
        }

        if (scenario === "dense" && width >= 1440) {
          const cardHeights = await page.locator("[data-dashboard-card]").evaluateAll((cards) => cards.map((card) => Math.round(card.getBoundingClientRect().height)));
          expect(new Set(cardHeights).size).toBeGreaterThan(1);
        }
      });
    }
  }
}
