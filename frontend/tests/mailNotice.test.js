import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const TWO_SCHOOLS = [
  { id: "a1", label: "School One", setup_complete: true },
  { id: "b2", label: "School Two", setup_complete: true },
];

function seed(window, mail, connections) {
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {}, connections: testArgs[1] };
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.messengerRooms = { rooms: [], can_write_to_teacher: false };
    state.holidays = {};
    state.mail = testArgs[0];
  `, mail, connections || []);
}

function notice(window) {
  return window.eval("overviewView()").querySelector(".mail-notice");
}

describe("the unread mail notice on the overview", () => {
  test("names the unread count and links to IServ", () => {
    const { window } = loadApp();
    seed(window, [{ connection_id: "a1", school: "School One", unread: 3, open_url: "https://school.example/iserv/mail" }]);
    const shown = notice(window);
    expect(shown).not.toBeNull();
    expect(shown.textContent).toContain(evalWith(window, "tCount('mail.unread', 3)"));
    const link = shown.querySelector("a");
    expect(link.getAttribute("href")).toBe("https://school.example/iserv/mail");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  test("stays away without unread mail or with an unknown count", () => {
    const { window } = loadApp();
    seed(window, [{ connection_id: "a1", school: "School One", unread: 0, open_url: "x" }, { connection_id: "b2", school: "School Two", unread: null, open_url: "y" }]);
    expect(notice(window)).toBeNull();
    seed(window, null);
    expect(notice(window)).toBeNull();
  });

  test("names the school when there are several", () => {
    const { window } = loadApp();
    seed(window, [
      { connection_id: "a1", school: "School One", unread: 2, open_url: "https://one.example/iserv/mail" },
      { connection_id: "b2", school: "School Two", unread: 0, open_url: "https://two.example/iserv/mail" },
    ], TWO_SCHOOLS);
    const shown = notice(window);
    expect(shown.querySelectorAll(".mail-notice-row").length).toBe(1);
    expect(shown.textContent).toContain("School One");
  });

  test("names the school when only one of two schools offers mail", () => {
    const { window } = loadApp();
    seed(window, [{ connection_id: "b2", school: "", unread: 4, open_url: "https://two.example/iserv/mail" }], TWO_SCHOOLS);
    expect(notice(window).textContent).toContain("School Two");
  });

  test("a pull to refresh reads the mail count again", async () => {
    const { window } = loadApp();
    seed(window, [{ connection_id: "a1", school: "School One", unread: 1, open_url: "" }]);
    const asked = [];
    window.fetch = (input) => {
      asked.push(String(input));
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve({ schools: [] }) });
    };
    await window.eval("refreshEverything()");
    expect(asked.some((url) => url.includes("api/mail"))).toBe(true);
  });

  test("shows no link without an address", () => {
    const { window } = loadApp();
    seed(window, [{ connection_id: "a1", school: "School One", unread: 1, open_url: "" }]);
    expect(notice(window).querySelector("a")).toBeNull();
  });
});
