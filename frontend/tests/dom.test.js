import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { ICON_SHAPES, createDom, domGlobals, iconSvg } from "../lib/dom.js";

function setup() {
  const { window } = new JSDOM("<!doctype html><html><body></body></html>");
  return { window, ...createDom({ page: window.document }) };
}

describe("el builds nodes in the injected page", () => {
  test("the node belongs to the page it was given", () => {
    const { window, el } = setup();
    const node = el("div");
    expect(node.ownerDocument).toBe(window.document);
    expect(node instanceof window.HTMLDivElement).toBe(true);
  });

  test("class, html, handlers and attributes each take their own path", () => {
    const { el } = setup();
    let clicks = 0;
    const node = el("button", {
      class: "btn primary",
      html: "<b>x</b>",
      onclick: () => {
        clicks += 1;
      },
      "aria-label": "a",
      title: null,
      hidden: undefined,
    });
    node.click();
    expect(node.className).toBe("btn primary");
    expect(node.innerHTML).toBe("<b>x</b>");
    expect(clicks).toBe(1);
    expect(node.getAttribute("aria-label")).toBe("a");
    expect(node.hasAttribute("title")).toBe(false);
    expect(node.hasAttribute("hidden")).toBe(false);
    expect(node.hasAttribute("onclick")).toBe(false);
  });

  test("children may be nodes, text or numbers and empty slots are skipped", () => {
    const { el } = setup();
    const inner = el("span", {}, "inner");
    const node = el("p", {}, [inner, "text", 3, null, undefined, false]);
    expect(node.childNodes).toHaveLength(3);
    expect(node.firstChild).toBe(inner);
    expect(node.textContent).toBe("innertext3");
    expect(el("p", {}, "single").textContent).toBe("single");
  });
});

describe("el never turns data into markup", () => {
  test("a string child that looks like markup stays one text node", () => {
    const { el } = setup();
    const markup = "<img src=x onerror=1>";
    const node = el("p", {}, markup);
    expect(node.childNodes).toHaveLength(1);
    expect(node.firstChild.nodeType).toBe(3);
    expect(node.children).toHaveLength(0);
    expect(node.querySelector("img")).toBe(null);
    expect(node.textContent).toBe(markup);
  });

  test("markup in any attribute other than html is set literally", () => {
    const { el } = setup();
    const markup = '"><img src=x onerror=1>';
    const node = el("div", { title: markup, "data-value": markup });
    expect(node.getAttribute("title")).toBe(markup);
    expect(node.getAttribute("data-value")).toBe(markup);
    expect(node.children).toHaveLength(0);
    expect(node.innerHTML).toBe("");
  });

  test("false as an attribute value is written as the text false, not dropped", () => {
    const { el } = setup();
    const node = el("button", { "aria-pressed": false, disabled: false });
    expect(node.getAttribute("aria-pressed")).toBe("false");
    expect(node.getAttribute("disabled")).toBe("false");
    expect(node.disabled).toBe(true);
  });
});

describe("text from the school server gets its own direction", () => {
  test("iservText adds dir=auto and keeps the caller's attributes", () => {
    const { iservText } = setup();
    const node = iservText("span", { class: "row-title" }, "title");
    expect(node.getAttribute("dir")).toBe("auto");
    expect(node.className).toBe("row-title");
    expect(iservText("b").getAttribute("dir")).toBe("auto");
    expect(iservText("b", { dir: "ltr" }).getAttribute("dir")).toBe("ltr");
  });
});

describe("icons", () => {
  test("iconSvg draws a known shape, sizes it on request and knows no unknown one", () => {
    expect(iconSvg("check")).toContain(ICON_SHAPES.check);
    expect(iconSvg("check")).not.toContain("style=");
    expect(iconSvg("check", 16)).toContain('style="width:16px;height:16px"');
    expect(iconSvg("nope")).toBe("");
  });

  test("icon and externalIcon wrap the drawing in a slot", () => {
    const { window, icon, externalIcon } = setup();
    const drawn = (markup) => {
      const probe = window.document.createElement("span");
      probe.innerHTML = markup;
      return probe.innerHTML;
    };
    const slot = icon("messages", 18);
    expect(slot.tagName).toBe("SPAN");
    expect(slot.className).toBe("ico-slot");
    expect(slot.innerHTML).toBe(drawn(iconSvg("messages", 18)));
    const external = externalIcon(12);
    expect(external.className).toBe("ico-slot ico-external");
    expect(external.innerHTML).toBe(drawn(iconSvg("external", 12)));
    expect(icon("nope").innerHTML).toBe("");
  });

  test("the shape table cannot be changed from outside", () => {
    expect(Object.isFrozen(ICON_SHAPES)).toBe(true);
  });
});

test("the globals hand out the icon table, iconSvg and the factory, frozen", () => {
  const globals = domGlobals();
  expect(Object.isFrozen(globals)).toBe(true);
  expect(Object.keys(globals).sort()).toEqual(["ICON_SHAPES", "createDom", "iconSvg"]);
});
