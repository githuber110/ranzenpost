const ACCOUNT_MODULE_NAMES = ["file", "addressbook", "mailinglist"];
const FILES_ROOTS = ["own", "groups"];
const FILES_MAX_BYTES = 50 * 1024 * 1024;
const FILES_TOTAL_MAX_BYTES = 100 * 1024 * 1024;
const FILES_MAX_COUNT = 20;
const FILES_MEGABYTE = 1024 * 1024;
const FILES_UPLOAD_TIMEOUT_MS = 480000;

function accountSchools(name) {
  const listed = Array.isArray(state.accountModules) ? state.accountModules : [];
  return listed.filter((entry) => entry && entry.connection_id && (!name || entry[name] === true));
}

function accountModuleOffered(name) {
  if (state.accountModules === null) {
    if (name === "file") return state.view === "files";
    return state.view === "contacts";
  }
  return accountSchools(name).length > 0;
}

async function loadAccountModules() {
  const outcome = await reload("accountModules", () => getJson("api/account-modules"), Array.isArray(state.accountModules));
  if (!outcome) return;
  if (outcome.data) {
    state.accountModules = Array.isArray(outcome.data.schools) ? outcome.data.schools : [];
    state.accountModulesError = null;
  } else if (outcome.error) {
    state.accountModulesError = outcome;
  }
  if (state.view === "files" || state.view === "contacts" || state.view === "settings") rerender();
}

function accountSchoolChips(name, active, onPick, className) {
  const listed = accountSchools(name);
  if (listed.length < 2) return null;
  return el("div", { class: `chipbar school-filter ${className}`, role: "tablist" }, listed.map((entry) => el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "aria-selected": String(entry.connection_id === active),
    onclick: () => onPick(entry.connection_id),
  }, [iservText("span", { class: "chip-label" }, schoolShortName(entry.connection_id) || entry.school || schoolFullName(entry.connection_id))])));
}

function accountFailureBlock(failure, retry) {
  if (anyOutage()) return outageEmptyBlock();
  return emptyBlock("alert", t("files.error.title"), apiMessage((failure && failure.body) || {}, "files.error.text"), retryButton(retry));
}

function filesSchool() {
  const listed = accountSchools("file").map((entry) => entry.connection_id);
  if (state.filesSchool && listed.includes(state.filesSchool)) return state.filesSchool;
  return listed[0] || "";
}

function filesPath() {
  return state.filesPath || "own";
}

function filesTrail() {
  return Array.isArray(state.filesTrail) ? state.filesTrail : [];
}

function filesKey() {
  return JSON.stringify([filesSchool(), filesPath(), state.filesQuery || ""]);
}

function filesData() {
  const listing = state.filesListing;
  return listing && listing.key === filesKey() ? listing : null;
}

async function loadFiles() {
  const school = filesSchool();
  if (!school) return;
  const key = filesKey();
  const path = filesPath();
  const query = state.filesQuery || "";
  const kept = !!(state.filesListing && state.filesListing.key === key && state.filesListing.data);
  const url = query ? `api/files/search?${connectionQuery(school, { path, q: query })}` : `api/files?${connectionQuery(school, { path })}`;
  const outcome = await reload("filesListing", () => getJson(url), kept, school);
  if (!outcome || filesKey() !== key) return;
  if (outcome.data) state.filesListing = { key, data: outcome.data };
  else if (outcome.error) state.filesListing = { key, error: outcome.error, body: outcome.body, timedOut: outcome.timedOut };
  if (state.view === "files") rerender();
}

function refreshFiles() {
  return loadFiles();
}

function showFilesAt(path, trail) {
  state.filesPath = path;
  state.filesTrail = trail;
  state.filesQuery = "";
  state.filesFilter = "";
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
}

function setFilesSchool(id) {
  if (id === filesSchool()) return;
  state.filesSchool = id;
  showFilesAt("own", []);
}

function openFilesRoot(root) {
  if (root === filesPath() && !filesTrail().length && !state.filesQuery) return;
  showFilesAt(root, []);
}

function openFilesFolder(entry) {
  showFilesAt(entry.path, filesTrail().concat([{ name: entry.name, path: entry.path }]));
}

function filesUp() {
  if (state.filesQuery) {
    state.filesQuery = "";
    render();
    return;
  }
  const trail = filesTrail().slice(0, -1);
  const parent = trail.length ? trail[trail.length - 1].path : filesRootOf();
  showFilesAt(parent, trail);
}

function filesRootOf() {
  const data = filesData();
  const root = data && data.data ? data.data.root : "";
  if (FILES_ROOTS.includes(root)) return root;
  return FILES_ROOTS.includes(state.filesRoot) ? state.filesRoot : "own";
}

function filesHeader() {
  const trail = filesTrail();
  if (state.filesQuery) return { text: t("files.search.title", { query: state.filesQuery }), onBack: filesUp };
  if (trail.length) return { node: iservText("span", { class: "header-title" }, trail[trail.length - 1].name), onBack: filesUp };
  return { text: t("files.title") };
}

function filesRootBar() {
  const active = FILES_ROOTS.includes(filesPath()) ? filesPath() : filesRootOf();
  return el("div", { class: "chipbar segmented files-roots", role: "tablist" }, FILES_ROOTS.map((root) => el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "data-root": root,
    "aria-selected": String(root === active && !filesTrail().length && !state.filesQuery),
    onclick: () => { state.filesRoot = root; openFilesRoot(root); },
  }, [icon(root === "own" ? "folder" : "conferences", 14), el("span", { class: "chip-label" }, t(`files.root.${root}`))])));
}

function filesEntrySub(entry) {
  const parts = [];
  const facts = [entry.size_text, entry.kind !== "folder" ? entry.type_text : ""].filter(Boolean).join(" · ");
  const when = listMoment(entry.modified, entry.modified_text);
  if (facts) parts.push(iservText("span", {}, facts));
  if (facts && when) parts.push(" · ");
  if (when) parts.push(el("span", { class: "files-when" }, when));
  return parts.length ? el("div", { class: "row-sub" }, parts) : null;
}

function filesFolderRow(entry) {
  return el("button", { class: "row read list-row files-folder", type: "button", onclick: () => openFilesFolder(entry) }, [
    el("span", { class: "row-dot" }, [icon("folder", 14)]),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, entry.name), filesEntrySub(entry)]),
  ]);
}

function filesFileRow(entry, school) {
  const file = { filename: entry.name, url: `api/files/file?${connectionQuery(school, { path: entry.path })}` };
  const button = el("button", { class: "row read files-file", type: "button" }, [
    el("span", { class: "row-dot" }, [icon("clip", 14)]),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, entry.name), filesEntrySub(entry)]),
  ]);
  button.addEventListener("click", () => openNestedSheet(() => attachmentActionsSheet(file, button)));
  return button;
}

function filesMatches(entry, query) {
  return !query || String(entry.name || "").toLowerCase().includes(query);
}

function filesView() {
  const view = el("div", { class: "school-list files-view" });
  if (state.accountModules === null) {
    view.append(state.accountModulesError
      ? accountFailureBlock(state.accountModulesError, () => { state.accountModulesError = null; rerender(); loadAccountModules(); })
      : loadingBlock());
    if (!state.accountModulesError) autoLoad("accountModules", loadAccountModules);
    return view;
  }
  const school = filesSchool();
  if (!school) {
    view.append(emptyBlock("folder", t("files.none.title"), t("files.none.text")));
    return view;
  }
  const head = el("div", { class: "list-head files-head" });
  const schools = accountSchoolChips("file", school, setFilesSchool, "files-schools");
  if (schools) head.append(schools);
  head.append(filesRootBar());
  view.append(head);
  const listing = filesData();
  if (!listing) {
    autoLoad(`files:${filesKey()}`, loadFiles);
    view.append(loadingBlock());
    return view;
  }
  if (listing.error) {
    view.append(accountFailureBlock(listing, () => { state.filesListing = null; rerender(); }));
    return view;
  }
  const data = listing.data || {};
  const entries = Array.isArray(data.entries) ? data.entries.filter((entry) => entry && entry.path) : [];
  const note = refreshFailureNote("filesListing");
  if (note) head.append(note);
  const hits = el("span", { class: "search-hits" });
  const host = el("div", {});
  const searchAll = el("button", { class: "link-btn files-search-all", type: "button" }, t("files.search.everywhere"));
  const searchAllHost = el("div", { class: "files-search-more" });
  searchAll.addEventListener("click", () => {
    const query = String(state.filesFilter || "").trim();
    if (!query) return;
    state.filesQuery = query;
    state.filesFilter = "";
    render();
  });
  const renderBody = () => {
    const query = String(state.filesFilter || "").trim().toLowerCase();
    const shown = entries.filter((entry) => filesMatches(entry, query));
    hits.textContent = query ? tCount("common.hits", shown.length) : "";
    searchAllHost.replaceChildren(...(query && data.can_search && !state.filesQuery ? [searchAll] : []));
    if (!entries.length) {
      host.replaceChildren(state.filesQuery
        ? emptyBlock("search", t("files.search.emptyTitle"), t("files.search.emptyText"))
        : emptyBlock("folder", t("files.empty.title"), t("files.empty.text")));
      return;
    }
    if (!shown.length) {
      host.replaceChildren(emptyBlock("search", t("files.search.emptyTitle"), t("files.filter.emptyText")));
      return;
    }
    host.replaceChildren(el("div", { class: "rows files-rows" }, shown.map((entry) => (entry.kind === "folder" ? filesFolderRow(entry) : filesFileRow(entry, school)))));
  };
  head.append(searchField(state.filesFilter, t("files.search.placeholder"), (value) => {
    state.filesFilter = value;
    renderBody();
  }, hits));
  head.append(searchAllHost);
  view.append(host);
  renderBody();
  return view;
}

function filesUploadButton() {
  const listing = filesData();
  const data = listing && listing.data;
  if (!data || !data.can_upload || state.filesQuery) return null;
  return el("button", { class: "icon-btn files-upload", type: "button", "aria-label": t("files.upload.open"), title: t("files.upload.open"), onclick: () => openFilesUpload(data) }, [icon("plus", 18)]);
}

function filesUploadProblem(data, files) {
  if (!files.length) return "empty";
  if (files.some((file) => file.size > FILES_MAX_BYTES)) return "large";
  if (!data.upload_multiple && files.length > 1) return "one";
  if (files.length > FILES_MAX_COUNT) return "many";
  if (files.reduce((sum, file) => sum + (Number(file.size) || 0), 0) > FILES_TOTAL_MAX_BYTES) return "total";
  return "";
}

function filesUploadProblemNote(problem) {
  if (problem === "large") return noteBlock(t("api.files.upload.fileTooLarge", { max: formatNumber(FILES_MAX_BYTES / FILES_MEGABYTE) }));
  if (problem === "one") return noteBlock(t("api.files.upload.oneFile"));
  if (problem === "many") return noteBlock(t("api.files.upload.tooMany", { max: formatNumber(FILES_MAX_COUNT) }));
  if (problem === "total") return noteBlock(t("api.files.upload.tooLarge", { max: formatNumber(FILES_TOTAL_MAX_BYTES / FILES_MEGABYTE) }));
  return null;
}

function filesFolderName() {
  const trail = filesTrail();
  return trail.length ? trail[trail.length - 1].name : t("files.upload.rootFolder");
}

function openFilesUpload(data) {
  state.filesUpload = { files: [], preview: false, busy: false, failure: "", school: filesSchool(), path: filesPath(), data };
  openSheet(filesUploadSheet);
}

function filesUploadSheet() {
  const draft = state.filesUpload;
  if (!draft) return sheet(t("files.upload.title"), [noteBlock(t("api.files.upload.unavailable"))]);
  if (draft.preview) {
    const body = [
      iservText("p", { class: "dlg-text" }, t("files.upload.previewText", { folder: filesFolderName() })),
      el("div", { class: "rows" }, draft.files.map(({ name, size }) => el("div", { class: "row read disabled" }, attachmentRowContent(name, formatBytes(size))))),
      draft.failure ? noteBlock(draft.failure) : null,
    ].filter(Boolean);
    if (draft.unclear) return sheet(t("files.upload.title"), body);
    return sheet(t("files.upload.title"), body, [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn files-upload-send", type: "button", disabled: draft.busy ? "" : null, onclick: sendFilesUpload }, [draft.busy ? el("span", { class: "spin" }) : null, t("files.upload.send")]),
      el("button", { class: "btn ghost", type: "button", disabled: draft.busy ? "" : null, onclick: () => { draft.preview = false; draft.failure = ""; rerender(); } }, t("tasks.upload.back")),
    ])]);
  }
  const input = el("input", { type: "file", class: "files-upload-input", hidden: "" });
  if (draft.data.upload_multiple) input.multiple = true;
  if (draft.data.upload_accept) input.accept = draft.data.upload_accept;
  input.addEventListener("change", () => {
    const chosen = Array.from(input.files || []);
    draft.files = draft.data.upload_multiple ? draft.files.concat(chosen) : chosen.slice(0, 1);
    input.value = "";
    rerender();
  });
  const rows = draft.files.map((file, index) => {
    const fileLabel = file.name || "";
    const remove = el("button", { class: "search-clear", type: "button", "aria-label": t("tasks.upload.drop", { name: fileLabel }) }, [icon("close", 14)]);
    remove.addEventListener("click", () => {
      draft.files.splice(index, 1);
      rerender();
    });
    return el("div", { class: "row read disabled" }, [
      el("span", { class: "row-dot" }, [icon("clip", 14)]),
      el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, fileLabel), el("div", { class: "row-sub" }, formatBytes(file.size))]),
      remove,
    ]);
  });
  const problem = filesUploadProblem(draft.data, draft.files);
  const add = el("button", { class: "btn ghost slim files-upload-add", type: "button" }, [icon("plus", 14), t(draft.data.upload_multiple ? "tasks.upload.add" : "tasks.upload.choose")]);
  add.addEventListener("click", () => input.click());
  const body = [
    iservText("p", { class: "dlg-text" }, t("files.upload.text", { folder: filesFolderName() })),
    rows.length ? el("div", { class: "rows" }, rows) : null,
    problem === "empty" ? null : filesUploadProblemNote(problem),
    add,
    input,
  ].filter(Boolean);
  return sheet(t("files.upload.title"), body, [el("div", { class: "btn-stack" }, [
    el("button", { class: "btn files-upload-next", type: "button", disabled: problem ? "" : null, onclick: () => { if (!filesUploadProblem(draft.data, draft.files)) { draft.preview = true; rerender(); } } }, t("tasks.upload.next")),
  ])]);
}

async function sendFilesUpload() {
  const draft = state.filesUpload;
  if (!draft || draft.busy) return;
  draft.busy = true;
  draft.failure = "";
  rerender();
  let result = null;
  try {
    result = await postFormData("api/files/upload", { connection_id: draft.school, path: draft.path, confirmed: true }, draft.files, FILES_UPLOAD_TIMEOUT_MS);
  } catch (error) {
    draft.busy = false;
    if (handleApiFailure(error, draft.school)) return;
    draft.unclear = true;
    draft.failure = t("files.upload.timeout");
    rerender();
    loadFiles();
    return;
  }
  draft.busy = false;
  const done = !!(result && result.ok);
  toast(apiMessage(result || {}, done ? "api.files.upload.done" : "files.upload.failed"), done ? "good" : "bad");
  if (result && result.listing && draft.school === filesSchool() && draft.path === filesPath() && !state.filesQuery) {
    state.filesListing = { key: filesKey(), data: Object.assign({}, result.listing, { connection_id: draft.school }) };
  }
  if (!done && result && Array.isArray(result.errors) && result.errors.length) {
    draft.failure = result.errors.join(" ");
    draft.preview = true;
    rerender();
    return;
  }
  state.filesUpload = null;
  discardSheet();
  rerender();
}
