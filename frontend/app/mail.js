const MAIL_PAGE_SIZE = 40;
const MAIL_ROLE_ICONS = { inbox: "inbox", drafts: "edit", sent: "send", archive: "archive", junk: "alert", trash: "trash", folder: "folder" };
const MAIL_STATUS_FILTERS = ["", "unread", "read", "flagged", "answered", "unanswered"];
const MAIL_ORDERS = ["newest", "oldest", "largest", "smallest"];
const MAIL_SCOPES = ["all", "from", "to", "subject", "body"];
const MAIL_SEARCH_DELAY_MS = 450;
const MAIL_RECEIPT_DONE = "$MDNSent";
const MAIL_SIGN_IN_REFUSED_KEY = "api.mail.signInRefused";
const MAIL_SMTP_TIMEOUT_MS = 120000;
const MAIL_SPAM_TIMEOUT_MS = 240000;
let mailSearchTimer = null;

function mailSchools() {
  return Array.isArray(state.mail) ? state.mail.filter((entry) => entry && entry.connection_id) : [];
}

function mailOffered() {
  if (state.mail === null) return state.view === "mail";
  return mailSchools().length > 0;
}

function mailUnreadTotal() {
  return mailSchools().reduce((sum, entry) => sum + (Number(entry.unread) > 0 ? Number(entry.unread) : 0), 0);
}

function mailSchool() {
  const listed = mailSchools().map((entry) => entry.connection_id);
  if (state.mailSchool && listed.includes(state.mailSchool)) return state.mailSchool;
  return listed[0] || "";
}

function connectionQuery(connection, params) {
  return mailQuery(Object.assign({ connection }, params || {}));
}

function mailQuery(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) query.set(key, String(value));
  }
  return query.toString();
}

function mailFolderState() {
  return (state.mailFolders || {})[mailSchool()] || null;
}

function mailFolderList() {
  const entry = mailFolderState();
  return entry && Array.isArray(entry.folders) ? entry.folders : [];
}

function mailFolderId() {
  const folders = mailFolderList();
  if (state.mailFolder && folders.some((folder) => folder.id === state.mailFolder)) return state.mailFolder;
  const inbox = folders.find((folder) => folder.role === "inbox");
  return inbox ? inbox.id : folders.length ? folders[0].id : "";
}

function mailFolderOf(id) {
  return mailFolderList().find((folder) => folder.id === id) || null;
}

function mailFolderLabel(folder) {
  if (!folder) return "";
  return folder.role && folder.role !== "folder" ? t(`mail.folder.${folder.role}`) : folder.name || folder.path || folder.id;
}

function mailFilter() {
  return state.mailFilter || {};
}

function mailFilterActive() {
  const filter = mailFilter();
  return !!(filter.status || filter.query || filter.since || filter.until || filter.tag || filter.everywhere || (filter.order && filter.order !== "newest"));
}

function mailListKey() {
  const filter = mailFilter();
  return JSON.stringify([mailSchool(), filter.everywhere ? "" : mailFolderId(), filter]);
}

async function loadMailFolders(connectionId) {
  const school = connectionId || mailSchool();
  if (!school) return;
  const folders = Object.assign({}, state.mailFolders || {});
  const outcome = await reload(`mailFolders:${school}`, () => getJson(`api/mail/folders?${connectionQuery(school)}`), !!(folders[school] && folders[school].folders), school);
  if (!outcome) return;
  const next = Object.assign({}, state.mailFolders || {});
  if (outcome.data) next[school] = { folders: Array.isArray(outcome.data.folders) ? outcome.data.folders : [] };
  else if (outcome.error) next[school] = { error: outcome.error, body: outcome.body };
  state.mailFolders = next;
  if (state.view === "mail") rerender();
}

async function loadMailList(append) {
  const school = mailSchool();
  const folder = mailFolderId();
  const filter = mailFilter();
  if (!school || (!folder && !filter.everywhere)) return;
  const key = mailListKey();
  const current = state.mailList && state.mailList.key === key ? state.mailList : null;
  const offset = append && current ? (current.messages || []).length : 0;
  const params = {
    connection: school,
    folder: filter.everywhere ? "" : folder,
    offset,
    order: filter.order || "newest",
    limit: mailPageSize(),
    status: filter.status,
    query: filter.query,
    scope: filter.query ? filter.scope || "all" : "",
    since: filter.since,
    until: filter.until,
    tag: filter.tag,
    everywhere: filter.everywhere ? "true" : "",
  };
  if (append && current) state.mailList = Object.assign({}, current, { loadingMore: true });
  const outcome = await reload("mailList", () => getJson(`api/mail/messages?${connectionQuery(school, params)}`), !!current && !append, school);
  if (!outcome) return;
  if (mailListKey() !== key) return;
  if (outcome.data) {
    const listed = (Array.isArray(outcome.data.messages) ? outcome.data.messages : []).map((entry) => Object.assign({}, entry, { connection: school }));
    const kept = append && current ? (current.messages || []).concat(listed) : listed;
    state.mailList = { key, messages: kept, total: outcome.data.total, more: outcome.data.more === true };
  } else if (outcome.error) {
    state.mailList = append && current ? Object.assign({}, current, { loadingMore: false, moreFailed: true }) : { key, error: outcome.error, body: outcome.body };
  }
  if (state.view === "mail") rerender();
}

function loadMail() {
  const school = mailSchool();
  if (!school) return Promise.resolve();
  const known = mailFolderState();
  return Promise.all([
    loadMailAccount(school),
    known && known.folders ? Promise.resolve() : loadMailFolders(school),
  ]).then(() => loadMailList(false));
}

function refreshMail() {
  return Promise.all([loadMailCounts(), loadMailFolders(), loadMailList(false)]);
}

function mailFailureBlock(failure, retry) {
  if (anyOutage()) return outageEmptyBlock();
  const body = failure && failure.body;
  const refused = body && body.message_key === MAIL_SIGN_IN_REFUSED_KEY;
  const text = body && body.message_key ? apiMessage(body, "mail.error.text") : t("mail.error.text");
  return emptyBlock("alert", t(refused ? "mail.error.signInTitle" : "mail.error.title"), text, retryButton(retry));
}

function openMailFolder(id) {
  if (id === state.mailFolder && !mailFilter().everywhere) return;
  state.mailFolder = id;
  state.mailFilter = Object.assign({}, mailFilter(), { everywhere: false });
  state.mailSelectMode = false;
  state.mailSelected = [];
  state.mailList = null;
  state._scrollTop = true;
  render();
  loadMailList(false);
}

function setMailSchool(id) {
  if (!id || id === mailSchool()) return;
  leaveDirtyForms(() => {
    state.mailSchool = id;
    state.mailFolder = "";
    state.mailList = null;
    state.mailDetail = null;
    state.mailSettings = null;
    closeMailCompose();
    state.mailSelectMode = false;
    state.mailSelected = [];
    render();
    loadMail();
  });
}

function mailSchoolBar() {
  const listed = mailSchools();
  if (listed.length < 2) return null;
  const active = mailSchool();
  return el("div", { class: "chipbar school-filter mail-schools", role: "tablist" }, listed.map((entry) => {
    const chip = el("button", {
      class: "chip",
      type: "button",
      role: "tab",
      "aria-selected": String(entry.connection_id === active),
      onclick: () => setMailSchool(entry.connection_id),
    }, [iservText("span", { class: "chip-label" }, schoolShortName(entry.connection_id) || entry.school || schoolFullName(entry.connection_id))]);
    if (Number(entry.unread) > 0) chip.append(el("span", { class: "n" }, formatNumber(Number(entry.unread))));
    return chip;
  }));
}

function mailFolderBar() {
  const folders = mailFolderList();
  const active = mailFilter().everywhere ? "" : mailFolderId();
  const bar = el("div", { class: "chipbar segmented mail-folders", role: "tablist" });
  for (const folder of folders) {
    const chip = el("button", {
      class: "chip",
      type: "button",
      role: "tab",
      "data-folder": folder.id,
      "aria-selected": String(folder.id === active),
      onclick: () => openMailFolder(folder.id),
    }, [icon(MAIL_ROLE_ICONS[folder.role] || "folder", 14), iservText("span", { class: "chip-label" }, mailFolderLabel(folder))]);
    if (Number(folder.unread) > 0 && folder.role !== "sent" && folder.role !== "drafts") chip.append(el("span", { class: "n" }, formatNumber(Number(folder.unread))));
    bar.append(chip);
  }
  return bar;
}

function mailPeople(list) {
  return (Array.isArray(list) ? list : []).map((entry) => entry.name || entry.address).filter(Boolean);
}

function mailPeopleShort(list) {
  const names = mailPeople(list);
  if (names.length <= 2) return names.join(", ");
  return tCount("mail.people.more", names.length - 2, { names: names.slice(0, 2).join(", ") });
}

function mailRowWho(entry) {
  const folder = mailFolderOf(entry.folder);
  const outgoing = folder && (folder.role === "sent" || folder.role === "drafts");
  const who = outgoing ? mailPeopleShort(entry.to) : mailPeopleShort(entry.from);
  return who || t(outgoing ? "mail.noRecipient" : "mail.noSender");
}

function mailMoment(entry) {
  const moment = entry && entry.date ? new Date(entry.date) : null;
  return moment && !Number.isNaN(moment.getTime()) ? moment : null;
}

function mailWhen(entry) {
  const moment = mailMoment(entry);
  if (!moment) return "";
  const byDay = !["largest", "smallest"].includes(mailFilter().order);
  return byDay ? formatTime(moment) : showDate(isoDate(moment));
}

function mailDayLabel(day) {
  const today = isoDate(new Date());
  const yesterday = isoDate(addDays(new Date(), -1));
  if (day === today) return t("mail.day.today");
  if (day === yesterday) return t("mail.day.yesterday");
  return day ? formatWeekdayDate(day) || dateLabel(day) : t("mail.day.unknown");
}

function mailKey(entry) {
  return `${entry.folder || ""}\u0000${entry.uid}`;
}

function mailRow(entry) {
  const key = mailKey(entry);
  const selectMode = state.mailSelectMode;
  const selected = (state.mailSelected || []).includes(key);
  const folder = mailFolderOf(entry.folder);
  const tags = [];
  if (mailFilter().everywhere && folder) tags.push(iservText("span", { class: "tag" }, mailFolderLabel(folder)));
  if (entry.draft || (folder && folder.role === "drafts")) tags.push(el("span", { class: "tag warn" }, t("mail.tag.draft")));
  for (const tag of Array.isArray(entry.tags) ? entry.tags : []) {
    if (tag && (mailTagOf(tag) || !String(tag).startsWith("$"))) tags.push(mailTagChip(tag));
  }
  const row = el("button", {
    class: openRowClass(`row mail-row${entry.unread ? "" : " read"}${selected ? " selected" : ""}`, "mail", key),
    type: "button",
    "data-uid": entry.uid,
    onclick: () => {
      if (selectMode) toggleMailSelected(key);
      else openMail(entry);
    },
  }, [
    selectMode
      ? el("span", { class: `row-check${selected ? " on" : ""}` }, selected ? [icon("check", 14)] : [])
      : el("span", { class: "row-dot" }, entry.unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags.length ? el("div", { class: "row-tags" }, tags) : null,
      iservText("div", { class: "row-title mail-who" }, mailRowWho(entry)),
      iservText("div", { class: "row-sub mail-subject" }, entry.subject || t("mail.noSubject")),
    ]),
    el("div", { class: "row-side" }, [
      el("span", { class: "row-meta" }, mailWhen(entry)),
      el("span", { class: "mail-marks" }, [
        entry.flagged ? el("span", { class: "mail-star on", "aria-label": t("mail.flagged") }, [icon("star", 14)]) : null,
        entry.answered ? el("span", { class: "row-clip", "aria-label": t("mail.answered") }, [icon("reply", 14)]) : null,
        entry.has_attachments ? el("span", { class: "row-clip" }, [icon("clip", 14)]) : null,
      ]),
    ]),
  ]);
  attachMailLongPress(row, key);
  return row;
}

function attachMailLongPress(row, key) {
  let timer = null;
  const cancel = () => {
    if (timer) window.clearTimeout(timer);
    timer = null;
  };
  row.addEventListener("pointerdown", () => {
    if (state.mailSelectMode) return;
    timer = window.setTimeout(() => {
      timer = null;
      state.mailSelectMode = true;
      state.mailSelected = [key];
      rerender();
    }, 550);
  });
  row.addEventListener("pointerup", cancel);
  row.addEventListener("pointerleave", cancel);
}

function mailRowsByDay(messages) {
  const groups = [];
  let current = null;
  const order = mailFilter().order || "newest";
  for (const entry of messages) {
    const moment = mailMoment(entry);
    const day = moment && (order === "newest" || order === "oldest") ? isoDate(moment) : "";
    if (!current || current.day !== day) {
      current = { day, rows: [] };
      groups.push(current);
    }
    current.rows.push(mailRow(entry));
  }
  if (order === "largest" || order === "smallest") return [el("div", { class: "rows" }, groups.flatMap((group) => group.rows))];
  return groups.map((group) => el("section", { class: "list-section mail-day" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, mailDayLabel(group.day))]),
    el("div", { class: "rows" }, group.rows),
  ]));
}

function mailToolbar() {
  const filter = mailFilter();
  const input = searchField(filter.query || "", t("mail.search.placeholder"), (value) => {
    state.mailFilter = Object.assign({}, mailFilter(), { query: value });
    if (mailSearchTimer) window.clearTimeout(mailSearchTimer);
    mailSearchTimer = window.setTimeout(() => {
      mailSearchTimer = null;
      state.mailList = null;
      rerender();
      loadMailList(false);
    }, MAIL_SEARCH_DELAY_MS);
  });
  return input;
}

function mailListHead(total) {
  return el("div", { class: "section-head" }, [
    el("span", { class: "overline" }, tCount("mail.count", total)),
    el("div", { class: "letters-tools mail-tools" }, [
      el("button", { type: "button", class: mailFilterActive() ? "mail-filter-on" : null, onclick: () => openSheet(mailFilterSheet) }, t("mail.filter.open")),
      el("button", { type: "button", onclick: () => openSheet(mailFoldersSheet) }, t("mail.folders.manage")),
      el("button", { type: "button", class: "mail-settings-open", onclick: openMailSettings }, t("mail.settings.open")),
      state.mailSelectMode ? null : el("button", { type: "button", onclick: () => { state.mailSelectMode = true; state.mailSelected = []; rerender(); } }, t("common.select")),
    ]),
  ]);
}

function mailView() {
  const view = el("div", { class: "mail-view" });
  if (state.mail === null) {
    view.append(state.mailCountsError
      ? mailFailureBlock(state.mailCountsError, () => { state.mailCountsError = null; rerender(); loadMailCounts(); })
      : loadingBlock());
    return view;
  }
  if (!mailSchools().length) {
    view.append(emptyBlock("letters", t("mail.none.title"), t("mail.none.text")));
    return view;
  }
  const head = el("div", { class: "list-head" });
  const schools = mailSchoolBar();
  if (schools) head.append(schools);
  view.append(head);
  const spamNotice = mailSpamNotice();
  if (spamNotice) view.append(spamNotice);
  if (!mailAccountOf()) {
    autoLoad(`mailAccount:${mailSchool()}`, () => loadMailAccount());
    view.append(loadingBlock());
    return view;
  }
  const folders = mailFolderState();
  if (!folders) {
    autoLoad(`mailFolders:${mailSchool()}`, () => loadMailFolders());
    view.append(loadingBlock());
    return view;
  }
  if (folders.error) {
    view.append(mailFailureBlock(folders, () => { const next = Object.assign({}, state.mailFolders); delete next[mailSchool()]; state.mailFolders = next; rerender(); }));
    return view;
  }
  head.append(mailFolderBar());
  head.append(mailToolbar());
  const note = refreshFailureNote("mailList");
  if (note) head.append(note);
  const list = state.mailList && state.mailList.key === mailListKey() ? state.mailList : null;
  if (!list) {
    autoLoad("mailList", () => loadMailList(false));
    view.append(loadingBlock());
    return view;
  }
  if (list.error) {
    view.append(mailFailureBlock(list, () => { state.mailList = null; rerender(); }));
    return view;
  }
  const messages = list.messages || [];
  head.append(mailListHead(Number(list.total) || messages.length));
  if (!messages.length) {
    view.append(mailFilterActive()
      ? emptyBlock("search", t("mail.search.emptyTitle"), t("mail.search.emptyText"))
      : emptyBlock("inbox", t("mail.empty.title"), t("mail.empty.text")));
  } else {
    for (const node of mailRowsByDay(messages)) view.append(node);
  }
  if (list.more) {
    view.append(el("div", { class: "btn-stack mail-more" }, [
      el("button", { class: "btn ghost", type: "button", disabled: list.loadingMore ? "" : null, onclick: () => loadMailList(true) }, [
        list.loadingMore ? el("span", { class: "spin" }) : null,
        t("mail.loadMore"),
      ]),
    ]));
  }
  if (state.mailSelectMode) view.append(mailSelectionBar(messages));
  return view;
}

function toggleMailSelected(key) {
  const chosen = new Set(state.mailSelected || []);
  if (chosen.has(key)) chosen.delete(key);
  else chosen.add(key);
  state.mailSelected = [...chosen];
  rerender();
}

function mailSelectedEntries(messages) {
  const chosen = new Set(state.mailSelected || []);
  return (messages || []).filter((entry) => chosen.has(mailKey(entry)));
}

function selectMailWhere(messages, test) {
  state.mailSelected = (messages || []).filter(test).map(mailKey);
  rerender();
}

function mailSelectionBar(messages) {
  const chosen = mailSelectedEntries(messages);
  const busy = !!state.mailBusy;
  const action = (iconName, label, run, className) => el("button", {
    class: `icon-btn mail-bulk ${className || ""}`.trim(),
    type: "button",
    "aria-label": label,
    title: label,
    disabled: !chosen.length || busy ? "" : null,
    onclick: () => run(chosen),
  }, [icon(iconName, 18)]);
  return el("div", { class: "select-bar mail-select-bar", "aria-busy": busy ? "true" : "false" }, [
    el("div", { class: "select-bar-info" }, [
      el("button", { class: "select-bar-cancel", type: "button", "aria-label": t("common.selection.end"), onclick: () => { state.mailSelectMode = false; state.mailSelected = []; rerender(); } }, [icon("close", 16)]),
      el("span", {}, tCount("common.selected", chosen.length)),
      el("button", { class: "link-btn mail-select-choose", type: "button", onclick: () => openSheet(() => mailSelectSheet(messages)) }, t("mail.select.choose")),
    ]),
    el("div", { class: "select-bar-actions mail-bulk-actions" }, [
      action("letters", t("mail.action.markRead"), (list) => mailBulkFlag(list, "seen", true), "mail-bulk-read"),
      action("inbox", t("mail.action.markUnread"), (list) => mailBulkFlag(list, "seen", false), "mail-bulk-unread"),
      action("star", t("mail.action.flag"), (list) => mailBulkFlag(list, "flagged", !list.every((entry) => entry.flagged)), "mail-bulk-flag"),
      action("folder", t("mail.action.move"), (list) => openSheet(() => mailMoveSheet(list)), "mail-bulk-move"),
      action("archive", t("mail.action.archive"), (list) => mailArchive(list), "mail-bulk-archive"),
      mailSpamTool(mailFolderId(), (iconName, label, run, className) => action(iconName, label, run, className.replace("mail-act-", "mail-bulk-")), null),
      action("trash", t("mail.action.trash"), (list) => mailTrash(list), "mail-bulk-trash"),
    ]),
  ]);
}

function mailSelectSheet(messages) {
  const choose = (test) => () => { dropSheet(); selectMailWhere(messages, test); };
  const row = (label, test) => el("button", { class: "setting-row", type: "button", onclick: choose(test) }, [el("span", { class: "lbl" }, label)]);
  return sheet(t("mail.select.choose"), [el("div", { class: "rows" }, [
    row(t("mail.select.all"), () => true),
    row(t("mail.select.none"), () => false),
    row(t("mail.filter.status.unread"), (entry) => entry.unread === true),
    row(t("mail.filter.status.flagged"), (entry) => entry.flagged === true),
    row(t("mail.filter.status.answered"), (entry) => entry.answered === true),
    row(t("mail.filter.status.unanswered"), (entry) => entry.answered !== true),
  ])]);
}

function mailGroups(list) {
  const groups = new Map();
  for (const entry of list) {
    const connection = entry.connection || mailSchool();
    const folder = entry.folder || mailFolderId();
    const key = `${connection}\u0000${folder}`;
    if (!groups.has(key)) groups.set(key, { connection, folder, entries: [] });
    groups.get(key).entries.push(entry);
  }
  return [...groups.values()];
}

function mailExpect(entries) {
  const expect = {};
  for (const entry of entries) {
    if (entry.message_id) expect[entry.uid] = entry.message_id;
  }
  return Object.keys(expect).length ? expect : undefined;
}

function mailPost(path, body, timeout) {
  return postJson(path, Object.assign({ connection_id: mailSchool() }, body), timeout);
}

function mailOutcome(result, okKey) {
  if (result && result.ok) {
    if (result.left && result.left.length) {
      toast(t("mail.toast.partly"), "bad");
      return false;
    }
    if (okKey) toast(t(okKey), "good");
    return true;
  }
  toast(apiMessage(result || {}, "mail.toast.failed"), "bad");
  return false;
}

function applyMailCounts(result) {
  if (!result) return;
  if (typeof result.unread_mail === "number" && Array.isArray(state.mail)) {
    state.mail = state.mail.map((entry) => (entry.connection_id === mailSchool() ? Object.assign({}, entry, { unread: result.unread_mail }) : entry));
  }
  const folders = mailFolderState();
  if (folders && Array.isArray(folders.folders) && result.folder && typeof result.unread === "number") {
    const next = Object.assign({}, state.mailFolders);
    next[mailSchool()] = { folders: folders.folders.map((folder) => (folder.id === result.folder ? Object.assign({}, folder, { unread: result.unread, total: result.total }) : folder)) };
    state.mailFolders = next;
  }
}

async function mailRun(list, path, extra, okKey) {
  state.mailBusy = true;
  rerender();
  let done = true;
  try {
    for (const group of mailGroups(list)) {
      const result = await mailPost(path, Object.assign({}, extra || {}, {
        connection_id: group.connection,
        folder: group.folder,
        uids: group.entries.map((entry) => entry.uid),
        expect: mailExpect(group.entries),
      }));
      applyMailCounts(result);
      if (!mailOutcome(result, null)) done = false;
    }
  } catch (error) {
    done = false;
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  state.mailBusy = false;
  if (done && okKey) toast(t(okKey), "good");
  state.mailSelectMode = false;
  state.mailSelected = [];
  if (state.mailDetail && list.some((entry) => mailKey(entry) === mailKey(state.mailDetail.entry)) && path !== "api/mail/flag") state.mailDetail = null;
  rerender();
  loadMailFolders();
  loadMailList(false);
  return done;
}

function mailBulkFlag(list, flag, on) {
  for (const entry of list) {
    if (flag === "seen") entry.unread = !on;
    if (flag === "flagged") entry.flagged = on;
  }
  return mailRun(list, "api/mail/flag", { flag, on }, null);
}

function mailArchive(list) {
  return mailRun(list, "api/mail/archive", {}, "mail.toast.archived");
}

function mailIsTrash(folderId) {
  const folder = mailFolderOf(folderId);
  return !!folder && folder.role === "trash";
}

async function mailTrash(list) {
  const inTrash = list.every((entry) => mailIsTrash(entry.folder || mailFolderId()));
  if (!inTrash) return mailRun(list, "api/mail/trash", {}, "mail.toast.trashed");
  const ok = await confirmAction({
    title: t("mail.delete.title"),
    text: tCount("mail.delete.text", list.length),
    confirmLabel: t("mail.delete.confirm"),
    destructive: true,
  });
  if (!ok) return false;
  return mailRun(list, "api/mail/trash", { confirmed: true }, "mail.toast.deleted");
}

function mailIsJunk(folderId) {
  const folder = mailFolderOf(folderId);
  return !!folder && folder.junk === true;
}

function mailJunkKnown() {
  return mailFolderList().some((folder) => folder.junk === true);
}

function mailSpamTool(folderId, make, own) {
  if (!mailJunkKnown()) return null;
  if (mailIsJunk(folderId)) return make("inbox", t("mail.action.notSpam"), (list) => mailNotSpam(own ? [own] : list), "mail-act-notspam");
  return make("alert", t("mail.action.spam"), (list) => mailSpam(own ? [own] : list), "mail-act-spam");
}

async function mailSpam(list) {
  const ok = await confirmAction({
    title: t("mail.spam.title"),
    text: tCount("mail.spam.text", list.length),
    confirmLabel: t("mail.spam.confirm"),
  });
  if (!ok) return false;
  state.mailBusy = true;
  rerender();
  const undo = [];
  let done = true;
  try {
    for (const group of mailGroups(list)) {
      const result = await mailPost("api/mail/spam", {
        connection_id: group.connection,
        folder: group.folder,
        uids: group.entries.map((entry) => entry.uid),
        expect: mailExpect(group.entries),
        confirmed: true,
      }, MAIL_SPAM_TIMEOUT_MS);
      applyMailCounts(result);
      if (!mailOutcome(result, null)) done = false;
      const restore = result && result.restore;
      if (restore && Array.isArray(restore.uids) && restore.uids.length) undo.push({ connection: group.connection, folder: restore.folder, uids: restore.uids, target: restore.target });
    }
  } catch (error) {
    done = false;
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.spam.unclear"), "bad");
  }
  state.mailBusy = false;
  state.mailSelectMode = false;
  state.mailSelected = [];
  if (state.mailDetail && list.some((entry) => mailKey(entry) === mailKey(state.mailDetail.entry))) state.mailDetail = null;
  state.mailSpamUndo = undo.length ? undo : null;
  if (done) toast(t("mail.toast.spam"), "good");
  rerender();
  loadMailFolders();
  loadMailList(false);
  return done;
}

async function undoMailSpam() {
  const undo = state.mailSpamUndo;
  if (!undo || state.mailBusy) return;
  state.mailSpamUndo = null;
  state.mailBusy = true;
  rerender();
  let done = true;
  try {
    for (const entry of undo) {
      const result = await mailPost("api/mail/move", { connection_id: entry.connection, folder: entry.folder, uids: entry.uids, target: entry.target }, MAIL_SPAM_TIMEOUT_MS);
      applyMailCounts(result);
      if (!mailOutcome(result, null)) done = false;
    }
  } catch (error) {
    done = false;
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  state.mailBusy = false;
  if (done) toast(t("mail.toast.spamUndone"), "good");
  rerender();
  loadMailFolders();
  loadMailList(false);
}

function mailNotSpam(list) {
  const inbox = mailFolderList().find((folder) => folder.role === "inbox");
  if (!inbox) return Promise.resolve(false);
  return mailRun(list, "api/mail/move", { target: inbox.id }, "mail.toast.notSpam");
}

function mailSpamNotice() {
  if (!state.mailSpamUndo) return null;
  return el("div", { class: "mail-notice mail-spam-notice", role: "status" }, [el("div", { class: "mail-notice-row" }, [
    el("span", { class: "mail-notice-text" }, t("mail.spam.moved")),
    el("button", { class: "btn ghost slim mail-spam-undo", type: "button", disabled: state.mailBusy ? "" : null, onclick: undoMailSpam }, [icon("restore", 16), t("mail.spam.undo")]),
  ])]);
}

function mailMoveSheet(list) {
  const sources = new Set(list.map((entry) => entry.folder || mailFolderId()));
  const targets = mailFolderList().filter((folder) => !(sources.size === 1 && sources.has(folder.id)));
  return sheet(t("mail.action.move"), [el("div", { class: "rows mail-move-targets" }, targets.map((folder) => el("button", {
    class: "setting-row",
    type: "button",
    "data-folder": folder.id,
    onclick: () => {
      dropSheet();
      mailRun(list, "api/mail/move", { target: folder.id }, "mail.toast.moved");
    },
  }, [
    el("span", { class: "nav-ico" }, [icon(MAIL_ROLE_ICONS[folder.role] || "folder", 18)]),
    iservText("span", { class: "lbl" }, mailFolderLabel(folder)),
  ])))]);
}

function mailFilterSheet() {
  const draft = sheetState(() => Object.assign({ status: "", order: "newest", scope: "all", since: "", until: "", tag: "", everywhere: false }, mailFilter()));
  const chips = (values, current, labelOf, onPick) => el("div", { class: "chipbar wrap" }, values.map((value) => el("button", {
    class: "chip",
    type: "button",
    "aria-pressed": String(current === value),
    onclick: () => { onPick(value); rerender(); },
  }, labelOf(value))));
  const apply = el("button", {
    class: "btn mail-filter-apply",
    type: "button",
    onclick: () => {
      state.mailFilter = Object.assign({}, mailFilter(), draft);
      state.mailList = null;
      discardSheet();
      rerender();
      loadMailList(false);
    },
  }, t("mail.filter.apply"));
  const reset = el("button", {
    class: "btn ghost",
    type: "button",
    onclick: () => {
      state.mailFilter = {};
      state.mailList = null;
      discardSheet();
      rerender();
      loadMailList(false);
    },
  }, t("mail.filter.reset"));
  const dateInput = (label, key) => {
    const input = el("input", { class: "inp", type: "date", value: draft[key] || "" });
    input.addEventListener("change", () => { draft[key] = input.value; });
    return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
  };
  const known = mailTagList();
  const tagInput = known.length
    ? chips([""].concat(known.map((tag) => tag.id)), draft.tag || "", (value) => (value ? (mailTagOf(value) || {}).name || value : t("mail.filter.status.all")), (value) => { draft.tag = value; })
    : el("input", { class: "inp", type: "text", value: draft.tag || "", autocomplete: "off", dir: "auto" });
  if (!known.length) tagInput.addEventListener("input", () => { draft.tag = tagInput.value.trim(); });
  const everywhere = el("input", { type: "checkbox", class: "mail-everywhere" });
  everywhere.checked = !!draft.everywhere;
  everywhere.addEventListener("change", () => { draft.everywhere = everywhere.checked; });
  return sheet(t("mail.filter.title"), [
    el("div", { class: "field" }, [el("span", { class: "lbl" }, t("mail.filter.status")), chips(MAIL_STATUS_FILTERS, draft.status || "", (value) => t(`mail.filter.status.${value || "all"}`), (value) => { draft.status = value; })]),
    el("div", { class: "field" }, [el("span", { class: "lbl" }, t("mail.filter.order")), chips(MAIL_ORDERS, draft.order || "newest", (value) => t(`mail.filter.order.${value}`), (value) => { draft.order = value; })]),
    el("div", { class: "field" }, [el("span", { class: "lbl" }, t("mail.filter.scope")), chips(MAIL_SCOPES, draft.scope || "all", (value) => t(`mail.filter.scope.${value}`), (value) => { draft.scope = value; })]),
    dateInput(t("mail.filter.since"), "since"),
    dateInput(t("mail.filter.until"), "until"),
    el(known.length ? "div" : "label", { class: "field" }, [el("span", { class: "lbl" }, t("mail.filter.tag")), tagInput]),
    el("label", { class: "check-row" }, [everywhere, el("span", {}, t("mail.filter.everywhere"))]),
  ], [el("div", { class: "btn-stack" }, [apply, reset])]);
}

function mailFoldersSheet() {
  const draft = sheetState(() => ({ name: "", busy: false }));
  const rows = mailFolderList().map((folder) => {
    const own = folder.role === "folder";
    return el("div", { class: "setting-row mail-folder-row", "data-folder": folder.id }, [
      el("span", { class: "nav-ico" }, [icon(MAIL_ROLE_ICONS[folder.role] || "folder", 18)]),
      el("span", { class: "lbl" }, [
        iservText("span", {}, mailFolderLabel(folder)),
        el("small", { class: "mail-folder-counts" }, folder.total === null || folder.total === undefined ? t("mail.folders.countUnknown") : tCount("mail.count", Number(folder.total))),
      ]),
      own ? el("button", { class: "icon-btn mail-folder-rename", type: "button", "aria-label": t("mail.folders.rename"), onclick: () => renameMailFolder(folder) }, [icon("edit", 16)]) : null,
      own ? el("button", { class: "icon-btn mail-folder-delete", type: "button", "aria-label": t("mail.folders.delete"), onclick: () => deleteMailFolder(folder) }, [icon("trash", 16)]) : null,
    ]);
  });
  const input = el("input", { class: "inp mail-folder-name", type: "text", value: draft.name, autocomplete: "off", dir: "auto", maxlength: "120" });
  const create = el("button", {
    class: "btn mail-folder-create",
    type: "button",
    disabled: draft.name.trim() && !draft.busy ? null : "",
    onclick: () => createMailFolder(draft),
  }, t("mail.folders.create"));
  input.addEventListener("input", () => {
    draft.name = input.value;
    create.disabled = !draft.name.trim();
  });
  return sheet(t("mail.folders.title"), [
    el("div", { class: "rows" }, rows),
    el("label", { class: "field mail-folder-new" }, [el("span", { class: "lbl" }, t("mail.folders.newName")), input]),
  ], [el("div", { class: "btn-stack" }, [create])]);
}

async function mailFolderAction(path, body, okKey) {
  try {
    const result = await mailPost(path, Object.assign({ connection_id: mailSchool() }, body));
    if (result && result.ok) {
      const next = Object.assign({}, state.mailFolders);
      next[mailSchool()] = { folders: Array.isArray(result.folders) ? result.folders : mailFolderList() };
      state.mailFolders = next;
      toast(t(okKey), "good");
      return result;
    }
    toast(apiMessage(result || {}, "mail.toast.failed"), "bad");
  } catch (error) {
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  return null;
}

async function createMailFolder(draft) {
  draft.busy = true;
  const result = await mailFolderAction("api/mail/folder/create", { name: draft.name.trim() }, "mail.folders.created");
  draft.busy = false;
  if (result) {
    resetSheetForm();
    discardSheet();
  }
  rerender();
}

async function renameMailFolder(folder) {
  dropSheet();
  openSheet(() => mailRenameSheet(folder));
}

function mailRenameSheet(folder) {
  const draft = sheetState(() => ({ name: folder.name || "" }));
  const input = el("input", { class: "inp", type: "text", value: draft.name, autocomplete: "off", dir: "auto", maxlength: "120" });
  input.addEventListener("input", () => { draft.name = input.value; });
  return sheet(t("mail.folders.rename"), [el("label", { class: "field" }, [el("span", { class: "lbl" }, t("mail.folders.newName")), input])], [
    el("div", { class: "btn-stack" }, [el("button", {
      class: "btn",
      type: "button",
      onclick: async () => {
        const result = await mailFolderAction("api/mail/folder/rename", { folder: folder.id, name: draft.name.trim() }, "mail.folders.renamed");
        if (!result) return;
        if (state.mailFolder === folder.id) state.mailFolder = result.folder;
        discardSheet();
        rerender();
      },
    }, t("common.save"))]),
  ]);
}

async function deleteMailFolder(folder) {
  const ok = await confirmAction({
    title: t("mail.folders.deleteTitle"),
    text: t("mail.folders.deleteText", { name: mailFolderLabel(folder) }),
    confirmLabel: t("mail.folders.delete"),
    destructive: true,
  });
  if (!ok) return;
  const result = await mailFolderAction("api/mail/folder/delete", { folder: folder.id, confirmed: true }, "mail.folders.deleted");
  if (result && state.mailFolder === folder.id) {
    state.mailFolder = "";
    state.mailList = null;
  }
  dropSheet();
  rerender();
  if (result) loadMailList(false);
}

function mailEntryAt(entry, step) {
  const list = state.mailList && Array.isArray(state.mailList.messages) ? state.mailList.messages : [];
  const index = list.findIndex((item) => mailKey(item) === mailKey(entry));
  if (index < 0) return null;
  return list[index + step] || null;
}

async function openMail(entry, origin) {
  const connection = entry.connection || mailSchool();
  entry.connection = connection;
  const pending = { entry, loading: true, origin: origin || null, connection };
  state.mailDetail = pending;
  state.mailShowText = false;
  dropSheet();
  render();
  const folder = entry.folder || mailFolderId();
  try {
    const detail = await getJson(`api/mail/message?${connectionQuery(connection, { folder, uid: entry.uid })}`);
    if (state.mailDetail !== pending) return;
    if (detail.message_id && !entry.message_id) entry.message_id = detail.message_id;
    state.mailDetail = { entry, detail, origin: origin || null, connection };
    if (detail.unread) markMailSeen(entry, folder);
  } catch (error) {
    if (handleApiFailure(error, mailSchool())) return;
    if (state.mailDetail !== pending) return;
    state.mailDetail = { entry, error: errorCode(error), body: (error && error.body) || null, origin: origin || null, connection };
  }
  rerender();
}

function markMailSeen(entry, folder) {
  const wasUnread = entry.unread;
  entry.unread = false;
  mailPost("api/mail/seen", { connection_id: entry.connection, folder, uid: entry.uid, expect: mailExpect([entry]) })
    .then((result) => {
      if (result && result.ok) {
        applyMailCounts(result);
        if (state.mailDetail && state.mailDetail.detail) state.mailDetail.detail.unread = false;
      } else {
        entry.unread = wasUnread;
      }
      rerender();
    })
    .catch((error) => {
      entry.unread = wasUnread;
      routeOrIgnoreBackgroundFailure(error);
      rerender();
    });
}

function leaveMailDetail() {
  const origin = state.mailDetail && state.mailDetail.origin;
  state.mailDetail = null;
  if (origin === OVERVIEW_ORIGIN) setView("overview", { keepAnchor: true });
  else rerender();
}

function mailAddressLine(label, list, collapsed, className) {
  const names = (Array.isArray(list) ? list : []).map((entry) => (entry.name && entry.address ? `${entry.name} <${entry.address}>` : entry.name || entry.address));
  if (!names.length) return null;
  const shown = collapsed && names.length > 3 ? names.slice(0, 3).join(", ") : names.join(", ");
  const nodes = [el("span", { class: "mail-addr-label" }, label), iservText("span", { class: "mail-addr-list" }, shown)];
  if (collapsed && names.length > 3) {
    nodes.push(el("button", { class: "link-btn mail-addr-more", type: "button", onclick: () => { state.mailAddressesOpen = true; rerender(); } }, tCount("mail.people.showAll", names.length - 3)));
  }
  return el("div", { class: `mail-addr ${className || ""}`.trim() }, nodes);
}

function mailAttachmentFiles(detail, folder, connection) {
  return (detail.attachments || []).map((part) => Object.assign({}, part, {
    url: `api/mail/attachment?${connectionQuery(connection || mailSchool(), { folder, uid: detail.uid, part: part.id })}`,
  }));
}

function mailFrameTheme() {
  if (state.theme === "dark" || state.theme === "light") return state.theme;
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function mailBodyFrame(detail, folder, connection) {
  return el("iframe", {
    class: "mail-frame",
    sandbox: "allow-popups allow-popups-to-escape-sandbox",
    referrerpolicy: "no-referrer",
    title: t("mail.body"),
    src: `api/mail/body?${connectionQuery(connection || mailSchool(), { folder, uid: detail.uid, theme: mailFrameTheme() })}`,
  });
}

const MAIL_SAFE_TAGS = new Set(["p", "br", "b", "strong", "i", "em", "u", "s", "ul", "ol", "li", "blockquote", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "code", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "hr", "a", "small", "sub", "sup"]);
const MAIL_DROPPED_TAGS = new Set(["script", "style", "template", "noscript", "iframe", "object", "embed", "svg", "math", "textarea", "title", "head", "img", "video", "audio", "picture", "source", "form", "input", "button", "select", "link", "meta", "base"]);

function safeMailNodes(html, target) {
  const doc = target || document;
  const parsed = new DOMParser().parseFromString(String(html || ""), "text/html");
  const out = doc.createDocumentFragment();
  const copy = (node, parent) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        parent.append(doc.createTextNode(child.textContent));
        continue;
      }
      if (child.nodeType !== 1) continue;
      const tag = child.tagName.toLowerCase();
      if (MAIL_DROPPED_TAGS.has(tag)) continue;
      if (!MAIL_SAFE_TAGS.has(tag)) {
        copy(child, parent);
        continue;
      }
      const made = doc.createElement(tag);
      if (tag === "a") {
        const href = String(child.getAttribute("href") || "").trim();
        if (/^(https?:\/\/|mailto:)/i.test(href)) {
          made.setAttribute("href", href);
          made.setAttribute("rel", "noopener noreferrer");
          made.setAttribute("target", "_blank");
        }
      }
      copy(child, made);
      parent.append(made);
    }
  };
  if (parsed.body) copy(parsed.body, out);
  return out;
}

function mailDetailActions(entry, detail) {
  const folder = detail.folder || entry.folder || mailFolderId();
  const own = Object.assign({}, entry, { folder });
  const drafts = (mailFolderOf(folder) || {}).role === "drafts";
  const tool = (iconName, label, run, className, pressed) => el("button", {
    class: `icon-btn mail-act ${className}`,
    type: "button",
    "aria-label": label,
    title: label,
    "aria-pressed": pressed === undefined ? null : String(pressed),
    onclick: run,
  }, [icon(iconName, 18)]);
  return el("div", { class: "mail-detail-tools" }, [
    drafts
      ? el("button", { class: "btn ghost slim mail-edit-draft", type: "button", onclick: () => openMailCompose("draft", own) }, [icon("edit", 16), t("mail.action.editDraft")])
      : el("div", { class: "mail-reply-row" }, [
        el("button", { class: "btn ghost slim mail-reply", type: "button", onclick: () => openMailCompose("reply", own) }, [el("span", { class: "dir-icon" }, [icon("reply", 16)]), t("mail.action.reply")]),
        el("button", { class: "btn ghost slim mail-reply-all", type: "button", onclick: () => openMailCompose("reply_all", own) }, t("mail.action.replyAll")),
        el("button", { class: "btn ghost slim mail-forward", type: "button", onclick: () => openMailCompose("forward", own) }, [el("span", { class: "dir-icon" }, [icon("forward", 16)]), t("mail.action.forward")]),
      ]),
    el("div", { class: "mail-tool-row" }, [
      tool("star", t(detail.flagged ? "mail.action.unflag" : "mail.action.flag"), () => { detail.flagged = !detail.flagged; mailBulkFlag([own], "flagged", detail.flagged); }, "mail-act-flag", !!detail.flagged),
      tool("inbox", t("mail.action.markUnread"), () => { mailBulkFlag([own], "seen", false); state.mailDetail = null; rerender(); }, "mail-act-unread"),
      tool("folder", t("mail.action.move"), () => openSheet(() => mailMoveSheet([own])), "mail-act-move"),
      tool("archive", t("mail.action.archive"), () => mailArchive([own]), "mail-act-archive"),
      mailSpamTool(folder, tool, own),
      tool("trash", t("mail.action.trash"), () => mailTrash([own]), "mail-act-trash"),
      tool("more", t("mail.action.more"), () => openSheet(() => mailMoreSheet(own, detail)), "mail-act-more"),
    ]),
  ]);
}

function mailMoreSheet(entry, detail) {
  const row = (iconName, label, run, className) => el("button", { class: `setting-row ${className}`, type: "button", onclick: () => { dropSheet(); run(); } }, [
    el("span", { class: "nav-ico" }, [icon(iconName, 18)]),
    el("span", { class: "lbl" }, label),
  ]);
  const formatted = Boolean(detail.body_html);
  return sheet(detail.subject || t("mail.noSubject"), [el("div", { class: "rows" }, [
    formatted ? row("letters", t(state.mailShowText ? "mail.view.formatted" : "mail.view.text"), () => { state.mailShowText = !state.mailShowText; rerender(); }, "mail-toggle-text") : null,
    row("star", t("mail.tags.title"), () => openSheet(() => mailTagSheet(entry, detail)), "mail-tags"),
    row("calendarAdd", t("mail.event.title"), () => openSheet(() => mailEventSheet(entry, detail)), "mail-event"),
    row("code", t("mail.view.source"), () => openMailSource(entry, detail), "mail-source"),
    row("print", t("mail.view.print"), () => printMail(detail), "mail-print"),
    row("copy", t("mail.action.openAsCopy"), () => openMailCompose("draft", entry, true), "mail-copy"),
  ])]);
}

async function openMailSource(entry, detail) {
  try {
    const answer = await getJson(`api/mail/source?${connectionQuery(entry.connection || mailSchool(), { folder: detail.folder || entry.folder, uid: detail.uid })}`);
    openSheet(() => sheet(t("mail.view.source"), [
      answer.cut ? noteBlock(t("mail.view.sourceCut")) : null,
      el("pre", { class: "mail-source-text", dir: "ltr" }, answer.source || ""),
    ]));
  } catch (error) {
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
}

function mailPrintPage(detail) {
  const page = document.implementation.createHTMLDocument("");
  const body = page.createElement("div");
  const line = (label, list) => {
    const names = mailPeople(list).join(", ");
    if (!names) return;
    const row = page.createElement("p");
    row.append(page.createTextNode(`${label}: ${names}`));
    body.append(row);
  };
  const title = page.createElement("h1");
  title.append(page.createTextNode(detail.subject || t("mail.noSubject")));
  body.append(title);
  line(t("mail.from"), detail.from);
  line(t("mail.to"), detail.to);
  line(t("mail.cc"), detail.cc);
  const when = page.createElement("p");
  when.append(page.createTextNode(`${t("mail.date")}: ${formatIsoMoment(detail.date)}`));
  body.append(when, page.createElement("hr"));
  if (detail.body_html) body.append(safeMailNodes(detail.body_html, page));
  else {
    const text = page.createElement("pre");
    text.append(page.createTextNode(detail.body_text || ""));
    body.append(text);
  }
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(detail.subject || "")}</title>` +
    "<style>body{font:14px/1.5 system-ui,sans-serif;margin:24px}pre{white-space:pre-wrap;font:inherit}h1{font-size:18px}</style>" +
    `</head><body>${body.innerHTML}</body></html>`;
}

async function printMail(detail) {
  const ok = await printInFrame(new Blob([mailPrintPage(detail)], { type: "text/html" }));
  if (!ok) toast(t("attachment.print.failed"), "bad");
}

function mailReceiptBlock(entry, detail) {
  const asked = Array.isArray(detail.receipt_to) && detail.receipt_to.length;
  const done = Array.isArray(detail.tags) && detail.tags.includes(MAIL_RECEIPT_DONE);
  const folder = mailFolderOf(detail.folder);
  if (!asked || done || (folder && (folder.role === "sent" || folder.role === "drafts"))) return null;
  const answer = async (send) => {
    if (send) {
      const target = (detail.receipt_to || []).map((entry) => (entry.name ? `${entry.name} <${entry.address}>` : entry.address)).join(", ");
      const ok = await confirmAction({ title: t("mail.receipt.confirmTitle"), text: t("mail.receipt.confirmText", { name: target }), confirmLabel: t("mail.receipt.send") });
      if (!ok) return;
    }
    if (!detail.receiptRequest) detail.receiptRequest = newMailRequestId();
    try {
      const result = await mailPost("api/mail/receipt", {
        connection_id: entry.connection || mailSchool(),
        folder: detail.folder, uid: detail.uid, send, confirmed: send, request_id: detail.receiptRequest, expect: mailExpect([entry]),
      }, MAIL_SMTP_TIMEOUT_MS);
      if (mailOutcome(result, send ? "mail.receipt.sent" : "mail.receipt.declined")) {
        detail.tags = (detail.tags || []).concat([MAIL_RECEIPT_DONE]);
        rerender();
      }
    } catch (error) {
      if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
    }
  };
  return el("div", { class: "card mail-receipt" }, [
    el("p", {}, t("mail.receipt.asked", { name: mailPeople(detail.receipt_to).join(", ") })),
    el("div", { class: "mail-reply-row" }, [
      el("button", { class: "btn slim mail-receipt-send", type: "button", onclick: () => answer(true) }, t("mail.receipt.send")),
      el("button", { class: "btn ghost slim mail-receipt-decline", type: "button", onclick: () => answer(false) }, t("mail.receipt.decline")),
    ]),
  ]);
}

function mailStepButtons(entry) {
  const previous = mailEntryAt(entry, -1);
  const next = mailEntryAt(entry, 1);
  if (!previous && !next) return null;
  return el("div", { class: "mail-steps" }, [
    el("button", { class: "btn ghost slim mail-prev", type: "button", disabled: previous ? null : "", onclick: () => previous && openMail(previous, state.mailDetail && state.mailDetail.origin) }, [el("span", { class: "chev-prev" }, [icon("chevron", 16)]), t("mail.previous")]),
    el("button", { class: "btn ghost slim mail-next", type: "button", disabled: next ? null : "", onclick: () => next && openMail(next, state.mailDetail && state.mailDetail.origin) }, [t("mail.next"), el("span", { class: "chev-next" }, [icon("chevron", 16)])]),
  ]);
}

function mailDetailView() {
  const { entry, detail, loading, error, body } = state.mailDetail;
  const view = el("div", { class: "mail-detail" });
  const meta = [mailPeopleShort(entry.from), formatIsoMoment(entry.date)].filter(Boolean).join(" · ");
  if (meta && !detail) view.append(el("div", { class: "row-meta mail-detail-meta" }, meta));
  if (loading) {
    view.append(loadingBlock());
    return view;
  }
  if (error || !detail) {
    view.append(mailFailureBlock({ error, body }, () => openMail(entry, state.mailDetail && state.mailDetail.origin)));
    return view;
  }
  const open = !!state.mailAddressesOpen;
  view.append(el("div", { class: "card mail-head" }, [
    iservText("h2", { class: "mail-subject-head" }, detail.subject || t("mail.noSubject")),
    (detail.tags || []).some((tag) => mailTagOf(tag)) ? el("div", { class: "row-tags" }, detail.tags.filter((tag) => mailTagOf(tag)).map(mailTagChip)) : null,
    mailAddressLine(t("mail.from"), detail.from, false, "mail-from"),
    mailAddressLine(t("mail.to"), detail.to, !open, "mail-to"),
    mailAddressLine(t("mail.cc"), detail.cc, !open, "mail-cc"),
    mailAddressLine(t("mail.bcc"), detail.bcc, !open, "mail-bcc"),
    el("div", { class: "mail-addr mail-date" }, [el("span", { class: "mail-addr-label" }, t("mail.date")), el("span", {}, formatIsoMoment(detail.date))]),
  ]));
  view.append(mailDetailActions(entry, detail));
  const receipt = mailReceiptBlock(entry, detail);
  if (receipt) view.append(receipt);
  const textOnly = state.mailShowText || !detail.body_html;
  const text = detail.body_text || (detail.body_html ? htmlText(detail.body_html) : "");
  const folder = detail.folder || entry.folder || mailFolderId();
  view.append(el("div", { class: `card mail-body${textOnly ? "" : " framed"}` }, [textOnly
    ? el("div", { class: "body-text mail-text", dir: "auto" }, text)
    : mailBodyFrame(detail, folder, state.mailDetail.connection)]));
  const files = mailAttachmentFiles(detail, folder, state.mailDetail.connection);
  if (files.length) {
    view.append(el("div", { class: "section-head mail-attachments-head" }, [el("span", { class: "overline" }, t("common.attachments"))]));
    view.append(attachmentRows(files));
  }
  const steps = mailStepButtons(entry);
  if (steps) view.append(steps);
  return view;
}

function htmlText(html) {
  const parsed = new DOMParser().parseFromString(String(html || "").replace(/<(br|\/p|\/div|\/li|\/h\d)[^>]*>/gi, "$&\n"), "text/html");
  return parsed.body ? parsed.body.textContent || "" : "";
}

function mailDetailTitle() {
  const current = state.mailDetail;
  if (!current) return t("mail.title");
  const detail = current.detail || {};
  return detail.subject || current.entry.subject || t("mail.noSubject");
}

function mailComposeButton() {
  return el("button", { class: "icon-btn mail-compose-open", type: "button", "aria-label": t("mail.compose.new"), title: t("mail.compose.new"), onclick: () => openMailCompose("new") }, [icon("edit", 18)]);
}

