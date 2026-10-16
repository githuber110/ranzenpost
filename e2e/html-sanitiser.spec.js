const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const LETTERS_TAB = 3;
const LETTER = "Tierpark";
const PAYLOADS = [
  "<p>Start</p>",
  "<!--><img src=x onerror=\"document.title='pwned'\">-->",
  "<![CDATA[ ><img src=x onerror=\"document.title='pwned'\"> ]]>",
  "<?x ><img src=x onerror=\"document.title='pwned'\"> ?>",
  "<iframe srcdoc=\"<script src='api/letters/attachment/1'></script>\"></iframe>",
  "<a href=\"java&#x09;script:alert(1)\">link</a>",
  "<p>Ende</p>",
  "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\"></noscript>",
  "<svg onload=\"document.title='pwned'\"><a href=\"javascript:alert(1)\">s</a></svg>",
  "<math><mtext><table><mglyph><style><img src=x onerror=\"document.title='pwned'\">",
];

test("a hostile letter body is shown without live markup in the browser", async ({ page }) => {
  const dialogs = [];
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.message());
    dialog.dismiss();
  });
  await page.route("**/api/letters/detail**", (route) =>
    route.fulfill({ json: { title: LETTER, body_html: PAYLOADS.join(""), attachments: [], archive_url_present: false, confirmation: null, reply: null } })
  );
  await goto(page);
  const title = await page.title();
  await page.locator(".tabbar .tab").nth(LETTERS_TAB).click();
  await page.locator(".rows .row", { hasText: LETTER }).first().click();
  const body = page.locator(".body-html");
  await expect(body).toContainText("Ende");
  await page.waitForTimeout(400);
  const found = await body.evaluate((root) => {
    const bad = [];
    for (const node of root.querySelectorAll("*")) {
      if (["script", "iframe", "svg", "math", "style", "object", "embed"].includes(node.localName)) bad.push(node.localName);
      for (const attribute of node.attributes) {
        if (/^on/i.test(attribute.name) || attribute.name === "srcdoc") bad.push(attribute.name);
        if (attribute.name === "href" && /script:/i.test(attribute.value)) bad.push(attribute.value);
      }
    }
    return bad;
  });
  expect(found).toEqual([]);
  expect(await page.title()).toBe(title);
  expect(dialogs).toEqual([]);
});
