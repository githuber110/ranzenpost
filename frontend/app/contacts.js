const CONTACTS_TABS = ["addressbook", "mailinglist"];
const CONTACTS_SEARCH_DELAY_MS = 400;
const CONTACTS_QUERY_MIN = 2;
const LIST_IMPORT_MAX_BYTES = 2 * 1024 * 1024;
const LIST_IMPORT_TIMEOUT_MS = 240000;
const LIST_DELETE_TIMEOUT_MS = 300000;
let contactsSearchTimer = null;

function contactsTabs() {
  return CONTACTS_TABS.filter((tab) => accountSchools(tab).length > 0);
}

function contactsTab() {
  const offered = contactsTabs();
  if (state.contactsTab && offered.includes(state.contactsTab)) return state.contactsTab;
  return offered[0] || "";
}

function contactsSchool() {
  const listed = accountSchools(contactsTab()).map((entry) => entry.connection_id);
  if (state.contactsSchool && listed.includes(state.contactsSchool)) return state.contactsSchool;
  return listed[0] || "";
}

function setContactsTab(tab) {
  if (tab === contactsTab()) return;
  state.contactsTab = tab;
  render();
}

function setContactsSchool(id) {
  if (id === contactsSchool()) return;
  state.contactsSchool = id;
  state.contactsPeople = null;
  render();
}

function refreshContacts() {
  if (contactsTab() === "mailinglist") return loadMailingLists();
  return state.contactsQuery ? searchPeople(state.contactsQuery) : Promise.resolve();
}

function mailOfferedAt(school) {
  return mailSchools().some((entry) => entry.connection_id === school);
}

function writeMailTo(school, recipients) {
  state.mailSchool = school;
  state.mailFolder = "";
  state.mailList = null;
  setView("mail");
  openMailCompose("new", null, false, { to: recipients });
}

function contactsTabBar() {
  const offered = contactsTabs();
  if (offered.length < 2) return null;
  const active = contactsTab();
  return el("div", { class: "chipbar segmented contacts-tabs", role: "tablist" }, offered.map((tab) => el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "data-tab": tab,
    "aria-selected": String(tab === active),
    onclick: () => setContactsTab(tab),
  }, [icon(tab === "addressbook" ? "conferences" : "letters", 14), el("span", { class: "chip-label" }, t(`contacts.tab.${tab}`))])));
}

function contactsView() {
  const view = el("div", { class: "school-list contacts-view" });
  if (state.accountModules === null) {
    view.append(state.accountModulesError
      ? accountFailureBlock(state.accountModulesError, () => { state.accountModulesError = null; rerender(); loadAccountModules(); })
      : loadingBlock());
    if (!state.accountModulesError) autoLoad("accountModules", loadAccountModules);
    return view;
  }
  const tab = contactsTab();
  if (!tab) {
    view.append(emptyBlock("conferences", t("contacts.none.title"), t("contacts.none.text")));
    return view;
  }
  const head = el("div", { class: "list-head contacts-head" });
  const tabs = contactsTabBar();
  if (tabs) head.append(tabs);
  const schools = accountSchoolChips(tab, contactsSchool(), setContactsSchool, "contacts-schools");
  if (schools) head.append(schools);
  view.append(head);
  if (tab === "addressbook") addressBookBody(view, head);
  else mailingListBody(view, head);
  return view;
}

function peopleKey(school, query) {
  return JSON.stringify([school, query]);
}

async function searchPeople(query) {
  const school = contactsSchool();
  const text = String(query || "").trim();
  if (!school || text.length < CONTACTS_QUERY_MIN) {
    state.contactsPeople = null;
    if (state.view === "contacts") rerender();
    return;
  }
  const key = peopleKey(school, text);
  state.contactsPeople = { key, loading: true };
  if (state.view === "contacts") rerender();
  const outcome = await reload("contactsPeople", () => getJson(`api/addressbook/search?${connectionQuery(school, { q: text })}`), false, school);
  if (!outcome || !state.contactsPeople || state.contactsPeople.key !== key) return;
  state.contactsPeople = outcome.data
    ? { key, people: Array.isArray(outcome.data.people) ? outcome.data.people : [] }
    : { key, error: outcome.error, body: outcome.body };
  if (state.view === "contacts") rerender();
}

function personSub(person) {
  return [person.address, person.class_name, person.book].filter(Boolean).join(" · ");
}

function personRow(person, school) {
  return el("button", { class: "row read list-row contact-person", type: "button", onclick: () => openSheet(() => personSheet(person, school)) }, [
    el("span", { class: "row-dot" }, [icon("conferences", 14)]),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, person.name || person.address),
      personSub(person) ? iservText("div", { class: "row-sub", dir: "auto" }, personSub(person)) : null,
    ]),
  ]);
}

function personSheet(person, school) {
  const facts = [];
  if (person.address) facts.push([t("contacts.person.address"), person.address]);
  if (person.class_name) facts.push([t("contacts.person.class"), person.class_name]);
  for (const extra of Array.isArray(person.extra) ? person.extra : []) {
    if (extra && extra.value) facts.push([extra.label || t("contacts.person.more"), extra.value]);
  }
  const body = facts.length ? [factList(facts)] : [];
  const actions = person.address && mailOfferedAt(school)
    ? [el("div", { class: "btn-stack" }, [el("button", { class: "btn contact-write", type: "button", onclick: () => writeMailTo(school, [{ name: person.name, address: person.address }]) }, [el("span", { class: "dir-icon" }, [icon("send", 16)]), t("contacts.write")])])]
    : [];
  return sheet(person.name || person.address, body, actions);
}

function addressBookBody(view, head) {
  const school = contactsSchool();
  const host = el("div", {});
  const renderPeople = () => {
    const query = String(state.contactsQuery || "").trim();
    const found = state.contactsPeople;
    if (query.length < CONTACTS_QUERY_MIN) {
      host.replaceChildren(emptyBlock("search", t("contacts.search.startTitle"), t("contacts.search.startText")));
      return;
    }
    if (!found || found.key !== peopleKey(school, query) || found.loading) {
      host.replaceChildren(loadingBlock());
      return;
    }
    if (found.error) {
      host.replaceChildren(accountFailureBlock(found, () => searchPeople(query)));
      return;
    }
    host.replaceChildren(found.people.length
      ? el("div", { class: "rows contacts-people" }, found.people.map((person) => personRow(person, school)))
      : emptyBlock("search", t("contacts.search.emptyTitle"), t("contacts.search.emptyText")));
  };
  head.append(searchField(state.contactsQuery, t("contacts.search.placeholder"), (value) => {
    state.contactsQuery = value;
    if (contactsSearchTimer) window.clearTimeout(contactsSearchTimer);
    contactsSearchTimer = window.setTimeout(() => searchPeople(value), CONTACTS_SEARCH_DELAY_MS);
    renderPeople();
  }));
  view.append(host);
  const query = String(state.contactsQuery || "").trim();
  if (query.length >= CONTACTS_QUERY_MIN && (!state.contactsPeople || state.contactsPeople.key !== peopleKey(school, query))) {
    autoLoad(`contactsPeople:${peopleKey(school, query)}`, () => searchPeople(query));
  }
  renderPeople();
}

function listsKey(school) {
  return school;
}

function listsData() {
  const data = state.mailingLists;
  return data && data.key === listsKey(contactsSchool()) ? data : null;
}

async function loadMailingLists(school) {
  const target = school || contactsSchool();
  if (!target) return null;
  const kept = !!(state.mailingLists && state.mailingLists.key === target && state.mailingLists.data);
  const outcome = await reload("mailingLists", () => getJson(`api/mailinglists?${connectionQuery(target)}`), kept, target);
  if (!outcome) return null;
  if (outcome.data) state.mailingLists = { key: target, data: outcome.data };
  else if (outcome.error) state.mailingLists = { key: target, error: outcome.error, body: outcome.body };
  if (state.view === "contacts" || state.mailCompose) rerender();
  return state.mailingLists;
}

function listSub(entry) {
  return (Array.isArray(entry.extra) ? entry.extra : []).map((extra) => (extra.label ? `${extra.label}: ${extra.value}` : extra.value)).join(" · ");
}

function mailingListRow(entry, school, data) {
  return el("button", { class: "row read list-row mailing-list", type: "button", onclick: () => openMailingList(entry, school, data) }, [
    el("span", { class: "row-dot" }, [icon("letters", 14)]),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, entry.title),
      listSub(entry) ? iservText("div", { class: "row-sub" }, listSub(entry)) : null,
    ]),
  ]);
}

function mailingListBody(view, head) {
  const school = contactsSchool();
  const lists = listsData();
  if (!lists) {
    autoLoad(`mailingLists:${school}`, () => loadMailingLists());
    view.append(loadingBlock());
    return;
  }
  if (lists.error) {
    view.append(accountFailureBlock(lists, () => { state.mailingLists = null; rerender(); }));
    return;
  }
  const data = lists.data || {};
  const note = refreshFailureNote("mailingLists");
  if (note) head.append(note);
  const entries = Array.isArray(data.lists) ? data.lists : [];
  view.append(entries.length
    ? el("div", { class: "rows lists-rows" }, entries.map((entry) => mailingListRow(entry, school, data)))
    : emptyBlock("letters", t("lists.empty.title"), t("lists.empty.text")));
}

async function readMailingList(school, entry) {
  return getJson(`api/mailinglists/detail?${connectionQuery(school, { list_id: entry.id })}`);
}

function openMailingList(entry, school, data) {
  state.listDetail = { id: entry.id, loading: true };
  openSheet(() => mailingListSheet(entry, school, data));
  readMailingList(school, entry).then((detail) => {
    if (state.listDetail && state.listDetail.id === entry.id) state.listDetail = { id: entry.id, detail };
  }).catch((error) => {
    if (handleApiFailure(error, school)) return;
    if (state.listDetail && state.listDetail.id === entry.id) state.listDetail = { id: entry.id, failed: true };
  }).finally(() => rerender());
}

function mailingListSheet(entry, school, data) {
  const open = state.listDetail && state.listDetail.id === entry.id ? state.listDetail : null;
  const body = [];
  if (!open || open.loading) body.push(loadingBlock());
  else if (open.failed) body.push(noteBlock(t("lists.detail.failed")));
  else {
    const addresses = Array.isArray(open.detail.addresses) ? open.detail.addresses : [];
    body.push(addresses.length
      ? el("div", { class: "rows list-addresses" }, addresses.map((address) => el("div", { class: "row read static" }, [
        el("span", { class: "row-dot" }, [icon("letters", 14)]),
        el("div", { class: "row-main" }, [iservText("div", { class: "row-title full", dir: "ltr" }, address)]),
      ])))
      : noteBlock(t(open.detail.read ? "lists.detail.noAddresses" : "lists.detail.unread")));
  }
  const addresses = open && open.detail && Array.isArray(open.detail.addresses) ? open.detail.addresses : [];
  const stack = [];
  if (addresses.length && mailOfferedAt(school)) {
    stack.push(el("button", { class: "btn list-write", type: "button", onclick: () => writeMailTo(school, addresses.map((address) => ({ name: "", address }))) }, [el("span", { class: "dir-icon" }, [icon("send", 16)]), t("lists.write")]));
  }
  if (entry.deletable && data.can_delete) {
    stack.push(el("button", { class: "link-btn danger list-delete", type: "button", onclick: () => deleteMailingList(entry, school) }, [icon("trash", 16), t("lists.delete.open")]));
  }
  return sheet(entry.title, body, stack.length ? [el("div", { class: "btn-stack" }, stack)] : []);
}

async function deleteMailingList(entry, school) {
  const ok = await confirmAction({
    title: t("lists.delete.title"),
    text: t("lists.delete.text", { title: entry.title }),
    confirmLabel: t("lists.delete.confirm"),
    destructive: true,
  });
  if (!ok) return;
  let result = null;
  try {
    result = await postJson("api/mailinglists/delete", { connection_id: school, list_id: entry.id, confirmed: true }, LIST_DELETE_TIMEOUT_MS);
  } catch (error) {
    if (handleApiFailure(error, school)) return;
    toast(t("lists.delete.timeout"), "bad");
    discardSheet();
    loadMailingLists(school);
    rerender();
    return;
  }
  finishListWrite(result, school, "api.lists.delete.done", "lists.delete.failed");
  if (result && result.ok) discardSheet();
  rerender();
}

function finishListWrite(result, school, okKey, failKey) {
  const done = !!(result && result.ok);
  toast(apiMessage(result || {}, done ? okKey : failKey), done ? "good" : "bad");
  if (result && result.overview) state.mailingLists = { key: school, data: result.overview };
  else loadMailingLists(school);
  return done;
}

function listImportButton() {
  if (contactsTab() !== "mailinglist") return null;
  const lists = listsData();
  const data = lists && lists.data;
  if (!data || !data.can_import) return null;
  const school = contactsSchool();
  return el("button", { class: "icon-btn lists-import", type: "button", "aria-label": t("lists.import.open"), title: t("lists.import.open"), onclick: () => openListImport(school, data) }, [icon("plus", 18)]);
}

function openListImport(school, data) {
  state.listImport = { school, data, file: null, values: {}, preview: false, busy: false, failure: "" };
  openSheet(listImportSheet);
}

function listImportProblem(draft) {
  if (!draft.file) return "empty";
  if (draft.file.size > LIST_IMPORT_MAX_BYTES) return "large";
  const missing = (draft.data.import_fields || []).find((field) => field.required && !String(draft.values[field.name] || "").trim());
  return missing ? "missing" : "";
}

function listImportSheet() {
  const draft = state.listImport;
  if (!draft) return sheet(t("lists.import.title"), [noteBlock(t("api.lists.import.unavailable"))]);
  const fields = Array.isArray(draft.data.import_fields) ? draft.data.import_fields : [];
  if (draft.preview) {
    const typed = fields.filter((field) => String(draft.values[field.name] || "").trim());
    const body = [
      iservText("p", { class: "dlg-text" }, t("lists.import.previewText", { name: draft.file.name })),
      typed.length ? factList(typed.map((field) => [field.label || field.name, draft.values[field.name]])) : null,
      draft.failure ? noteBlock(draft.failure) : null,
    ].filter(Boolean);
    if (draft.unclear) return sheet(t("lists.import.title"), body);
    return sheet(t("lists.import.title"), body, [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn lists-import-send", type: "button", disabled: draft.busy ? "" : null, onclick: sendListImport }, [draft.busy ? el("span", { class: "spin" }) : null, t("lists.import.send")]),
      el("button", { class: "btn ghost", type: "button", disabled: draft.busy ? "" : null, onclick: () => { draft.preview = false; draft.failure = ""; rerender(); } }, t("tasks.upload.back")),
    ])]);
  }
  const input = el("input", { type: "file", class: "lists-import-input", hidden: "", accept: draft.data.import_accept || ".txt,.csv,text/plain,text/csv" });
  input.addEventListener("change", () => {
    const chosen = Array.from(input.files || []);
    draft.file = chosen[0] || draft.file;
    input.value = "";
    rerender();
  });
  const choose = el("button", { class: "btn ghost slim lists-import-choose", type: "button" }, [icon("plus", 14), t("tasks.upload.choose")]);
  choose.addEventListener("click", () => input.click());
  const inputs = fields.map((field) => {
    const box = el("input", { class: "inp lists-import-field", type: "text", value: draft.values[field.name] || "", dir: "auto", maxlength: field.maxlength || "200", "aria-label": field.label || field.name });
    box.addEventListener("input", () => { draft.values[field.name] = box.value; });
    return el("label", { class: "field" }, [iservText("span", { class: "lbl" }, field.label || field.name), box]);
  });
  const problem = listImportProblem(draft);
  const chosenName = draft.file ? draft.file.name : "";
  const body = [
    el("p", { class: "dlg-text" }, t("lists.import.text")),
    draft.file ? el("div", { class: "row read disabled" }, attachmentRowContent(chosenName, formatBytes(draft.file.size))) : null,
    problem === "large" ? noteBlock(t("api.lists.import.tooLarge", { max: formatNumber(LIST_IMPORT_MAX_BYTES / 1024) })) : null,
    choose,
    input,
    ...inputs,
  ].filter(Boolean);
  return sheet(t("lists.import.title"), body, [el("div", { class: "btn-stack" }, [
    el("button", { class: "btn lists-import-next", type: "button", onclick: () => { if (!listImportProblem(draft)) { draft.preview = true; rerender(); } else rerender(); } }, t("tasks.upload.next")),
  ])]);
}

async function sendListImport() {
  const draft = state.listImport;
  if (!draft || draft.busy) return;
  draft.busy = true;
  draft.failure = "";
  rerender();
  let result = null;
  try {
    result = await postFormData("api/mailinglists/import", { connection_id: draft.school, values: draft.values, confirmed: true }, [draft.file], LIST_IMPORT_TIMEOUT_MS);
  } catch (error) {
    draft.busy = false;
    if (handleApiFailure(error, draft.school)) return;
    draft.unclear = true;
    draft.failure = t("lists.import.timeout");
    rerender();
    loadMailingLists(draft.school);
    return;
  }
  draft.busy = false;
  const done = finishListWrite(result, draft.school, "api.lists.import.done", "lists.import.failed");
  if (!done && result && Array.isArray(result.errors) && result.errors.length) {
    draft.failure = result.errors.join(" ");
    rerender();
    return;
  }
  state.listImport = null;
  discardSheet();
  rerender();
}

function composeListOffered(connection) {
  return accountSchools("mailinglist").some((entry) => entry.connection_id === connection);
}

function composeListButton(form) {
  const connection = (state.mailCompose && state.mailCompose.connection) || mailSchool();
  if (!composeListOffered(connection)) return null;
  return el("button", { class: "link-btn mail-from-list", type: "button", onclick: () => openComposeLists(form, connection) }, t("lists.compose.open"));
}

function openComposeLists(form, connection) {
  state.composeLists = { connection, chosen: null, detail: null, picked: [] };
  openNestedSheet(() => composeListSheet(form));
  const known = state.mailingLists && state.mailingLists.key === connection && state.mailingLists.data;
  if (!known) loadMailingLists(connection).then(() => rerender());
}

function composeListSheet(form) {
  const pick = state.composeLists;
  if (!pick) return sheet(t("lists.compose.title"), []);
  const lists = state.mailingLists && state.mailingLists.key === pick.connection ? state.mailingLists : null;
  if (pick.chosen) {
    const detail = pick.detail;
    const body = [];
    if (!detail) body.push(loadingBlock());
    else if (detail.failed) body.push(noteBlock(t("lists.detail.failed")));
    else if (!detail.addresses.length) body.push(noteBlock(t(detail.read ? "lists.detail.noAddresses" : "lists.detail.unread")));
    else {
      body.push(el("div", { class: "rows compose-list-addresses" }, detail.addresses.map((address) => {
        const box = el("input", { type: "checkbox", class: "compose-list-pick" });
        box.checked = pick.picked.includes(address);
        box.addEventListener("change", () => {
          pick.picked = box.checked ? pick.picked.concat([address]) : pick.picked.filter((entry) => entry !== address);
        });
        return el("label", { class: "check-row" }, [box, iservText("span", { dir: "ltr" }, address)]);
      })));
    }
    return sheet(pick.chosen.title, body, detail && detail.addresses && detail.addresses.length ? [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn compose-list-add", type: "button", onclick: () => addListRecipients(form) }, t("lists.compose.add")),
    ])] : []);
  }
  const body = [];
  if (!lists) body.push(loadingBlock());
  else if (lists.error) body.push(noteBlock(t("files.error.text")));
  else {
    const entries = Array.isArray(lists.data.lists) ? lists.data.lists : [];
    body.push(entries.length
      ? el("div", { class: "rows" }, entries.map((entry) => el("button", { class: "row read compose-list", type: "button", onclick: () => chooseComposeList(entry) }, [
        el("span", { class: "row-dot" }, [icon("letters", 14)]),
        el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, entry.title)]),
      ])))
      : noteBlock(t("lists.empty.text")));
  }
  return sheet(t("lists.compose.title"), body);
}

function chooseComposeList(entry) {
  const pick = state.composeLists;
  if (!pick) return;
  pick.chosen = entry;
  pick.detail = null;
  rerender();
  readMailingList(pick.connection, entry).then((detail) => {
    if (state.composeLists !== pick) return;
    pick.detail = { addresses: Array.isArray(detail.addresses) ? detail.addresses : [], read: detail.read === true };
    pick.picked = pick.detail.addresses.slice();
  }).catch((error) => {
    if (handleApiFailure(error, pick.connection)) return;
    if (state.composeLists === pick) pick.detail = { failed: true, addresses: [] };
  }).finally(() => rerender());
}

function addListRecipients(form) {
  const pick = state.composeLists;
  if (!pick || !pick.picked.length) return;
  const present = parseMailAddresses(form.to).found.map((entry) => String(entry.address || entry).toLowerCase());
  const fresh = pick.picked.filter((address) => !present.includes(address.toLowerCase()));
  const current = String(form.to || "").trim().replace(/[,;]\s*$/, "");
  form.to = [current, mailAddressText(fresh.map((address) => ({ name: "", address })))].filter(Boolean).join(", ");
  state.composeLists = null;
  discardSheet();
  rerender();
}
