const MAIL_SETTING_ICONS = { vacation: "upcoming", forward: "send", filter: "filter", signature: "edit", tags: "star", settings: "settings" };

async function loadMailAccount(connectionId) {
  const school = connectionId || mailSchool();
  if (!school) return null;
  const known = (state.mailAccount || {})[school];
  if (known) return known;
  try {
    const answer = await getJson(`api/mail/account?${connectionQuery(school)}`);
    const next = Object.assign({}, state.mailAccount || {});
    next[school] = answer && answer.account ? answer.account : { unknown: true };
    state.mailAccount = next;
  } catch (error) {
    const next = Object.assign({}, state.mailAccount || {});
    next[school] = { unknown: true };
    state.mailAccount = next;
  }
  if (state.view === "mail") rerender();
  return state.mailAccount[school];
}

function mailAccountOf() {
  return (state.mailAccount || {})[mailSchool()] || null;
}

function mailPageSize() {
  const account = mailAccountOf();
  return account && Number(account.page_size) > 0 ? Number(account.page_size) : MAIL_PAGE_SIZE;
}

function mailTagList() {
  const account = mailAccountOf();
  return account && Array.isArray(account.tags) ? account.tags : [];
}

function mailTagOf(keyword) {
  return mailTagList().find((tag) => tag.id === keyword || tag.name === keyword) || null;
}

function mailTagChip(keyword) {
  const tag = mailTagOf(keyword);
  const chip = iservText("span", { class: "tag mail-tag" }, tag ? tag.name : keyword);
  if (tag && tag.color) {
    const dot = el("i", { class: "mail-tag-dot", "aria-hidden": "true" });
    dot.style.background = /^[0-9A-Fa-f]{3,8}$/.test(tag.color) ? `#${tag.color}` : tag.color;
    chip.prepend(dot);
  }
  return chip;
}

function mailTagSheet(entry, detail) {
  const current = new Set(Array.isArray(detail.tags) ? detail.tags : []);
  const tags = mailTagList();
  const rows = tags.map((tag) => {
    const check = el("input", { type: "checkbox", class: "mail-tag-check", "data-tag": tag.id });
    check.checked = current.has(tag.id);
    check.addEventListener("change", async () => {
      const on = check.checked;
      check.disabled = true;
      const ok = await mailRun([entry], "api/mail/flag", { flag: tag.id, on }, null);
      check.disabled = false;
      if (ok) {
        detail.tags = on ? [...new Set([...(detail.tags || []), tag.id])] : (detail.tags || []).filter((name) => name !== tag.id);
      } else {
        check.checked = !on;
      }
    });
    return el("label", { class: "check-row" }, [check, mailTagChip(tag.id)]);
  });
  return sheet(t("mail.tags.title"), [
    rows.length ? el("div", { class: "mail-tag-rows" }, rows) : el("p", { class: "sheet-hint" }, t("mail.tags.none")),
  ]);
}

async function openMailSettings() {
  state.mailSettings = { loading: true };
  state.mailDetail = null;
  dropSheet();
  render();
  try {
    const answer = await getJson(`api/mail/settings?${connectionQuery(mailSchool())}`);
    state.mailSettings = { pages: Array.isArray(answer.pages) ? answer.pages : [], unknown: answer.unknown === true };
  } catch (error) {
    if (handleApiFailure(error, mailSchool())) return;
    state.mailSettings = { error: errorCode(error), body: (error && error.body) || null };
  }
  rerender();
}

function leaveMailSettings() {
  if (state.mailSettings && state.mailSettings.page) {
    leavePageForm(() => {
      state.mailSettings = Object.assign({}, state.mailSettings, { page: null });
      rerender();
    });
    return;
  }
  state.mailSettings = null;
  rerender();
}

function mailSettingTitle(page) {
  return page.title || t(`mail.settings.kind.${page.kind}`);
}

function mailSettingsView() {
  const current = state.mailSettings;
  if (current.page) return mailSettingsPageView();
  const view = el("div", { class: "mail-settings" });
  if (current.loading) {
    view.append(loadingBlock());
    return view;
  }
  if (current.error) {
    view.append(mailFailureBlock(current, openMailSettings));
    return view;
  }
  if (!current.pages.length) {
    view.append(current.unknown
      ? mailFailureBlock({ body: null }, openMailSettings)
      : emptyBlock("settings", t("mail.settings.none.title"), t("mail.settings.none.text")));
    return view;
  }
  view.append(el("div", { class: "rows" }, current.pages.map((page) => el("button", {
    class: "setting-row mail-setting-page",
    type: "button",
    "data-kind": page.kind,
    onclick: () => openMailSettingsPage(page),
  }, [
    el("span", { class: "nav-ico" }, [icon(MAIL_SETTING_ICONS[page.kind] || "settings", 20)]),
    el("span", { class: "lbl" }, [
      iservText("span", {}, mailSettingTitle(page)),
      mailSettingTitle(page) !== t(`mail.settings.kind.${page.kind}`) ? el("small", {}, t(`mail.settings.kind.${page.kind}`)) : null,
    ]),
    el("span", { class: "chev" }, [icon("chevron", 16)]),
  ]))));
  view.append(el("p", { class: "sheet-hint mail-settings-hint" }, t("mail.settings.hint")));
  return view;
}

async function openMailSettingsPage(page) {
  state.mailSettings = Object.assign({}, state.mailSettings, { page: { entry: page, loading: true } });
  render();
  try {
    const answer = await getJson(`api/mail/settings/page?${connectionQuery(mailSchool(), { path: page.path })}`);
    discardPageForm();
    state.mailSettings = Object.assign({}, state.mailSettings, { page: { entry: page, data: answer } });
    pageState(() => mailSettingsDraft(answer));
  } catch (error) {
    if (handleApiFailure(error, mailSchool())) return;
    state.mailSettings = Object.assign({}, state.mailSettings, { page: { entry: page, error: errorCode(error), body: (error && error.body) || null } });
  }
  rerender();
}

function mailFieldValue(field) {
  if (field.kind === "checkbox" || field.kind === "radio") return (field.choices || []).filter((choice) => choice.checked).map((choice) => choice.value);
  if (field.kind === "select" && field.multiple) return Array.isArray(field.value) ? field.value.slice() : [];
  return field.value === undefined || field.value === null ? "" : String(field.value);
}

function mailSettingsDraft(answer) {
  const forms = {};
  for (const form of answer.forms || []) {
    const values = {};
    for (const field of form.fields) values[field.name] = mailFieldValue(field);
    forms[form.index] = { values, added: [], removed: [] };
  }
  return { forms };
}

function settingsFieldNode(field, draft, name) {
  const key = name || field.name;
  const label = field.label || field.name;
  const disabled = field.disabled ? "" : null;
  if (field.kind === "checkbox" || field.kind === "radio") {
    const chosen = new Set(Array.isArray(draft.values[key]) ? draft.values[key] : []);
    const rows = (field.choices || []).map((choice) => {
      const input = el("input", { type: field.kind, name: `mail-${key}`, value: choice.value, disabled });
      input.checked = chosen.has(choice.value);
      input.addEventListener("change", () => {
        const next = field.kind === "radio" ? new Set() : new Set(Array.isArray(draft.values[key]) ? draft.values[key] : []);
        if (input.checked) next.add(choice.value);
        else next.delete(choice.value);
        draft.values[key] = [...next];
      });
      return el("label", { class: "check-row" }, [input, iservText("span", {}, choice.label || label)]);
    });
    return el("div", { class: "field mail-setting-field", "data-name": key }, [field.label ? iservText("span", { class: "lbl" }, field.label) : null, ...rows]);
  }
  let control;
  if (field.kind === "textarea") {
    control = el("textarea", { class: "inp", rows: "5", dir: "auto", disabled, maxlength: field.maxlength || null });
    control.value = draft.values[key] || "";
  } else if (field.kind === "select") {
    control = el("select", { class: "inp", disabled, multiple: field.multiple ? "" : null }, (field.options || []).map((option) => {
      const node = el("option", { value: option.value }, option.label || option.value);
      const current = draft.values[key];
      node.selected = Array.isArray(current) ? current.includes(option.value) : current === option.value;
      return node;
    }));
  } else {
    control = el("input", {
      class: "inp",
      type: ["text", "email", "number", "date", "time", "datetime-local", "url", "tel", "color", "search"].includes(field.kind) ? field.kind : "text",
      value: draft.values[key] || "",
      dir: field.kind === "email" || field.kind === "url" ? "ltr" : "auto",
      autocomplete: "off",
      disabled,
      maxlength: field.maxlength || null,
      min: field.min || null,
      max: field.max || null,
    });
  }
  const read = () => {
    if (field.kind === "select" && field.multiple) return [...control.selectedOptions].map((option) => option.value);
    return control.value;
  };
  control.addEventListener(field.kind === "select" ? "change" : "input", () => { draft.values[key] = read(); });
  return el("label", { class: "field mail-setting-field", "data-name": key }, [iservText("span", { class: "lbl" }, label), control]);
}

function inMailCollection(name, form) {
  return form.collections.some((collection) => collection.fields.some((proto) => {
    const [head, tail] = proto.name.split("__name__");
    if (!name.startsWith(head) || !name.endsWith(tail || "")) return false;
    const middle = name.slice(head.length, name.length - (tail || "").length);
    return /^\d{1,3}$/.test(middle);
  }));
}

function collectionEntryNames(collection, index) {
  return collection.fields.map((field) => field.name.replace("__name__", String(index)));
}

function settingsCollectionNode(form, collection, draft) {
  const rows = [];
  const existing = collection.entries.filter((index) => !draft.removed.includes(index));
  for (const index of existing.concat(draft.added)) {
    const names = collectionEntryNames(collection, index);
    const fields = collection.fields.map((field, position) => {
      const current = form.fields.find((entry) => entry.name === names[position]);
      const shown = Object.assign({}, current || field, { name: names[position] });
      if (!(names[position] in draft.values)) draft.values[names[position]] = mailFieldValue(shown);
      return settingsFieldNode(shown, draft, names[position]);
    });
    rows.push(el("div", { class: "card mail-rule", "data-index": String(index) }, [
      ...fields,
      el("button", {
        class: "btn ghost slim mail-rule-remove",
        type: "button",
        onclick: () => {
          if (draft.added.includes(index)) draft.added = draft.added.filter((entry) => entry !== index);
          else draft.removed.push(index);
          for (const name of names) draft.values[name] = null;
          rerender();
        },
      }, [icon("trash", 16), t("mail.settings.removeEntry")]),
    ]));
  }
  rows.push(el("button", {
    class: "btn ghost slim mail-rule-add",
    type: "button",
    onclick: () => {
      const taken = collection.entries.concat(draft.added);
      const next = Math.max(collection.next_index, taken.length ? Math.max(...taken) + 1 : 0);
      draft.added.push(next);
      rerender();
    },
  }, [icon("plus", 16), t("mail.settings.addEntry")]));
  return el("div", { class: "mail-collection" }, [
    collection.label ? el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, collection.label)]) : null,
    ...rows,
  ]);
}

function mailSettingsPageView() {
  const page = state.mailSettings.page;
  const view = el("div", { class: "mail-settings-page" });
  if (page.loading) {
    view.append(loadingBlock());
    return view;
  }
  if (page.error) {
    view.append(mailFailureBlock(page, () => openMailSettingsPage(page.entry)));
    return view;
  }
  const draftAll = state.pageForm || pageState(() => mailSettingsDraft(page.data));
  for (const form of page.data.forms || []) {
    const draft = draftAll.forms[form.index];
    const plain = form.fields.filter((field) => !inMailCollection(field.name, form));
    const block = el("div", { class: "card mail-setting-form", "data-form": String(form.index) }, [
      form.title && (page.data.forms.length > 1) ? iservText("h3", { class: "mail-setting-form-title" }, form.title) : null,
      ...plain.map((field) => settingsFieldNode(field, draft)),
      ...form.collections.map((collection) => settingsCollectionNode(form, collection, draft)),
    ]);
    view.append(block);
    if (page.result && page.result.formIndex === form.index) view.append(mailSettingsResult(page.result));
    view.append(el("div", { class: "btn-stack mail-setting-actions" }, [
      el("button", { class: "btn mail-setting-save", type: "button", disabled: page.saving ? "" : null, onclick: () => saveMailSettingsForm(form) }, [
        page.saving === form.index ? el("span", { class: "spin" }) : null,
        t("common.save"),
      ]),
    ]));
  }
  return view;
}

function mailSettingsResult(result) {
  if (result.errors && result.errors.length) {
    return el("div", { class: "note mail-setting-errors", role: "alert" }, [icon("alert", 16), el("div", {}, result.errors.map((text) => iservText("p", {}, text)))]);
  }
  if (result.verified) return el("div", { class: "stamp mail-setting-saved", role: "status" }, t("mail.settings.saved"));
  return el("div", { class: "note mail-setting-unconfirmed", role: "status" }, [icon("alert", 16), el("span", {}, t("mail.settings.unconfirmed", { fields: (result.unconfirmed || []).join(", ") }))]);
}

function settingsChangedValues(form, draft) {
  const changed = {};
  const original = {};
  for (const field of form.fields) original[field.name] = mailFieldValue(field);
  for (const [name, value] of Object.entries(draft.values)) {
    if (value === null) {
      if (name in original) changed[name] = null;
      continue;
    }
    if (!(name in original) || JSON.stringify(original[name]) !== JSON.stringify(value)) changed[name] = value;
  }
  return changed;
}

async function saveMailSettingsForm(form) {
  const page = state.mailSettings.page;
  const draft = state.pageForm.forms[form.index];
  const values = settingsChangedValues(form, draft);
  if (!Object.keys(values).length) {
    toast(t("mail.settings.nothing"), "good");
    return;
  }
  const kind = page.entry.kind;
  const ok = await confirmAction({
    title: t("mail.settings.confirmTitle"),
    text: t(kind === "forward" || kind === "filter" || kind === "vacation" ? `mail.settings.confirm.${kind}` : "mail.settings.confirm.settings"),
    confirmLabel: t("common.save"),
  });
  if (!ok) return;
  page.saving = form.index;
  page.result = null;
  rerender();
  try {
    const result = await mailPost("api/mail/settings/page", {
      connection_id: mailSchool(),
      path: page.entry.path,
      form: form.index,
      values,
      fields: form.fields.map((field) => field.name),
      confirmed: true,
    });
    if (!result || !Array.isArray(result.errors)) {
      toast(apiMessage(result || {}, "mail.toast.failed"), "bad");
    } else {
      page.result = Object.assign({}, result, { formIndex: form.index });
      if (result && result.form) {
        const forms = page.data.forms.map((entry) => (entry.index === result.form.index ? result.form : entry));
        page.data = Object.assign({}, page.data, { forms });
        discardPageForm();
        pageState(() => mailSettingsDraft(page.data));
      }
    }
  } catch (error) {
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  page.saving = false;
  rerender();
}

function mailSettingsTitle() {
  const current = state.mailSettings;
  if (current && current.page) return mailSettingTitle(current.page.entry);
  return t("mail.settings.title");
}

async function loadSignatures() {
  const pages = await getJson(`api/mail/settings?${connectionQuery(mailSchool())}`);
  const found = [];
  for (const page of (pages.pages || []).filter((entry) => entry.kind === "signature")) {
    const answer = await getJson(`api/mail/settings/page?${connectionQuery(mailSchool(), { path: page.path })}`);
    for (const form of answer.forms || []) {
      for (const field of form.fields) {
        if (field.kind !== "textarea" || !String(field.value || "").trim()) continue;
        found.push({ label: field.label || page.title || t("mail.signature.title"), text: String(field.value), address: signatureAddress(form, field) });
      }
    }
  }
  return found;
}

function signatureAddress(form, textarea) {
  const stem = textarea.name.replace(/\[[^\[\]]*\]$/, "");
  const choices = form.fields.filter((field) => field.kind === "select" && !field.multiple
    && (field.options || []).some((option) => option.value.includes("@")));
  const own = choices.find((field) => field.name.startsWith(stem)) || (choices.length === 1 ? choices[0] : null);
  if (!own) return "";
  const value = Array.isArray(own.value) ? own.value[0] : own.value;
  return String(value || "").includes("@") ? String(value).toLowerCase() : "";
}

let mailSignatureCache = null;

async function defaultSignatureFor(address) {
  if (!mailSignatureCache || mailSignatureCache.school !== mailSchool()) {
    mailSignatureCache = { school: mailSchool(), list: await loadSignatures() };
  }
  return mailSignatureCache.list.find((entry) => entry.address && entry.address === String(address || "").toLowerCase()) || null;
}

const mailEventRequests = {};

function mailEventSheet(entry, detail) {
  const draft = sheetState(() => ({ loading: true, data: null, values: {}, errors: [], failed: null, saving: false, unconfirmed: false }));
  if (draft.loading && !draft.started) {
    draft.started = true;
    draft.connection = entry.connection || mailSchool();
    draft.key = [draft.connection, detail.folder || entry.folder, detail.uid].join("|");
    getJson(`api/mail/event?${connectionQuery(draft.connection, { folder: detail.folder || entry.folder, uid: detail.uid })}`)
      .then((answer) => {
        draft.data = answer;
        for (const field of answer.form.fields) draft.values[field.name] = mailFieldValue(field);
        Object.assign(draft.values, answer.prefill || {});
      })
      .catch((error) => { draft.failed = error && error.body ? error.body : {}; })
      .finally(() => { draft.loading = false; rerender(); });
  }
  if (draft.loading) return sheet(t("mail.event.title"), [loadingBlock()]);
  if (draft.failed) return sheet(t("mail.event.title"), [noteBlock(apiMessage(draft.failed, "mail.event.failed"))]);
  const form = draft.data.form;
  const body = [el("p", { class: "dlg-text" }, t("mail.event.text"))];
  for (const field of form.fields) body.push(settingsFieldNode(field, draft));
  if (draft.errors.length) body.push(el("div", { class: "note mail-setting-errors", role: "alert" }, [icon("alert", 16), el("div", {}, draft.errors.map((text) => iservText("p", {}, text)))]));
  if (draft.unconfirmed) body.push(el("div", { class: "note mail-event-unconfirmed", role: "status" }, [icon("alert", 16), el("span", {}, t("mail.event.unconfirmed"))]));
  const save = el("button", { class: "btn mail-event-save", type: "button", disabled: draft.saving ? "" : null, onclick: () => saveMailEvent(draft) }, [
    draft.saving ? el("span", { class: "spin" }) : null,
    t("common.save"),
  ]);
  return sheet(t("mail.event.title"), body, [el("div", { class: "btn-stack" }, [save])]);
}

async function saveMailEvent(draft) {
  const ok = await confirmAction({ title: t("mail.event.confirmTitle"), text: t("mail.event.confirmText"), confirmLabel: t("common.save") });
  if (!ok) return;
  draft.saving = true;
  draft.errors = [];
  draft.unconfirmed = false;
  if (!mailEventRequests[draft.key]) mailEventRequests[draft.key] = newMailRequestId();
  rerender();
  try {
    const result = await mailPost("api/mail/event", {
      connection_id: draft.connection,
      path: draft.data.path,
      form: draft.data.form.index,
      check: draft.data.check || "",
      values: draft.values,
      fields: draft.data.form.fields.map((field) => field.name),
      request_id: mailEventRequests[draft.key],
      confirmed: true,
    });
    if (result && result.verified) {
      draft.saving = false;
      delete mailEventRequests[draft.key];
      discardSheet();
      toast(t("mail.event.saved"), "good");
      return;
    }
    if (result && result.state === "uncertain") {
      draft.unconfirmed = true;
      toast(t("mail.event.unconfirmed"), "bad");
    } else {
      if (result && Array.isArray(result.errors) && result.errors.length) draft.errors = result.errors;
      toast(apiMessage(result || {}, "mail.toast.failed"), "bad");
    }
    if (result && result.state !== "uncertain" && result.message_key !== "api.mail.event.busy") delete mailEventRequests[draft.key];
  } catch (error) {
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  draft.saving = false;
  rerender();
}

function mailSignatureSheet(onPick) {
  const draft = sheetState(() => ({ loading: true, list: [], failed: false }));
  if (draft.loading && !draft.started) {
    draft.started = true;
    loadSignatures()
      .then((list) => { draft.list = list; })
      .catch(() => { draft.failed = true; })
      .finally(() => { draft.loading = false; rerender(); });
  }
  const body = draft.loading
    ? [loadingBlock()]
    : draft.failed
      ? [noteBlock(t("mail.signature.failed"))]
      : draft.list.length
        ? [el("div", { class: "rows" }, draft.list.map((entry) => el("button", {
          class: "setting-row mail-signature-pick",
          type: "button",
          onclick: () => { discardSheet(); onPick(entry.text); },
        }, [el("span", { class: "lbl" }, [iservText("span", {}, entry.label), iservText("small", { class: "mail-signature-preview" }, entry.text)])])))]
        : [el("p", { class: "sheet-hint" }, t("mail.signature.none"))];
  return sheet(t("mail.signature.title"), body);
}
