import { describe, expect, test } from "vitest";
import { createStore, storeGlobals } from "../lib/store.js";

describe("the store wraps the object it was given", () => {
  test("get reads the same object, so a direct write shows through the store", () => {
    const target = { view: "overview" };
    const store = createStore(target);
    expect(store.get("view")).toBe("overview");
    target.view = "post";
    expect(store.get("view")).toBe("post");
    expect(store.get("missing")).toBe(undefined);
  });

  test("set writes into the same object and keeps values by identity", () => {
    const target = { sheet: null };
    const store = createStore(target);
    const factory = () => null;
    store.set("sheet", factory);
    expect(target.sheet).toBe(factory);
    expect(store.get("sheet")).toBe(factory);
    store.set("added", 1);
    expect(target.added).toBe(1);
  });

  test("patch writes every own key of the partial into the same object and leaves the rest", () => {
    const form = { label: "a" };
    const target = { sheetForm: null, sheetFormDefault: null, view: "overview" };
    const store = createStore(target);
    store.patch({ sheetForm: form, sheetFormDefault: null });
    expect(target).toEqual({ sheetForm: form, sheetFormDefault: null, view: "overview" });
    expect(target.sheetForm).toBe(form);
    const inherited = Object.create({ view: "post" });
    inherited.sheetFormDefault = 2;
    store.patch(inherited);
    expect(target.view).toBe("overview");
    expect(target.sheetFormDefault).toBe(2);
  });

  test("the store never copies or replaces the object, it only reads and writes its keys", () => {
    const nested = { draft: 1 };
    const target = { form: nested };
    const store = createStore(target);
    expect(store.get("form")).toBe(nested);
    store.patch({ other: true });
    expect(Object.keys(target)).toEqual(["form", "other"]);
    expect(Object.isFrozen(target)).toBe(false);
    expect(Object.getPrototypeOf(target)).toBe(Object.prototype);
  });

  test("the store API is fixed", () => {
    const store = createStore({});
    expect(Object.keys(store).sort()).toEqual(["get", "patch", "set", "subscribe"]);
    expect(Object.isFrozen(store)).toBe(true);
    expect(createStore).toHaveLength(1);
  });
});

describe("subscribe tells listeners about writes and does nothing else", () => {
  test("a listener hears the changed key after set, when the new value is already there", () => {
    const target = { toast: null };
    const store = createStore(target);
    const heard = [];
    store.subscribe((keys) => heard.push({ keys, value: target.toast }));
    store.set("toast", { message: "saved", kind: "good" });
    expect(heard).toEqual([{ keys: ["toast"], value: { message: "saved", kind: "good" } }]);
  });

  test("patch tells every listener once with all changed keys", () => {
    const store = createStore({});
    const first = [];
    const second = [];
    store.subscribe((keys) => first.push(keys));
    store.subscribe((keys) => second.push(keys));
    store.patch({ sheet: null, onSheetClose: null });
    expect(first).toEqual([["sheet", "onSheetClose"]]);
    expect(second).toEqual([["sheet", "onSheetClose"]]);
  });

  test("get never notifies, and an unsubscribed listener hears nothing more", () => {
    const store = createStore({ view: "overview" });
    const heard = [];
    const stop = store.subscribe((keys) => heard.push(keys));
    store.get("view");
    expect(heard).toEqual([]);
    store.set("view", "post");
    stop();
    store.set("view", "absence");
    expect(heard).toEqual([["view"]]);
  });

  test("a listener that leaves during a notification does not stop the others", () => {
    const store = createStore({});
    const heard = [];
    let stopFirst = null;
    stopFirst = store.subscribe(() => {
      heard.push("first");
      stopFirst();
    });
    store.subscribe(() => heard.push("second"));
    store.set("a", 1);
    store.set("a", 2);
    expect(heard).toEqual(["first", "second", "second"]);
  });

  test("writes without listeners change the object and call nothing", () => {
    const target = {};
    const store = createStore(target);
    store.set("a", 1);
    store.patch({ b: 2 });
    expect(target).toEqual({ a: 1, b: 2 });
  });
});

describe("the store module is published as a frozen global bundle", () => {
  test("storeGlobals hands out createStore only", () => {
    const globals = storeGlobals();
    expect(Object.keys(globals)).toEqual(["createStore"]);
    expect(globals.createStore).toBe(createStore);
    expect(Object.isFrozen(globals)).toBe(true);
  });
});
