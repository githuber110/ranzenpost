import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const UNKNOWN = { ok: false, error: "network", message_key: "api.letters.unknown" };

function jsonResponse(body, status = 200) {
  return Promise.resolve({
    ok: status < 400,
    status,
    headers: { get: (name) => (name.toLowerCase() === "content-type" ? "application/json" : null) },
    json: () => Promise.resolve(body),
  });
}

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function outcome(window, result, single = false) {
  return window.eval(`markReadOutcome(${JSON.stringify(result)}, ${single})`);
}

describe("marking letters read reports letters that could not be marked", () => {
  test("nothing marked because of a failure is a failure, not nothing to mark", () => {
    const { window } = loadApp();
    expect(outcome(window, { read: 0, blocked: 0, failed: 2 })).toEqual([window.eval('t("letters.toast.markFailed")'), "bad"]);
    expect(outcome(window, { read: 0, blocked: 0, failed: 1 }, true)).toEqual([window.eval('t("letters.toast.markFailed")'), "bad"]);
  });

  test("an error answer is a failure", () => {
    const { window } = loadApp();
    expect(outcome(window, UNKNOWN)).toEqual([window.eval('t("letters.toast.markFailed")'), "bad"]);
  });

  test("some marked and some failed says both", () => {
    const { window } = loadApp();
    expect(outcome(window, { read: 2, blocked: 0, failed: 1 })).toEqual([
      window.eval('t("letters.toast.markedSomeFailed", { read: formatNumber(2) })'),
      "bad",
    ]);
  });

  test("really nothing to mark stays a calm note", () => {
    const { window } = loadApp();
    expect(outcome(window, { read: 0, blocked: 0, failed: 0 })).toEqual([window.eval('t("letters.toast.nothingToMark")'), "good"]);
  });
});

describe("a letter outside the school list", () => {
  test("a refused restore shows the short note and reloads the list", async () => {
    const { window } = loadApp();
    await settle(window);
    window.eval("state.letters = { tab: 'archive', letters: [] }; state.letterDetail = { letter: {} };");
    window.fetch = () => jsonResponse(UNKNOWN);
    await window.eval("restoreLetter({ letter_id: '1', recipient_id: '1', connection_id: 'a' })");
    expect(window.eval("state.toast.message")).toBe(window.eval('t("api.letters.unknown")'));
    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.letterDetail")).toBeNull();
    expect(window.eval("state.letters === null || !state.letters.letters")).toBe(true);
  });

  test("a refused archive shows the short note instead of the archive failure", async () => {
    const { window } = loadApp();
    await settle(window);
    window.fetch = () => jsonResponse(UNKNOWN);
    const done = window.eval("archiveLetter({ letter_id: '1', recipient_id: '1', connection_id: 'a' })");
    window.document.querySelector(".scrim .btn-stack .btn:not(.ghost)").click();
    await done;
    expect(window.eval("state.toast.message")).toBe(window.eval('t("api.letters.unknown")'));
    expect(window.eval("state.toast.kind")).toBe("bad");
  });

  test("a refused attachment shows the short note", async () => {
    const { window } = loadApp();
    await settle(window);
    window.fetch = () => jsonResponse({ message_key: "api.letters.unknown" }, 404);
    await window.eval("runAttachmentAction('open', { url: 'api/letters/attachment/x' }, 'Brief.pdf', null)");
    expect(window.eval("state.toast.message")).toBe(window.eval('t("api.letters.unknown")'));
    expect(window.eval("state.toast.kind")).toBe("bad");
  });
});
