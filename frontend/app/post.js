function lettersLoadKey(tab) {
  return `letters:${tab}`;
}

async function loadLetters(tab) {
  const current = state.letters;
  const keep = !!(current && !current.error && current.tab === tab);
  const outcome = await reload(
    lettersLoadKey(tab),
    () => getJson(`api/letters?tab=${encodeURIComponent(tab)}`),
    keep
  );
  if (!outcome) return;
  if (outcome.data) state.letters = { letters: outcome.data.letters || [], tab };
  else if (outcome.error) state.letters = { error: outcome.error, tab };
  rerender();
}

function matchesLetterQuery(letter, query) {
  const haystack = [
    letter.title,
    letter.sender,
    letter.child,
    letter.recipients,
    stripHtml(letter.body_text || ""),
    ...(letter.attachments || []).map((attachment) => attachment.filename || ""),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function postView() {
  const lead = postSegment();
  return postSegmentIs("pinboard") ? pinboardView(lead) : lettersView(lead);
}

function postSegment() {
  if (!moduleOn("letters") || !moduleOn("pinboard")) return null;
  return el("div", { class: "segment", role: "tablist" }, [
    segmentButton(t("post.segment.letters"), postSegmentIs("letters"), lettersUnreadCount(), () =>
      switchPostTab("letters")
    ),
    segmentButton(t("post.segment.pinboard"), postSegmentIs("pinboard"), pinboardUnreadCount(), () =>
      switchPostTab("pinboard")
    ),
  ]);
}

function switchPostTab(segment) {
  if (postSegmentIs(segment)) return;
  state.postTab = segment;
  selection.resetAll();
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
  revalidateActiveView();
}

function openPostSegment(segment) {
  setView("post", { segment });
}

function lettersFolderChip(tab, iconName, label, count) {
  const chip = el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "aria-selected": String(state.lettersTab === tab),
    onclick: () => openLettersFolder(tab),
  }, [icon(iconName, 14), el("span", {}, label)]);
  if (count) chip.append(el("span", { class: "n" }, formatNumber(count)));
  return chip;
}

function lettersFolderRow() {
  return el("div", { class: "chipbar segmented", role: "tablist" }, [
    lettersFolderChip("current", "inbox", t("letters.folder.current"), lettersUnreadCount()),
    lettersFolderChip("archive", "archive", t("letters.folder.archive"), 0),
  ]);
}

function openLettersFolder(tab) {
  if (tab === state.lettersTab) return;
  setLettersFolder(tab);
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
}

function lettersView(lead) {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  if (lead) head.append(lead);
  head.append(lettersFolderRow());
  view.append(head);
  const data = state.letters;
  if (!data || data.tab !== state.lettersTab) {
    autoLoad(lettersLoadKey(state.lettersTab), () => loadLetters(state.lettersTab));
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("letters.error.title"), t("letters.error.text"), retryButton(() => { state.letters = null; rerender(); })));
    return view;
  }
  const letters = data.letters || [];
  if (!letters.length) {
    view.append(
      state.lettersTab === "archive"
        ? emptyBlock("archive", t("letters.empty.archiveTitle"), t("letters.empty.archiveText"))
        : emptyBlock("inbox", t("letters.empty.title"), t("letters.empty.text"))
    );
    return view;
  }
  const unread = letters.filter((entry) => entry.unread).length;
  head.append(
    el("div", { class: "section-head" }, [
      el(
        "span",
        { class: "overline" },
        unread && state.lettersTab === "current" ? t("letters.unread", { count: formatNumber(unread) }) : tCount("letters.count", letters.length)
      ),
      el("div", { class: "letters-tools" }, [
        unread && state.lettersTab === "current" && !state.lettersSelectMode
          ? el("button", { type: "button", onclick: markAllLettersRead }, t("letters.markAllRead"))
          : null,
        state.lettersSelectMode ? null : el("button", { type: "button", onclick: toggleLetterSelectMode }, t("common.select")),
      ]),
    ])
  );
  const note = refreshFailureNote(lettersLoadKey(state.lettersTab));
  if (note) head.append(note);
  const schoolBar = schoolFilterBar(letters, state.postSchoolFilter, setPostSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  const hitCount = el("span", { class: "search-hits" });
  const rowsHost = el("div", {});
  function renderLetterRows() {
    const query = (state.lettersSearch || "").trim().toLowerCase();
    const bySchool = filterBySchool(letters, state.postSchoolFilter);
    const filtered = query ? bySchool.filter((letter) => matchesLetterQuery(letter, query)) : bySchool;
    letterSelection.keepVisible(filtered.map(letterKey));
    hitCount.textContent = query ? tCount("common.hits", filtered.length) : "";
    const nodes = [];
    if (!filtered.length) {
      nodes.push(emptyBlock("search", t("letters.search.emptyTitle"), t("letters.search.emptyText")));
    } else {
      const rows = el("div", { class: "rows" });
      for (const letter of filtered) rows.append(letterRow(letter));
      nodes.push(rows);
    }
    if (state.lettersSelectMode) nodes.push(letterSelectionBar());
    rowsHost.replaceChildren(...nodes);
  }
  head.append(searchField(state.lettersSearch, t("letters.search.placeholder"), (value) => {
    state.lettersSearch = value;
    renderLetterRows();
  }, hitCount));
  view.append(rowsHost);
  renderLetterRows();
  return view;
}

function letterKey(letter) {
  if (letter.key) return letter.key;
  const prefix = letter.connection_id ? `${letter.connection_id}:` : "";
  return `${prefix}${letter.letter_id}:${letter.recipient_id}`;
}

function letterIdentity(letter) {
  return { connection_id: letter.connection_id || "", letter_id: letter.letter_id, recipient_id: letter.recipient_id };
}

function tileKey(tile) {
  return tile.key || String(tile.id);
}

function folderKey(folder) {
  return folder.key || String(folder.id);
}

function letterConfirmation(source) {
  const info = source && source.confirmation;
  return info && typeof info === "object" ? info : null;
}

function letterConfirmationOpen(letter) {
  const info = letterConfirmation(letter);
  return !!(info && info.open);
}

async function runBulk(targets, step) {
  if (state.bulkProgress) return null;
  let done = 0;
  const failed = [];
  state.bulkProgress = { done: 0, total: targets.length };
  rerender();
  for (const target of targets) {
    try {
      if (await step(target)) done += 1;
      else failed.push(target);
    } catch (error) {
      if (handleApiFailure(error)) {
        state.bulkProgress = null;
        return null;
      }
      failed.push(target);
    }
    state.bulkProgress = { done: done + failed.length, total: targets.length };
    rerender();
  }
  state.bulkProgress = null;
  return { done, failed };
}

function bulkFailureNames(failed) {
  const names = failed.map((letter) => letter.title || t("letters.fallback")).filter(Boolean);
  return names.slice(0, 3).join(", ");
}

function toggleLetterSelectMode() {
  letterSelection.toggleMode();
}

function enterLetterSelectMode(key) {
  letterSelection.enter(key);
}

function exitLetterSelectMode() {
  letterSelection.exit();
}

function toggleLetterSelected(key) {
  letterSelection.toggleItem(key);
}

function selectedLetterObjects() {
  const data = state.letters;
  if (!data || !data.letters) return [];
  const keys = new Set(state.lettersSelected);
  return data.letters.filter((letter) => keys.has(letterKey(letter)));
}

function letterSelectionBar() {
  const actions = state.lettersTab === "archive"
    ? [{ icon: "restore", label: t("letters.action.restore"), run: bulkRestoreLetters }]
    : [
        { icon: "check", label: t("letters.action.read"), run: bulkMarkLettersRead },
        { icon: "archive", label: t("letters.action.archive"), run: bulkArchiveLetters },
      ];
  return letterSelection.bar(actions);
}

function markReadOutcome(result, singleKey) {
  const read = Number(result && result.read) || 0;
  const blocked = Number(result && result.blocked) || 0;
  const failed = Number(result && result.failed) || 0;
  if (!result || result.error || (failed && !read)) return [t("letters.toast.markFailed"), "bad"];
  if (failed) return [t("letters.toast.markedSomeFailed", { read: formatNumber(read) }), "bad"];
  if (blocked && !read) {
    return [t(singleKey && blocked === 1 ? "letters.toast.blocked" : "letters.toast.markedPartial", {
      read: formatNumber(read),
      blocked: formatNumber(blocked),
    }), "bad"];
  }
  if (blocked) {
    return [t("letters.toast.markedPartial", { read: formatNumber(read), blocked: formatNumber(blocked) }), "good"];
  }
  if (!read) return [t("letters.toast.nothingToMark"), "good"];
  return [singleKey ? t("letters.toast.markedSingle") : t("letters.toast.marked", { count: formatNumber(read) }), "good"];
}

async function bulkMarkLettersRead() {
  const keys = state.lettersSelected.slice();
  if (!keys.length) return;
  try {
    const result = await postJson("api/letters/seen", { keys });
    toast(...markReadOutcome(result, false));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

async function bulkArchiveLetters() {
  const targets = selectedLetterObjects();
  if (!targets.length) return;
  const ok = await confirmAction({
    title: tCount("letters.archive.confirmTitle", targets.length),
    text: t("letters.archive.confirmText"),
    confirmLabel: t("letters.action.archive"),
  });
  if (!ok) return;
  const outcome = await runBulk(targets, async (letter) => {
    const result = await postJson("api/letters/archive", letterIdentity(letter));
    return !!(result && result.ok);
  });
  if (!outcome) return;
  toast(
    outcome.failed.length === 0
      ? tCount("letters.toast.archived", outcome.done)
      : t("letters.toast.archivedPartial", {
          done: formatNumber(outcome.done),
          total: formatNumber(targets.length),
          names: bulkFailureNames(outcome.failed),
        }),
    outcome.done ? "good" : "bad"
  );
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

async function bulkRestoreLetters() {
  const targets = selectedLetterObjects();
  if (!targets.length) return;
  const outcome = await runBulk(targets, async (letter) => {
    const result = await postJson("api/letters/restore", letterIdentity(letter));
    return !!(result && result.ok);
  });
  if (!outcome) return;
  toast(
    outcome.failed.length === 0
      ? tCount("letters.toast.restored", outcome.done)
      : t("letters.toast.restoredPartial", {
          done: formatNumber(outcome.done),
          total: formatNumber(targets.length),
          names: bulkFailureNames(outcome.failed),
        }),
    outcome.done ? "good" : "bad"
  );
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

function letterActionsSheet(letter) {
  const isArchive = state.lettersTab === "archive";
  const rows = [];
  if (!isArchive && letterConfirmationOpen(letter)) {
    rows.push(letterActionRow("alert", t("letters.action.confirmFirst"), () => { closeSheet(); openLetter(letter); }));
  } else if (!isArchive && letter.unread) {
    rows.push(letterActionRow("check", t("letters.action.markRead"), () => { closeSheet(); markLetterRead(letter); }));
  }
  if (isArchive) {
    rows.push(letterActionRow("restore", t("letters.action.restore"), () => { closeSheet(); restoreLetter(letter); }));
  } else {
    rows.push(letterActionRow("archive", t("letters.action.archive"), () => { closeSheet(); archiveLetter(letter); }));
  }
  return sheet(letter.title || t("letters.fallback"), [el("div", { class: "rows flat" }, rows)]);
}

function letterActionRow(iconName, label, onclick) {
  return el("button", { class: "row", type: "button", onclick }, [
    el("span", { class: "row-dot" }, [icon(iconName, 18)]),
    el("div", { class: "row-main" }, [el("div", { class: "row-title" }, label)]),
  ]);
}

async function markLetterRead(letter) {
  try {
    const result = await postJson("api/letters/seen", { keys: [letterKey(letter)] });
    toast(...markReadOutcome(result, true));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  state.letters = null;
  rerender();
}

function attachLetterSwipe(row, swipe, letter) {
  let startX = 0;
  let startY = 0;
  let decided = null;
  let pointerId = null;
  let longPressTimer = 0;
  row.style.touchAction = "pan-y";
  const clearLongPress = () => {
    window.clearTimeout(longPressTimer);
    longPressTimer = 0;
  };
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    pointerId = event.pointerId;
    startX = event.clientX;
    startY = event.clientY;
    decided = null;
    longPressTimer = window.setTimeout(() => {
      if (decided === null) enterLetterSelectMode(letterKey(letter));
    }, 480);
  });
  row.addEventListener("pointermove", (event) => {
    if (event.pointerId !== pointerId) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!decided && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      decided = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
      clearLongPress();
      if (decided === "x") {
        swipe.wasSwipe = true;
        row.classList.add("swiping");
      }
    }
    if (decided === "x") event.preventDefault();
  });
  const finish = (event) => {
    if (event.pointerId !== pointerId) return;
    clearLongPress();
    row.classList.remove("swiping");
    if (decided === "x" && Math.abs(event.clientX - startX) > 46) {
      openSheet(() => letterActionsSheet(letter));
    }
    pointerId = null;
    decided = null;
  };
  row.addEventListener("pointerup", finish);
  row.addEventListener("pointercancel", () => {
    clearLongPress();
    row.classList.remove("swiping");
    pointerId = null;
    decided = null;
  });
}

function segmentButton(text, selected, count, onclick) {
  const button = el("button", {
    type: "button",
    role: "tab",
    "aria-selected": String(selected),
    "aria-label": count ? t("post.segment.unread", { area: text, count: formatNumber(count) }) : null,
    onclick,
  }, [el("span", { class: "seg-label" }, text)]);
  if (count) button.append(el("span", { class: "badge seg-badge", "aria-hidden": "true" }, badgeText(count)));
  return button;
}

function setLettersFolder(tab) {
  if (tab === state.lettersTab) return;
  state.lettersTab = tab;
  state.letters = null;
  letterSelection.reset();
}

function letterChildTag(letter) {
  const name = firstName(letter && letter.child);
  return name ? iservText("span", { class: "tag child" }, name) : null;
}

function letterClassTag(letter) {
  return letter && letter.recipients ? iservText("span", { class: "tag" }, letter.recipients) : null;
}

function letterConfirmTag(letter) {
  return letterConfirmationOpen(letter)
    ? el("span", { class: "tag confirm" }, t("letters.confirm.badge"))
    : null;
}

function letterTagNodes(letter) {
  return [schoolTag(letter), letterConfirmTag(letter), letterClassTag(letter), letterChildTag(letter)].filter(Boolean);
}

function letterRow(letter) {
  const key = letterKey(letter);
  const selectMode = state.lettersSelectMode;
  const selected = state.lettersSelected.includes(key);
  const sub = letter.sender || "";
  const swipe = { wasSwipe: false };
  const chips = letterTagNodes(letter);
  const tags = chips.length ? el("div", { class: "row-tags" }, chips) : null;
  const row = el("button", {
    class: openRowClass(`row${letter.unread ? "" : " read"}${selected ? " selected" : ""}`, "letter", key),
    type: "button",
    onclick: () => {
      if (swipe.wasSwipe) {
        swipe.wasSwipe = false;
        return;
      }
      if (selectMode) toggleLetterSelected(key);
      else openLetter(letter);
    },
  }, [
    selectMode
      ? el("span", { class: `row-check${selected ? " on" : ""}` }, selected ? [icon("check", 14)] : [])
      : el("span", { class: "row-dot" }, letter.unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags,
      iservText("div", { class: "row-title" }, letter.title || t("letters.untitled")),
      sub ? el("div", { class: "row-sub" }, sub) : null,
    ]),
    el("div", { class: "row-side" }, [
      letter.published ? el("span", { class: "row-meta" }, showDate(letter.published)) : null,
      (letter.attachments || []).length ? el("span", { class: "row-clip" }, [icon("clip", 14)]) : null,
    ]),
  ]);
  if (!selectMode) attachLetterSwipe(row, swipe, letter);
  return row;
}

async function markAllLettersRead() {
  try {
    const result = await postJson("api/letters/seen", { all: true });
    toast(...markReadOutcome(result, false));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  state.letters = null;
  rerender();
}

function restoreUnreadMark(letter) {
  letter.unread = true;
  if (state.view === "post" && postSegmentIs("letters")) rerender();
}

function markLetterSeen(letter) {
  letter.unread = false;
  postJson("api/letters/seen", { keys: [letterKey(letter)] })
    .then((result) => {
      if (result && Number(result.read) > 0) return;
      restoreUnreadMark(letter);
    })
    .catch((error) => {
      restoreUnreadMark(letter);
      routeOrIgnoreBackgroundFailure(error);
    });
}

function openLetterFromOverview(letter) {
  rememberOverviewAnchor();
  setView("post", { segment: "letters" });
  openLetter(letter, OVERVIEW_ORIGIN);
}

function leaveLetterDetail() {
  const origin = state.letterDetail && state.letterDetail.origin;
  state.letterDetail = null;
  if (origin === OVERVIEW_ORIGIN) setView("overview", { keepAnchor: true });
  else rerender();
  loadLetters(state.lettersTab);
}

const unreadLetterOpens = new Map();

function beginUnreadOpen(letter) {
  const key = letterKey(letter);
  const open = unreadLetterOpens.get(key) || (letter.unread ? { key, pending: 0, read: false } : null);
  if (!open) return null;
  open.pending += 1;
  unreadLetterOpens.set(key, open);
  return open;
}

function settleUnreadOpen(letter, open, arrived) {
  if (!open) return;
  open.pending -= 1;
  const firstArrival = arrived && !open.read;
  if (arrived) open.read = true;
  if (open.pending === 0 && unreadLetterOpens.get(open.key) === open) unreadLetterOpens.delete(open.key);
  if (firstArrival) markLetterSeen(letter);
  else if (!open.read && open.pending === 0) restoreUnreadMark(letter);
}

async function openLetter(letter, origin) {
  const pending = { letter, loading: true, origin: origin || null };
  const unreadOpen = beginUnreadOpen(letter);
  state.letterDetail = pending;
  dropSheet();
  letter.unread = false;
  render();
  try {
    const detail = await getJson(
      `api/letters/detail?letter_id=${encodeURIComponent(letter.letter_id)}&recipient_id=${encodeURIComponent(letter.recipient_id)}&connection=${encodeURIComponent(letter.connection_id || "")}`
    );
    settleUnreadOpen(letter, unreadOpen, true);
    if (state.letterDetail !== pending) return;
    state.letterDetail = { letter, detail, origin: origin || null };
  } catch (error) {
    settleUnreadOpen(letter, unreadOpen, false);
    if (handleApiFailure(error)) return;
    if (state.letterDetail !== pending) return;
    const refused = !!(error && error.body && error.body.message_key === LETTER_UNKNOWN_KEY);
    state.letterDetail = { letter, error: errorCode(error), refused, origin: origin || null };
  }
  rerender();
}

function letterTechEntries(letter) {
  return [
    { label: t("letters.tech.letterId"), value: letter.letter_id, kind: "text" },
    { label: t("letters.tech.recipientId"), value: letter.recipient_id, kind: "text" },
    { label: t("letters.tech.additionalSenders"), value: letter.additional_senders, kind: "text" },
    { label: t("letters.tech.recipients"), value: letter.recipients, kind: "text" },
  ];
}

function letterDetailView() {
  const { letter, detail, loading, error, refused } = state.letterDetail;
  const view = el("div", {});
  const chips = letterTagNodes(letter);
  if (chips.length) view.append(el("div", { class: "row-tags" }, chips));
  const meta = [letter.sender || "", letter.published ? showDate(letter.published) : ""].filter(Boolean).join(" · ");
  if (meta) view.append(el("div", { class: "row-meta", style: "margin:0 0 20px" }, meta));
  if (loading) {
    view.append(loadingBlock());
    return view;
  }
  if (refused) {
    view.append(noteBlock(t(LETTER_UNKNOWN_KEY)));
    return view;
  }
  if (error || !detail) {
    view.append(emptyBlock("alert", t("letters.detail.errorTitle"), t("letters.detail.errorText"), retryButton(() => openLetter(letter, state.letterDetail && state.letterDetail.origin))));
    return view;
  }
  view.append(el("div", { class: "card" }, [el("div", { class: "body-html", dir: "auto", richHtml: detail.body_html || "" })]));
  const attachments = detail.attachments || [];
  if (attachments.length) {
    view.append(el("div", { class: "section-head", style: "margin-top:24px" }, [el("span", { class: "overline" }, t("common.attachments"))]));
    view.append(attachmentRows(attachments));
  }
  const confirmBlock = letterConfirmationBlock(letter, detail);
  if (confirmBlock) view.append(confirmBlock);
  view.append(
    el("div", { style: "margin-top:24px; display:flex; gap:12px; flex-wrap:wrap" }, [
      letterReplyAvailable(detail)
        ? el("button", { class: "btn ghost letter-reply-action", type: "button", onclick: () => openLetterReply(letter) }, t("letters.reply.action"))
        : null,
      state.lettersTab === "archive"
        ? el("button", { class: "btn ghost", type: "button", onclick: () => restoreLetter(letter) }, [icon("restore", 18), t("letters.action.restore")])
        : el("button", { class: "btn ghost", type: "button", onclick: () => archiveLetter(letter) }, [icon("archive", 18), t("letters.action.archive")]),
    ])
  );
  return view;
}

const LETTER_REPLY_MAX_LENGTH = 4000;
const LETTER_REPLY_TIMEOUT_MS = 90000;

const LETTER_RELOAD_KEYS = ["api.letters.confirm.uncertain", "api.letters.confirm.changed"];

function letterConfirmationBlock(letter, detail) {
  const info = letterConfirmation(detail) || letterConfirmation(letter);
  if (!info || !info.type) return null;
  if (info.done) return letterAnsweredCard(letter, info);
  if (!info.open) return null;
  const choice = info.sendable && info.choice && Array.isArray(info.choice.options) ? info.choice : null;
  if (choice) return letterChoiceCard(letter, detail, info, choice);
  if (info.sendable && info.type !== "seen") return letterChoiceUnreadCard(letter, detail);
  const sendable = !!info.sendable;
  const card = el("div", { class: "card confirm-card" }, [
    letterConfirmHead(sendable ? t("letters.confirm.title") : t("letters.confirm.choiceTitle")),
    el("p", { class: "confirm-text" }, sendable ? t("letters.confirm.text") : t("letters.confirm.unsupportedText")),
    sendable && info.can_reply ? letterReplyField(letter) : null,
    sendable
      ? el("button", { class: "btn confirm-action", type: "button", disabled: letter && letter.confirming ? "" : null, onclick: () => confirmLetterRead(letter) }, [
          icon("check", 18),
          t("letters.confirm.action"),
        ])
      : el("button", { class: "btn ghost slim confirm-action letter-confirm-report", type: "button", onclick: openHelpPage }, [icon("info", 16), t("letters.confirm.report")]),
  ]);
  return letterConfirmFooter(card, letter, detail);
}

function letterChoiceUnreadCard(letter, detail) {
  const card = el("div", { class: "card confirm-card" }, [
    letterConfirmHead(t("letters.confirm.choiceTitle")),
    el("p", { class: "confirm-text" }, t("letters.confirm.choiceText")),
    el("button", { class: "btn ghost slim confirm-action letter-confirm-reload", type: "button", onclick: () => reloadLetter(letter) }, [icon("restore", 16), t("letters.confirm.reload")]),
  ]);
  return letterConfirmFooter(card, letter, detail);
}

function letterFailureNote(card, letter) {
  const failure = letter && letter.confirmationFailure;
  if (failure && failure.message) card.append(noteBlock(failure.message));
  return failure || null;
}

function letterConfirmHead(title) {
  return el("div", { class: "confirm-head" }, [
    el("span", { class: "confirm-mark" }, [icon("check", 16)]),
    el("span", { class: "confirm-title" }, title),
  ]);
}

function letterConfirmFooter(card, letter, detail) {
  const failure = letterFailureNote(card, letter);
  if (failure && failure.reload && !card.querySelector(".letter-confirm-reload")) {
    card.append(el("button", { class: "btn ghost slim confirm-action letter-confirm-reload", type: "button", onclick: () => reloadLetter(letter) }, [icon("restore", 16), t("letters.confirm.reload")]));
  }
  const facts = [
    ...diagnosisEntries(failure && failure.diagnosis),
    ...diagnosisEntries(detail && detail.confirmation_evidence),
  ];
  if (facts.length) card.append(techDetailsButton(facts));
  return card;
}

function letterAnsweredCard(letter, info) {
  const editing = letter && letter.answerEdit;
  if (editing && editing.choice !== undefined) return letterAnswerEditCard(letter, info, editing);
  const answer = Array.isArray(info.answer) ? info.answer.filter(Boolean) : [];
  const answered = info.type !== "seen";
  const stamp = info.confirmed_at
    ? t(answered ? "letters.confirm.answeredAt" : "letters.confirm.doneAt", { when: showTimestamp(info.confirmed_at) })
    : t(answered ? "letters.confirm.answeredText" : "letters.confirm.doneText");
  const card = el("div", { class: "card confirm-card done" }, [
    letterConfirmHead(t(answered ? "letters.confirm.answeredTitle" : "letters.confirm.doneTitle")),
    answer.length ? el("p", { class: "confirm-text letter-answer", dir: "auto" }, t("letters.confirm.answerText", { answer: localList(answer) })) : null,
    el("p", { class: "confirm-text" }, stamp),
    info.editable
      ? el("button", { class: "btn ghost slim confirm-action letter-answer-edit", type: "button", disabled: editing ? "" : null, onclick: () => openAnswerEdit(letter) }, [
          editing ? el("span", { class: "spin" }) : null,
          t("letters.confirm.edit"),
        ])
      : null,
  ]);
  letterFailureNote(card, letter);
  return card;
}

function letterChoiceDraft(letter, choice) {
  if (!letter.choiceDraft || letter.choiceDraft.source !== choice) {
    letter.choiceDraft = { source: choice, picked: choice.options.filter((option) => option.selected).map((option) => option.id) };
  }
  return letter.choiceDraft;
}

function letterChoiceOptions(letter, choice) {
  const draft = letterChoiceDraft(letter, choice);
  return el("div", { class: "opt-list confirm-choices", role: choice.multiple ? "group" : "radiogroup" }, choice.options.map((option) => {
    const active = draft.picked.includes(option.id);
    return el("button", {
      class: "opt letter-choice",
      type: "button",
      role: choice.multiple ? "checkbox" : "radio",
      "aria-checked": String(active),
      "aria-pressed": String(active),
      disabled: letter.confirming ? "" : null,
      onclick: () => {
        if (choice.multiple) {
          draft.picked = active ? draft.picked.filter((id) => id !== option.id) : draft.picked.concat(option.id);
        } else {
          draft.picked = [option.id];
        }
        rerender();
      },
    }, [el("b", { dir: "auto" }, option.label)]);
  }));
}

function letterChoiceCard(letter, detail, info, choice) {
  const draft = letterChoiceDraft(letter, choice);
  const card = el("div", { class: "card confirm-card" }, [
    letterConfirmHead(t("letters.confirm.choiceTitle")),
    el("p", { class: "confirm-text" }, t(choice.multiple ? "letters.confirm.choiceTextMultiple" : "letters.confirm.choiceText")),
    letterChoiceOptions(letter, choice),
    info.can_reply ? letterReplyField(letter) : null,
    el("button", {
      class: "btn confirm-action letter-answer-send",
      type: "button",
      disabled: letter.confirming || !draft.picked.length ? "" : null,
      onclick: () => sendLetterAnswer(letter, choice, info.can_reply, false),
    }, [letter.confirming ? el("span", { class: "spin" }) : icon("check", 18), t("letters.confirm.answerAction")]),
  ]);
  return letterConfirmFooter(card, letter, detail);
}

function letterAnswerEditCard(letter, info, editing) {
  const choice = editing.choice && Array.isArray(editing.choice.options) ? editing.choice : null;
  const draft = choice ? letterChoiceDraft(letter, choice) : { picked: [] };
  const card = el("div", { class: "card confirm-card letter-answer-editing" }, [
    letterConfirmHead(t("letters.confirm.edit")),
    el("p", { class: "confirm-text" }, t("letters.confirm.editText")),
    choice ? letterChoiceOptions(letter, choice) : null,
    editing.can_reply ? letterReplyField(letter) : null,
    el("div", { class: "btn-stack confirm-action" }, [
      el("button", {
        class: "btn letter-answer-send",
        type: "button",
        disabled: letter.confirming || (choice && !draft.picked.length) ? "" : null,
        onclick: () => sendLetterAnswer(letter, choice, editing.can_reply, true),
      }, [letter.confirming ? el("span", { class: "spin" }) : icon("check", 18), t("letters.confirm.answerAction")]),
      el("button", {
        class: "btn ghost letter-answer-cancel",
        type: "button",
        disabled: letter.confirming ? "" : null,
        onclick: () => {
          letter.answerEdit = null;
          letter.choiceDraft = null;
          letter.confirmationFailure = null;
          rerender();
        },
      }, t("common.cancel")),
    ]),
  ]);
  letterFailureNote(card, letter);
  return card;
}

async function openAnswerEdit(letter) {
  if (letter.answerEdit) return;
  letter.answerEdit = { loading: true };
  letter.confirmationFailure = null;
  rerender();
  try {
    const result = await getJson(
      `api/letters/answer?letter_id=${encodeURIComponent(letter.letter_id)}&recipient_id=${encodeURIComponent(letter.recipient_id)}&connection=${encodeURIComponent(letter.connection_id || "")}`
    );
    if (result && result.ok) {
      letter.choiceDraft = null;
      letter.replyDraft = String(result.text || "");
      letter.answerEdit = { choice: result.choice || null, can_reply: !!result.can_reply };
    } else {
      letter.answerEdit = null;
      letter.confirmationFailure = { message: apiMessage(result, "letters.confirm.editFailed") };
    }
  } catch (error) {
    letter.answerEdit = null;
    if (handleApiFailure(error)) return;
    letter.confirmationFailure = { message: t("letters.confirm.editFailed") };
  }
  rerender();
}

function reloadLetter(letter) {
  letter.confirmationFailure = null;
  letter.choiceDraft = null;
  letter.answerEdit = null;
  const open = state.letterDetail;
  openLetter(letter, open && open.origin);
}

async function sendLetterAnswer(letter, choice, canReply, edit) {
  if (letter.confirming) return;
  const picked = choice ? letterChoiceDraft(letter, choice).picked.slice() : [];
  if (choice && !picked.length) return;
  const labels = choice ? choice.options.filter((option) => picked.includes(option.id)).map((option) => option.label) : [];
  const message = canReply ? String(letter.replyDraft || "").trim() : "";
  const ok = await confirmAction({
    title: t(edit ? "letters.confirm.editSheetTitle" : "letters.confirm.answerSheetTitle"),
    text: t("letters.confirm.answerSheetText"),
    quote: labels.concat(message ? [message] : edit && canReply ? [t("letters.confirm.emptyText")] : []).join("\n"),
    confirmLabel: t("letters.confirm.answerAction"),
  });
  if (!ok) return;
  letter.confirming = true;
  letter.confirmationFailure = null;
  rerender();
  const body = Object.assign({}, letterIdentity(letter));
  if (picked.length) body.choices = picked;
  if (message || (edit && canReply)) body.text = message;
  if (edit) body.edit = true;
  let result = null;
  try {
    result = await postJson("api/letters/confirm", body, LETTER_REPLY_TIMEOUT_MS);
  } catch (error) {
    letter.confirming = false;
    if (handleApiFailure(error)) return;
    letter.confirmationFailure = { message: t("api.letters.confirm.uncertain"), reload: true };
    toast(letter.confirmationFailure.message, "bad");
    rerender();
    return;
  }
  letter.confirming = false;
  if (result && result.ok) {
    letter.replyDraft = "";
    letter.choiceDraft = null;
    letter.answerEdit = null;
    applyLetterConfirmed(letter, result.confirmed_at || "", result.answer || labels, true);
    toast(t(edit ? "letters.confirm.edited" : "letters.confirm.answerSent"), "good");
    rerender();
    return;
  }
  const key = result && result.message_key;
  letter.confirmationFailure = {
    message: apiMessage(result, "letters.confirm.failed"),
    diagnosis: (result && result.diagnosis) || null,
    reload: LETTER_RELOAD_KEYS.includes(key),
  };
  toast(letter.confirmationFailure.message, "bad");
  if (key === "api.letters.confirm.changed") {
    reloadLetter(letter);
    letter.confirmationFailure = { message: apiMessage(result, "letters.confirm.failed") };
    return;
  }
  rerender();
}

function applyLetterConfirmed(letter, stamp, answer, editable) {
  const previous = letterConfirmation(openLetterDetailOf(letter)) || letterConfirmation(letter) || {};
  const done = { type: previous.type && previous.type !== "seen" ? previous.type : "seen", open: false, done: true, sendable: false, confirmed_at: stamp || "" };
  if (Array.isArray(answer) && answer.length) {
    done.type = previous.type && previous.type !== "seen" ? previous.type : "answered";
    done.answer = answer.slice();
  }
  if (editable && previous.editable) done.editable = true;
  letter.confirmation = done;
  const detail = state.letterDetail && state.letterDetail.detail;
  if (detail && openLetterDetailOf(letter)) detail.confirmation = done;
  const list = state.letters && state.letters.letters;
  const key = letterKey(letter);
  if (list) {
    for (const entry of list) {
      if (letterKey(entry) === key) entry.confirmation = done;
    }
  }
}

function letterReplyField(letter) {
  const field = el("textarea", {
    class: "inp confirm-message",
    dir: "auto",
    rows: "3",
    maxlength: String(LETTER_REPLY_MAX_LENGTH),
    "aria-label": t("letters.confirm.messageLabel"),
  });
  field.value = letter.replyDraft || "";
  field.addEventListener("input", () => {
    letter.replyDraft = field.value;
  });
  return el("label", { class: "field confirm-message-field" }, [
    el("span", { class: "lbl" }, t("letters.confirm.messageLabel")),
    field,
  ]);
}

function openLetterDetailOf(letter) {
  const open = state.letterDetail;
  if (!open || !open.detail || !open.letter || letterKey(open.letter) !== letterKey(letter)) return null;
  return open.detail;
}

async function confirmLetterRead(letter) {
  if (letter.confirming) return;
  const info = letterConfirmation(openLetterDetailOf(letter)) || letterConfirmation(letter) || {};
  const message = info.can_reply ? String(letter.replyDraft || "").trim() : "";
  const ok = await confirmAction({
    title: t("letters.confirm.sheetTitle"),
    text: message ? t("letters.confirm.sheetTextWithMessage") : t("letters.confirm.sheetText"),
    quote: message,
    confirmLabel: t("letters.confirm.action"),
  });
  if (!ok) return;
  letter.confirming = true;
  rerender();
  try {
    const body = message ? Object.assign({}, letterIdentity(letter), { text: message }) : letterIdentity(letter);
    const result = await postJson("api/letters/confirm", body);
    if (result && result.ok) {
      letter.confirmationFailure = null;
      letter.replyDraft = "";
      applyLetterConfirmed(letter, result.confirmed_at || "");
      toast(t("letters.confirm.sent"), "good");
    } else {
      const message = apiMessage(result, "letters.confirm.failed");
      letter.confirmationFailure = {
        message,
        diagnosis: (result && result.diagnosis) || null,
        reload: LETTER_RELOAD_KEYS.includes(result && result.message_key),
      };
      toast(message, "bad");
    }
  } catch (error) {
    letter.confirming = false;
    if (handleApiFailure(error)) return;
    letter.confirmationFailure = { message: t("api.letters.confirm.uncertain"), reload: true };
    toast(letter.confirmationFailure.message, "bad");
  }
  letter.confirming = false;
  rerender();
}

function letterReplyAvailable(detail) {
  if (!detail || !detail.reply || detail.reply.available !== true) return false;
  return !letterConfirmationOpen(detail);
}

function newReplyRequestId() {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function openLetterReply(letter) {
  letter.replySending = false;
  letter.replyFailure = "";
  letter.replyUncertain = false;
  openSheet(() => letterReplySheet(letter));
}

function letterReplySheet(letter) {
  const draft = sheetState(() => ({ text: "", preview: false, request: newReplyRequestId() }));
  if (draft.preview) return letterReplyPreview(letter, draft);
  const field = el("textarea", {
    class: "inp letter-reply-text",
    dir: "auto",
    rows: "5",
    maxlength: String(LETTER_REPLY_MAX_LENGTH),
    "aria-label": t("letters.reply.label"),
  });
  field.value = draft.text;
  const next = el("button", {
    class: "btn letter-reply-next",
    type: "button",
    disabled: draft.text.trim() ? null : "",
    onclick: () => {
      if (!draft.text.trim()) return;
      draft.preview = true;
      rerender();
    },
  }, t("letters.reply.preview"));
  field.addEventListener("input", () => {
    draft.text = field.value;
    next.disabled = !draft.text.trim();
  });
  window.setTimeout(() => { if (field.isConnected) field.focus(); }, 0);
  return sheet(
    t("letters.reply.title"),
    [
      el("p", { class: "dlg-text" }, t("letters.reply.text")),
      el("label", { class: "field" }, [el("span", { class: "lbl" }, t("letters.reply.label")), field]),
    ],
    [el("div", { class: "btn-stack" }, [next])]
  );
}

function letterReplyPreview(letter, draft) {
  const sending = !!letter.replySending;
  const body = [
    el("p", { class: "dlg-text" }, t("letters.reply.previewText")),
    el("blockquote", { class: "dlg-quote letter-reply-quote", dir: "auto" }, draft.text.trim()),
  ];
  if (letter.replyFailure) body.push(noteBlock(letter.replyFailure));
  return sheet(t("letters.reply.title"), body, [
    el("div", { class: "btn-stack" }, [
      el("button", { class: "btn letter-reply-send", type: "button", disabled: sending ? "" : null, onclick: () => sendLetterReply(letter, draft) }, [
        sending ? el("span", { class: "spin" }) : null,
        t(letter.replyUncertain ? "letters.reply.sendAgain" : "letters.reply.send"),
      ]),
      el("button", {
        class: "btn ghost letter-reply-edit",
        type: "button",
        disabled: sending ? "" : null,
        onclick: () => {
          draft.preview = false;
          letter.replyFailure = "";
          rerender();
        },
      }, t("letters.reply.edit")),
    ]),
  ]);
}

async function sendLetterReply(letter, draft) {
  const text = String(draft.text || "").trim();
  if (letter.replySending || !text) return;
  if (letter.replyUncertain) draft.request = newReplyRequestId();
  letter.replySending = true;
  letter.replyFailure = "";
  letter.replyUncertain = false;
  rerender();
  let result = null;
  try {
    result = await postJson(
      "api/letters/reply",
      Object.assign({}, letterIdentity(letter), { text, request_id: draft.request, confirmed: true }),
      LETTER_REPLY_TIMEOUT_MS
    );
  } catch (error) {
    letter.replySending = false;
    if (handleApiFailure(error)) return;
    letter.replyFailure = t("api.letters.reply.uncertain");
    toast(letter.replyFailure, "bad");
    rerender();
    return;
  }
  letter.replySending = false;
  if (result && result.ok) {
    dropSheet();
    toast(t("letters.reply.sent"), "good");
    rerender();
    return;
  }
  letter.replyFailure = apiMessage(result, "letters.reply.failed");
  letter.replyUncertain = !!(result && result.message_key === "api.letters.reply.uncertain");
  toast(letter.replyFailure, "bad");
  rerender();
}

function letterRefused(result) {
  return !!(result && result.message_key === LETTER_UNKNOWN_KEY);
}

function dropRefusedLetter() {
  toast(t(LETTER_UNKNOWN_KEY), "bad");
  state.letterDetail = null;
  state.letters = null;
}

async function archiveLetter(letter) {
  const ok = await confirmAction({
    title: t("letters.archive.singleTitle"),
    text: t("letters.archive.singleText"),
    confirmLabel: t("letters.action.archive"),
  });
  if (!ok) return;
  try {
    const result = await postJson("api/letters/archive", letterIdentity(letter));
    if (result && result.ok) {
      toast(t("letters.toast.archivedSingle"));
      state.letterDetail = null;
      state.letters = null;
    } else if (letterRefused(result)) {
      dropRefusedLetter();
    } else {
      toast(t("letters.toast.archiveFailed"), "bad");
    }
  } catch (error) {
    toast(t("letters.toast.archiveFailed"), "bad");
  }
  rerender();
}

async function restoreLetter(letter) {
  try {
    const result = await postJson("api/letters/restore", letterIdentity(letter));
    if (result && result.ok) {
      toast(t("letters.toast.restoredSingle"));
      state.letterDetail = null;
      state.letters = null;
    } else if (letterRefused(result)) {
      dropRefusedLetter();
    } else {
      toast(t("letters.toast.restoreFailed"), "bad");
    }
  } catch (error) {
    toast(t("letters.toast.restoreFailed"), "bad");
  }
  rerender();
}

async function loadPinboard() {
  const keep = !!(state.pinboard && !state.pinboard.error);
  const outcome = await reload("pinboard", () => getJson("api/pinboard"), keep);
  if (!outcome) return;
  if (outcome.data) state.pinboard = outcome.data;
  else if (outcome.error) state.pinboard = { error: outcome.error };
  rerender();
}

function matchesTileQuery(tile, query) {
  const haystack = [
    tile.title || "",
    stripHtml(tile.text || ""),
    tile.folder_title || "",
    tile.column_title || "",
    ...(tile.attachments || []).map((attachment) => attachment.filename || ""),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function pinboardView(lead) {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  if (lead) head.append(lead);
  view.append(head);
  const data = state.pinboard;
  if (!data) {
    autoLoad("pinboard", loadPinboard);
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("pinboard.error.title"), t("pinboard.error.text"), retryButton(() => { state.pinboard = null; rerender(); })));
    return view;
  }
  const pinboardNote = refreshFailureNote("pinboard");
  if (pinboardNote) head.append(pinboardNote);
  const folders = data.folders || [];
  const unread = (data.feed || []).filter((tile) => tile.unread).length;
  const folder = state.pinboardFolder ? folders.find((f) => folderKey(f) === state.pinboardFolder) : null;
  head.append(
    el("div", { class: "chipbar" }, [
      el("button", { class: "chip", type: "button", "aria-pressed": String(!state.pinboardOnlyNew), onclick: () => setPinboardFilter(false) }, t("pinboard.filter.all")),
      el("button", { class: "chip", type: "button", "aria-pressed": String(state.pinboardOnlyNew), onclick: () => setPinboardFilter(true) }, [
        el("span", {}, t("pinboard.filter.new")),
        unread ? el("span", { class: "n" }, formatNumber(unread)) : null,
      ]),
      el("button", { class: "chip chip-filter", type: "button", "aria-pressed": String(!!folder), onclick: () => openSheet(folderSheet) }, [
        icon("filter", 14),
        folder
          ? iservText("span", { class: "chip-label" }, folder.title || t("pinboard.folder.fallback"))
          : el("span", { class: "chip-label" }, t("pinboard.folder.all")),
      ]),
    ])
  );
  const schoolBar = schoolFilterBar(data.feed || [], state.postSchoolFilter, setPostSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  head.append(
    el("div", { class: "section-head" }, [
      el("span", { class: "overline" }, unread ? t("pinboard.unread", { count: formatNumber(unread) }) : tCount("pinboard.count", (data.feed || []).length)),
      el("div", { class: "letters-tools" }, [
        state.pinboardSelectMode ? null : el("button", { type: "button", onclick: togglePinboardSelectMode }, t("common.select")),
      ]),
    ])
  );
  const hitCount = el("span", { class: "search-hits" });
  const bodyHost = el("div", {});
  function renderPinboardBody() {
    const query = (state.pinboardSearch || "").trim().toLowerCase();
    const nodes = [];
    if (folder) {
      nodes.push(
        el("div", { class: "section-head" }, [
          iservText("span", { class: "overline" }, folder.title),
          el("button", { type: "button", onclick: () => { state.pinboardFolder = null; rerender(); } }, t("pinboard.folder.leave")),
        ])
      );
      const folderAttachments = folder.attachments || [];
      if (folderAttachments.length) {
        const rows = attachmentRows(folderAttachments);
        rows.style.marginBottom = "16px";
        nodes.push(rows);
      }
    }
    const tiles = pinboardTiles(data, folder, query);
    pinboardSelection.keepVisible(tiles.map(tileKey));
    hitCount.textContent = query ? tCount("common.hits", tiles.length) : "";
    if (!tiles.length) {
      nodes.push(
        query
          ? emptyBlock("search", t("pinboard.search.emptyTitle"), t("pinboard.search.emptyText"))
          : state.pinboardOnlyNew
          ? emptyBlock("check", t("pinboard.empty.newTitle"), t("pinboard.empty.newText"))
          : emptyBlock("pinboard", t("pinboard.empty.title"), t("pinboard.empty.text"))
      );
      bodyHost.replaceChildren(...nodes);
      return;
    }
    if (unread && state.pinboardOnlyNew && !query) {
      nodes.push(
        el("div", { class: "section-head" }, [
          el("span", { class: "overline" }, t("pinboard.unread", { count: formatNumber(unread) })),
          el("button", { type: "button", onclick: markAllPostsRead }, t("pinboard.markAllRead")),
        ])
      );
    }
    if (!folder) {
      nodes.push(el("div", { class: "sort-hint" }, t("pinboard.sortHint")));
      const rows = el("div", { class: "rows" });
      for (const tile of tiles) rows.append(postRow(tile, false, query));
      nodes.push(rows);
      if (state.pinboardSelectMode) nodes.push(pinboardSelectionBar());
      bodyHost.replaceChildren(...nodes);
      return;
    }
    let lastGroup = null;
    let rows = null;
    for (const tile of tiles) {
      const label = tile.column_title || "";
      if (label !== lastGroup || !rows) {
        lastGroup = label;
        if (label) nodes.push(el("div", { class: "section-head", style: "margin-top:20px" }, [el("span", { class: "overline" }, label)]));
        rows = el("div", { class: "rows" });
        nodes.push(rows);
      }
      rows.append(postRow(tile, true, query));
    }
    if (state.pinboardSelectMode) nodes.push(pinboardSelectionBar());
    bodyHost.replaceChildren(...nodes);
  }
  head.append(searchField(state.pinboardSearch, t("pinboard.search.placeholder"), (value) => {
    state.pinboardSearch = value;
    renderPinboardBody();
  }, hitCount));
  view.append(bodyHost);
  renderPinboardBody();
  return view;
}

function pinboardTiles(data, folder, query) {
  let tiles = folder ? (folder.columns || []).flatMap((column) => column.tiles || []) : filterBySchool(data.feed || [], state.postSchoolFilter).slice();
  if (state.pinboardOnlyNew) tiles = tiles.filter((tile) => tile.unread);
  if (query) tiles = tiles.filter((tile) => matchesTileQuery(tile, query));
  if (!folder) tiles.sort((a, b) => (b.id || 0) - (a.id || 0));
  return tiles;
}

function setPinboardFilter(onlyNew) {
  state.pinboardOnlyNew = onlyNew;
  rerender();
}

function togglePinboardSelectMode() {
  pinboardSelection.toggleMode();
}

function enterPinboardSelectMode(key) {
  pinboardSelection.enter(key);
}

function exitPinboardSelectMode() {
  pinboardSelection.exit();
}

function togglePinboardSelected(key) {
  pinboardSelection.toggleItem(key);
}

function pinboardSelectionBar() {
  return pinboardSelection.bar([
    { icon: "check", label: t("pinboard.action.markRead"), run: bulkMarkPinboardRead },
    { icon: "restore", label: t("pinboard.action.markUnread"), run: bulkMarkPinboardUnread },
  ]);
}

async function bulkSetPinboardSeen(unseen) {
  const keys = state.pinboardSelected.slice();
  if (!keys.length) return;
  try {
    await postJson("api/pinboard/seen", { keys, unseen });
    toast(t(unseen ? "pinboard.toast.markedUnread" : "pinboard.toast.markedRead"));
  } catch (error) {
    toast(t("pinboard.toast.changeFailed"), "bad");
  }
  exitPinboardSelectMode();
  state.pinboard = null;
  loadPinboard();
}

function bulkMarkPinboardRead() {
  return bulkSetPinboardSeen(false);
}

function bulkMarkPinboardUnread() {
  return bulkSetPinboardSeen(true);
}

function attachPinboardLongPress(row, tile) {
  let longPressTimer = 0;
  let moved = false;
  let startX = 0;
  let startY = 0;
  const clear = () => {
    window.clearTimeout(longPressTimer);
    longPressTimer = 0;
  };
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    moved = false;
    startX = event.clientX;
    startY = event.clientY;
    longPressTimer = window.setTimeout(() => {
      if (!moved) enterPinboardSelectMode(tileKey(tile));
    }, 480);
  });
  row.addEventListener("pointermove", (event) => {
    if (Math.abs(event.clientX - startX) > 10 || Math.abs(event.clientY - startY) > 10) {
      moved = true;
      clear();
    }
  });
  row.addEventListener("pointerup", clear);
  row.addEventListener("pointercancel", clear);
}

function folderTechEntries(folder) {
  return [
    { label: t("pinboard.tech.author"), value: folder.author, kind: "text" },
    { label: t("pinboard.tech.studentsCanCreate"), value: folder.students_can_create_tiles, kind: "bool" },
  ];
}

function folderSheet() {
  const data = state.pinboard || {};
  const sortedFolders = (data.folders || [])
    .slice()
    .sort((a, b) => (a.title || "").localeCompare(b.title || "", currentLanguage(), { numeric: true, sensitivity: "base" }));
  const rows = sortedFolders.map((folder) =>
    el("div", { class: "opt", "aria-pressed": String(folderKey(folder) === state.pinboardFolder) }, [
      el("button", {
        class: "opt-main",
        type: "button",
        onclick: () => { state.pinboardFolder = folderKey(folder); closeSheet(); },
      }, [
        icon("folder", 20),
        el("span", {}, [
          iservText("b", {}, folder.title || t("pinboard.folder.fallback")),
        ]),
        folder.unread ? el("span", { class: "badge" }, badgeText(folder.unread)) : null,
      ]),
      techDetailsButton(folderTechEntries(folder)),
    ])
  );
  rows.unshift(
    el("div", { class: "opt", "aria-pressed": String(!state.pinboardFolder) }, [
      el("button", {
        class: "opt-main",
        type: "button",
        onclick: () => { state.pinboardFolder = null; closeSheet(); },
      }, [icon("pinboard", 20), el("span", {}, [el("b", {}, t("pinboard.folder.all")), el("small", {}, t("pinboard.folder.allHint"))])])
    ])
  );
  return sheet(t("pinboard.folder.sheet"), [el("div", { class: "opt-list" }, rows)]);
}

function filenameHitFor(tile, query) {
  if (!query) return null;
  const textHaystack = `${tile.title || ""} ${stripHtml(tile.text || "")}`.toLowerCase();
  if (textHaystack.includes(query)) return null;
  const attachments = tile.attachments || [];
  const hit = attachments.find((attachment) => (attachment.filename || "").toLowerCase().includes(query));
  return hit ? hit.filename : null;
}

function postRow(tile, insideFolder, query) {
  const preview = stripHtml(tile.text).slice(0, 140);
  const title = tile.title && tile.title !== "..." ? tile.title : (preview.split(". ")[0] || t("pinboard.post.fallback"));
  const filenameHit = filenameHitFor(tile, query);
  const sub = filenameHit || (preview && preview !== title ? preview : "");
  const tagNodes = [
    schoolTag(tile),
    !insideFolder && tile.folder_title ? el("span", { class: "tag" }, tile.folder_title) : null,
    tile.column_title ? el("span", { class: "tag" }, tile.column_title) : null,
  ].filter(Boolean);
  const tags = tagNodes.length ? el("div", { class: "row-tags" }, tagNodes) : null;
  const selectMode = state.pinboardSelectMode;
  const selected = state.pinboardSelected.includes(tileKey(tile));
  const row = el("button", {
    class: openRowClass(`${tile.unread ? "row" : "row read"}${selected ? " selected" : ""}`, "post", tileKey(tile)),
    type: "button",
    onclick: () => {
      if (selectMode) togglePinboardSelected(tileKey(tile));
      else openPost(tile);
    },
  }, [
    selectMode
      ? el("span", { class: `row-check${selected ? " on" : ""}` }, selected ? [icon("check", 14)] : [])
      : el("span", { class: "row-dot" }, tile.unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags,
      el("div", { class: "row-title" }, title),
      sub ? el("div", { class: "row-sub" }, sub) : null,
    ]),
    el("div", { class: "row-side" }, [
      (tile.attachments || []).length ? el("span", { class: "row-clip" }, [icon("clip", 14)]) : null,
    ]),
  ]);
  if (!selectMode) attachPinboardLongPress(row, tile);
  return row;
}

function postTechEntries(tile) {
  const entries = [
    { label: t("pinboard.tech.tileId"), value: tile.id, kind: "text" },
    { label: t("pinboard.tech.color"), value: tile.color, kind: "text" },
  ];
  const attachments = tile.attachments || [];
  attachments.forEach((attachment, index) => {
    const prefix = attachments.length > 1
      ? t("pinboard.tech.attachmentIndexed", { index: formatNumber(index + 1) })
      : t("pinboard.tech.attachment");
    entries.push(
      { label: t("pinboard.tech.uploaded", { prefix }), value: attachment.created_at, kind: "epoch" },
      { label: t("pinboard.tech.changed", { prefix }), value: attachment.updated_at, kind: "epoch" }
    );
    if ((attachment.mimetype || "").startsWith("image/") && attachment.image_width && attachment.image_height) {
      entries.push({
        label: t("pinboard.tech.imageSize", { prefix }),
        value: t("common.imageSize", {
          width: formatNumber(attachment.image_width),
          height: formatNumber(attachment.image_height),
        }),
        kind: "text",
      });
    }
  });
  return entries;
}

function postDetailParts(tile) {
  const body = [];
  const meta = [tile.folder_title || "", tile.column_title || "", tile.owner || ""].filter(Boolean).join(" · ");
  if (meta) body.push(el("div", { class: "row-meta", style: "margin-bottom:12px" }, meta));
  body.push(el("div", { class: "body-html", dir: "auto", richHtml: tile.text || "" }));

  const attachments = tile.attachments || [];
  if (attachments.length) {
    const rows = attachmentRows(attachments);
    rows.style.marginTop = "16px";
    body.push(rows);
  }
  const foot = el("button", {
    class: "btn ghost",
    type: "button",
    onclick: () => togglePostRead(tile),
  }, [icon(tile.unread ? "check" : "restore", 18), t(tile.unread ? "pinboard.post.markRead" : "pinboard.post.markUnread")]);
  return {
    title: tile.title && tile.title !== "..." ? tile.title : t("pinboard.post.title"),
    body,
    foot: [foot],
    extra: techDetailsButton(postTechEntries(tile)),
  };
}

function openPost(tile) {
  markPostRead(tile);
  const detail = { kind: "post", tile };
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") return openDetail(detail);
  openSheet(detailSheetFactory(detail));
}

async function togglePostRead(tile) {
  const target = !tile.unread;
  tile.unread = target;
  state.detail = null;
  closeSheet();
  try {
    await postJson("api/pinboard/seen", { keys: [tileKey(tile)], unseen: target });
    toast(t(target ? "pinboard.toast.markedUnreadAgain" : "pinboard.toast.markedRead"));
  } catch (error) {
    tile.unread = !target;
    toast(t("pinboard.toast.changeFailed"), "bad");
  }
  rerender();
}

async function markPostRead(tile) {
  if (!tile.unread) return;
  tile.unread = false;
  try {
    await postJson("api/pinboard/seen", { keys: [tileKey(tile)] });
  } catch (error) {
    tile.unread = true;
    routeOrIgnoreBackgroundFailure(error);
    if (state.view === "post" && postSegmentIs("pinboard")) rerender();
  }
}

async function markAllPostsRead() {
  try {
    await postJson("api/pinboard/seen", { all: true });
    toast(t("pinboard.toast.allRead"));
  } catch (error) {
    toast(t("pinboard.toast.markFailed"), "bad");
  }
  state.pinboard = null;
  loadPinboard();
}
