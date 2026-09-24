import { BASE_LANGUAGE, LANGUAGES, RTL_LANGUAGES } from "./i18n.js";

export function normalizeLanguage(value) {
  const tag = String(value || "").toLowerCase().split("-")[0];
  return LANGUAGES.includes(tag) ? tag : "";
}

export function preferredLanguages(agent) {
  const list = agent.languages && agent.languages.length ? agent.languages : [agent.language];
  return [].concat(list).filter(Boolean);
}

export function resolveLanguage(choice, preferred) {
  if (choice && choice !== "system") return normalizeLanguage(choice) || BASE_LANGUAGE;
  for (const tag of preferred) {
    const match = normalizeLanguage(tag);
    if (match) return match;
  }
  return BASE_LANGUAGE;
}

export function createLanguageLoader(core, { getJson, page, agent }) {
  function resolveChoice(choice) {
    return resolveLanguage(choice, preferredLanguages(agent));
  }

  function fetchBundle(language) {
    return getJson(`i18n/${encodeURIComponent(language)}.json`).then((data) =>
      data && typeof data === "object" && !Array.isArray(data) ? data : null
    );
  }

  function applyDocumentLanguage() {
    const language = core.currentLanguage();
    page.documentElement.setAttribute("lang", language);
    page.documentElement.setAttribute("dir", RTL_LANGUAGES.includes(language) ? "rtl" : "ltr");
    for (const node of page.querySelectorAll("[data-i18n]")) {
      node.textContent = core.t(node.getAttribute("data-i18n"));
    }
  }

  async function loadBaseLanguage() {
    if (Object.keys(core.i18n.base).length) return;
    try {
      const data = await fetchBundle(BASE_LANGUAGE);
      if (data) core.setLanguageBundle(BASE_LANGUAGE, data, data);
    } catch (error) {}
    applyDocumentLanguage();
  }

  async function applyLanguageChoice(choice) {
    const language = resolveChoice(core.setLanguageChoice(choice));
    let messages = null;
    if (language !== BASE_LANGUAGE) {
      try {
        messages = await fetchBundle(language);
      } catch (error) {
        messages = null;
      }
    }
    core.setLanguageBundle(messages ? language : BASE_LANGUAGE, messages || core.i18n.base, core.i18n.base);
    applyDocumentLanguage();
  }

  return { resolveLanguage: resolveChoice, loadBaseLanguage, applyLanguageChoice };
}
