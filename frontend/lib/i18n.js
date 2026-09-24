export const BASE_LANGUAGE = "de";
export const LANGUAGES = Object.freeze(["de", "en", "ar", "tr", "ru", "uk"]);
export const LANGUAGE_CHOICES = Object.freeze(["system"].concat(LANGUAGES));
export const RTL_LANGUAGES = Object.freeze(["ar"]);

const PLACEHOLDER_PATTERN = /\{(\w+)\}/g;

export function formatTemplate(text, vars) {
  if (!vars) return text;
  return text.replace(PLACEHOLDER_PATTERN, (match, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
  );
}

export function createI18n() {
  const i18n = { choice: "system", language: BASE_LANGUAGE, messages: {}, base: {} };

  function t(key, vars) {
    const message = i18n.messages[key] || i18n.base[key];
    if (!message) return key;
    return formatTemplate(message, vars);
  }

  function hasMessage(key) {
    return !!(i18n.messages[key] || i18n.base[key]);
  }

  function pluralCategory(count) {
    try {
      return new Intl.PluralRules(i18n.language).select(count);
    } catch (error) {
      return count === 1 ? "one" : "other";
    }
  }

  function tCount(key, count, vars) {
    const candidate = `${key}.${pluralCategory(count)}`;
    const merged = Object.assign({ count: formatNumber(count) }, vars || {});
    return t(hasMessage(candidate) ? candidate : `${key}.other`, merged);
  }

  function setLanguageBundle(language, messages, base) {
    i18n.language = language;
    if (base) i18n.base = base;
    i18n.messages = messages || i18n.base;
  }

  function languageChoices() {
    return LANGUAGE_CHOICES.slice();
  }

  function currentLanguageChoice() {
    return i18n.choice;
  }

  function setLanguageChoice(choice) {
    i18n.choice = LANGUAGE_CHOICES.includes(choice) ? choice : "system";
    return i18n.choice;
  }

  function currentLanguage() {
    return i18n.language;
  }

  function formatNumber(value) {
    try {
      return new Intl.NumberFormat(i18n.language).format(value);
    } catch (error) {
      return String(value);
    }
  }

  function dateFormatter(options) {
    try {
      return new Intl.DateTimeFormat(i18n.language, options);
    } catch (error) {
      return new Intl.DateTimeFormat(BASE_LANGUAGE, options);
    }
  }

  function relativeFormatter() {
    try {
      return new Intl.RelativeTimeFormat(i18n.language, { numeric: "auto" });
    } catch (error) {
      return new Intl.RelativeTimeFormat(BASE_LANGUAGE, { numeric: "auto" });
    }
  }

  return {
    i18n,
    t,
    hasMessage,
    pluralCategory,
    tCount,
    setLanguageBundle,
    languageChoices,
    currentLanguageChoice,
    setLanguageChoice,
    currentLanguage,
    formatNumber,
    dateFormatter,
    relativeFormatter,
  };
}
