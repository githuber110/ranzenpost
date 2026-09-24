export const ICON_SHAPES = Object.freeze({
  download: '<path d="M12 4.4v10.4"/><path d="m7.6 10.6 4.4 4.4 4.4-4.4"/><path d="M4.6 16.2v1.8a1.8 1.8 0 0 0 1.8 1.8h11.2a1.8 1.8 0 0 0 1.8-1.8v-1.8"/>',
  print: '<path d="M7 8.4V4.6h10v3.8"/><rect x="4.2" y="8.4" width="15.6" height="7.4" rx="1.6"/><path d="M7 13.4h10v6H7z"/>',
  open: '<path d="M4.4 12s2.8-5.2 7.6-5.2 7.6 5.2 7.6 5.2-2.8 5.2-7.6 5.2S4.4 12 4.4 12z"/><circle cx="12" cy="12" r="2.3"/>',
  timetable: '<rect x="3.2" y="5.2" width="17.6" height="15.6" rx="3.6"/><path d="M8 2.9v4.4M16 2.9v4.4M3.2 10.4h17.6"/>',
  absence: '<path d="M14 14.3V5.4a2 2 0 0 0-4 0v8.9a3.9 3.9 0 1 0 4 0z"/><path d="M14 8.6h-2.3M14 11.4h-2.3"/>',
  overview: '<path d="M3.9 10.5 12 3.6l8.1 6.9v9.2a1.4 1.4 0 0 1-1.4 1.4H5.3a1.4 1.4 0 0 1-1.4-1.4z"/><path d="M9.4 21.1v-6.2h5.2v6.2"/>',
  letters: '<rect x="3.2" y="5.2" width="17.6" height="13.6" rx="3.6"/><path d="m4.4 7.8 6.7 4.6a1.6 1.6 0 0 0 1.8 0l6.7-4.6"/>',
  pinboard: '<path d="M9 3.4h6"/><path d="M10 3.4v6.3L7.1 14h9.8L14 9.7V3.4"/><path d="M12 14v6.6"/>',
  settings: '<circle cx="12" cy="12" r="3.1"/><circle cx="12" cy="12" r="7.3"/><path d="M12 2.8v1.9M12 19.3v1.9M21.2 12h-1.9M4.7 12H2.8M18.5 5.5l-1.3 1.3M6.8 17.2l-1.3 1.3M18.5 18.5l-1.3-1.3M6.8 6.8 5.5 5.5"/>',
  chevron: '<path d="m7.4 10.3 4.6 4.6 4.6-4.6"/>',
  today: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.3v5.1l3.3 1.9"/>',
  upcoming: '<rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3.4"/><path d="M8 3v4.4M16 3v4.4M3.4 10.4h17.2"/><path d="m8.7 15 2.3 2.3 4.3-4.3"/>',
  conferences: '<circle cx="9.2" cy="8.4" r="3.3"/><path d="M3.7 19.6a5.5 5.5 0 0 1 11 0"/><path d="M16.4 5.6a3.3 3.3 0 0 1 0 6.4"/><path d="M17.6 14.5a5.5 5.5 0 0 1 2.7 4.5"/>',
  clip: '<path d="M19.7 10.5 11 19.2a4.6 4.6 0 0 1-6.5-6.5l8.7-8.7a3.1 3.1 0 0 1 4.4 4.4l-8.7 8.7a1.5 1.5 0 0 1-2.2-2.2l8-8"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.6 4.6 4.6L19 7.4"/>',
  alert: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.6v5M12 15.8v.6"/>',
  phone: '<path d="M6.2 3.6h3.1l1.6 3.9-2 1.2a11 11 0 0 0 5 5l1.2-2 3.9 1.6v3.1a1.8 1.8 0 0 1-2 1.8A15.6 15.6 0 0 1 4.4 5.6a1.8 1.8 0 0 1 1.8-2z"/>',
  back: '<path d="M14.6 5.4 8 12l6.6 6.6"/>',
  folder: '<path d="M3.4 6.6a2 2 0 0 1 2-2h3.4l2 2.4h7.8a2 2 0 0 1 2 2v8.4a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2z"/>',
  filter: '<path d="M3.6 5.2h16.8l-6.5 7.7v6l-3.8 1.9v-7.9z" stroke-linejoin="round"/>',
  trash: '<path d="M4.6 6.8h14.8M9.4 6.8V4.6h5.2v2.2M6.6 6.8l.9 12.2a1.6 1.6 0 0 0 1.6 1.5h5.8a1.6 1.6 0 0 0 1.6-1.5l.9-12.2"/>',
  archive: '<rect x="3.4" y="4.4" width="17.2" height="4.4" rx="1.6"/><path d="M5.2 8.8v9.2a2 2 0 0 0 2 2h9.6a2 2 0 0 0 2-2V8.8"/><path d="M10 12.6h4"/>',
  restore: '<path d="M4.4 10.6a8 8 0 1 1 .6 6"/><path d="M3.6 4.8v5.8h5.8"/>',
  inbox: '<path d="M3.4 13.2h4.2l1.4 2.6h6l1.4-2.6h4.2"/><path d="M5.4 4.6h13.2l2 8.6v4.4a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2v-4.4z"/>',
  plus: '<path d="M12 5.4v13.2M5.4 12h13.2"/>',
  minus: '<path d="M5.4 12h13.2"/>',
  info: '<circle cx="12" cy="12" r="8.4"/><path d="M12 8.1h.01"/><path d="M12 11.4v5"/>',
  search: '<circle cx="10.6" cy="10.6" r="6.6"/><path d="m20 20-4.8-4.8"/>',
  calendarAdd: '<rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3.4"/><path d="M8 3v4.4M16 3v4.4M3.4 10.4h17.2"/><path d="M12 13.6v4.8M9.6 16h4.8"/>',
  exam: '<path d="M12 3.4 14.7 9l6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.9 9.3 9z" fill="currentColor" stroke-linejoin="round"/>',
  messages: '<path d="M20.6 11.6a8.4 8.4 0 0 1-8.4 8.4H4.4l1.9-3.5a8.4 8.4 0 1 1 14.3-4.9z"/><path d="M8.6 11.6h.01M12 11.6h.01M15.4 11.6h.01"/>',
  send: '<path d="M20.4 3.6 3.9 10.1a.5.5 0 0 0 .05.95l6.15 1.75 1.75 6.15a.5.5 0 0 0 .95.05z" stroke-linejoin="round"/><path d="m10.1 12.8 4.7-4.7"/>',
  qr: '<rect x="3.6" y="3.6" width="6.6" height="6.6" rx="1.6"/><rect x="13.8" y="3.6" width="6.6" height="6.6" rx="1.6"/><rect x="3.6" y="13.8" width="6.6" height="6.6" rx="1.6"/><path d="M13.8 13.8h3v3h-3z"/><path d="M20.4 13.8v3M20.4 20.4h-3.6M13.8 20.4h.01"/>',
  more: '<circle cx="5.6" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="18.4" cy="12" r="1.4" fill="currentColor"/>',
  lock: '<rect x="5.4" y="10.4" width="13.2" height="10" rx="2.4"/><path d="M8.4 10.4V7.6a3.6 3.6 0 0 1 7.2 0v2.8"/>',
  external: '<path d="M18.4 13.4v4.8a1.8 1.8 0 0 1-1.8 1.8H5.8A1.8 1.8 0 0 1 4 18.2V7.4a1.8 1.8 0 0 1 1.8-1.8h4.8"/><path d="M14.2 4h5.8v5.8"/><path d="M10.6 13.4 20 4"/>',
});

export function iconSvg(name, size) {
  const shape = ICON_SHAPES[name];
  if (!shape) return "";
  const sized = size ? ` style="width:${size}px;height:${size}px"` : "";
  return `<svg class="ico" viewBox="0 0 24 24" stroke="currentColor" fill="none" aria-hidden="true"${sized}>${shape}</svg>`;
}

export function createDom({ page }) {
  const el = (tag, attrs = {}, children = []) => {
    const node = page.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "html") node.innerHTML = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of [].concat(children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : page.createTextNode(child));
    }
    return node;
  };

  const iservText = (tag, attrs, children) => el(tag, Object.assign({ dir: "auto" }, attrs || {}), children);

  const icon = (name, size) => el("span", { class: "ico-slot", html: iconSvg(name, size) });

  const externalIcon = (size) => el("span", { class: "ico-slot ico-external", html: iconSvg("external", size) });

  return { el, iservText, icon, externalIcon };
}

export function domGlobals() {
  return Object.freeze({ ICON_SHAPES, iconSvg, createDom });
}
