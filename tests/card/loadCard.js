import { vi } from "vitest";

import { FROZEN_NOW } from "./fakeHass.js";

const CARD_FILE = "../../custom_components/ranzenpost/frontend/ranzenpost-card.js";

export async function loadCard() {
  await import(CARD_FILE);
  const CardClass = customElements.get("ranzenpost-card");
  if (!CardClass) throw new Error("the card did not register itself");
  CardClass.resetCaches();
  return CardClass;
}

export function freezeClock(iso = FROZEN_NOW) {
  vi.useFakeTimers({ now: new Date(iso), toFake: ["Date"] });
}

export async function mountCard(config, hass, dir = "ltr") {
  document.body.innerHTML = "";
  document.documentElement.dir = dir;
  const card = document.createElement("ranzenpost-card");
  card.setConfig(config);
  document.body.appendChild(card);
  card.hass = hass;
  await card.settled;
  return card;
}

export function shadow(card) {
  return card.shadowRoot;
}

export function texts(root, selector) {
  return [...root.querySelectorAll(selector)].map((node) => node.textContent.trim());
}
