import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { createDom, richUrl } from "../lib/dom.js";
import { loadApp } from "./loadApp.js";
import { readShipped, scriptNames } from "./shippedSources.js";

const PAYLOADS = [
  "<!--><img src=x onerror=alert(1)>-->",
  "<!---><img src=x onerror=alert(1)>-->",
  "<!-- a --!> <img src=x onerror=alert(1)> -->",
  "<![CDATA[ ><img src=x onerror=alert(1)> ]]>",
  "<?x ><img src=x onerror=alert(1)> ?>",
  "<!DOCTYPE x><p>ok</p><!x ><img src=x onerror=alert(1)>>",
  "<scr<script>ipt>alert(1)</script>",
  "<ScRiPt>alert(1)</sCrIpT><IMG SRC=x OnErRoR=alert(1)>",
  "<img src=x on\u0000error=alert(1)><a href=\"java\u0000script:alert(1)\">x</a>",
  '<a href="&#106;avascript:alert(1)">x</a><a href="java&Tab;script:alert(1)">y</a>',
  '<a href=" &#14;javascript:alert(1)">x</a><a href="VBSCRIPT:msgbox(1)">y</a>',
  '<a href="data:text/html,<script>alert(1)</script>">x</a>',
  '<img src="javascript:alert(1)"><img src="data:text/html,x">',
  "<svg onload=alert(1)><script>alert(1)</script><a href=javascript:alert(1)>s</a></svg>",
  "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>",
  '<iframe srcdoc="<script src=\'api/letters/attachment/1\'></script>"></iframe>',
  '<object data="x"></object><embed src="x"><form><button formaction="javascript:alert(1)">b</button></form>',
  '<base href="javascript:/"><meta http-equiv="refresh" content="0"><link rel="stylesheet" href="x">',
  '<p style="background:url(javascript:alert(1))">x</p><style>p{}</style>',
  "<template><img src=x onerror=alert(1)></template>",
  '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>',
  "<details open ontoggle=alert(1)>x</details><video><source onerror=alert(1)></video>",
  '<a href="https://example.org" onclick="alert(1)" target="_self">x</a>',
  "<img src=x onerror=alert(1)" + "/".repeat(2),
];

const FORBIDDEN = "script, iframe, frame, object, embed, svg, math, style, form, base, meta, link, template, noscript, video, details";

function problems(root) {
  const found = [];
  for (const node of root.querySelectorAll("*")) {
    if (node.matches(FORBIDDEN)) found.push(node.localName);
    for (const attribute of Array.from(node.attributes)) {
      if (/^on/i.test(attribute.name) || ["style", "srcdoc", "formaction"].includes(attribute.name)) found.push(`${node.localName}[${attribute.name}]`);
      if (["href", "src"].includes(attribute.name) && !/^(https?:|mailto:|tel:|\/|#|data:image\/)/i.test(attribute.value)) {
        found.push(`${node.localName}[${attribute.name}]=${attribute.value}`);
      }
      if (attribute.name === "target" && attribute.value !== "_blank") found.push("target");
    }
  }
  const walker = root.ownerDocument.createTreeWalker(root, 128);
  if (walker.nextNode()) found.push("comment");
  return found;
}

function bodyOf(payload) {
  const { window } = new JSDOM("<!doctype html><html><body></body></html>");
  const { el } = createDom({ page: window.document });
  return el("div", { class: "body-html", richHtml: payload });
}

describe("school html is rebuilt from an allowlist before it reaches the page", () => {
  test.each(PAYLOADS)("%s leaves no live markup", (payload) => {
    expect(problems(bodyOf(payload))).toEqual([]);
  });

  test("formatting, tables, links and images survive", () => {
    const body = bodyOf('<p>A <b>bold</b> <a href="https://example.org/x.pdf" title="t">link</a></p><table><tr><td colspan="2">c</td></tr></table><img src="/a.png" alt="a" width="20">');
    expect(body.innerHTML).toBe(
      '<p>A <b>bold</b> <a href="https://example.org/x.pdf" title="t" rel="noopener noreferrer" target="_blank">link</a></p>' +
        '<table><tbody><tr><td colspan="2">c</td></tr></tbody></table><img src="/a.png" alt="a" width="20">'
    );
  });

  test("text inside unknown tags stays readable in its place", () => {
    expect(bodyOf("<p>a<marquee>b<blink>c</blink></marquee>d</p>e").innerHTML).toBe("<p>abcd</p>e");
  });

  test("markup the browser reads past a broken comment loses every handler", () => {
    expect(bodyOf("<p>a</p><!--><img src=x onerror=alert(1)>--><p>b</p>").innerHTML).toBe("<p>a</p><img>--&gt;<p>b</p>");
  });

  test("urls are judged the way the browser reads them", () => {
    expect(richUrl("https://example.org/x", false)).toBe("https://example.org/x");
    expect(richUrl("ja\tva\nscript:alert(1)", false)).toBeNull();
    expect(richUrl("\u0001javascript:alert(1)", false)).toBeNull();
    expect(richUrl("data:image/png;base64,AA", true)).toBe("data:image/png;base64,AA");
    expect(richUrl("data:image/png;base64,AA", false)).toBeNull();
    expect(richUrl("relative/path", false)).toBeNull();
  });
});

describe("the app renders school html only through the allowlist", () => {
  const letterBody = (window, html) =>
    window.eval(`
      (function (html) {
        state.view = "post";
        state.letterDetail = { letter: { letter_id: "1", recipient_id: "1", title: "Brief" }, detail: { body_html: html, attachments: [] }, loading: false, error: "" };
        return letterDetailView();
      })
    `)(html);

  test.each(PAYLOADS)("a letter body with %s stays inert", (payload) => {
    const { window } = loadApp();
    const view = letterBody(window, payload);
    const body = view.querySelector(".body-html");
    expect(body).toBeTruthy();
    expect(problems(body)).toEqual([]);
  });

  test.each(PAYLOADS)("a pinboard tile and an absence answer with %s stay inert", (payload) => {
    const { window } = loadApp();
    const tile = window.eval("postDetailParts")({ title: "Info", text: payload, attachments: [] });
    const answer = window.eval("absenceDetailParts")({ kind: "leave", answer: payload, attachments: [] });
    for (const parts of [tile, answer]) {
      const holder = window.document.createElement("div");
      holder.append(...parts.body);
      const body = holder.querySelector(".body-html");
      expect(body).toBeTruthy();
      expect(problems(body)).toEqual([]);
    }
  });
});

describe("raw html only ever comes from the app itself", () => {
  const TRUSTED_HTML = /^html:\s*(iconSvg\(|window\.RanzenpostDom\.iconSvg\(|shapeSvg\(|markup\b)/;
  const REQUEST_FIELDS = {
    "app/mailCompose.js: html: form.html": "the written mail body in the request to the backend, never handed to the page",
  };

  test("every html: and innerHTML sink in the shipped scripts takes app-made markup", () => {
    const seen = new Set();
    for (const name of scriptNames()) {
      const text = readShipped(name);
      for (const match of text.matchAll(/\bhtml:\s*[^,}\n]+/g)) {
        const found = `${name}: ${match[0]}`;
        if (REQUEST_FIELDS[found]) {
          seen.add(found);
          continue;
        }
        expect(TRUSTED_HTML.test(match[0]) ? "" : found).toBe("");
      }
      for (const match of text.matchAll(/\.innerHTML\s*=\s*([^;\n]+)/g)) {
        expect(match[1] === "value" || match[1] === "String(html ?? \"\")" ? "" : `${name}: ${match[0]}`).toBe("");
      }
      expect(text).not.toMatch(/insertAdjacentHTML|outerHTML\s*=|document\.write|createContextualFragment|srcdoc/);
    }
    expect([...seen].sort()).toEqual(Object.keys(REQUEST_FIELDS).sort());
  });
});
