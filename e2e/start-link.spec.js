const { test, expect } = require("@playwright/test");

const PANEL = '<!doctype html><html><body><iframe id="ingress" src="/" style="width:1000px;height:760px"></iframe></body></html>';

test.describe("links from the dashboard card", () => {
  test.use({ viewport: { width: 1024, height: 800 } });

  test("open the timetable when the app runs inside a Home Assistant panel", async ({ page }) => {
    await page.route("**/app/local_ranzenpost**", (route) => route.fulfill({ contentType: "text/html", body: PANEL }));
    await page.goto("/app/local_ranzenpost?view=timetable");
    await expect(page.frameLocator("#ingress").locator("#app")).toHaveAttribute("data-view", "timetable", { timeout: 15000 });
  });

  test("open the pinboard of the post view when the app is opened directly", async ({ page }) => {
    await page.goto("/?view=post&segment=pinboard");
    await expect(page.locator("#app")).toHaveAttribute("data-view", "post", { timeout: 15000 });
    await expect(page.locator('.segment [role="tab"][aria-selected="true"]').first()).toHaveText(/Pinnwand/);
  });

  test("start at the overview without a link", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#app")).toHaveAttribute("data-view", "overview", { timeout: 15000 });
  });
});
