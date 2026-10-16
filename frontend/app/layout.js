async function saveLayout(patch) {
  if (!state.config) state.config = {};
  Object.assign(state.config, patch);
  rerender();
  try {
    await postJson("api/config", patch);
  } catch (error) {
    toast(t("common.saveFailed"), "bad");
  }
}

function blockTitle(key) {
  return t(`blocks.${key}.title`);
}

function blockExplain(key) {
  return t(`blocks.${key}.explain`);
}

function switchButton(checked, label, onclick) {
  return el("button", {
    class: "switch",
    type: "button",
    role: "switch",
    "aria-checked": String(!!checked),
    "aria-label": label,
    onclick,
  });
}

function orderButtons(name, canUp, canDown, onMove, key) {
  const arrow = (direction, enabled, label) => el("button", {
    class: "icon-btn",
    type: "button",
    "data-dir": direction < 0 ? "up" : "down",
    "aria-label": label,
    "aria-disabled": enabled ? null : "true",
    onclick: () => {
      if (enabled) onMove(direction);
    },
  }, [el("span", { class: direction < 0 ? "ico-slot chev-up" : "ico-slot", html: iconSvg("chevron", 18) })]);
  return el("div", { class: "order-btns", "data-order": key }, [
    arrow(-1, canUp, t("settings.order.up", { name })),
    arrow(1, canDown, t("settings.order.down", { name })),
  ]);
}

function liveAnnouncement() {
  return el("p", { class: "visually-hidden", "aria-live": "polite" }, state.layoutAnnouncement || "");
}

function announceMove(name, position) {
  state.layoutAnnouncement = t("settings.order.moved", { name, position: formatNumber(position) });
}

function sizeSegment(key, size, onPick) {
  const sizes = layoutBlocks().SIZES;
  return el("div", { class: "segment mini", role: "radiogroup", "aria-label": t("settings.blocks.size", { name: blockTitle(key) }) }, sizes.map((option) => el("button", {
    type: "button",
    role: "radio",
    "aria-checked": String(option === size),
    "aria-selected": String(option === size),
    onclick: () => onPick(option),
  }, [el("span", { class: "seg-label" }, t(`settings.blocks.size.${option}`))])));
}

function blockInfoSheet(key) {
  const block = layoutBlocks().blockOf(key);
  const facts = [
    [t("settings.blocks.info.module"), t(`settings.modules.name.${block.module}`)],
    [t("settings.blocks.info.when"), t(`blocks.${key}.when`)],
    [t("settings.blocks.info.compact"), t(`blocks.${key}.compact`)],
    [t("settings.blocks.info.normal"), t(`blocks.${key}.normal`)],
    [t("settings.blocks.info.target"), t(`blocks.${key}.target`)],
  ];
  return sheet(blockTitle(key), [
    el("p", { class: "cal-hint" }, blockExplain(key)),
    el("dl", { class: "block-facts" }, facts.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
  ]);
}

function moveOverviewBlock(key, direction) {
  const enabled = enabledOverviewBlocks();
  const keys = enabled.map((entry) => entry.key);
  const moved = layoutBlocks().moveKey(keys, key, direction);
  const bySize = new Map(enabled.map((entry) => [entry.key, entry.size]));
  announceMove(blockTitle(key), moved.indexOf(key) + 1);
  focusAfterRender(`.block-row[data-block="${key}"] .order-btns [data-dir="${direction < 0 ? "up" : "down"}"]`);
  saveLayout({ overview_blocks: moved.map((item) => ({ key: item, size: bySize.get(item) })) });
}

function setOverviewBlockSize(key, size) {
  const listed = enabledOverviewBlocks().map((entry) => (entry.key === key ? { key, size } : entry));
  saveLayout({ overview_blocks: listed });
}

function toggleOverviewBlock(key, on) {
  const enabled = enabledOverviewBlocks();
  const listed = on
    ? enabled.concat([{ key, size: layoutBlocks().blockOf(key).size }])
    : enabled.filter((entry) => entry.key !== key);
  focusAfterRender(`.block-row[data-block="${key}"] .switch`);
  saveLayout({ overview_blocks: listed });
}

function blockRow(key, entry, index, total) {
  const on = !!entry;
  const name = blockTitle(key);
  const row = el("div", { class: on ? "block-row" : "block-row off", "data-block": key }, [
    el("div", { class: "block-text" }, [
      el("div", { class: "block-name" }, [
        el("span", { class: "lbl" }, name),
        el("button", { class: "info-btn", type: "button", "aria-label": t("settings.blocks.info", { name }), onclick: () => openSheet(() => blockInfoSheet(key)) }, [icon("info", 18)]),
      ]),
      el("div", { class: "block-desc" }, blockExplain(key)),
    ]),
    switchButton(on, t("settings.blocks.show", { name }), () => toggleOverviewBlock(key, !on)),
    on ? el("div", { class: "block-tools" }, [
      sizeSegment(key, entry.size, (size) => setOverviewBlockSize(key, size)),
      orderButtons(name, index > 0, index < total - 1, (direction) => moveOverviewBlock(key, direction), key),
    ]) : null,
  ]);
  return row;
}

function blockSearchThreshold() {
  return layoutBlocks().BLOCK_SEARCH_FROM;
}

function blockMatchesQuery(key, query) {
  return blockTitle(key).toLowerCase().includes(query);
}

function blockGroupBody(list, query, emptyKey, renderRow) {
  if (list.length) return el("div", { class: "rows block-rows" }, list.map(renderRow));
  return el("p", { class: "cal-hint" }, query ? t("settings.blocks.search.empty") : t(emptyKey));
}

function overviewSettingsPage() {
  const enabled = enabledOverviewBlocks();
  const hidden = hiddenOverviewBlocks();
  const searchOn = enabled.length + hidden.length >= blockSearchThreshold();
  const shownBody = el("div", {});
  const hiddenBody = el("div", {});
  function renderGroups() {
    const query = searchOn ? (state.blocksSearch || "").trim().toLowerCase() : "";
    const filteredEnabled = query ? enabled.filter((entry) => blockMatchesQuery(entry.key, query)) : enabled;
    const filteredHidden = query ? hidden.filter((block) => blockMatchesQuery(block.key, query)) : hidden;
    shownBody.replaceChildren(blockGroupBody(filteredEnabled, query, "settings.blocks.none", (entry) => blockRow(entry.key, entry, enabled.indexOf(entry), enabled.length)));
    hiddenBody.replaceChildren(blockGroupBody(filteredHidden, query, "settings.blocks.hiddenNone", (block) => blockRow(block.key, null, 0, 0)));
  }
  renderGroups();
  const shown = el("section", { class: "settings-group" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.blocks.shown"))]),
    el("p", { class: "section-lead" }, t("settings.blocks.lead")),
    shownBody,
  ]);
  const rest = el("section", { class: "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.blocks.hidden"))]),
    el("p", { class: "section-lead" }, t("settings.blocks.hiddenLead")),
    hiddenBody,
  ]);
  const searchNode = searchOn
    ? searchField(state.blocksSearch, t("settings.blocks.search.placeholder"), (value) => {
        state.blocksSearch = value;
        renderGroups();
      })
    : null;
  return el("div", { class: "blocks-page" }, [
    searchNode,
    shown,
    rest,
    el("p", { class: "sheet-hint layout-foot" }, t("settings.blocks.foot")),
  ]);
}

function moveNavigationArea(area, direction) {
  const areas = navigationAreas();
  const moved = layoutBlocks().moveKey(areas, area, direction);
  const full = layoutBlocks().normalizeNavigation(state.config && state.config.navigation);
  const rest = full.filter((entry) => !areas.includes(entry));
  announceMove(areaLabel(area), moved.indexOf(area) + 2);
  focusAfterRender(`.nav-row[data-area="${area}"] .order-btns [data-dir="${direction < 0 ? "up" : "down"}"]`);
  saveLayout({ navigation: moved.concat(rest) });
}

function navigationModuleNames(area, label) {
  const names = (VIEW_MODULES[area] || []).filter(moduleOn).map((name) => t(`settings.modules.name.${name}`));
  const joined = names.join(" · ");
  return joined && joined !== label ? joined : "";
}

function navigationRow(area, index, total) {
  const item = VIEW_BY_KEY[area];
  const label = t(item.label);
  const sub = navigationModuleNames(area, label);
  const row = el("div", { class: "nav-row", "data-area": area, tabindex: "0" }, [
    el("span", { class: "pos" }, formatNumber(index + 2)),
    el("span", { class: "nav-ico" }, [icon(item.icon, 22)]),
    el("span", { class: "lbl" }, [label, sub ? el("small", {}, sub) : null]),
    orderButtons(label, index > 0, index < total - 1, (direction) => moveNavigationArea(area, direction), area),
  ]);
  row.addEventListener("keydown", (event) => {
    if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    const direction = event.key === "ArrowUp" ? -1 : 1;
    if ((direction < 0 && index === 0) || (direction > 0 && index === total - 1)) return;
    event.preventDefault();
    moveNavigationArea(area, direction);
  });
  return row;
}

function navigationBand(key, textKey) {
  return el("div", { class: "rows-band", "data-band": key }, [icon(key === "bar" ? "overview" : "more", 14), el("span", {}, t(textKey))]);
}

function navigationSettingsPage() {
  const areas = navigationAreas();
  const layout = navigationLayout();
  const rows = [];
  if (areas.length) {
    rows.push(navigationBand("bar", "settings.nav.band.bar"));
    rows.push(el("div", { class: "nav-row fixed", "data-area": "overview" }, [
      el("span", { class: "pos" }, formatNumber(1)),
      el("span", { class: "nav-ico" }, [icon("overview", 22), el("span", { class: "nav-lock" }, [icon("lock", 12)])]),
      el("span", { class: "lbl" }, t("nav.overview")),
      el("span", { class: "val" }, t("settings.nav.fixed")),
    ]));
    areas.forEach((area, index) => {
      if (layout.more.length && layout.more[0] === area) rows.push(navigationBand("more", "settings.nav.band.more"));
      rows.push(navigationRow(area, index, areas.length));
    });
  }
  const body = areas.length
    ? el("div", { class: "rows nav-rows" }, rows)
    : emptyBlock("overview", t("settings.nav.empty.title"), t("modules.empty.text"), modulesRecheckButton());
  return el("div", { class: "nav-page" }, [
    el("section", { class: "settings-group" }, [
      el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.nav.order"))]),
      el("p", { class: "section-lead" }, t("settings.nav.lead")),
      body,
    ]),
  ]);
}

function layoutPart(key, titleKey, first, body) {
  return el("section", { class: first ? "layout-part" : "layout-part spaced", "data-part": key }, [
    el("h2", { class: "layout-part-title" }, t(titleKey)),
    body,
  ]);
}

function layoutSettingsPage() {
  return el("div", { class: "layout-page app-layout-page" }, [
    layoutPart("overview", "settings.blocks.title", true, overviewSettingsPage()),
    layoutPart("navigation", "settings.nav.title", false, navigationSettingsPage()),
    liveAnnouncement(),
  ]);
}

function setModuleDisabled(name, off) {
  const listed = modulesDisabled().filter((entry) => entry !== name);
  if (off) listed.push(name);
  focusAfterRender(`.module-row[data-module="${name}"] .switch`);
  saveLayout({ modules_disabled: listed });
}

function moduleRow(name) {
  const label = t(`settings.modules.name.${name}`);
  return el("div", { class: "module-row switchable", "data-module": name }, [
    el("span", { class: "lbl" }, label),
    switchButton(!moduleDisabled(name), t("settings.modules.switch", { name: label }), () => setModuleDisabled(name, !moduleDisabled(name))),
  ]);
}

function overviewEmptyState() {
  return el("div", { class: "overview-empty" }, [
    emptyBlock("overview", t("blocks.overview.emptyTitle"), t("blocks.overview.emptyText"), el("button", {
      class: "btn ghost slim",
      type: "button",
      onclick: () => openSettingsPage(SETTINGS_PAGE_LAYOUT),
    }, t("settings.blocks.title"))),
  ]);
}

function modulesSection(everySchool) {
  const available = MODULE_NAMES.filter(moduleAvailable);
  const block = el("div", { class: "modules-block" });
  block.append(el("p", { class: "section-lead" }, t(everySchool ? "settings.modules.leadAll" : "settings.modules.lead")));
  if (available.length) block.append(el("div", { class: "module-rows" }, available.map(moduleRow)));
  else block.append(el("p", { class: "cal-hint modules-none" }, t("settings.modules.none")));
  if (!everySchool) block.append(el("div", { class: "cal-action-row" }, [modulesRecheckButton()]));
  const help = modulesHelpBlock();
  if (help) block.append(help);
  return el("section", { class: "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.section.modules"))]),
    block,
  ]);
}

function noModulesView() {
  const help = modulesHelpBlock();
  return el("div", { class: "modules-empty" }, [
    emptyBlock("overview", t("modules.empty.title"), t("modules.empty.text")),
    help,
  ]);
}
