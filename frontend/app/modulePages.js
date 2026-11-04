const MODULE_PAGE_ERROR_KEYS = ["api.modulePages.unreadable", "api.modulePages.refused", "api.conferences.page.unknown"];

function modulePageOffers() {
  return MODULE_PAGE_NAMES.flatMap((slug) => accountSchools(slug).map((school) => ({
    slug,
    connection_id: school.connection_id,
    school: school.school,
  })));
}

function modulePageEntry() {
  const stack = state.modulePageStack || [];
  return stack.length ? stack[stack.length - 1] : null;
}

function modulePagesHeader() {
  const entry = modulePageEntry();
  if (!entry) return { text: t("nav.modulepages") };
  const title = (entry.data && entry.data.title) || entry.title;
  return { text: title, onBack: leaveModulePage };
}

function openModulePage(target) {
  const entry = { slug: target.slug, connection_id: target.connection_id, page: target.page || "", title: target.title, data: null, error: "" };
  state.modulePageStack = (state.modulePageStack || []).concat([entry]);
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
  loadModulePage(entry);
}

function leaveModulePage() {
  state.modulePageStack = (state.modulePageStack || []).slice(0, -1);
  state._scrollTop = true;
  rerender();
}

async function loadModulePage(entry) {
  const ticket = (entry.loadTicket || 0) + 1;
  entry.loadTicket = ticket;
  const query = `module=${encodeURIComponent(entry.slug)}&page=${encodeURIComponent(entry.page)}&connection=${encodeURIComponent(entry.connection_id)}`;
  try {
    const data = await getJson(`api/module-pages/page?${query}`);
    if (ticket !== entry.loadTicket) return;
    entry.data = data;
    entry.error = "";
    entry.stale = false;
  } catch (error) {
    if (ticket !== entry.loadTicket) return;
    if (handleApiFailure(error, entry.connection_id)) return;
    entry.errorKey = modulePageErrorKey(error);
    if (entry.data) entry.stale = true;
    else entry.error = errorCode(error) || "unknown";
  }
  if (state.view === "modulepages" && modulePageEntry() === entry) rerender();
}

function modulePageErrorKey(error) {
  const key = error && error.body ? error.body.message_key : "";
  return MODULE_PAGE_ERROR_KEYS.includes(key) ? key : "modulepages.error.text";
}

function refreshModulePage() {
  const entry = modulePageEntry();
  return entry ? loadModulePage(entry) : loadAccountModules();
}

function modulePageChild(entry, link) {
  return { slug: entry.slug, connection_id: entry.connection_id, page: link.page, title: link.label || entry.title };
}

function modulePageTableRow(entry, table, row) {
  const { title, lines } = pageRowParts(table, row, (header, value) => t("modulepages.cell", { header, value }));
  const link = row.links[0];
  const parts = [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      title ? iservText("div", { class: "row-title" }, title) : null,
      lines.length ? el("div", { class: "row-sub conference-lines" }, lines.map((line) => iservText("span", { class: "conference-line" }, line))) : null,
    ]),
  ];
  if (!link) return el("div", { class: "row read conference-row module-page-row" }, parts);
  parts.push(pageChevron());
  return el("button", { class: "row read conference-row module-page-row", type: "button", onclick: () => openModulePage(modulePageChild(entry, link)) }, parts);
}

function modulePageTable(entry, block) {
  const nodes = [];
  if (block.caption) nodes.push(el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, block.caption)]));
  const rows = block.rows.map((row) => modulePageTableRow(entry, block, row));
  if (rows.length) nodes.push(el("div", { class: "rows" }, rows));
  else if (!entry.data.hidden_forms) nodes.push(el("p", { class: "conference-text muted" }, t("conferences.page.noRows")));
  return nodes;
}

function moduleTaskDue(task) {
  const day = conferenceBookingDay(task.date);
  if (!day) return "";
  const when = task.time && task.time !== "00:00" ? t("conferences.booking.when", { day, time: task.time }) : day;
  return t("modulepages.todo.due", { date: when });
}

function moduleTaskRow(task) {
  const lines = [moduleTaskDue(task), task.description].filter(Boolean);
  return el("div", { class: "row read conference-row module-page-row" }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, task.summary || t("modulepages.todo.untitled")),
      lines.length ? el("div", { class: "row-sub conference-lines" }, lines.map((line) => iservText("span", { class: "conference-line" }, line))) : null,
    ]),
  ]);
}

function moduleTaskNodes(block) {
  if (!block.open.length && !block.done.length) return [emptyBlock("check", t("modulepages.todo.empty.title"), t("modulepages.todo.empty.text"))];
  const nodes = [];
  if (block.open.length) nodes.push(el("div", { class: "rows" }, block.open.map(moduleTaskRow)));
  if (block.done.length) {
    nodes.push(el("div", { class: "section-head conference-head" }, [el("span", { class: "overline" }, t("modulepages.todo.done"))]));
    nodes.push(el("div", { class: "rows" }, block.done.map(moduleTaskRow)));
  }
  return nodes;
}

function modulePageBlockNodes(entry, block) {
  const fixed = pageStaticBlock(block);
  if (fixed) return fixed;
  switch (block.kind) {
    case "links":
      return [el("div", { class: "rows" }, block.links.map((link) => pageLinkRow(link, () => openModulePage(modulePageChild(entry, link)))))];
    case "table":
      return modulePageTable(entry, block);
    case "tasks":
      return moduleTaskNodes(block);
    default:
      return [];
  }
}

function modulePageFailure(entry, key) {
  return emptyBlock("alert", t("modulepages.error.title"), t(key), retryButton(() => {
    entry.error = "";
    rerender();
    loadModulePage(entry);
  }));
}

function modulePageView(entry) {
  const view = el("div", { class: "conference-page" });
  if (entry.error) {
    view.append(modulePageFailure(entry, entry.errorKey || "modulepages.error.text"));
    return view;
  }
  if (!entry.data) {
    view.append(loadingBlock());
    return view;
  }
  if (entry.stale) view.append(conferenceNotice("warning", t(entry.errorKey)));
  const nodes = entry.data.blocks.flatMap((block) => modulePageBlockNodes(entry, block));
  if (!nodes.length && !entry.data.hidden_forms) {
    view.append(modulePageFailure(entry, "api.modulePages.unreadable"));
    return view;
  }
  view.append(...nodes);
  if (entry.data.hidden_forms) view.append(conferenceNotice("info", t("modulepages.formsHidden")));
  view.append(el("p", { class: "conference-text muted module-page-note" }, t("modulepages.readOnly")));
  return view;
}

function modulePageOfferRow(offer) {
  const tag = schoolTag(offer);
  const title = t(`modules.catalogue.${offer.slug}`);
  return el("button", {
    class: "row read conference-row module-page-row",
    type: "button",
    onclick: () => openModulePage(Object.assign({ title }, offer)),
  }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      tag ? el("div", { class: "row-tags" }, [tag]) : null,
      el("div", { class: "row-title" }, title),
    ]),
    pageChevron(),
  ]);
}

function modulePagesView() {
  const entry = modulePageEntry();
  if (entry) return modulePageView(entry);
  const view = el("div", {});
  if (state.accountModules === null) {
    view.append(state.accountModulesError
      ? accountFailureBlock(state.accountModulesError, () => { state.accountModulesError = null; rerender(); })
      : loadingBlock());
    if (!state.accountModulesError) autoLoad("accountModules", loadAccountModules);
    return view;
  }
  const offers = modulePageOffers();
  view.append(offers.length
    ? el("div", { class: "rows" }, offers.map(modulePageOfferRow))
    : emptyBlock("info", t("modulepages.none.title"), t("modulepages.none.text")));
  return view;
}
