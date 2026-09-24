(() => {
  const SIZE_COMPACT = "compact";
  const SIZE_NORMAL = "normal";
  const SIZES = [SIZE_COMPACT, SIZE_NORMAL];
  const AREA_OVERVIEW = "overview";
  const AREA_MODULES = {
    timetable: ["timetable"],
    absence: ["absences"],
    post: ["letters", "pinboard"],
    messenger: ["messenger"],
    conferences: ["conferences"],
  };
  const DEFAULT_NAVIGATION = ["timetable", "absence", "post", "messenger", "conferences"];
  const BAR_LIMIT = 5;
  const BLOCK_SEARCH_FROM = 20;
  const MORE_KEY = "more";

  const BLOCK_CATALOGUE = [
    { key: "today", module: "timetable", area: "timetable", compact: 3, normal: 10, size: "normal", surfaces: ["overview", "card"] },
    { key: "next_lesson", module: "timetable", area: "timetable", compact: 1, normal: 1, size: "compact", surfaces: ["overview", "card"] },
    { key: "week", module: "timetable", area: "timetable", compact: 1, normal: 1, size: "normal", surfaces: ["overview", "card"] },
    { key: "letters", module: "letters", area: "post", compact: 3, normal: 5, size: "normal", surfaces: ["overview", "card"] },
    { key: "noticeboard", module: "pinboard", area: "post", compact: 3, normal: 5, size: "compact", surfaces: ["overview", "card"] },
    { key: "absences", module: "absences", area: "absence", compact: 2, normal: 5, size: "normal", surfaces: ["overview", "card"] },
    { key: "conferences", module: "conferences", area: "conferences", compact: 1, normal: 3, size: "normal", surfaces: ["overview", "card"] },
    { key: "holidays", module: "timetable", area: "timetable", compact: 1, normal: 3, size: "compact", surfaces: ["overview", "card"] },
    { key: "changes", module: "timetable", area: "timetable", compact: 3, normal: 6, size: "compact", surfaces: ["overview", "card"] },
    { key: "chat", module: "messenger", area: "messenger", compact: 3, normal: 5, size: "compact", surfaces: ["overview"] },
  ];
  const BLOCK_BY_KEY = new Map(BLOCK_CATALOGUE.map((block) => [block.key, block]));
  const DEFAULT_OVERVIEW_KEYS = ["today", "letters", "noticeboard", "conferences", "changes", "chat"];

  function blockOf(key) {
    return BLOCK_BY_KEY.get(key) || null;
  }

  function blockKeys() {
    return BLOCK_CATALOGUE.map((block) => block.key);
  }

  function sizeOf(block, size) {
    return SIZES.includes(size) ? size : block.size;
  }

  function limitOf(block, size) {
    return block[sizeOf(block, size)];
  }

  function hasContent(items) {
    return Array.isArray(items) && items.length > 0;
  }

  function shownItems(block, size, items) {
    const list = Array.isArray(items) ? items : [];
    const limit = limitOf(block, size);
    return { items: list.slice(0, limit), more: list.length > limit };
  }

  function offeredBlocks(moduleOn, surface) {
    return BLOCK_CATALOGUE.filter((block) => moduleOn(block.module) && (!surface || block.surfaces.includes(surface)));
  }

  function defaultOverviewBlocks() {
    return BLOCK_CATALOGUE.filter((block) => DEFAULT_OVERVIEW_KEYS.includes(block.key)).map((block) => ({ key: block.key, size: block.size }));
  }

  function normalizeOverviewBlocks(raw, offered) {
    const allowed = new Set((offered || BLOCK_CATALOGUE).map((block) => block.key));
    const source = Array.isArray(raw) ? raw : defaultOverviewBlocks();
    const kept = [];
    const seen = new Set();
    for (const entry of source) {
      const key = entry && typeof entry === "object" ? entry.key : entry;
      const block = typeof key === "string" ? blockOf(key) : null;
      if (!block || seen.has(block.key) || !allowed.has(block.key)) continue;
      seen.add(block.key);
      kept.push({ key: block.key, size: sizeOf(block, entry && typeof entry === "object" ? entry.size : null) });
    }
    return kept;
  }

  function hiddenBlocks(enabled, offered) {
    const on = new Set(enabled.map((entry) => entry.key));
    return (offered || BLOCK_CATALOGUE).filter((block) => !on.has(block.key));
  }

  function normalizeNavigation(raw) {
    const kept = [];
    for (const entry of Array.isArray(raw) ? raw : []) {
      if (typeof entry === "string" && AREA_MODULES[entry] && !kept.includes(entry)) kept.push(entry);
    }
    for (const area of DEFAULT_NAVIGATION) {
      if (!kept.includes(area)) kept.push(area);
    }
    return kept;
  }

  function moveKey(list, key, direction) {
    const index = list.indexOf(key);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= list.length) return list.slice();
    const moved = list.slice();
    moved.splice(index, 1);
    moved.splice(target, 0, key);
    return moved;
  }

  function barLayout(areas, limit) {
    const cap = Math.max(2, Number(limit) || BAR_LIMIT);
    const entries = [AREA_OVERVIEW].concat(areas);
    if (entries.length <= cap) return { bar: entries, more: [] };
    return { bar: entries.slice(0, cap - 1).concat([MORE_KEY]), more: entries.slice(cap - 1) };
  }

  window.RanzenpostBlocks = {
    SIZE_COMPACT,
    SIZE_NORMAL,
    SIZES,
    AREA_OVERVIEW,
    AREA_MODULES,
    DEFAULT_NAVIGATION,
    BAR_LIMIT,
    BLOCK_SEARCH_FROM,
    MORE_KEY,
    BLOCK_CATALOGUE,
    DEFAULT_OVERVIEW_KEYS,
    blockOf,
    blockKeys,
    sizeOf,
    limitOf,
    hasContent,
    shownItems,
    offeredBlocks,
    defaultOverviewBlocks,
    normalizeOverviewBlocks,
    hiddenBlocks,
    normalizeNavigation,
    moveKey,
    barLayout,
  };
})();
