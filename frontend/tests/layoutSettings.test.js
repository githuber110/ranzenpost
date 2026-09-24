import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { shippedScriptText } from "./shippedSources.js";

function seed(window, extra = "") {
  window.eval(`
    state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
    state.childId = "c1";
    state.me = { forename: "Alice" };
    state.config = { language: "de", notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.timetable = { lessons: [], period_times: {} };
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.messengerRooms = { rooms: [] };
    window.__posts = [];
    window.fetch = (url, options) => {
      const request = options || {};
      if (request.method === "POST") window.__posts.push({ path: String(url), body: JSON.parse(request.body) });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ saved: true }) });
    };
    ${extra}
  `);
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || null)})`);
}

function overviewPage(window) {
  return window.eval("overviewSettingsPage()");
}

function navigationPage(window) {
  return window.eval("navigationSettingsPage()");
}

describe("settings › Layout › Overview", () => {
  test("every offered block is either shown with its tools or hidden with a switch only", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "compact" }];');
    const page = overviewPage(window);
    const shown = [...page.querySelectorAll(".settings-group")[0].querySelectorAll(".block-row")];
    expect(shown.map((row) => row.dataset.block)).toEqual(["today", "letters"]);
    expect(shown.every((row) => row.querySelector(".switch").getAttribute("aria-checked") === "true")).toBe(true);
    expect(shown.every((row) => row.querySelector(".block-tools .segment.mini") && row.querySelectorAll(".order-btns .icon-btn").length === 2)).toBe(true);
    const hidden = [...page.querySelectorAll(".settings-group")[1].querySelectorAll(".block-row")];
    expect(hidden.map((row) => row.dataset.block)).toEqual(["next_lesson", "week", "noticeboard", "absences", "conferences", "holidays", "changes", "chat"]);
    expect(hidden.every((row) => row.classList.contains("off") && !row.querySelector(".block-tools"))).toBe(true);
    expect(page.querySelector(".layout-foot").textContent).toBe(label(window, "settings.blocks.foot"));
  });

  test("blocks of modules the account lacks are offered nowhere", () => {
    const { window } = loadApp();
    seed(window, 'state.modules = applyModules({ modules: { messenger: false, conferences: false } });');
    const keys = [...overviewPage(window).querySelectorAll(".block-row")].map((row) => row.dataset.block);
    expect(keys).not.toContain("chat");
    expect(keys).not.toContain("conferences");
    expect(keys).toContain("today");
  });

  test("the size segment is a radiogroup that writes the size of that block", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }];');
    const page = overviewPage(window);
    const segment = page.querySelector('.block-row[data-block="letters"] .segment.mini');
    expect(segment.getAttribute("role")).toBe("radiogroup");
    const radios = [...segment.querySelectorAll('[role="radio"]')];
    expect(radios.map((radio) => radio.getAttribute("aria-checked"))).toEqual(["false", "true"]);
    radios[0].click();
    expect(window.eval("window.__posts[0].body")).toEqual({ overview_blocks: [{ key: "today", size: "normal" }, { key: "letters", size: "compact" }] });
  });

  test("the arrows reorder, the first up and the last down are disabled, focus returns to the pressed arrow", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }, { key: "chat", size: "compact" }];');
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    const page = window.document;
    const up = (key) => page.querySelector(`.block-row[data-block="${key}"] .order-btns [data-dir="up"]`);
    const down = (key) => page.querySelector(`.block-row[data-block="${key}"] .order-btns [data-dir="down"]`);
    expect(up("today").getAttribute("aria-disabled")).toBe("true");
    expect(down("chat").getAttribute("aria-disabled")).toBe("true");
    expect(up("letters").getAttribute("aria-disabled")).toBeNull();
    up("chat").click();
    expect(window.eval("window.__posts[0].body.overview_blocks.map((b) => b.key)")).toEqual(["today", "chat", "letters"]);
    expect(page.activeElement).toBe(up("chat"));
    expect(page.querySelector('[aria-live="polite"]').textContent).toBe(label(window, "settings.order.moved", { name: label(window, "blocks.chat.title"), position: "2" }));
    up("today").click();
    expect(window.eval("window.__posts.length")).toBe(1);
  });

  test("switching off moves a block to hidden, switching on appends it at the end", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }];');
    let page = overviewPage(window);
    page.querySelector('.block-row[data-block="today"] .switch').click();
    expect(window.eval("window.__posts[0].body")).toEqual({ overview_blocks: [{ key: "letters", size: "normal" }] });
    page = overviewPage(window);
    expect([...page.querySelectorAll(".settings-group")[0].querySelectorAll(".block-row")].map((row) => row.dataset.block)).toEqual(["letters"]);
    page.querySelector('.block-row[data-block="chat"] .switch').click();
    expect(window.eval("window.__posts[1].body")).toEqual({ overview_blocks: [{ key: "letters", size: "normal" }, { key: "chat", size: "compact" }] });
  });

  test("the info button opens a sheet with the block's facts", () => {
    const { window } = loadApp();
    seed(window);
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    window.document.querySelector('.block-row[data-block="holidays"] .info-btn').click();
    const sheet = window.document.querySelector(".sheet");
    expect(sheet).not.toBeNull();
    expect(sheet.textContent).toContain(label(window, "blocks.holidays.explain"));
    expect(sheet.textContent).toContain(label(window, "blocks.holidays.when"));
    expect(sheet.textContent).toContain(label(window, "blocks.holidays.target"));
    expect(sheet.textContent).toContain(label(window, "settings.modules.name.timetable"));
  });

  test("no search field below the threshold, ten catalogue blocks", () => {
    const { window } = loadApp();
    seed(window);
    const page = overviewPage(window);
    expect(page.querySelector(".search-field")).toBeNull();
  });

  test("at or above the threshold a search field filters shown and hidden blocks by their translated name", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }];');
    window.RanzenpostBlocks.BLOCK_SEARCH_FROM = 5;
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    const page = window.document;
    const input = page.querySelector(".search-field .search-input");
    expect(input).not.toBeNull();
    expect(input.getAttribute("placeholder")).toBe(label(window, "settings.blocks.search.placeholder"));
    input.focus();
    input.value = label(window, "blocks.chat.title");
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    const shownKeys = [...page.querySelectorAll(".settings-group")[0].querySelectorAll(".block-row")].map((row) => row.dataset.block);
    const hiddenKeys = [...page.querySelectorAll(".settings-group")[1].querySelectorAll(".block-row")].map((row) => row.dataset.block);
    expect(shownKeys).toEqual([]);
    expect(hiddenKeys).toEqual(["chat"]);
    expect(page.activeElement).toBe(page.querySelector(".search-field .search-input"));
  });

  test("a search with no matches shows the empty-result text in both groups", () => {
    const { window } = loadApp();
    seed(window);
    window.RanzenpostBlocks.BLOCK_SEARCH_FROM = 5;
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    const page = window.document;
    const input = page.querySelector(".search-field .search-input");
    input.value = "zzz-no-such-block";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(page.querySelectorAll(".block-row").length).toBe(0);
    expect(page.querySelectorAll(".cal-hint")).toHaveLength(2);
    for (const hint of page.querySelectorAll(".cal-hint")) {
      expect(hint.textContent).toBe(label(window, "settings.blocks.search.empty"));
    }
    input.value = "";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(page.querySelectorAll(".block-row").length).toBe(10);
  });

  test("every offered block has its six texts in the base bundle", () => {
    const { window } = loadApp();
    for (const key of window.eval("RanzenpostBlocks.blockKeys()")) {
      for (const part of ["title", "explain", "when", "compact", "normal", "target"]) {
        expect(window.eval(`hasMessage("blocks.${key}.${part}")`), `${key}.${part}`).toBe(true);
      }
    }
  });
});

describe("settings › Layout › Navigation", () => {
  test("the overview is locked first, the areas follow in order with position numbers and the two bands", () => {
    const { window } = loadApp();
    seed(window);
    const page = navigationPage(window);
    expect(page.querySelector(".section-lead").textContent).toBe(label(window, "settings.nav.lead"));
    const rows = [...page.querySelectorAll(".nav-rows > *")].map((node) => node.dataset.band || node.dataset.area);
    expect(rows).toEqual(["bar", "overview", "timetable", "absence", "post", "more", "messenger", "conferences"]);
    const fixed = page.querySelector('.nav-row[data-area="overview"]');
    expect(fixed.querySelector(".order-btns")).toBeNull();
    expect(fixed.querySelector(".val").textContent).toBe(label(window, "settings.nav.fixed"));
    expect([...page.querySelectorAll(".nav-row .pos")].map((node) => node.textContent)).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(page.querySelector('.nav-row[data-area="post"] small').textContent).toBe("Elternbriefe · Pinnwand");
  });

  test("the overview keeps its own icon with a small lock, and areas name their module where the words differ", () => {
    const { window } = loadApp();
    seed(window);
    const page = navigationPage(window);
    const fixedIcon = page.querySelector('.nav-row[data-area="overview"] .nav-ico');
    expect(fixedIcon.querySelector(":scope > .ico-slot path").getAttribute("d")).toBe(
      window.eval("ICON_SHAPES.overview").match(/d="([^"]+)"/)[1]
    );
    expect(fixedIcon.querySelector(".nav-lock .ico")).not.toBeNull();
    const sub = (area) => {
      const node = page.querySelector(`.nav-row[data-area="${area}"] .lbl small`);
      return node ? node.textContent : null;
    };
    expect(sub("timetable")).toBe(label(window, "settings.modules.name.timetable"));
    expect(sub("absence")).toBe(label(window, "settings.modules.name.absences"));
    expect(sub("conferences")).toBe(label(window, "settings.modules.name.conferences"));
    expect(sub("messenger")).toBeNull();
  });

  test("with four areas or fewer there is no More band", () => {
    const { window } = loadApp();
    seed(window, 'state.modules = applyModules({ modules: { messenger: false } });');
    const rows = [...navigationPage(window).querySelectorAll(".nav-rows > *")].map((node) => node.dataset.band || node.dataset.area);
    expect(rows).toEqual(["bar", "overview", "timetable", "absence", "post", "conferences"]);
  });

  test("moving an area writes the whole navigation list and keeps switched-off areas behind", () => {
    const { window } = loadApp();
    seed(window, 'state.config.modules_disabled = ["absences"];');
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    const page = window.document;
    page.querySelector('.nav-row[data-area="messenger"] .order-btns [data-dir="up"]').click();
    expect(window.eval("window.__posts[0].body")).toEqual({ navigation: ["timetable", "messenger", "post", "conferences", "absence"] });
    expect(page.activeElement).toBe(page.querySelector('.nav-row[data-area="messenger"] .order-btns [data-dir="up"]'));
  });

  test("Alt+arrow on a focused row moves it like a tap", () => {
    const { window } = loadApp();
    seed(window);
    const page = navigationPage(window);
    const row = page.querySelector('.nav-row[data-area="post"]');
    row.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowUp", altKey: true, bubbles: true }));
    expect(window.eval("window.__posts[0].body.navigation")).toEqual(["timetable", "post", "absence", "messenger", "conferences"]);
    row.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    expect(window.eval("window.__posts.length")).toBe(1);
  });

  test("an account with only the overview shows the empty state with the recheck button", () => {
    const { window } = loadApp();
    seed(window, 'state.modules = applyModules({ modules: { timetable: false, letters: false, pinboard: false, absences: false, conferences: false, messenger: false } });');
    const page = navigationPage(window);
    expect(page.querySelector(".nav-rows")).toBeNull();
    const empty = page.querySelector(".empty");
    expect(empty.querySelector("b").textContent).toBe(label(window, "settings.nav.empty.title"));
    expect(empty.querySelector(".modules-recheck")).not.toBeNull();
  });
});

describe("settings › IServ modules with switches", () => {
  test("a switch per available module writes modules_disabled and the area vanishes everywhere", () => {
    const { window } = loadApp();
    seed(window);
    window.eval('state.view = "settings"; render();');
    const row = window.document.querySelector('.module-row[data-module="messenger"]');
    expect(row.querySelector(".switch").getAttribute("aria-checked")).toBe("true");
    row.querySelector(".switch").click();
    expect(window.eval("window.__posts[0].body")).toEqual({ modules_disabled: ["messenger"] });
    expect(window.eval("moduleOn('messenger')")).toBe(false);
    expect(window.eval("moduleAvailable('messenger')")).toBe(true);
    expect(window.eval("visibleViews().map((item) => item.key)")).not.toContain("messenger");
    expect(window.eval("enabledOverviewBlocks().map((entry) => entry.key)")).not.toContain("chat");
    expect(window.document.querySelector('.module-row[data-module="messenger"] .switch').getAttribute("aria-checked")).toBe("false");
    expect(window.document.querySelector(".modules-block .section-lead").textContent).toBe(label(window, "settings.modules.lead"));
  });
});

describe("the app layout page", () => {
  test("one display row leads into one page with the overview and the navigation part, back returns", () => {
    const { window } = loadApp();
    seed(window);
    const view = window.eval("settingsView()");
    expect(view.querySelectorAll(".blocks-setting, .nav-setting").length).toBe(0);
    const row = view.querySelector(".layout-setting");
    expect(row.closest(".settings-group").querySelector(".overline").textContent).toBe(label(window, "settings.section.display"));
    expect(row.querySelector(".lbl").textContent).toBe(label(window, "settings.layout.title"));
    expect(row.querySelector(".val").textContent).toBe(label(window, "settings.blocks.value.other", { count: "6" }));
    window.eval('state.view = "settings"; render();');
    window.document.querySelector(".layout-setting").click();
    expect(window.eval("state.settingsPage")).toBe("layout");
    const header = window.document.querySelector(".header");
    expect(header.querySelector(".header-title").textContent).toBe(label(window, "settings.layout.title"));
    const parts = [...window.document.querySelectorAll(".app-layout-page .layout-part")];
    expect(parts.map((part) => part.dataset.part)).toEqual(["overview", "navigation"]);
    expect(parts.map((part) => part.querySelector(".layout-part-title").textContent)).toEqual([label(window, "settings.blocks.title"), label(window, "settings.nav.title")]);
    expect(parts[0].querySelector(".blocks-page")).not.toBeNull();
    expect(parts[1].querySelector(".nav-page .nav-rows")).not.toBeNull();
    expect(window.document.querySelectorAll('.app-layout-page [aria-live="polite"]').length).toBe(1);
    header.querySelector(".header-back").click();
    expect(window.eval("state.settingsPage")).toBe(null);
  });

  test("every shown block keeps its own compact and normal switch on the merged page and it writes that block's size", () => {
    const { window } = loadApp();
    seed(window, 'state.config.overview_blocks = [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }, { key: "chat", size: "compact" }];');
    window.eval('state.view = "settings"; state.settingsPage = "layout"; render();');
    const page = window.document.querySelector(".app-layout-page");
    const shown = [...page.querySelectorAll('.layout-part[data-part="overview"] .block-row:not(.off)')];
    expect(shown.map((row) => row.dataset.block)).toEqual(["today", "letters", "chat"]);
    for (const row of shown) {
      const radios = [...row.querySelectorAll('.segment.mini[role="radiogroup"] [role="radio"]')];
      expect(radios.map((radio) => radio.textContent)).toEqual([label(window, "settings.blocks.size.compact"), label(window, "settings.blocks.size.normal")]);
    }
    page.querySelector('.block-row[data-block="today"] .segment.mini [role="radio"]').click();
    expect(window.eval("window.__posts[0].body")).toEqual({ overview_blocks: [{ key: "today", size: "compact" }, { key: "letters", size: "normal" }, { key: "chat", size: "compact" }] });
    expect(window.document.querySelector('.block-row[data-block="today"] .segment.mini [aria-checked="true"]').textContent).toBe(label(window, "settings.blocks.size.compact"));
    window.document.querySelectorAll('.block-row[data-block="chat"] .segment.mini [role="radio"]')[1].click();
    expect(window.eval("window.__posts[1].body.overview_blocks.find((entry) => entry.key === 'chat').size")).toBe("normal");
  });

  test("the empty overview button opens the merged page", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("overviewEmptyState().querySelector('button').click()");
    expect(window.eval("state.settingsPage")).toBe("layout");
  });
});

describe("the More tab and its sheet", () => {
  test("More carries the sum of the hidden badges and lists the hidden areas with their counts", () => {
    const { window } = loadApp();
    seed(window, `
      state.messengerRooms = { rooms: [{ room_id: "!a:x", name: "R", unread_count: 4 }] };
      state.view = "overview";
      render();
    `);
    const more = window.document.querySelector(".tabbar .tab-more");
    expect(more).not.toBeNull();
    expect(more.querySelector(".badge").textContent).toBe("4");
    expect(more.getAttribute("aria-haspopup")).toBe("dialog");
    more.click();
    const sheet = window.document.querySelector(".sheet");
    const rows = [...sheet.querySelectorAll(".more-row")];
    expect(rows.map((row) => row.querySelector(".lbl").textContent)).toEqual([label(window, "nav.messenger"), label(window, "nav.conferences")]);
    expect(rows[0].querySelector(".badge").textContent).toBe("4");
    expect(rows[1].querySelector(".badge")).toBeNull();
    expect(sheet.querySelector(".sheet-hint").textContent).toBe(label(window, "nav.more.hint"));
    rows[1].click();
    expect(window.eval("state.view")).toBe("conferences");
    expect(window.document.querySelector(".sheet")).toBeNull();
  });

  test("the bar limit cookie lowers the limit for tests only", () => {
    const { window } = loadApp();
    seed(window);
    window.document.cookie = "e2e_bar_limit=3";
    const bar = window.eval("tabbar()");
    expect(bar.querySelectorAll(".tab").length).toBe(3);
    expect(window.eval("navigationLayout().more")).toEqual(["absence", "post", "messenger", "conferences"]);
  });
});

describe("block search threshold", () => {
  test("production code keeps the threshold in the block catalogue, not in a test cookie", async () => {
    expect(shippedScriptText()).not.toContain("e2e_block_search_threshold");
    const { window } = loadApp();
    expect(window.RanzenpostBlocks.BLOCK_SEARCH_FROM).toBe(20);
  });
});
