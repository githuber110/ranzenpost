async function waitForBoot(page) {
  await page.waitForSelector(".screen", { state: "attached", timeout: 15000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 15000 }).catch(() => {});
}

async function goto(page, path = "/") {
  await page.goto(path);
  await waitForBoot(page);
}

async function openView(page, tabLabel) {
  await page.getByRole("button", { name: tabLabel, exact: true }).click();
  await page.waitForTimeout(50);
}

async function openSettings(page, ariaLabel) {
  await page.getByRole("button", { name: ariaLabel, exact: true }).click();
  await page.waitForTimeout(50);
}

function collectViolations(kind, message) {
  return { kind, message };
}

async function checkHorizontalOverflow(page) {
  return page.evaluate(() => {
    const root = document.scrollingElement || document.documentElement;
    const describe = (el) => {
      const cls = typeof el.className === "string" ? el.className : "";
      return `${el.tagName.toLowerCase()}${cls ? "." + cls.trim().split(/\s+/).join(".") : ""}`;
    };
    const containers = [{ selector: "document.scrollingElement", scrollWidth: root.scrollWidth, clientWidth: root.clientWidth }];
    document.querySelectorAll("body *").forEach((el) => {
      if (el.closest(".chipbar")) return;
      const style = getComputedStyle(el);
      if (style.overflowX !== "auto" && style.overflowX !== "scroll") return;
      containers.push({ selector: describe(el), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
    });
    const offenders = containers.filter((c) => c.scrollWidth > c.clientWidth + 1);
    return {
      scrollWidth: root.scrollWidth,
      clientWidth: root.clientWidth,
      overflow: offenders.length > 0,
      offendingContainers: offenders,
    };
  });
}

async function checkElementsWithinViewport(page) {
  return page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const offenders = [];
    const isVisible = (el) => {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      if (el.getAttribute("aria-hidden") === "true") return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const insideScrollableAncestor = (el) => !!el.closest(".chipbar");
    const all = document.querySelectorAll("body *");
    for (const el of all) {
      if (!isVisible(el)) continue;
      if (insideScrollableAncestor(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.right > viewportWidth + 1 || rect.left < -1) {
        offenders.push({
          tag: el.tagName,
          className: typeof el.className === "string" ? el.className : "",
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          viewportWidth,
        });
      }
    }
    return offenders.slice(0, 20);
  });
}

async function checkTapTargets(page) {
  return page.evaluate(() => {
    const parsePx = (value) => {
      if (value === "auto" || value === "" || value == null) return null;
      const num = parseFloat(value);
      return Number.isNaN(num) ? null : num;
    };
    const effectiveRect = (el) => {
      const rect = el.getBoundingClientRect();
      let top = rect.top;
      let left = rect.left;
      let right = rect.right;
      let bottom = rect.bottom;
      const after = getComputedStyle(el, "::after");
      if (after && after.content && after.content !== "none" && after.position === "absolute") {
        const t = parsePx(after.top);
        const b = parsePx(after.bottom);
        const l = parsePx(after.left);
        const r = parsePx(after.right);
        if (t !== null) top = Math.min(top, rect.top + t);
        if (b !== null) bottom = Math.max(bottom, rect.bottom - b);
        if (l !== null) left = Math.min(left, rect.left + l);
        if (r !== null) right = Math.max(right, rect.right - r);
      }
      return { width: right - left, height: bottom - top };
    };
    const isVisible = (el) => {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      if (el.disabled) return false;
      if (el.hasAttribute("disabled")) return false;
      if (el.getAttribute("aria-hidden") === "true") return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const offenders = [];
    const candidates = document.querySelectorAll('button, a[href], [role="button"]');
    for (const el of candidates) {
      if (!isVisible(el)) continue;
      const size = effectiveRect(el);
      if (size.width < 44 || size.height < 44) {
        offenders.push({
          tag: el.tagName,
          className: typeof el.className === "string" ? el.className : "",
          text: (el.textContent || "").trim().slice(0, 30),
          width: Math.round(size.width),
          height: Math.round(size.height),
        });
      }
    }
    return offenders.slice(0, 20);
  });
}

async function checkTapTargetOverlaps(page, minGap = 0) {
  return page.evaluate((gap) => {
    const parsePx = (value) => {
      if (value === "auto" || value === "" || value == null) return null;
      const num = parseFloat(value);
      return Number.isNaN(num) ? null : num;
    };
    const effectiveRect = (el) => {
      const rect = el.getBoundingClientRect();
      let top = rect.top;
      let left = rect.left;
      let right = rect.right;
      let bottom = rect.bottom;
      const after = getComputedStyle(el, "::after");
      if (after && after.content && after.content !== "none" && after.position === "absolute") {
        const t = parsePx(after.top);
        const b = parsePx(after.bottom);
        const l = parsePx(after.left);
        const r = parsePx(after.right);
        if (t !== null) top = Math.min(top, rect.top + t);
        if (b !== null) bottom = Math.max(bottom, rect.bottom - b);
        if (l !== null) left = Math.min(left, rect.left + l);
        if (r !== null) right = Math.max(right, rect.right - r);
      }
      return { top, left, right, bottom };
    };
    const isVisible = (el) => {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      if (el.disabled) return false;
      if (el.hasAttribute("disabled")) return false;
      if (el.getAttribute("aria-hidden") === "true") return false;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return false;
      if (rect.bottom <= 0 || rect.top >= window.innerHeight) return false;
      if (rect.right <= 0 || rect.left >= window.innerWidth) return false;
      return true;
    };
    const describe = (el) => {
      const cls = typeof el.className === "string" ? el.className : "";
      return `${el.tagName.toLowerCase()}${cls ? "." + cls.trim().split(/\s+/).join(".") : ""}`;
    };
    const fixedAncestor = (el) => {
      let node = el;
      while (node && node !== document.documentElement) {
        const style = getComputedStyle(node);
        if (style.position === "fixed" || style.position === "sticky") return node;
        node = node.parentElement;
      }
      return null;
    };
    const overlapCenter = (rectA, rectB) => {
      const left = Math.max(rectA.left, rectB.left);
      const right = Math.min(rectA.right, rectB.right);
      const top = Math.max(rectA.top, rectB.top);
      const bottom = Math.min(rectA.bottom, rectB.bottom);
      if (right <= left || bottom <= top) return null;
      return {
        x: Math.min(Math.max((left + right) / 2, 0), window.innerWidth - 1),
        y: Math.min(Math.max((top + bottom) / 2, 0), window.innerHeight - 1),
      };
    };
    const deterministicallyWins = (winner, loser, winnerRect, loserRect) => {
      const cover = fixedAncestor(winner);
      if (!cover || cover.contains(loser)) return false;
      const point = overlapCenter(winnerRect, loserRect);
      if (!point) return false;
      const topEl = document.elementFromPoint(point.x, point.y);
      return !!topEl && (topEl === winner || winner.contains(topEl) || cover.contains(topEl));
    };
    const candidates = [...document.querySelectorAll('button, a[href], [role="button"]')].filter(isVisible);
    const entries = candidates.map((el) => ({ el, rect: effectiveRect(el) }));
    const offenders = [];
    for (let i = 0; i < entries.length; i++) {
      for (let j = i + 1; j < entries.length; j++) {
        const a = entries[i];
        const b = entries[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const gapLeft = b.rect.left - a.rect.right;
        const gapRight = a.rect.left - b.rect.right;
        const gapTop = b.rect.top - a.rect.bottom;
        const gapBottom = a.rect.top - b.rect.bottom;
        const horizontalGap = Math.max(gapLeft, gapRight);
        const verticalGap = Math.max(gapTop, gapBottom);
        const separated = horizontalGap >= gap || verticalGap >= gap;
        if (!separated) {
          if (deterministicallyWins(a.el, b.el, a.rect, b.rect) || deterministicallyWins(b.el, a.el, b.rect, a.rect)) continue;
          offenders.push({
            a: describe(a.el),
            b: describe(b.el),
            aText: (a.el.textContent || "").trim().slice(0, 24),
            bText: (b.el.textContent || "").trim().slice(0, 24),
            horizontalGap: Math.round(horizontalGap),
            verticalGap: Math.round(verticalGap),
          });
        }
      }
    }
    return offenders.slice(0, 20);
  }, minGap);
}

async function waitForSheetSettled(page) {
  await page.waitForSelector(".sheet", { timeout: 5000 });
  await page.evaluate(async () => {
    const sheet = document.querySelector(".sheet");
    if (!sheet) return;
    if (typeof sheet.getAnimations !== "function") return;
    await Promise.all(sheet.getAnimations().map((animation) => animation.finished.catch(() => {})));
  });
}

async function checkSheetContainment(page) {
  return page.evaluate(() => {
    const sheet = document.querySelector(".sheet");
    if (!sheet) return { present: false };
    const body = sheet.querySelector(".sheet-body");
    const viewportHeight = window.innerHeight;
    const sheetRect = sheet.getBoundingClientRect();
    const fitsViewport = sheetRect.bottom <= viewportHeight + 1;
    if (!body) return { present: true, fitsViewport, scrollable: true, overflows: false };
    const overflows = body.scrollHeight > body.clientHeight + 1;
    const style = getComputedStyle(body);
    const scrollable = style.overflowY === "auto" || style.overflowY === "scroll";
    return { present: true, fitsViewport, overflows, scrollable };
  });
}

async function checkLastRowReachable(page, rowSelector) {
  return page.evaluate((selector) => {
    const screen = document.querySelector(".screen");
    if (!screen) return { present: false };
    const describe = (el) => {
      const cls = typeof el.className === "string" ? el.className : "";
      return `${el.tagName.toLowerCase()}${cls ? "." + cls.trim().split(/\s+/).join(".") : ""}`;
    };
    const fixedOverlays = [...document.querySelectorAll("body *")].filter((el) => {
      const style = getComputedStyle(el);
      if (style.position !== "fixed" && style.position !== "sticky") return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    screen.scrollTop = screen.scrollHeight;
    const rows = screen.querySelectorAll(selector);
    const last = rows[rows.length - 1];
    if (!last) return { present: false };
    const rowRect = last.getBoundingClientRect();
    const fullyScrolled = screen.scrollHeight - screen.scrollTop - screen.clientHeight <= 1;
    const covering = fixedOverlays.filter((el) => {
      if (el.contains(last) || last.contains(el)) return false;
      const rect = el.getBoundingClientRect();
      return rowRect.bottom > rect.top + 1 && rowRect.top < rect.bottom - 1 && rowRect.right > rect.left + 1 && rowRect.left < rect.right - 1;
    });
    return {
      present: true,
      fullyScrolled,
      covered: covering.length > 0,
      coveringElements: covering.map(describe),
      rowRect,
    };
  }, rowSelector);
}

module.exports = {
  waitForBoot,
  goto,
  openView,
  openSettings,
  waitForSheetSettled,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkTapTargetOverlaps,
  checkSheetContainment,
  checkLastRowReachable,
};
