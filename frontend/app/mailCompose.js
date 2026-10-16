const MAIL_AUTOSAVE_MS = 60000;
const MAIL_MANY_RECIPIENTS = 10;
const MAIL_ADDRESS_PATTERN = /^[^@\s<>"(),;:]+@[A-Za-z0-9.-]+\.[A-Za-z0-9-]{2,}$/;
const MAIL_SEND_UNCERTAIN_KEY = "api.mail.sendUncertain";
const MAIL_EDITOR_COMMANDS = [
  ["bold", "mail.editor.bold", "B"],
  ["italic", "mail.editor.italic", "I"],
  ["insertUnorderedList", "mail.editor.list", "•"],
  ["insertOrderedList", "mail.editor.numbered", "1."],
];
const MAIL_LOOKUP_DELAY_MS = 300;
let mailAutosaveTimer = null;
let mailComposeLookupTimer = null;

function newMailRequestId() {
  const bytes = new Uint8Array(16);
  if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function mailAddressText(list) {
  return (Array.isArray(list) ? list : []).map((entry) => {
    if (!entry.name) return entry.address;
    const name = /[,;"<>]/.test(entry.name) ? `"${entry.name.replace(/"/g, "")}"` : entry.name;
    return `${name} <${entry.address}>`;
  }).filter(Boolean).join(", ");
}

function splitMailAddresses(text) {
  const parts = [];
  let current = "";
  let quoted = false;
  let angled = false;
  for (const char of String(text || "")) {
    if (char === '"') quoted = !quoted;
    if (char === "<" && !quoted) angled = true;
    if (char === ">" && !quoted) angled = false;
    if (!quoted && !angled && (char === "," || char === ";" || char === "\n")) {
      parts.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  parts.push(current);
  return parts;
}

function parseMailAddresses(text) {
  const found = [];
  const invalid = [];
  for (const raw of splitMailAddresses(text)) {
    const part = raw.trim();
    if (!part) continue;
    const match = /^(.*)<([^<>]+)>\s*$/.exec(part);
    const name = match ? match[1].trim().replace(/^"|"$/g, "") : "";
    const address = (match ? match[2] : part).trim();
    if (MAIL_ADDRESS_PATTERN.test(address)) found.push({ name, address });
    else invalid.push(part);
  }
  return { found, invalid };
}

function textAsHtml(text) {
  return `<p>${escapeHtml(text || "").replace(/\n/g, "<br>")}</p>`;
}

function quoteHtml(start) {
  const original = start.original || {};
  const intro = start.mode === "forward"
    ? t("mail.compose.forwardIntro", { name: mailPeople(original.from).join(", "), date: formatIsoMoment(original.date) })
    : t("mail.compose.replyIntro", { name: mailPeople(original.from).join(", "), date: formatIsoMoment(original.date) });
  const quoted = start.html ? htmlText(start.html) : start.text || "";
  return `<p><br></p><p>${escapeHtml(intro)}</p><blockquote>${textAsHtml(quoted.trim())}</blockquote>`;
}

function safeHtmlString(html) {
  const box = document.createElement("div");
  box.append(safeMailNodes(html));
  return box.innerHTML;
}

function composeFormFrom(start, asCopy) {
  const senders = Array.isArray(start.senders) ? start.senders : [];
  const html = start.mode === "reply" || start.mode === "reply_all" || start.mode === "forward"
    ? quoteHtml(start)
    : start.html ? safeHtmlString(start.html) : start.text ? textAsHtml(start.text) : "";
  return {
    from: senders.length ? senders[0].address : "",
    to: mailAddressText(start.to),
    cc: mailAddressText(start.cc),
    bcc: mailAddressText(start.bcc),
    showCopies: !!((start.cc && start.cc.length) || (start.bcc && start.bcc.length)),
    subject: start.subject || "",
    html,
    receipt: start.receipt === true,
    carry: (start.attachments || []).map((part) => part.id),
    fileCount: 0,
    draft: asCopy ? null : start.draft || null,
  };
}

async function openMailCompose(mode, entry, asCopy, preset) {
  leaveDirtyForms(async () => {
    discardPageForm();
    state.mailComposeFiles = [];
    const connection = (entry && entry.connection) || mailSchool();
    state.mailCompose = { mode, loading: true, request: newMailRequestId(), connection, groups: {}, source: entry ? { folder: entry.folder, uid: entry.uid } : null };
    dropSheet();
    render();
    const params = entry ? { connection, folder: entry.folder || mailFolderId(), uid: entry.uid, mode } : { connection, mode: "new" };
    try {
      const start = await getJson(`api/mail/compose?${connectionQuery(connection, params)}`);
      if (!state.mailCompose || !state.mailCompose.loading) return;
      state.mailCompose = Object.assign({}, state.mailCompose, {
        loading: false,
        mode: start.mode || mode,
        senders: Array.isArray(start.senders) ? start.senders : [],
        attachments: Array.isArray(start.attachments) ? start.attachments : [],
        source: start.source || state.mailCompose.source,
        inReplyTo: start.in_reply_to || "",
        references: start.references || "",
      });
      pageState(() => composeFormFrom(preset ? Object.assign({}, start, preset) : start, asCopy));
      startMailAutosave();
    } catch (error) {
      if (handleApiFailure(error, mailSchool())) return;
      state.mailCompose = Object.assign({}, state.mailCompose, { loading: false, error: errorCode(error), body: (error && error.body) || null });
    }
    rerender();
  });
}

function closeMailCompose() {
  stopMailAutosave();
  state.mailCompose = null;
  state.mailComposeFiles = [];
  discardPageForm();
}

function leaveMailCompose() {
  leavePageForm(() => {
    closeMailCompose();
    rerender();
  });
}

function startMailAutosave() {
  stopMailAutosave();
  mailAutosaveTimer = window.setInterval(() => {
    if (!state.mailCompose || state.mailCompose.sending || state.mailCompose.saving) return;
    const form = state.pageForm;
    if (!form) return;
    const signature = JSON.stringify(form);
    if (signature === state.mailCompose.savedSignature || !isPageFormDirty()) return;
    saveMailDraft(true);
  }, MAIL_AUTOSAVE_MS);
}

function stopMailAutosave() {
  if (mailAutosaveTimer) window.clearInterval(mailAutosaveTimer);
  mailAutosaveTimer = null;
}

function composePayload(form, compose, extra) {
  const to = parseMailAddresses(form.to);
  const cc = parseMailAddresses(form.cc);
  const bcc = parseMailAddresses(form.bcc);
  return {
    payload: Object.assign({
      connection_id: compose.connection || mailSchool(),
      from: form.from,
      to: to.found,
      cc: cc.found,
      bcc: bcc.found,
      subject: form.subject,
      html: form.html,
      text: htmlText(form.html),
      receipt: form.receipt === true,
      mode: compose.mode,
      source: compose.source,
      carry: form.carry,
      in_reply_to: compose.inReplyTo,
      references: compose.references,
      draft: form.draft,
    }, extra || {}),
    invalid: to.invalid.concat(cc.invalid, bcc.invalid),
    count: to.found.length + cc.found.length + bcc.found.length,
  };
}

function saveMailDraft(quiet) {
  const compose = state.mailCompose;
  if (!compose || compose.sending) return Promise.resolve();
  if (compose.savePromise) return compose.savePromise;
  compose.savePromise = runMailDraftSave(quiet).finally(() => { compose.savePromise = null; });
  return compose.savePromise;
}

async function runMailDraftSave(quiet) {
  const compose = state.mailCompose;
  const form = state.pageForm;
  if (!compose || !form) return;
  compose.saving = true;
  if (!quiet) rerender();
  const { payload } = composePayload(form, compose);
  const signature = JSON.stringify(form);
  const uploaded = (state.mailComposeFiles || []).slice();
  try {
    const result = await postFormData("api/mail/draft", payload, uploaded);
    if (result && result.ok && result.draft) {
      form.draft = result.draft;
      if (result.source) {
        compose.source = result.source;
        compose.attachments = Array.isArray(result.attachments) ? result.attachments : [];
        form.carry = compose.attachments.map((part) => part.id);
        state.mailComposeFiles = (state.mailComposeFiles || []).filter((file) => !uploaded.includes(file));
        form.fileCount = state.mailComposeFiles.length;
      }
      compose.savedSignature = JSON.stringify(form);
      compose.savedAt = Date.now();
      if (!quiet) toast(t("mail.compose.draftSaved"), "good");
      if (signature) loadMailFolders();
    } else if (!quiet) {
      toast(apiMessage(result || {}, "mail.toast.failed"), "bad");
    }
  } catch (error) {
    if (!quiet && !handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
  compose.saving = false;
  rerender();
}

function mailSendSummary(form, compose) {
  const named = (text) => parseMailAddresses(text).found.map((entry) => {
    const group = (compose.groups || {})[entry.address.toLowerCase()];
    if (group) return t("mail.compose.group", { name: group });
    return entry.name ? `${entry.name} <${entry.address}>` : entry.address;
  });
  const files = (compose.attachments || []).filter((part) => form.carry.includes(part.id)).map((part) => part.filename)
    .concat((state.mailComposeFiles || []).map((file) => file.name || t("common.attachment")));
  return { to: named(form.to), cc: named(form.cc), bcc: named(form.bcc), files };
}

function confirmMailSend(summary, form) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      dropSheet();
      rerender();
      resolve(value);
    };
    const block = (label, list) => (list.length ? el("div", { class: "mail-confirm-block" }, [
      el("span", { class: "overline" }, label),
      el("ul", { class: "mail-confirm-list" }, list.map((name) => iservText("li", {}, name))),
    ]) : null);
    const body = [
      el("p", { class: "dlg-text" }, tCount("mail.compose.confirmCount", summary.to.length + summary.cc.length + summary.bcc.length)),
      form.subject.trim() ? null : noteBlock(t("mail.compose.emptySubject")),
      block(t("mail.to"), summary.to),
      block(t("mail.cc"), summary.cc),
      block(t("mail.bcc"), summary.bcc),
      block(t("common.attachments"), summary.files),
    ];
    openSheet(() => sheet(t("mail.compose.confirmTitle"), body, [
      el("div", { class: "btn-stack" }, [
        el("button", { class: "btn mail-send-confirm", type: "button", onclick: () => finish(true) }, t("mail.compose.send")),
        el("button", { class: "btn ghost", type: "button", onclick: () => finish(false) }, t("common.cancel")),
      ]),
    ]), () => finish(false));
  });
}

function mailRefusedSheet(addresses) {
  return sheet(t("mail.compose.refusedTitle"), [
    el("p", { class: "dlg-text" }, t("mail.compose.refusedText")),
    el("ul", { class: "mail-confirm-list mail-refused" }, addresses.map((address) => el("li", { dir: "ltr" }, address))),
  ]);
}

async function sendMail() {
  const compose = state.mailCompose;
  const form = state.pageForm;
  if (!compose || !form || compose.sending) return;
  stopMailAutosave();
  if (compose.savePromise) await compose.savePromise;
  const { payload, invalid, count } = composePayload(form, compose, { request_id: compose.request, confirmed: true });
  if (invalid.length) {
    toast(t("mail.compose.invalid", { addresses: invalid.join(", ") }), "bad");
    return;
  }
  if (!count) {
    toast(t("mail.compose.noRecipient"), "bad");
    return;
  }
  const ok = await confirmMailSend(mailSendSummary(form, compose), form);
  if (!ok) {
    startMailAutosave();
    return;
  }
  compose.sending = true;
  compose.failure = "";
  rerender();
  try {
    const result = await postFormData("api/mail/send", payload, state.mailComposeFiles || []);
    if (result && result.ok && result.sent) {
      toast(t(result.saved === false ? "mail.compose.sentNotFiled" : "mail.compose.sent"), result.saved === false ? "bad" : "good");
      closeMailCompose();
      const refused = Array.isArray(result.refused) ? result.refused : [];
      if (refused.length) openSheet(() => mailRefusedSheet(refused));
      rerender();
      refreshMail();
      return;
    }
    compose.failure = apiMessage(result || {}, "mail.compose.failed");
    compose.uncertain = !!(result && result.message_key === MAIL_SEND_UNCERTAIN_KEY);
  } catch (error) {
    compose.sending = false;
    if (handleApiFailure(error, compose.connection || mailSchool())) return;
    compose.failure = t("mail.compose.uncertainText");
    compose.uncertain = true;
  }
  compose.sending = false;
  rerender();
}

function lastMailToken(text) {
  const parts = splitMailAddresses(text);
  return (parts[parts.length - 1] || "").trim();
}

function replaceLastMailToken(text, entry) {
  const parts = splitMailAddresses(text);
  parts.pop();
  const kept = parts.map((part) => part.trim()).filter(Boolean);
  kept.push(mailAddressText([entry]));
  return `${kept.join(", ")}, `;
}

function showMailSuggestions(box, input, form, key, list) {
  box.replaceChildren(...list.map((entry) => el("button", {
    class: "row read mail-suggestion",
    type: "button",
    onmousedown: (event) => event.preventDefault(),
    onclick: () => {
      input.value = replaceLastMailToken(input.value, entry);
      form[key] = input.value;
      if (entry.group && state.mailCompose) state.mailCompose.groups[entry.address.toLowerCase()] = entry.name || entry.address;
      box.replaceChildren();
      input.focus();
    },
  }, [
    el("span", { class: "row-dot" }, [icon(entry.group ? "conferences" : "letters", 14)]),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, entry.name || entry.address),
      el("div", { class: "row-sub", dir: "ltr" }, entry.address),
    ]),
  ])));
}

function lookupMailRecipients(box, input, form, key) {
  const token = lastMailToken(input.value);
  if (mailComposeLookupTimer) window.clearTimeout(mailComposeLookupTimer);
  if (token.length < 2 || token.includes("@")) {
    box.replaceChildren();
    return;
  }
  mailComposeLookupTimer = window.setTimeout(() => {
    getJson(`api/mail/recipients?${connectionQuery(mailSchool(), { q: token })}`)
      .then((answer) => {
        if (lastMailToken(input.value) !== token) return;
        showMailSuggestions(box, input, form, key, Array.isArray(answer.recipients) ? answer.recipients : []);
      })
      .catch(() => box.replaceChildren());
  }, MAIL_LOOKUP_DELAY_MS);
}

function composeAddressField(form, key, label) {
  const input = el("input", { class: `inp mail-${key}`, type: "text", value: form[key] || "", autocomplete: "off", dir: "auto", inputmode: "email", "aria-label": label });
  const box = el("div", { class: "rows mail-suggestions", role: "listbox", "aria-label": t("mail.compose.suggestions") });
  input.addEventListener("input", () => {
    form[key] = input.value;
    const hint = input.parentNode && input.parentNode.querySelector(".hint");
    const many = parseMailAddresses(input.value).found.length > MAIL_MANY_RECIPIENTS && key !== "bcc";
    if (hint) hint.hidden = !many;
    lookupMailRecipients(box, input, form, key);
  });
  const many = parseMailAddresses(form[key]).found.length > MAIL_MANY_RECIPIENTS && key !== "bcc";
  return el("div", { class: "field" }, [
    el("label", { class: "lbl" }, label),
    input,
    box,
    el("span", { class: "hint mail-many-hint", hidden: many ? null : "" }, t("mail.compose.manyRecipients")),
  ]);
}

function composeEditor(form) {
  const editor = el("div", {
    class: "body-html mail-editor inp",
    contenteditable: "true",
    role: "textbox",
    "aria-multiline": "true",
    "aria-label": t("mail.compose.body"),
    dir: "auto",
  });
  editor.append(safeMailNodes(form.html || ""));
  editor.addEventListener("input", () => { form.html = editor.innerHTML; });
  const command = (name, value) => {
    editor.focus();
    if (typeof document.execCommand === "function") document.execCommand(name, false, value);
    form.html = editor.innerHTML;
  };
  const tools = MAIL_EDITOR_COMMANDS.map(([name, label, text]) => el("button", {
    class: `icon-btn mail-editor-${name}`,
    type: "button",
    "aria-label": t(label),
    title: t(label),
    onmousedown: (event) => event.preventDefault(),
    onclick: () => command(name),
  }, el("span", { class: "mail-editor-glyph" }, text)));
  tools.push(el("button", {
    class: "icon-btn mail-editor-link",
    type: "button",
    "aria-label": t("mail.editor.link"),
    title: t("mail.editor.link"),
    onmousedown: (event) => event.preventDefault(),
    onclick: () => {
      const chosen = window.getSelection && window.getSelection();
      const range = chosen && chosen.rangeCount ? chosen.getRangeAt(0).cloneRange() : null;
      openNestedSheet(() => mailLinkSheet((address) => {
        if (range && window.getSelection) {
          editor.focus();
          const current = window.getSelection();
          current.removeAllRanges();
          current.addRange(range);
        }
        command("createLink", address);
      }));
    },
  }, [icon("external", 16)]));
  tools.push(el("button", {
    class: "icon-btn mail-editor-signature",
    type: "button",
    "aria-label": t("mail.signature.insert"),
    title: t("mail.signature.insert"),
    onmousedown: (event) => event.preventDefault(),
    onclick: () => openNestedSheet(() => mailSignatureSheet((text) => insertMailSignature(editor, form, text))),
  }, [icon("edit", 16)]));
  return el("div", { class: "field mail-editor-field" }, [
    el("span", { class: "lbl" }, t("mail.compose.body")),
    el("div", { class: "mail-editor-tools", role: "toolbar", "aria-label": t("mail.editor.tools") }, tools),
    editor,
  ]);
}

function mailLinkSheet(onLink) {
  const draft = sheetState(() => ({ address: "https://" }));
  const input = el("input", { class: "inp mail-link-input", type: "url", value: draft.address, autocomplete: "off", dir: "ltr" });
  const apply = el("button", {
    class: "btn mail-link-apply",
    type: "button",
    onclick: () => {
      const address = draft.address.trim();
      if (!/^(https?:\/\/\S+|mailto:\S+)$/i.test(address)) return;
      discardSheet();
      onLink(address);
    },
  }, t("mail.editor.linkApply"));
  input.addEventListener("input", () => { draft.address = input.value; });
  return sheet(t("mail.editor.link"), [el("label", { class: "field" }, [el("span", { class: "lbl" }, t("mail.editor.linkPrompt")), input])], [el("div", { class: "btn-stack" }, [apply])]);
}

function composeAttachments(form, compose) {
  const carried = (compose.attachments || []).filter((part) => form.carry.includes(part.id));
  const files = state.mailComposeFiles || [];
  const rows = carried.map((part) => el("div", { class: "row read mail-carried" }, [
    el("span", { class: "row-dot" }, [icon("clip", 14)]),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, part.filename)]),
    el("button", { class: "icon-btn", type: "button", "aria-label": t("mail.compose.removeAttachment"), onclick: () => { form.carry = form.carry.filter((id) => id !== part.id); rerender(); } }, [icon("close", 14)]),
  ])).concat(files.map((file, index) => el("div", { class: "row read mail-upload" }, [
    el("span", { class: "row-dot" }, [icon("clip", 14)]),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, file.name || t("common.attachment"))]),
    el("button", { class: "icon-btn", type: "button", "aria-label": t("mail.compose.removeAttachment"), onclick: () => {
      state.mailComposeFiles = files.filter((_, position) => position !== index);
      form.fileCount = state.mailComposeFiles.length;
      rerender();
    } }, [icon("close", 14)]),
  ])));
  const picker = el("input", { type: "file", multiple: "", class: "mail-file-input", hidden: "" });
  picker.addEventListener("change", () => {
    state.mailComposeFiles = files.concat(Array.from(picker.files || []));
    form.fileCount = state.mailComposeFiles.length;
    rerender();
  });
  return el("div", { class: "mail-compose-attachments" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("common.attachments"))]),
    rows.length ? el("div", { class: "rows" }, rows) : null,
    picker,
    el("button", { class: "btn ghost slim mail-attach", type: "button", onclick: () => picker.click() }, [icon("clip", 16), t("mail.compose.attach")]),
  ]);
}

function mailComposeView() {
  const compose = state.mailCompose;
  const view = el("div", { class: "mail-compose" });
  if (compose.loading) {
    view.append(loadingBlock());
    return view;
  }
  if (compose.error) {
    view.append(mailFailureBlock(compose, () => openMailCompose(compose.mode, compose.source)));
    return view;
  }
  const form = state.pageForm;
  if (!form) return view;
  if (compose.senders && compose.senders.length > 1) {
    const select = el("select", { class: "inp mail-from" }, compose.senders.map((sender) => el("option", { value: sender.address, selected: sender.address === form.from ? "" : null }, sender.name ? t("mail.compose.senderOption", { name: sender.name, address: sender.address }) : sender.address)));
    select.addEventListener("change", () => {
      form.from = select.value;
      applyDefaultSignature(form, select.value);
    });
    view.append(el("label", { class: "field" }, [el("span", { class: "lbl" }, t("mail.from")), el("div", { class: "sel-wrap" }, [select, el("span", { class: "caret", html: iconSvg("chevron", 14) })])]));
  } else if (compose.senders && compose.senders.length) {
    view.append(el("div", { class: "row-meta mail-from-line" }, t("mail.compose.fromLine", { address: compose.senders[0].address })));
  }
  view.append(composeAddressField(form, "to", t("mail.to")));
  const fromList = composeListButton(form);
  if (fromList) view.append(fromList);
  if (form.showCopies) {
    view.append(composeAddressField(form, "cc", t("mail.cc")));
    view.append(composeAddressField(form, "bcc", t("mail.bcc")));
  } else {
    view.append(el("button", { class: "link-btn mail-show-copies", type: "button", onclick: () => { form.showCopies = true; rerender(); } }, t("mail.compose.showCopies")));
  }
  const subject = el("input", { class: "inp mail-subject-input", type: "text", value: form.subject, autocomplete: "off", dir: "auto", maxlength: "500" });
  subject.addEventListener("input", () => { form.subject = subject.value; });
  view.append(el("label", { class: "field" }, [el("span", { class: "lbl" }, t("mail.subject")), subject]));
  view.append(composeEditor(form));
  view.append(composeAttachments(form, compose));
  const receipt = el("input", { type: "checkbox", class: "mail-receipt-ask" });
  receipt.checked = form.receipt === true;
  receipt.addEventListener("change", () => { form.receipt = receipt.checked; });
  view.append(el("label", { class: "check-row" }, [receipt, el("span", {}, t("mail.compose.askReceipt"))]));
  if (compose.failure) {
    view.append(compose.uncertain
      ? el("div", { class: "card mail-uncertain", role: "alert" }, [el("b", {}, t("mail.compose.uncertainTitle")), el("p", {}, compose.failure)])
      : noteBlock(compose.failure));
  }
  if (compose.savedAt) view.append(el("div", { class: "stamp mail-saved" }, t("mail.compose.savedAt", { time: formatTime(new Date(compose.savedAt)) })));
  view.append(el("div", { class: "btn-stack mail-compose-actions" }, [
    el("button", { class: "btn mail-send", type: "button", disabled: compose.sending || compose.uncertain ? "" : null, onclick: sendMail }, [
      compose.sending ? el("span", { class: "spin" }) : el("span", { class: "dir-icon" }, [icon("send", 16)]),
      t("mail.compose.send"),
    ]),
    el("button", { class: "btn ghost mail-save-draft", type: "button", disabled: compose.saving || compose.sending ? "" : null, onclick: () => saveMailDraft(false) }, t("mail.compose.saveDraft")),
    form.draft ? el("button", { class: "btn ghost mail-delete-draft", type: "button", disabled: compose.sending ? "" : null, onclick: deleteMailDraft }, t("mail.compose.deleteDraft")) : null,
  ]));
  return view;
}

async function deleteMailDraft() {
  const form = state.pageForm;
  if (!form || !form.draft) return;
  const ok = await confirmAction({ title: t("mail.compose.deleteDraftTitle"), text: t("mail.compose.deleteDraftText"), confirmLabel: t("mail.compose.deleteDraft"), destructive: true });
  if (!ok) return;
  try {
    const result = await mailPost("api/mail/draft/delete", { connection_id: compose.connection || mailSchool(), folder: form.draft.folder, uid: form.draft.uid, confirmed: true });
    if (mailOutcome(result, "mail.compose.draftDeleted")) {
      closeMailCompose();
      rerender();
      loadMailList(false);
    }
  } catch (error) {
    if (!handleApiFailure(error, mailSchool())) toast(t("mail.toast.failed"), "bad");
  }
}

async function applyDefaultSignature(form, address) {
  let chosen = null;
  try {
    chosen = await defaultSignatureFor(address);
  } catch (error) {
    return;
  }
  if (!chosen || !state.pageForm || state.pageForm !== form) return;
  const editor = root().querySelector(".mail-compose .mail-editor");
  if (!editor) return;
  insertMailSignature(editor, form, chosen.text);
}

function insertMailSignature(editor, form, text) {
  const old = editor.querySelector(".mail-signature");
  if (old) old.remove();
  const block = el("div", { class: "mail-signature" }, ["-- "]);
  for (const line of String(text).split("\n")) {
    block.append(el("br", {}));
    block.append(document.createTextNode(line));
  }
  editor.append(block);
  form.html = editor.innerHTML;
}

function mailComposeTitle() {
  const compose = state.mailCompose;
  if (!compose) return t("mail.compose.new");
  if (compose.mode === "reply" || compose.mode === "reply_all") return t("mail.action.reply");
  if (compose.mode === "forward") return t("mail.action.forward");
  if (compose.mode === "draft") return t("mail.action.editDraft");
  return t("mail.compose.new");
}
