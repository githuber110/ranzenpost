const CONFERENCES_TAB_CURRENT = "current";
const CONFERENCES_TAB_ARCHIVE = "archive";
const CONFERENCE_PAGE_UNKNOWN_KEY = "api.conferences.page.unknown";
const CONFERENCE_SUBMIT_TIMEOUT_MS = 90000;
const CONFERENCE_DATE_IN_TEXT = /(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)/;

function conferencesLoadKey(tab) {
  return tab === CONFERENCES_TAB_ARCHIVE ? "conferencesArchive" : "conferences";
}

function conferencesData(archive) {
  return archive ? state.conferencesArchive : state.conferences;
}

function setConferencesData(archive, data) {
  if (archive) state.conferencesArchive = data;
  else state.conferences = data;
}

async function loadConferences(tab) {
  const archive = tab === CONFERENCES_TAB_ARCHIVE;
  const current = conferencesData(archive);
  const keep = !!(current && !current.error);
  const outcome = await reload(conferencesLoadKey(tab), () => getJson(archive ? "api/conferences?tab=archive" : "api/conferences"), keep);
  if (!outcome) return;
  if (outcome.data) setConferencesData(archive, outcome.data);
  else if (outcome.error) setConferencesData(archive, { error: outcome.error });
  if (state.view === "overview" || state.view === "conferences") rerender();
}

async function refreshConferencesView() {
  const entry = conferenceEntry();
  await Promise.all([loadConferences(state.conferencesTab), entry && entry.data ? reloadConferencePage(entry) : null]);
}

function conferenceCellDate(cell) {
  const text = String(cell || "").trim();
  const direct = parseAnyDate(text);
  if (direct) return direct;
  const match = CONFERENCE_DATE_IN_TEXT.exec(text);
  return match ? parseAnyDate(`${match[1]}.${match[2]}.${match[3]}`) : null;
}

function conferenceCells(item) {
  return (item.cells || []).map((cell) => String(cell || "").trim()).filter(Boolean);
}

function conferencesFolderChip(tab, iconName, label) {
  return el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "aria-selected": String(state.conferencesTab === tab),
    onclick: () => openConferencesFolder(tab),
  }, [icon(iconName, 14), el("span", {}, label)]);
}

function openConferencesFolder(tab) {
  if (tab === state.conferencesTab) return;
  state.conferencesTab = tab;
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
}

function conferencesFolderRow() {
  return el("div", { class: "chipbar segmented", role: "tablist" }, [
    conferencesFolderChip(CONFERENCES_TAB_CURRENT, "inbox", t("conferences.folder.current")),
    conferencesFolderChip(CONFERENCES_TAB_ARCHIVE, "archive", t("conferences.folder.archive")),
  ]);
}

function conferenceRowNode(item) {
  const cells = conferenceCells(item);
  if (!cells.length) return null;
  const openable = !!item.page;
  const tag = schoolTag(item);
  const main = el("div", { class: "row-main" }, [
    tag ? el("div", { class: "row-tags" }, [tag]) : null,
    iservText("div", { class: "row-title" }, cells[0]),
    cells.length > 1 ? iservText("div", { class: "row-sub" }, cells.slice(1).join(" · ")) : null,
  ]);
  const parts = [el("span", { class: "row-dot" }), main];
  if (!openable) return el("div", { class: "row read conference-row" }, parts);
  parts.push(el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]));
  return el("button", { class: "row read conference-row", type: "button", onclick: () => openConference(item) }, parts);
}

function conferencesListBody(data, archive) {
  const nodes = [];
  if (!data) {
    autoLoad(conferencesLoadKey(state.conferencesTab), () => loadConferences(state.conferencesTab));
    nodes.push(loadingBlock());
    return nodes;
  }
  if (data.error) {
    nodes.push(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("conferences.error.title"), t("conferences.error.text"), retryButton(() => {
        setConferencesData(archive, null);
        rerender();
      })));
    return nodes;
  }
  const note = refreshFailureNote(conferencesLoadKey(state.conferencesTab));
  if (note) nodes.push(note);
  const rows = (data.items || []).map(conferenceRowNode).filter(Boolean);
  if (data.empty || !rows.length) {
    nodes.push(archive
      ? emptyBlock("archive", t("conferences.archive.empty.title"), t("conferences.archive.empty.text"))
      : emptyBlock("conferences", t("conferences.empty.title"), t("conferences.empty.text")));
    return nodes;
  }
  nodes.push(el("div", { class: "rows" }, rows));
  return nodes;
}

function conferencesView() {
  if (conferenceEntry()) return conferencePageView();
  const view = el("div", {});
  view.append(el("div", { class: "list-head" }, [conferencesFolderRow()]));
  const archive = state.conferencesTab === CONFERENCES_TAB_ARCHIVE;
  view.append(...conferencesListBody(conferencesData(archive), archive));
  return view;
}

function conferenceEntry() {
  const detail = state.conferenceDetail;
  if (!detail || !detail.stack.length) return null;
  return detail.stack[detail.stack.length - 1];
}

function conferenceHeader() {
  const entry = conferenceEntry();
  if (!entry) return { text: t("conferences.title") };
  const title = (entry.data && entry.data.title) || entry.title || t("conferences.title");
  return { text: title, onBack: leaveConferencePage };
}

function openConferenceFromOverview(item) {
  rememberOverviewAnchor();
  setView("conferences");
  openConference(item, OVERVIEW_ORIGIN);
}

function openConference(item, origin) {
  const cells = conferenceCells(item);
  state.conferenceDetail = { stack: [], origin: origin || null };
  pushConferencePage({ page: item.page, connection_id: item.connection_id || "", title: cells[0] || "" });
}

function pushConferencePage(target, data) {
  const detail = state.conferenceDetail || { stack: [], origin: null };
  state.conferenceDetail = detail;
  const entry = {
    page: target.page,
    connection_id: target.connection_id || "",
    title: target.title || "",
    data: data || null,
    loading: !data,
    error: "",
    refused: false,
    values: {},
    outcome: null,
    sending: null,
  };
  detail.stack.push(entry);
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
  if (!data) loadConferencePage(entry);
}

async function loadConferencePage(entry) {
  entry.loading = true;
  try {
    const data = await getJson(`api/conferences/page?page=${encodeURIComponent(entry.page)}&connection=${encodeURIComponent(entry.connection_id)}`);
    entry.data = data;
    entry.error = "";
    entry.refused = false;
  } catch (error) {
    if (handleApiFailure(error, entry.connection_id)) return;
    entry.error = errorCode(error) || "unknown";
    entry.refused = !!(error && error.body && error.body.message_key === CONFERENCE_PAGE_UNKNOWN_KEY);
  }
  entry.loading = false;
  if (state.view === "conferences" && conferenceEntry() === entry) rerender();
}

async function reloadConferencePage(entry) {
  await loadConferencePage(entry);
}

function leaveConferencePage() {
  const detail = state.conferenceDetail;
  if (!detail) return;
  detail.stack.pop();
  if (detail.stack.length) {
    const entry = conferenceEntry();
    rerender();
    loadConferencePage(entry);
    return;
  }
  const origin = detail.origin;
  state.conferenceDetail = null;
  if (origin === OVERVIEW_ORIGIN) setView("overview", { keepAnchor: true });
  else rerender();
  loadConferences(state.conferencesTab);
}

function conferenceTarget(entry, link) {
  return { page: link.page, connection_id: entry.connection_id, title: link.label || "" };
}

function conferenceLinkRow(entry, link) {
  return el("button", { class: "row read conference-link", type: "button", onclick: () => pushConferencePage(conferenceTarget(entry, link)) }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, link.label || t("conferences.page.open"))]),
    el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]),
  ]);
}

function conferenceNotice(tone, text) {
  const tones = { success: "note good", error: "note bad", warning: "note", info: "note info" };
  return el("div", { class: tones[tone] || "note info", role: tone === "error" ? "alert" : "status" }, [
    icon(tone === "success" ? "check" : tone === "info" ? "info" : "alert", 16),
    iservText("span", {}, text),
  ]);
}

function conferenceTableRow(entry, table, row) {
  const cells = row.cells.map((cell) => String(cell || "").trim());
  const firstIndex = cells.findIndex(Boolean);
  const title = firstIndex >= 0 ? cells[firstIndex] : (row.links[0] && row.links[0].label) || "";
  const sub = cells
    .map((cell, index) => {
      if (!cell || index === firstIndex) return "";
      const header = String((table.headers || [])[index] || "").trim();
      return header ? `${header}: ${cell}` : cell;
    })
    .filter(Boolean)
    .join(" · ");
  const main = el("div", { class: "row-main" }, [
    title ? iservText("div", { class: "row-title" }, title) : null,
    sub ? iservText("div", { class: "row-sub" }, sub) : null,
  ]);
  const forms = row.forms.map((id) => entry.data.forms.find((form) => form.id === id)).filter(Boolean);
  if (forms.length) main.append(el("div", { class: "conference-row-actions" }, forms.flatMap((form) => conferenceRowActions(entry, form))));
  const link = row.links[0];
  if (link && !forms.length) {
    return el("button", { class: "row read conference-row", type: "button", onclick: () => pushConferencePage(conferenceTarget(entry, link)) }, [
      el("span", { class: "row-dot" }),
      main,
      el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]),
    ]);
  }
  const node = el("div", { class: "row read conference-row" }, [el("span", { class: "row-dot" }), main]);
  if (link) main.append(el("button", { class: "btn ghost slim", type: "button", onclick: () => pushConferencePage(conferenceTarget(entry, link)) }, link.label || t("conferences.page.open")));
  return node;
}

function conferenceRowActions(entry, form) {
  if (form.fields.length) {
    return [el("button", { class: "btn ghost slim", type: "button", onclick: () => openSheet(() => conferenceFormSheet(entry, form)) }, conferenceSubmitLabel(form.submits[0]))];
  }
  return form.submits.map((submit) => el("button", {
    class: "btn ghost slim",
    type: "button",
    disabled: entry.sending !== null ? "" : null,
    onclick: () => sendConferenceForm(entry, form, submit),
  }, [entry.sending === form.id ? el("span", { class: "spin" }) : null, conferenceSubmitLabel(submit)]));
}

function conferenceSubmitLabel(submit) {
  return (submit && submit.label) || t("conferences.form.send");
}

function conferenceTableView(entry, block) {
  const nodes = [];
  if (block.caption) nodes.push(el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, block.caption)]));
  const rows = block.rows.map((row) => conferenceTableRow(entry, block, row));
  nodes.push(rows.length ? el("div", { class: "rows" }, rows) : el("p", { class: "conference-text muted" }, t("conferences.page.noRows")));
  return nodes;
}

function conferenceBlockNodes(entry, block) {
  switch (block.kind) {
    case "notice":
      return [conferenceNotice(block.tone, block.text)];
    case "heading":
      return [el("div", { class: "section-head conference-head" }, [iservText("span", { class: "overline" }, block.text)])];
    case "text":
      return [iservText("p", { class: "conference-text" }, block.text)];
    case "facts":
      return [factList(block.facts.map((fact) => [fact.label, fact.value]))];
    case "links":
      return [el("div", { class: "rows" }, block.links.map((link) => conferenceLinkRow(entry, link)))];
    case "table":
      return conferenceTableView(entry, block);
    case "form": {
      const form = entry.data.forms.find((candidate) => candidate.id === block.form);
      return form ? [conferenceFormCard(entry, form)] : [];
    }
    default:
      return [];
  }
}

function conferencePageView() {
  const entry = conferenceEntry();
  const view = el("div", { class: "conference-page" });
  if (entry.outcome) view.append(conferenceOutcomeNode(entry.outcome));
  if (entry.loading && !entry.data) {
    view.append(loadingBlock());
    return view;
  }
  if (entry.refused) {
    view.append(noteBlock(t(CONFERENCE_PAGE_UNKNOWN_KEY)));
    return view;
  }
  if (entry.error && !entry.data) {
    view.append(emptyBlock("alert", t("conferences.page.error.title"), t("conferences.page.error.text"), retryButton(() => loadConferencePage(entry))));
    return view;
  }
  const blocks = (entry.data && entry.data.blocks) || [];
  const nodes = blocks.flatMap((block) => conferenceBlockNodes(entry, block));
  if (!nodes.length) nodes.push(emptyBlock("conferences", t("conferences.page.empty.title"), t("conferences.page.empty.text")));
  view.append(...nodes);
  return view;
}

function conferenceOutcomeNode(outcome) {
  const node = el("div", { class: outcome.tone === "good" ? "note good conference-outcome" : outcome.tone === "bad" ? "note bad conference-outcome" : "note conference-outcome", role: "status" }, [
    icon(outcome.tone === "good" ? "check" : "alert", 16),
    el("span", { class: "conference-outcome-body" }, [
      el("span", {}, outcome.text),
      ...(outcome.details || []).map((text) => iservText("span", { class: "conference-outcome-detail" }, text)),
    ]),
  ]);
  if (outcome.diagnosis && Object.keys(outcome.diagnosis).length) node.append(techDetailsButton(diagnosisEntries(outcome.diagnosis)));
  return node;
}

function conferenceValues(entry, form) {
  if (!entry.values[form.id]) {
    const values = {};
    for (const field of form.fields) values[field.key] = conferenceDefault(field);
    entry.values[form.id] = values;
  }
  return entry.values[form.id];
}

function conferenceDefault(field) {
  if (field.kind === "radio") {
    const chosen = field.options.find((option) => option.selected && !option.disabled);
    return chosen ? chosen.value : "";
  }
  if (field.kind === "select") {
    const chosen = field.options.filter((option) => option.selected && !option.disabled).map((option) => option.value);
    if (field.multiple) return chosen;
    if (chosen.length) return chosen[0];
    const first = field.options.find((option) => !option.disabled);
    return first ? first.value : "";
  }
  if (field.kind === "checkbox") return !!field.checked;
  return field.value || "";
}

function conferenceFieldId(form, field, suffix) {
  return `conf-${form.id}-${String(field.key).replace(/[^A-Za-z0-9_-]/g, "_")}${suffix || ""}`;
}

function conferenceChoiceList(form, field, values, multiple) {
  const name = conferenceFieldId(form, field);
  return el("div", { class: "field-group", role: multiple ? "group" : "radiogroup", "aria-label": field.label || field.name }, field.options.map((option) => {
    const input = el("input", { type: multiple ? "checkbox" : "radio", name, value: option.value });
    const current = values[field.key];
    input.checked = multiple ? Array.isArray(current) && current.includes(option.value) : current === option.value;
    if (option.disabled || field.disabled) input.disabled = true;
    input.addEventListener("change", () => {
      if (multiple) {
        const kept = (Array.isArray(values[field.key]) ? values[field.key] : []).filter((value) => value !== option.value);
        values[field.key] = input.checked ? kept.concat([option.value]) : kept;
      } else if (input.checked) {
        values[field.key] = option.value;
      }
    });
    return el("label", { class: option.disabled ? "cell check conference-choice off" : "cell check conference-choice" }, [
      input,
      iservText("span", {}, option.label || option.value),
    ]);
  }));
}

function conferenceFieldNode(form, field, values) {
  const label = field.label || field.name;
  const error = field.error ? iservText("span", { class: "err" }, field.error) : null;
  const caption = el("span", { class: "lbl" }, [iservText("span", {}, label), field.required ? el("span", { "aria-hidden": "true" }, " *") : null]);
  if (field.kind === "radio") return el("div", { class: "field" }, [caption, conferenceChoiceList(form, field, values, false), error]);
  if (field.kind === "select" && field.multiple) return el("div", { class: "field" }, [caption, conferenceChoiceList(form, field, values, true), error]);
  if (field.kind === "select") {
    const select = el("select", { class: error ? "sel bad" : "sel", id: conferenceFieldId(form, field), "aria-label": label });
    for (const option of field.options) {
      const node = el("option", { value: option.value }, option.group ? t("conferences.option.grouped", { group: option.group, label: option.label }) : option.label);
      if (option.disabled) node.disabled = true;
      if (String(option.value) === String(values[field.key])) node.selected = true;
      select.append(node);
    }
    if (field.disabled) select.disabled = true;
    select.addEventListener("change", () => { values[field.key] = select.value; });
    return el("label", { class: "field" }, [caption, el("div", { class: "sel-wrap" }, [select, el("span", { class: "caret", html: iconSvg("chevron", 14) })]), error]);
  }
  if (field.kind === "checkbox") {
    const box = el("input", { type: "checkbox", id: conferenceFieldId(form, field) });
    box.checked = !!values[field.key];
    if (field.disabled) box.disabled = true;
    box.addEventListener("change", () => { values[field.key] = box.checked; });
    return el("div", { class: "field" }, [el("div", { class: "field-group" }, [el("label", { class: "cell check" }, [box, iservText("span", {}, label)])]), error]);
  }
  const area = field.kind === "textarea";
  const input = el(area ? "textarea" : "input", {
    class: error ? (area ? "txt bad" : "inp bad") : area ? "txt" : "inp",
    id: conferenceFieldId(form, field),
    dir: "auto",
    "aria-label": label,
    type: area ? null : field.kind,
    rows: area ? "3" : null,
    maxlength: field.maxlength ? String(field.maxlength) : null,
    placeholder: field.placeholder || null,
    min: field.min || null,
    max: field.max || null,
    step: field.step || null,
  });
  input.value = values[field.key] || "";
  if (field.disabled) input.disabled = true;
  if (field.readonly) input.readOnly = true;
  input.addEventListener("input", () => { values[field.key] = input.value; });
  return el("label", { class: "field" }, [caption, input, error]);
}

function conferenceFormNodes(entry, form) {
  const values = conferenceValues(entry, form);
  const nodes = [];
  if (form.title) nodes.push(iservText("div", { class: "conference-form-title" }, form.title));
  const onFields = new Set(form.fields.map((field) => field.error).filter(Boolean));
  for (const text of form.errors || []) {
    if (!onFields.has(text)) nodes.push(conferenceNotice("error", text));
  }
  if (form.unsupported) nodes.push(noteBlock(t("conferences.form.unsupported")));
  for (const field of form.fields) {
    nodes.push(conferenceFieldNode(form, field, values));
    if (field.profiles_missing === true) nodes.push(conferenceNoProfileNote());
  }
  if (form.profiles_missing === true) nodes.push(conferenceNoProfileNote());
  return nodes;
}

function conferenceNoProfileNote() {
  return el("div", { class: "note info conference-no-profile", role: "status" }, [icon("info", 16), el("span", {}, t("conferences.form.noProfile"))]);
}

function conferenceProfileMissing(form) {
  return form.profiles_missing === true || form.fields.some((field) => field.profiles_missing === true);
}

function conferenceSubmitButtons(entry, form, after) {
  if (form.unsupported || conferenceProfileMissing(form)) return [];
  let primaryUsed = false;
  return form.submits.map((submit) => {
    const primary = !primaryUsed && !submit.destructive;
    if (primary) primaryUsed = true;
    const busy = entry.sending === form.id;
    return el("button", {
      class: primary ? "btn conference-submit" : "btn ghost conference-submit",
      type: "button",
      disabled: entry.sending !== null ? "" : null,
      onclick: () => {
        if (after) after();
        sendConferenceForm(entry, form, submit);
      },
    }, [busy ? el("span", { class: "spin" }) : null, conferenceSubmitLabel(submit)]);
  });
}

function conferenceFormCard(entry, form) {
  return el("div", { class: "conference-form" }, [
    ...conferenceFormNodes(entry, form),
    el("div", { class: "btn-stack" }, conferenceSubmitButtons(entry, form)),
  ]);
}

function conferenceFormSheet(entry, form) {
  return sheet(form.title || conferenceSubmitLabel(form.submits[0]), conferenceFormNodes(entry, form), [
    el("div", { class: "btn-stack" }, conferenceSubmitButtons(entry, form, dropSheet)),
  ]);
}

function conferenceMissing(form, values) {
  const missing = [];
  for (const field of form.fields) {
    if (!field.required || field.disabled) continue;
    const value = values[field.key];
    const empty = field.kind === "checkbox" ? !value : Array.isArray(value) ? !value.length : !String(value || "").trim();
    if (empty) missing.push(field.label || field.name);
  }
  return missing;
}

function conferenceChoiceLabel(field, value) {
  const option = (field.options || []).find((candidate) => candidate.value === value);
  return option ? option.label || option.value : value;
}

function conferenceSummary(form, submit, values) {
  const lines = [];
  const row = (form.row || []).map((cell) => String(cell || "").trim()).filter(Boolean);
  if (row.length) lines.push(row.join(" · "));
  for (const field of form.fields) {
    const value = values[field.key];
    let shown = "";
    if (field.kind === "radio" || (field.kind === "select" && !field.multiple)) shown = value ? conferenceChoiceLabel(field, value) : "";
    else if (field.kind === "select") shown = (value || []).map((item) => conferenceChoiceLabel(field, item)).join(", ");
    else if (field.kind === "checkbox") shown = value ? t("common.yes") : "";
    else shown = String(value || "").trim();
    if (shown) lines.push(`${field.label || field.name}: ${shown}`);
  }
  const action = conferenceSubmitLabel(submit);
  lines.push(t("conferences.confirm.action", { label: action }));
  return lines.join("\n");
}

function newConferenceRequestId() {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

async function sendConferenceForm(entry, form, submit) {
  if (entry.sending !== null) return;
  const values = conferenceValues(entry, form);
  const missing = conferenceMissing(form, values);
  if (missing.length) {
    entry.outcome = { tone: "bad", text: t("conferences.form.required", { fields: missing.join(", ") }) };
    rerender();
    return;
  }
  const reading = form.method === "get" && !form.writes;
  if (!reading) {
    const ok = await confirmAction({
      title: t("conferences.confirm.title"),
      text: t("conferences.confirm.text"),
      quote: conferenceSummary(form, submit, values),
      confirmLabel: t("conferences.confirm.send"),
      destructive: !!(form.destructive || submit.destructive),
    });
    if (!ok) return;
  }
  entry.sending = form.id;
  entry.outcome = null;
  rerender();
  let result = null;
  try {
    result = await postJson("api/conferences/submit", {
      connection_id: entry.connection_id,
      page: entry.page,
      form: form.id,
      check: form.check,
      submit: submit.id,
      values,
      request_id: reading ? "" : newConferenceRequestId(),
      confirmed: !reading,
    }, CONFERENCE_SUBMIT_TIMEOUT_MS);
  } catch (error) {
    entry.sending = null;
    if (handleApiFailure(error, entry.connection_id)) return;
    entry.outcome = { tone: reading ? "bad" : "warn", text: t(reading ? "conferences.page.error.text" : "api.conferences.submit.uncertain") };
    toast(entry.outcome.text, "bad");
    rerender();
    loadConferencePage(entry);
    return;
  }
  entry.sending = null;
  applyConferenceResult(entry, form, result || {}, reading);
}

function applyConferenceResult(entry, form, result, reading) {
  if (result.ok && result.page && (reading || result.state === "opened")) {
    pushConferencePage({ page: result.page.page, connection_id: entry.connection_id, title: result.page.title }, result.page);
    return;
  }
  if (result.page) {
    entry.data = result.page;
    if (result.page.page) entry.page = result.page.page;
    if (result.ok) delete entry.values[form.id];
  }
  const text = apiMessage(result, "api.conferences.submit.uncertain");
  const details = result.ok ? result.notices || [] : result.state === "invalid" && !result.page ? result.errors || [] : [];
  const tone = result.ok ? "good" : result.state === "uncertain" ? "warn" : "bad";
  entry.outcome = { tone, text, details, diagnosis: result.ok ? null : result.diagnosis || null };
  toast(text, result.ok ? "good" : "bad");
  if (!reading) {
    loadConferences(CONFERENCES_TAB_CURRENT);
  }
  state._scrollTop = true;
  rerender();
  if (!result.ok && !result.page) loadConferencePage(entry);
}
