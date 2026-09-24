import {
  BASE_LANGUAGE,
  LANGUAGES,
  LANGUAGE_CHOICES,
  RTL_LANGUAGES,
  createI18n,
  formatTemplate,
} from "./i18n.js";
import { createLanguageLoader } from "./language.js";

export function i18nGlobals(instance = createI18n()) {
  const { i18n, setLanguageChoice, ...functions } = instance;
  return Object.freeze({
    BASE_LANGUAGE,
    LANGUAGES,
    LANGUAGE_CHOICES,
    RTL_LANGUAGES,
    formatTemplate,
    createLanguageLoader: (dependencies) => createLanguageLoader(instance, dependencies),
    ...functions,
  });
}
