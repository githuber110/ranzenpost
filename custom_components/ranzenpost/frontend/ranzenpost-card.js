(() => {
  const CARD_TAG = "ranzenpost-card";
  const EDITOR_TAG = "ranzenpost-card-editor";
  const DOMAIN = "ranzenpost";
  const VIEWS = ["today", "week", "family"];
  const DEFAULT_VIEW = "today";
  const DEFAULT_DAYS = 2;
  const CACHE_TTL_MS = 5 * 60 * 1000;
  const REGISTRY_TTL_MS = 60 * 1000;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const SCHOOL_DAYS = 5;
  const DEFAULT_PERIODS = 5;
  const SCROLL_FROM_CHILDREN = 4;
  const FALLBACK_LANGUAGE = "en";
  const KEY_LESSONS = "lessons";
  const KEY_EXAMS = "exams";
  const KEY_HOLIDAYS = "holidays";
  const WS_OWN_ENTRIES = `${DOMAIN}/own_entries`;
  const OWN_PREFIX = "own:";
  const KEY_CHANGES = "changes_today";
  const KEY_LETTERS = "unread_letters";
  const KEY_POSTS = "unread_posts";
  const KEY_SCHOOL_END = "school_end_today";
  const KEY_STAMP = "timetable_last_updated";
  const KEY_HOLIDAY = "next_holiday";
  const KEY_NEXT_LESSON = "next_lesson";
  const KEY_ABSENCES = "open_absences";
  const KEY_CONFERENCE = "next_conference";
  const KEY_CONNECTION = "connection";
  const CHILD_CALENDARS = [KEY_LESSONS, KEY_EXAMS, "absences"];
  const SIZE_COMPACT = "compact";
  const SIZE_NORMAL = "normal";
  const SIZES = [SIZE_COMPACT, SIZE_NORMAL];
  const ABSENCE_DAYS_AHEAD = 14;
  const BLOCK_CATALOGUE = [
    { key: "today", module: "timetable", area: "timetable", compact: 3, normal: 10, size: "normal", surfaces: ["overview", "card"], scope: "child" },
    { key: "next_lesson", module: "timetable", area: "timetable", compact: 1, normal: 1, size: "compact", surfaces: ["overview", "card"], scope: "child" },
    { key: "week", module: "timetable", area: "timetable", compact: 1, normal: 1, size: "normal", surfaces: ["overview", "card"], scope: "child" },
    { key: "letters", module: "letters", area: "post", compact: 3, normal: 5, size: "normal", surfaces: ["overview", "card"], scope: "family" },
    { key: "noticeboard", module: "pinboard", area: "post", compact: 3, normal: 5, size: "compact", surfaces: ["overview", "card"], scope: "family" },
    { key: "absences", module: "absences", area: "absence", compact: 2, normal: 5, size: "normal", surfaces: ["overview", "card"], scope: "child" },
    { key: "conferences", module: "conferences", area: "conferences", compact: 1, normal: 3, size: "normal", surfaces: ["overview", "card"], scope: "school" },
    { key: "holidays", module: "timetable", area: "timetable", compact: 1, normal: 3, size: "compact", surfaces: ["overview", "card"], scope: "school" },
    { key: "changes", module: "timetable", area: "timetable", compact: 3, normal: 6, size: "compact", surfaces: ["overview", "card"], scope: "child" },
    { key: "chat", module: "messenger", area: "messenger", compact: 3, normal: 5, size: "compact", surfaces: ["overview"], scope: "family" },
  ];
  const BLOCK_BY_KEY = new Map(BLOCK_CATALOGUE.map((block) => [block.key, block]));
  const CARD_BLOCKS = BLOCK_CATALOGUE.filter((block) => block.surfaces.includes("card"));
  const LEGACY_BLOCKS = { today: ["today"], week: ["week"], family: ["today", "letters", "noticeboard", "holidays"] };
  const TIMETABLE_BLOCKS = ["today", "next_lesson", "week", "changes"];
  const DAY_BLOCKS = ["today", "next_lesson", "week"];
  const MISSING_STATES = new Set(["unknown", "unavailable", "none", ""]);
  const BIDI_MARKS = new RegExp(`[${String.fromCharCode(0x200e, 0x200f, 0x061c)}]`, "g");
  const CHILD_COLORS = ["#0e6b70", "#7a4b9c", "#b4602a", "#2f6b3a", "#9c3b5e", "#3a5a9c"];
  const RanzenpostColour = (() => {
    const PALETTE = [
      ["white", "#ffffff", "#ffffff", "#8a9793", "#e3e8e6", "#6f7c79"],
      ["yellow", "#ffe100", "#ffe100", "#8a7a00", "#e6cf00", "#6e6300"],
      ["orange", "#ff9a1f", "#ff9a1f", "#8a4a00", "#ec8a14", "#7a4600"],
      ["red", "#d42020", "#d42020", "#ffb0b0", "#c92a2a", "#ffb0b0"],
      ["pink", "#ff69b4", "#ffb0cc", "#b8235f", "#f08ab2", "#8e1f4c"],
      ["magenta", "#c2187a", "#c2187a", "#ffb0dc", "#b8267a", "#ffb0dc"],
      ["purple", "#8f24b4", "#8f24b4", "#e2b8ff", "#9a38c0", "#e2b8ff"],
      ["lavender", "#9b7de8", "#d6c2ff", "#6f47c9", "#b39cf2", "#5b3bb0"],
      ["indigo", "#3d3ad0", "#3d3ad0", "#c0bfff", "#5a4ee6", "#c8c4ff"],
      ["blue", "#2a66d6", "#2a66d6", "#b0ccff", "#2860c8", "#b0ccff"],
      ["navy", "#1a2a66", "#1a2a66", "#9db0ff", "#243580", "#9db0ff"],
      ["sky", "#3b9cf0", "#b0d8ff", "#1c74c4", "#7ab8f2", "#0f4f8c"],
      ["cyan", "#22d3ee", "#22d3ee", "#0a6f80", "#22b8d0", "#075a68"],
      ["teal", "#0f7470", "#0f7470", "#9fe0dc", "#0f6e6a", "#9fe0dc"],
      ["mint", "#2ec48a", "#b6f0d6", "#1f8a63", "#7dd8b4", "#14624a"],
      ["green", "#2fa83c", "#4dbf57", "#1c5e22", "#3faa4c", "#164e1e"],
      ["forest", "#1f5c2c", "#1f5c2c", "#a8e6b4", "#2a6f39", "#a8e6b4"],
      ["lime", "#9be020", "#b8f03a", "#527a08", "#9fd428", "#4a6e08"],
      ["olive", "#8a8a1e", "#a8a626", "#4f4e0c", "#908e1e", "#3a3908"],
      ["brown", "#7a4a22", "#7a4a22", "#e6bd96", "#8a552a", "#e6bd96"],
      ["sand", "#c9a45c", "#e8d2a4", "#8a6a30", "#c9b07f", "#6e5426"],
      ["grey", "#8d9795", "#b9c0be", "#525c5a", "#8d9795", "#3e4745"],
      ["black", "#000000", "#262b2a", "#9aa5a1", "#000000", "#8a9793"],
      ["maroon", "#7a1236", "#7a1236", "#ffb0c8", "#8c1a42", "#ffb0c8"],
    ];
    const FIELDS = ["name", "base", "lightFill", "lightBar", "darkFill", "darkBar"];
    const DARK_INK = "#000000";
    const LIGHT_INK = "#ffffff";
    const BAR_SHADE = 0.55;
    const DEFAULT_NAME = "grey";
    const HEX = /^#?([0-9a-f]{6})$/;
    const entries = PALETTE.map((row) => Object.fromEntries(row.map((value, index) => [FIELDS[index], value])));
    const byName = new Map(entries.map((entry) => [entry.name, entry]));
    const byBase = new Map(entries.map((entry) => [entry.base, entry]));

    function parseHex(value) {
      const match = HEX.exec(String(value || "").trim().toLowerCase());
      return match ? `#${match[1]}` : "";
    }

    function isHex(value) {
      return /^#[0-9a-f]{6}$/i.test(String(value || "").trim());
    }

    function rgbOf(hex) {
      return [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16));
    }

    function hexOf(rgb) {
      return `#${rgb.map((channel) => Math.max(0, Math.min(255, Math.round(channel))).toString(16).padStart(2, "0")).join("")}`;
    }

    function linear(channel) {
      const value = channel / 255;
      return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    }

    function luminance(hex) {
      const [red, green, blue] = rgbOf(hex).map(linear);
      return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    }

    function contrast(hexA, hexB) {
      const lumA = luminance(hexA);
      const lumB = luminance(hexB);
      const lighter = Math.max(lumA, lumB);
      const darker = Math.min(lumA, lumB);
      return (lighter + 0.05) / (darker + 0.05);
    }

    function inkFor(fill) {
      return contrast(DARK_INK, fill) >= contrast(LIGHT_INK, fill) ? DARK_INK : LIGHT_INK;
    }

    function barFor(fill) {
      const target = inkFor(fill) === DARK_INK ? 0 : 255;
      return hexOf(rgbOf(fill).map((channel) => channel + (target - channel) * BAR_SHADE));
    }

    function entryOf(value) {
      const text = String(value || "").trim().toLowerCase();
      if (!text) return null;
      if (byName.has(text)) return byName.get(text);
      const hex = parseHex(text);
      if (hex) return byBase.get(hex) || null;
      return byName.get(DEFAULT_NAME);
    }

    function resolve(value) {
      const text = String(value || "").trim();
      if (!text) return null;
      const entry = entryOf(text);
      if (entry) {
        return {
          name: entry.name,
          custom: false,
          hex: entry.base,
          light: { fill: entry.lightFill, ink: inkFor(entry.lightFill), bar: entry.lightBar },
          dark: { fill: entry.darkFill, ink: inkFor(entry.darkFill), bar: entry.darkBar },
        };
      }
      const hex = parseHex(text);
      const theme = { fill: hex, ink: inkFor(hex), bar: barFor(hex) };
      return { name: "", custom: true, hex, light: theme, dark: { ...theme } };
    }

    function cellVars(value) {
      const colour = resolve(value);
      if (!colour) return null;
      if (colour.custom) return { fill: colour.light.fill, ink: colour.light.ink, bar: colour.light.bar };
      return {
        fill: `var(--subject-${colour.name}-fill)`,
        ink: `var(--subject-${colour.name}-ink)`,
        bar: `var(--subject-${colour.name}-bar)`,
      };
    }

    function tokens(theme) {
      const result = {};
      for (const entry of entries) {
        const fill = theme === "dark" ? entry.darkFill : entry.lightFill;
        result[`subject-${entry.name}-fill`] = fill;
        result[`subject-${entry.name}-bar`] = theme === "dark" ? entry.darkBar : entry.lightBar;
        result[`subject-${entry.name}-ink`] = inkFor(fill);
      }
      return result;
    }

    return {
      PALETTE: entries,
      NAMES: entries.map((entry) => entry.name),
      DARK_INK,
      LIGHT_INK,
      DEFAULT_NAME,
      parseHex,
      isHex,
      luminance,
      contrast,
      inkFor,
      barFor,
      entryOf,
      resolve,
      cellVars,
      tokens,
    };
  })();
  const CROSS = String.fromCharCode(0x00d7);

  const ICON_SHAPES = {
    exam: '<path d="M12 3.4 14.7 9l6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.9 9.3 9z" fill="currentColor" stroke-linejoin="round"/>',
    upcoming: '<rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3.4"/><path d="M8 3v4.4M16 3v4.4M3.4 10.4h17.2"/><path d="m8.7 15 2.3 2.3 4.3-4.3"/>',
    alert: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.6v5M12 15.8v.6"/>',
    timetable: '<rect x="3.2" y="5.2" width="17.6" height="15.6" rx="3.6"/><path d="M8 2.9v4.4M16 2.9v4.4M3.2 10.4h17.6"/>',
  };

  const TEXTS = {
    de: {
      "card.description": "Stundenplan, Vertretungen und Post aus Ranzenpost",
      "view.today": "Heute",
      "view.week": "Woche",
      "view.family": "Familie",
      "today.free": "Heute ist schulfrei.",
      "day.free": "Schulfrei",
      "timetable.none": "Diese Schule stellt keinen Stundenplan bereit.",
      "lesson.now": "Jetzt",
      "lesson.next": "Nächste",
      "lesson.substitution": "Vertretung",
      "lesson.substitutionShort": "Vertr.",
      "lesson.cancelled": "Entfällt",
      "lesson.exam": "Prüfung",
      "count.letters": "Elternbriefe",
      "count.posts": "Pinnwand",
      "count.changes": "Änderungen",
      "holiday.from": "ab {date}",
      "holiday.until": "bis {date}",
      "date.range": "{from} – {till}",
      "day.today": "Heute",
      "day.tomorrow": "Morgen",
      "school.end": "Die letzte Stunde endet um {time}.",
      "school.over": "Der Unterricht ist für heute vorbei.",
      "own.until": "Eigener Eintrag · bis {time}",
      "stamp": "Stand {time}",
      "child.missing": "Keine Person gewählt. Trage in der Karte „child“ ein.",
      "child.unknown": "Person „{child}“ nicht gefunden.",
      "children.none": "Die Ranzenpost-Integration hat noch keine Profile.",
      "error.title": "Nicht erreichbar",
      "state.unavailable": "Ranzenpost ist gerade nicht erreichbar.",
      "config.view": "Die Ansicht muss today, week oder family sein.",
      "editor.view": "Ansicht",
      "editor.child": "Person",
      "editor.children": "Profile",
      "editor.allChildren": "Leer lassen für alle Profile",
      "editor.title": "Titel",
      "editor.days": "Tage",
      "editor.days1": "Nur heute",
      "editor.days2": "Heute und morgen",
      "block.today": "Heute",
      "block.today.explain": "Stunden von heute, Änderungen, Schulschluss.",
      "block.next_lesson": "Nächste Stunde",
      "block.next_lesson.explain": "Die nächste Stunde, auch morgen früh.",
      "block.week": "Woche",
      "block.week.explain": "Der Stundenplan der laufenden Woche.",
      "block.letters": "Elternbriefe",
      "block.letters.explain": "Ungelesene Elternbriefe.",
      "block.noticeboard": "Pinnwand",
      "block.noticeboard.explain": "Neue Beiträge der Pinnwände.",
      "block.absences": "Abwesenheiten",
      "block.absences.explain": "Gemeldete Abwesenheiten, 14 Tage voraus.",
      "block.conferences": "Elternsprechtage",
      "block.conferences.explain": "Nur wenn ein Sprechtag eingetragen ist.",
      "block.holidays": "Ferien",
      "block.holidays.explain": "Die nächsten Ferien und freien Tage.",
      "block.changes": "Änderungen",
      "block.changes.explain": "Vertretungen und Ausfälle von heute.",
      "block.chat": "Chat",
      "block.chat.explain": "Räume mit ungelesenen Nachrichten.",
      "block.showAll": "Alle ansehen",
      "block.toTimetable": "Zum Stundenplan",
      "block.noBlocks": "Keine Bausteine gewählt. Wähle in der Karte mindestens einen.",
      "block.unknown": "Unbekannter Baustein „{block}“.",
      "editor.blocks": "Bausteine",
      "editor.blocks.helper": "Nur Bausteine der Module, die dein Konto hat.",
      "editor.blocks.missing": "Ohne Modul an dieser Schule: {names}.",
      "editor.size": "Größe von {name}",
      "editor.size.compact": "Kompakt",
      "editor.size.normal": "Normal",
      "editor.sizes": "Größe je Baustein",
      "status.open": "Offen",
      "status.accepted": "Genehmigt",
      "status.rejected": "Abgelehnt",
    },
    en: {
      "card.description": "Timetable, substitutions and school mail from Ranzenpost",
      "view.today": "Today",
      "view.week": "Week",
      "view.family": "Family",
      "today.free": "No school today.",
      "day.free": "No school",
      "timetable.none": "This school does not provide a timetable.",
      "lesson.now": "Now",
      "lesson.next": "Next",
      "lesson.substitution": "Substitute",
      "lesson.substitutionShort": "Sub.",
      "lesson.cancelled": "Cancelled",
      "lesson.exam": "Exam",
      "count.letters": "Letters",
      "count.posts": "Notices",
      "count.changes": "Changes",
      "holiday.from": "from {date}",
      "holiday.until": "until {date}",
      "date.range": "{from} – {till}",
      "day.today": "Today",
      "day.tomorrow": "Tomorrow",
      "school.end": "The last lesson ends at {time}.",
      "school.over": "Lessons are over for today.",
      "own.until": "Own entry · until {time}",
      "stamp": "Updated {time}",
      "child.missing": "No person chosen. Set “child” in the card.",
      "child.unknown": "Person “{child}” not found.",
      "children.none": "The Ranzenpost integration has no profiles yet.",
      "error.title": "Can't connect",
      "state.unavailable": "Ranzenpost cannot be reached right now.",
      "config.view": "The view must be today, week or family.",
      "editor.view": "View",
      "editor.child": "Person",
      "editor.children": "Profiles",
      "editor.allChildren": "Leave empty for all profiles",
      "editor.title": "Title",
      "editor.days": "Days",
      "editor.days1": "Today only",
      "editor.days2": "Today and tomorrow",
      "block.today": "Today",
      "block.today.explain": "Today's lessons, changes and the end of school.",
      "block.next_lesson": "Next lesson",
      "block.next_lesson.explain": "The next lesson, even tomorrow morning.",
      "block.week": "Week",
      "block.week.explain": "The timetable of the current week.",
      "block.letters": "Letters",
      "block.letters.explain": "Unread letters.",
      "block.noticeboard": "Noticeboard",
      "block.noticeboard.explain": "New posts on the noticeboards.",
      "block.absences": "Absences",
      "block.absences.explain": "Reported absences, 14 days ahead.",
      "block.conferences": "Parent conferences",
      "block.conferences.explain": "Only when a conference day is listed.",
      "block.holidays": "Holidays",
      "block.holidays.explain": "The next holidays and free days.",
      "block.changes": "Changes",
      "block.changes.explain": "Substitutions and cancellations of today.",
      "block.chat": "Chat",
      "block.chat.explain": "Rooms with unread messages.",
      "block.showAll": "Show all",
      "block.toTimetable": "Open the timetable",
      "block.noBlocks": "No blocks chosen. Pick at least one in the card.",
      "block.unknown": "Unknown block “{block}”.",
      "editor.blocks": "Blocks",
      "editor.blocks.helper": "Only blocks of the modules your account has.",
      "editor.blocks.missing": "Without a module at this school: {names}.",
      "editor.size": "Size of {name}",
      "editor.size.compact": "Compact",
      "editor.size.normal": "Normal",
      "editor.sizes": "Size per block",
      "status.open": "Open",
      "status.accepted": "Accepted",
      "status.rejected": "Rejected",
    },
    ar: {
      "card.description": "الجدول الدراسي والبدائل ورسائل المدرسة من Ranzenpost",
      "view.today": "اليوم",
      "view.week": "الأسبوع",
      "view.family": "العائلة",
      "today.free": "اليوم عطلة مدرسية.",
      "day.free": "لا توجد دراسة",
      "timetable.none": "هذه المدرسة لا توفر جدولًا دراسيًا.",
      "lesson.now": "الآن",
      "lesson.next": "التالية",
      "lesson.substitution": "حصة بديلة",
      "lesson.substitutionShort": "بديل",
      "lesson.cancelled": "ملغاة",
      "lesson.exam": "اختبار",
      "count.letters": "الرسائل",
      "count.posts": "الإعلانات",
      "count.changes": "التغييرات",
      "holiday.from": "من {date}",
      "holiday.until": "حتى {date}",
      "date.range": "{from} – {till}",
      "day.today": "اليوم",
      "day.tomorrow": "غدًا",
      "school.end": "تنتهي الحصة الأخيرة في {time}.",
      "school.over": "انتهت الدروس لهذا اليوم.",
      "own.until": "إدخال خاص بك · حتى {time}",
      "stamp": "آخر تحديث {time}",
      "child.missing": "لم يُختر شخص. أدخل «child» في البطاقة.",
      "child.unknown": "الشخص «{child}» غير موجود.",
      "children.none": "لا توجد ملفات شخصية في تكامل Ranzenpost بعد.",
      "error.title": "تعذّر الوصول",
      "state.unavailable": "تعذر الوصول إلى Ranzenpost حاليًا.",
      "config.view": "يجب أن يكون العرض today أو week أو family.",
      "editor.view": "العرض",
      "editor.child": "الشخص",
      "editor.children": "الملفات الشخصية",
      "editor.allChildren": "اتركه فارغًا لكل الملفات الشخصية",
      "editor.title": "العنوان",
      "editor.days": "الأيام",
      "editor.days1": "اليوم فقط",
      "editor.days2": "اليوم وغدًا",
      "block.today": "اليوم",
      "block.today.explain": "حصص اليوم والتغييرات ونهاية الدوام.",
      "block.next_lesson": "الحصة التالية",
      "block.next_lesson.explain": "الحصة التالية، حتى صباح الغد.",
      "block.week": "الأسبوع",
      "block.week.explain": "جدول الأسبوع الجاري.",
      "block.letters": "رسائل الأهل",
      "block.letters.explain": "رسائل الأهل غير المقروءة.",
      "block.noticeboard": "لوحة الإعلانات",
      "block.noticeboard.explain": "المنشورات الجديدة على لوحات الإعلانات.",
      "block.absences": "الغيابات",
      "block.absences.explain": "الغيابات المبلغ عنها خلال 14 يومًا.",
      "block.conferences": "لقاءات الأهل",
      "block.conferences.explain": "فقط عند وجود موعد لقاء مسجل.",
      "block.holidays": "العطل",
      "block.holidays.explain": "العطل والأيام الحرة القادمة.",
      "block.changes": "التغييرات",
      "block.changes.explain": "الحصص البديلة والملغاة اليوم.",
      "block.chat": "الدردشة",
      "block.chat.explain": "الغرف التي فيها رسائل غير مقروءة.",
      "block.showAll": "عرض الكل",
      "block.toTimetable": "فتح الجدول",
      "block.noBlocks": "لم تُختر كتل. اختر كتلة واحدة على الأقل في البطاقة.",
      "block.unknown": "كتلة غير معروفة «{block}».",
      "editor.blocks": "الكتل",
      "editor.blocks.helper": "فقط كتل الوحدات التي يملكها حسابك.",
      "editor.blocks.missing": "بلا وحدة في هذه المدرسة: {names}.",
      "editor.size": "حجم {name}",
      "editor.size.compact": "مضغوط",
      "editor.size.normal": "عادي",
      "editor.sizes": "الحجم لكل كتلة",
      "status.open": "مفتوح",
      "status.accepted": "مقبول",
      "status.rejected": "مرفوض",
    },
    tr: {
      "card.description": "Ranzenpost'tan ders programı, vekil dersler ve okul postası",
      "view.today": "Bugün",
      "view.week": "Hafta",
      "view.family": "Aile",
      "today.free": "Bugün okul yok.",
      "day.free": "Okul yok",
      "timetable.none": "Bu okul ders programı sunmuyor.",
      "lesson.now": "Şimdi",
      "lesson.next": "Sonraki",
      "lesson.substitution": "Vekil öğretmen",
      "lesson.substitutionShort": "Vekil",
      "lesson.cancelled": "İptal",
      "lesson.exam": "Sınav",
      "count.letters": "Mektuplar",
      "count.posts": "Duyurular",
      "count.changes": "Değişiklikler",
      "holiday.from": "{date} tarihinden itibaren",
      "holiday.until": "{date} tarihine kadar",
      "date.range": "{from} – {till}",
      "day.today": "Bugün",
      "day.tomorrow": "Yarın",
      "school.end": "Son ders {time} itibarıyla bitiyor.",
      "school.over": "Bugünkü dersler bitti.",
      "own.until": "Kendi kayıt · {time} saatine kadar",
      "stamp": "Son güncelleme {time}",
      "child.missing": "Kişi seçilmedi. Karta “child” girin.",
      "child.unknown": "“{child}” adlı kişi bulunamadı.",
      "children.none": "Ranzenpost entegrasyonunda henüz profil yok.",
      "error.title": "Ulaşılamıyor",
      "state.unavailable": "Ranzenpost şu anda ulaşılamıyor.",
      "config.view": "Görünüm today, week veya family olmalı.",
      "editor.view": "Görünüm",
      "editor.child": "Kişi",
      "editor.children": "Profiller",
      "editor.allChildren": "Tüm profiller için boş bırakın",
      "editor.title": "Başlık",
      "editor.days": "Gün",
      "editor.days1": "Yalnızca bugün",
      "editor.days2": "Bugün ve yarın",
      "block.today": "Bugün",
      "block.today.explain": "Bugünün dersleri, değişiklikler ve okul çıkışı.",
      "block.next_lesson": "Sonraki ders",
      "block.next_lesson.explain": "Sonraki ders, yarın sabah olsa bile.",
      "block.week": "Hafta",
      "block.week.explain": "Bu haftanın ders programı.",
      "block.letters": "Veli mektupları",
      "block.letters.explain": "Okunmamış veli mektupları.",
      "block.noticeboard": "Pano",
      "block.noticeboard.explain": "Panolardaki yeni gönderiler.",
      "block.absences": "Devamsızlıklar",
      "block.absences.explain": "Bildirilen devamsızlıklar, 14 gün ilerisi.",
      "block.conferences": "Veli görüşmeleri",
      "block.conferences.explain": "Yalnızca bir görüşme günü kayıtlıysa.",
      "block.holidays": "Tatiller",
      "block.holidays.explain": "Sıradaki tatiller ve boş günler.",
      "block.changes": "Değişiklikler",
      "block.changes.explain": "Bugünün vekil dersleri ve iptalleri.",
      "block.chat": "Sohbet",
      "block.chat.explain": "Okunmamış mesajı olan odalar.",
      "block.showAll": "Tümünü gör",
      "block.toTimetable": "Ders programını aç",
      "block.noBlocks": "Blok seçilmedi. Kartta en az bir blok seç.",
      "block.unknown": "Bilinmeyen blok “{block}”.",
      "editor.blocks": "Bloklar",
      "editor.blocks.helper": "Yalnızca hesabının sahip olduğu modüllerin blokları.",
      "editor.blocks.missing": "Bu okulda modülü olmayan: {names}.",
      "editor.size": "{name} boyutu",
      "editor.size.compact": "Sıkışık",
      "editor.size.normal": "Normal",
      "editor.sizes": "Blok başına boyut",
      "status.open": "Açık",
      "status.accepted": "Onaylandı",
      "status.rejected": "Reddedildi",
    },
    ru: {
      "card.description": "Расписание, замены и школьная почта из Ranzenpost",
      "view.today": "Сегодня",
      "view.week": "Неделя",
      "view.family": "Семья",
      "today.free": "Сегодня занятий нет.",
      "day.free": "Занятий нет",
      "timetable.none": "Эта школа не предоставляет расписание.",
      "lesson.now": "Сейчас",
      "lesson.next": "Следующий",
      "lesson.substitution": "Замена",
      "lesson.substitutionShort": "Замена",
      "lesson.cancelled": "Отмена",
      "lesson.exam": "Контрольная",
      "count.letters": "Письма",
      "count.posts": "Объявления",
      "count.changes": "Изменения",
      "holiday.from": "с {date}",
      "holiday.until": "до {date}",
      "date.range": "{from} – {till}",
      "day.today": "Сегодня",
      "day.tomorrow": "Завтра",
      "school.end": "Последний урок заканчивается в {time}.",
      "school.over": "Уроки на сегодня закончились.",
      "own.until": "Своя запись · до {time}",
      "stamp": "Обновлено {time}",
      "child.missing": "Человек не выбран. Укажите «child» в карточке.",
      "child.unknown": "Человек «{child}» не найден.",
      "children.none": "В интеграции Ranzenpost пока нет профилей.",
      "error.title": "Нет связи",
      "state.unavailable": "Ranzenpost сейчас недоступен.",
      "config.view": "Вид должен быть today, week или family.",
      "editor.view": "Вид",
      "editor.child": "Человек",
      "editor.children": "Профили",
      "editor.allChildren": "Оставьте пустым для всех профилей",
      "editor.title": "Заголовок",
      "editor.days": "Дни",
      "editor.days1": "Только сегодня",
      "editor.days2": "Сегодня и завтра",
      "block.today": "Сегодня",
      "block.today.explain": "Уроки на сегодня, изменения, конец занятий.",
      "block.next_lesson": "Следующий урок",
      "block.next_lesson.explain": "Следующий урок, даже завтра утром.",
      "block.week": "Неделя",
      "block.week.explain": "Расписание текущей недели.",
      "block.letters": "Письма родителям",
      "block.letters.explain": "Непрочитанные письма родителям.",
      "block.noticeboard": "Доска объявлений",
      "block.noticeboard.explain": "Новые записи на досках объявлений.",
      "block.absences": "Отсутствия",
      "block.absences.explain": "Заявленные отсутствия на 14 дней вперёд.",
      "block.conferences": "Родительские встречи",
      "block.conferences.explain": "Только если назначен день встреч.",
      "block.holidays": "Каникулы",
      "block.holidays.explain": "Ближайшие каникулы и свободные дни.",
      "block.changes": "Изменения",
      "block.changes.explain": "Замены и отмены на сегодня.",
      "block.chat": "Чат",
      "block.chat.explain": "Комнаты с непрочитанными сообщениями.",
      "block.showAll": "Показать все",
      "block.toTimetable": "Открыть расписание",
      "block.noBlocks": "Блоки не выбраны. Выберите в карточке хотя бы один.",
      "block.unknown": "Неизвестный блок «{block}».",
      "editor.blocks": "Блоки",
      "editor.blocks.helper": "Только блоки модулей, которые есть у вашего аккаунта.",
      "editor.blocks.missing": "Без модуля в этой школе: {names}.",
      "editor.size": "Размер блока {name}",
      "editor.size.compact": "Компактно",
      "editor.size.normal": "Обычно",
      "editor.sizes": "Размер каждого блока",
      "status.open": "Открыто",
      "status.accepted": "Одобрено",
      "status.rejected": "Отклонено",
    },
    uk: {
      "card.description": "Розклад, заміни та шкільна пошта з Ranzenpost",
      "view.today": "Сьогодні",
      "view.week": "Тиждень",
      "view.family": "Сім'я",
      "today.free": "Сьогодні уроків немає.",
      "day.free": "Занять немає",
      "timetable.none": "Ця школа не надає розклад.",
      "lesson.now": "Зараз",
      "lesson.next": "Наступний",
      "lesson.substitution": "Заміна",
      "lesson.substitutionShort": "Зам.",
      "lesson.cancelled": "Скасовано",
      "lesson.exam": "Контрольна",
      "count.letters": "Листи",
      "count.posts": "Оголошення",
      "count.changes": "Зміни",
      "holiday.from": "з {date}",
      "holiday.until": "до {date}",
      "date.range": "{from} – {till}",
      "day.today": "Сьогодні",
      "day.tomorrow": "Завтра",
      "school.end": "Останній урок закінчується о {time}.",
      "school.over": "Уроки на сьогодні закінчилися.",
      "own.until": "Власний запис · до {time}",
      "stamp": "Станом на {time}",
      "child.missing": "Особу не вибрано. Вкажіть «child» у картці.",
      "child.unknown": "Особу «{child}» не знайдено.",
      "children.none": "В інтеграції Ranzenpost ще немає профілів.",
      "error.title": "Немає зв’язку",
      "state.unavailable": "Ranzenpost зараз недоступний.",
      "config.view": "Вигляд має бути today, week або family.",
      "editor.view": "Вигляд",
      "editor.child": "Особа",
      "editor.children": "Профілі",
      "editor.allChildren": "Залиште порожнім для всіх профілів",
      "editor.title": "Заголовок",
      "editor.days": "Дні",
      "editor.days1": "Лише сьогодні",
      "editor.days2": "Сьогодні і завтра",
      "block.today": "Сьогодні",
      "block.today.explain": "Уроки на сьогодні, зміни, кінець занять.",
      "block.next_lesson": "Наступний урок",
      "block.next_lesson.explain": "Наступний урок, навіть завтра вранці.",
      "block.week": "Тиждень",
      "block.week.explain": "Розклад поточного тижня.",
      "block.letters": "Листи батькам",
      "block.letters.explain": "Непрочитані листи батькам.",
      "block.noticeboard": "Дошка оголошень",
      "block.noticeboard.explain": "Нові дописи на дошках оголошень.",
      "block.absences": "Відсутності",
      "block.absences.explain": "Заявлені відсутності на 14 днів наперед.",
      "block.conferences": "Батьківські зустрічі",
      "block.conferences.explain": "Лише якщо призначено день зустрічей.",
      "block.holidays": "Канікули",
      "block.holidays.explain": "Найближчі канікули та вільні дні.",
      "block.changes": "Зміни",
      "block.changes.explain": "Заміни та скасування на сьогодні.",
      "block.chat": "Чат",
      "block.chat.explain": "Кімнати з непрочитаними повідомленнями.",
      "block.showAll": "Показати все",
      "block.toTimetable": "Відкрити розклад",
      "block.noBlocks": "Блоки не вибрано. Виберіть у картці хоча б один.",
      "block.unknown": "Невідомий блок «{block}».",
      "editor.blocks": "Блоки",
      "editor.blocks.helper": "Лише блоки модулів, які має ваш обліковий запис.",
      "editor.blocks.missing": "Без модуля в цій школі: {names}.",
      "editor.size": "Розмір блоку {name}",
      "editor.size.compact": "Компактно",
      "editor.size.normal": "Звичайно",
      "editor.sizes": "Розмір кожного блоку",
      "status.open": "Відкрито",
      "status.accepted": "Схвалено",
      "status.rejected": "Відхилено",
    },
  };

  const LIGHT_TOKENS = {
    bg: "#e4eae8",
    surface: "#ffffff",
    "surface-2": "#d9e1de",
    "surface-sunken": "#d0dad6",
    line: "#c0cbc8",
    "line-strong": "#66807a",
    hairline: "color-mix(in srgb, var(--line) 60%, transparent)",
    ink: "#101917",
    "ink-2": "#3a463f",
    "ink-3": "#515f59",
    accent: "#0e6b70",
    "accent-ink": "#ffffff",
    "accent-soft": "#d0e4e3",
    warn: "#6e4409",
    "warn-soft": "#faeedd",
    "warn-tint": "#f7e3c2",
    danger: "#b03a2e",
    "danger-soft": "#fae7e4",
    "badge-ink": "#ffffff",
    "sh-1": "0 1px 2px rgba(16, 25, 23, 0.06), 0 3px 10px -2px rgba(16, 25, 23, 0.07)",
    "sh-sunken": "inset 0 1px 2px rgba(16, 25, 23, 0.06)",
  };

  const DARK_TOKENS = {
    bg: "#0e1412",
    surface: "#18201e",
    "surface-2": "#202927",
    "surface-sunken": "#0b100f",
    line: "#2c3735",
    "line-strong": "#627470",
    ink: "#e9efed",
    "ink-2": "#a7b4b1",
    "ink-3": "#84938f",
    accent: "#4fbdba",
    "accent-ink": "#06231f",
    "accent-soft": "#12332f",
    warn: "#e0a45c",
    "warn-soft": "#31251a",
    "warn-tint": "#31251a",
    danger: "#ef8074",
    "danger-soft": "#33201d",
    "badge-ink": "#33201d",
    "sh-1": "0 2px 8px -2px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(233, 239, 237, 0.05)",
    "sh-sunken": "inset 0 1px 2px rgba(0, 0, 0, 0.4)",
  };

  const SCALE_TOKENS = {
    "s-1": "2px",
    "s-2": "4px",
    "s-3": "6px",
    "s-4": "8px",
    "s-5": "12px",
    "s-6": "16px",
    "s-7": "20px",
    "s-8": "24px",
    "s-9": "32px",
    "s-10": "40px",
    "s-11": "48px",
    "r-xs": "6px",
    "r-sm": "10px",
    "r-md": "14px",
    "r-lg": "18px",
    "r-xl": "24px",
    "r-full": "999px",
    "tt-stack-gap": "2px",
    "tt-row": "52px",
    "font-display": '"Archivo", "Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    "font-text": '"Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  };

  function tokenBlock(tokens) {
    return Object.entries(tokens)
      .map(([name, value]) => `--${name}: ${value};`)
      .join(" ");
  }

  const STYLE = `
    :host { display: block; container: card / inline-size; ${tokenBlock(LIGHT_TOKENS)} ${tokenBlock(RanzenpostColour.tokens("light"))} ${tokenBlock(SCALE_TOKENS)} color-scheme: light; }
    @media (prefers-color-scheme: dark) { :host(:not([data-theme="light"])) { ${tokenBlock(DARK_TOKENS)} ${tokenBlock(RanzenpostColour.tokens("dark"))} color-scheme: dark; } }
    :host([data-theme="dark"]) { ${tokenBlock(DARK_TOKENS)} ${tokenBlock(RanzenpostColour.tokens("dark"))} color-scheme: dark; }
    * { box-sizing: border-box; }
    ha-card { display: block; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--sh-1); padding: var(--s-6); color: var(--ink); font-family: var(--font-text); font-size: 0.9375rem; line-height: 1.55; -webkit-font-smoothing: antialiased; }
    ha-card[lang="ar"] * { letter-spacing: normal; text-transform: none; }
    .ico { inline-size: 20px; block-size: 20px; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; fill: none; display: block; }
    .ico-slot { display: inline-flex; flex: none; }
    .panel-head { display: flex; align-items: center; gap: var(--s-4); min-block-size: 44px; min-inline-size: 0; }
    .section-label { font-family: var(--font-display); font-size: 0.6875rem; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase; color: var(--accent); margin: 0; flex: 0 1 auto; min-inline-size: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .panel-meta { flex: 0 1 auto; min-inline-size: 0; font-size: 0.875rem; font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .badge { min-inline-size: 18px; block-size: 18px; padding: 0 5px; border-radius: var(--r-full); background: var(--danger); color: var(--badge-ink); font-size: 0.6875rem; font-weight: 600; font-variant-numeric: tabular-nums; display: inline-flex; align-items: center; justify-content: center; line-height: 1; }
    .panel-head .badge { flex: none; }
    .rows { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--sh-1); overflow: hidden; }
    .rows.flat { margin-block-start: var(--s-4); box-shadow: none; border-radius: var(--r-xs); }
    .row { display: flex; align-items: flex-start; gap: var(--s-3); inline-size: 100%; min-block-size: 68px; padding: 14px var(--s-6); background: none; border: 0; text-align: start; font: inherit; color: inherit; position: relative; }
    .row.past { opacity: 0.55; }
    .row + .row::before { content: ""; position: absolute; inset-inline-start: var(--s-6); inset-inline-end: 0; inset-block-start: 0; block-size: 1px; background: var(--hairline); }
    .row-dot { inline-size: 14px; flex: none; padding-block-start: 7px; }
    .row-dot i { display: block; inline-size: 6px; block-size: 6px; border-radius: 50%; background: var(--accent); }
    .row-main { flex: 1; min-inline-size: 0; }
    .row-title { font-size: 0.9375rem; font-weight: 600; letter-spacing: -0.005em; line-height: 1.35; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .row-sub { font-size: 0.875rem; line-height: 1.45; color: var(--ink-2); margin-block-start: var(--s-1); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .row-side { flex: none; display: flex; flex-direction: column; align-items: flex-end; gap: var(--s-2); padding-block-start: var(--s-1); }
    .row-meta { font-size: 0.75rem; font-weight: 500; letter-spacing: 0.01em; color: var(--ink-3); font-variant-numeric: tabular-nums; white-space: nowrap; }
    .row-when { font-size: 0.6875rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; white-space: nowrap; color: var(--ink-3); }
    .row-when.now { background: var(--accent); color: var(--accent-ink); font-weight: 700; border-radius: var(--r-full); padding-inline: var(--s-3); padding-block: 1px; }
    .row-when.next { color: var(--accent); font-weight: 700; }
    .row.row-note { align-items: center; }
    .row.marked .row-dot i { box-shadow: 0 0 0 2px var(--accent); }
    .row.own .row-dot i.ring { background: transparent; box-shadow: inset 0 0 0 1.5px var(--accent); }
    .dlg-text { font-size: 0.875rem; line-height: 1.45; color: var(--ink-2); margin: 0; }
    .tag { display: inline-flex; align-items: center; gap: var(--s-3); block-size: 22px; padding: 0 var(--s-4); border-radius: var(--r-full); font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.01em; background: var(--surface-2); color: var(--ink-2); }
    .row-side .tag { flex: none; max-inline-size: 96px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; line-height: 22px; }
    .tag.open { background: var(--accent-soft); color: var(--accent); }
    .tag.no { background: var(--danger-soft); color: var(--danger); }
    .tag.exam { background: var(--accent-soft); color: var(--accent); gap: var(--s-2); max-inline-size: 100%; }
    .tag.exam .ico-slot { line-height: 0; flex: none; }
    .tag.exam span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .row-main > .tag.exam { margin-block-start: var(--s-3); }
    .tt-multi { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: var(--s-6); align-items: start; }
    .tt-multi.scrolls { grid-auto-columns: calc((100% - 2 * var(--s-6)) / 3); overflow-x: auto; overscroll-behavior-x: contain; scroll-snap-type: x proximity; padding-block-end: var(--s-4); scrollbar-width: thin; }
    .tt-child { min-inline-size: 0; scroll-snap-align: start; }
    .tt-child-head { display: flex; align-items: center; gap: var(--s-4); min-block-size: 44px; margin-block-end: var(--s-4); padding-inline: var(--s-2); }
    .tt-child-head .who { font-size: 0.9375rem; font-weight: 600; letter-spacing: -0.005em; overflow-wrap: anywhere; }
    .tt-child-head .cls { font-size: 0.75rem; font-weight: 500; color: var(--ink-3); }
    .avatar { inline-size: 30px; block-size: 30px; border-radius: 50%; display: grid; place-items: center; font-size: 0.75rem; font-weight: 700; color: var(--accent-ink); background: var(--accent); flex: none; }
    .tt { display: grid; grid-template-columns: 30px repeat(${SCHOOL_DAYS}, 1fr); gap: 4px; background: var(--surface-sunken); border-radius: var(--r-md); padding: var(--s-4) var(--s-4) var(--s-5); box-shadow: var(--sh-sunken); }
    .tt-head { text-align: center; padding-block-end: var(--s-3); }
    .tt-head .d { font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-3); display: block; }
    .tt-head .n { font-size: 0.875rem; font-weight: 600; font-variant-numeric: tabular-nums; display: block; margin-block-start: 2px; }
    .tt-head .n.off { color: var(--ink-3); font-weight: 500; }
    .tt-head.today .n { inline-size: 22px; block-size: 22px; line-height: 22px; border-radius: 50%; background: var(--accent); color: var(--accent-ink); margin: 2px auto 0; }
    .tt-hour { display: flex; flex-direction: column; align-items: center; justify-content: center; min-block-size: var(--tt-row); }
    .tt-hour b { font-size: 0.75rem; font-weight: 700; color: var(--ink-2); font-variant-numeric: tabular-nums; }
    .tt-hour span { font-size: 0.625rem; font-weight: 500; color: var(--ink-3); font-variant-numeric: tabular-nums; }
    .tt-cell { block-size: var(--tt-row); min-block-size: var(--tt-row); border-radius: var(--r-sm); border: 0; padding: var(--s-2) var(--s-1); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; position: relative; overflow: hidden; background: var(--surface); font: inherit; color: var(--ink); }
    .tt-cell.free { background: color-mix(in srgb, var(--ink) 3%, transparent); box-shadow: none; border-radius: var(--r-xs); }
    .tt-cell .sub { font-size: 0.875rem; font-weight: 700; letter-spacing: 0.015em; line-height: 1.05; }
    .tt-cell .room { font-size: 0.625rem; font-weight: 500; line-height: 1.05; }
    .tt-cell .bar { position: absolute; inset-inline-start: 0; inset-block: 0; inline-size: 3px; }
    .tt-cell.subject-bar::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--subject-bar, transparent); }
    .tt-cell.compact.subject-bar::before { inline-size: 2px; }
    .tt-cell.subject { background: var(--subject-cell-fill); color: var(--subject-cell-ink); }
    .tt-cell.subbed { background: var(--warn-tint); }
    .tt-cell.subbed .bar { background: var(--warn); }
    .tt-cell.out { background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); }
    .tt-cell.out .sub { color: var(--ink-3); text-decoration: line-through; text-decoration-thickness: 2px; }
    .tt-cell.out .room { color: var(--ink-3); }
    .tt-cell.subbed::after { content: ""; position: absolute; inset-block-start: 5px; inset-inline-end: 5px; inline-size: 9px; block-size: 9px; border-radius: 50%; background: var(--warn); }
    .tt-cell.out::after { content: "${CROSS}"; position: absolute; inset-block-start: 1px; inset-inline-end: 4px; font-size: 0.75rem; font-weight: 700; line-height: 1; color: var(--danger); }
    .tt-stack { display: flex; flex-direction: column; gap: var(--tt-stack-gap); block-size: var(--tt-row); min-block-size: var(--tt-row); }
    .tt-cell.compact { block-size: auto; min-block-size: 0; flex: 1 1 0; padding: 0 var(--s-1); }
    .tt-cell.compact .sub { font-size: 0.6875rem; }
    .tt-cell.compact .room { display: none; }
    .tt-cell.compact .bar { inline-size: 2px; }
    .tt-cell.compact.subbed::after { inset-block-start: 3px; inset-inline-end: 3px; inline-size: 6px; block-size: 6px; }
    .tt-cell.compact.out::after { inset-block-start: 0; inset-inline-end: 3px; font-size: 0.625rem; }
    .tt-cell.marked { box-shadow: inset 0 0 0 2px var(--accent); }
    .tt-cell .exam-flag { position: absolute; inset-block-end: 2px; inset-inline-end: 3px; display: block; line-height: 0; color: var(--accent); }
    .tt-cell.compact .exam-flag { inset-block-end: 1px; inset-inline-end: 2px; }
    .tt-cell.out .exam-flag, .tt-cell.subbed .exam-flag { color: var(--accent); }
    .tt-hol { min-block-size: var(--tt-row); min-inline-size: 0; border: 0; border-radius: var(--r-sm); background: color-mix(in srgb, var(--ink) 5%, transparent); padding: var(--s-3) var(--s-2); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-1); overflow: hidden; font: inherit; color: var(--ink); text-align: center; }
    .tt-hol .name { min-inline-size: 0; max-inline-size: 100%; font-size: 0.75rem; font-weight: 700; line-height: 1.15; hyphens: auto; -webkit-hyphens: auto; }
    .tt-hol .meta { min-inline-size: 0; max-inline-size: 100%; font-size: 0.625rem; font-weight: 500; line-height: 1.2; color: var(--ink-2); }
    .tt-hol.full { grid-column: 2 / span ${SCHOOL_DAYS}; flex-direction: row; align-items: center; justify-content: flex-start; gap: var(--s-5); min-block-size: 88px; padding: var(--s-5); text-align: start; }
    .tt-hol.full .ico-slot { flex: none; color: var(--accent); display: flex; }
    .tt-hol-text { min-inline-size: 0; display: flex; flex-direction: column; gap: 2px; text-align: start; }
    .tt-hol.full .name { font-size: 1.0625rem; font-weight: 600; line-height: 1.25; font-family: var(--font-display); }
    .tt-hol.full .meta { font-size: 0.75rem; }
    .tt-multi + .tt-hol.full { margin-block-start: var(--s-5); }
    .tt-hol.full + .tt-hol.full { margin-block-start: var(--s-4); }
    .legend, .counts { display: flex; flex-wrap: wrap; gap: var(--s-6); margin-block-start: var(--s-5); padding: 0 var(--s-4); }
    .legend span, .counts > span { display: inline-flex; align-items: center; gap: var(--s-3); font-size: 0.6875rem; font-weight: 500; color: var(--ink-3); }
    .legend i { inline-size: 3px; block-size: 12px; border-radius: 2px; display: block; }
    .legend i.dot { inline-size: 9px; block-size: 9px; border-radius: 50%; }
    .legend i.sym { inline-size: auto; block-size: auto; border-radius: 0; font-size: 0.75rem; font-weight: 700; line-height: 1; font-style: normal; }
    .stamp { margin-block-start: var(--s-4); font-size: 0.6875rem; color: var(--ink-3); text-align: start; font-variant-numeric: tabular-nums; padding: 0 var(--s-4); }
    .empty { text-align: center; padding: var(--s-11) var(--s-6) var(--s-8); }
    .empty > .ico-slot > .ico { inline-size: 64px; block-size: 64px; margin: 0 auto var(--s-6); padding: 18px; background: var(--surface-2); border-radius: 50%; color: var(--ink-2); }
    .empty > .ico-slot { display: block; }
    .empty b { display: block; font-size: 1.0625rem; font-weight: 600; margin-block-end: var(--s-3); }
    .empty p { margin: 0 auto; max-inline-size: 260px; font-size: 0.875rem; color: var(--ink-2); line-height: 1.45; }
    .card-title { font-family: var(--font-display); font-size: 1.125rem; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 var(--s-4); overflow-wrap: anywhere; }
    .block + .block { margin-block-start: var(--s-7); }
    .block .panel-head { padding: 0; min-block-size: 40px; }
    .panel-link { flex: 0 1 auto; margin-inline-start: auto; min-block-size: 40px; padding-inline: var(--s-3); display: inline-flex; align-items: center; font-size: 0.875rem; font-weight: 600; color: var(--accent); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .panel-head .count { flex: none; margin-inline-start: auto; font-size: 0.875rem; font-weight: 600; color: var(--ink-3); font-variant-numeric: tabular-nums; }
    .panel-head .count.fresh { color: var(--accent); }
    .panel-head .count + .panel-link { margin-inline-start: var(--s-3); }
    .row.compact { min-block-size: 42px; padding-block: var(--s-2); align-items: center; }
    .row.compact .row-dot { padding-block-start: 0; }
    .row.compact .row-main { min-inline-size: min(45%, 8em); }
    .row.compact .row-side { padding-block-start: 0; flex-direction: row; flex-shrink: 1; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: var(--s-1) var(--s-4); min-inline-size: 0; }
    .row-tags { display: flex; flex-wrap: wrap; gap: var(--s-2); margin-block-end: var(--s-2); }
    .row-tags .tag { max-inline-size: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .row-all { min-block-size: 44px; padding-block: var(--s-3); align-items: center; text-decoration: none; }
    .row-all .row-title { color: var(--accent); font-weight: 600; font-size: 0.875rem; }
    .row-all .row-dot { display: none; }
    .family { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--s-7); }
    @container card (min-width: 560px) { .family { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .member { min-inline-size: 0; }
    .member .tt-child-head { margin-block-end: 0; padding-inline: 0; }
    .member .block { margin-block-start: var(--s-4); }
    .tt-child-head .cls::before { content: "· "; }
    .tt.compact-cells .tt-cell .room { display: none; }
  `;

  const EDITOR_STYLE = `
    :host { display: block; }
    .form { display: flex; flex-direction: column; gap: 12px; padding: 4px 0; color: var(--primary-text-color); }
    .field { display: flex; flex-direction: column; gap: 4px; }
    label { font-size: 0.8rem; color: var(--secondary-text-color); }
    select, input { font: inherit; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
    .children, .blocks { display: flex; flex-wrap: wrap; gap: 10px; }
    .children label, .blocks label { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; color: var(--primary-text-color); }
    .blocks label { flex-direction: column; align-items: flex-start; inline-size: 100%; }
    .blocks label .hint { padding-inline-start: 22px; }
    .hint { font-size: 0.75rem; color: var(--secondary-text-color); }
    .size-list { display: flex; flex-direction: column; gap: 8px; }
    .size-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  `;

  const eventCache = new Map();
  let registryPromise = null;
  let registryAt = 0;

  function blockOf(key) {
    return BLOCK_BY_KEY.get(key) || null;
  }

  function sizeOf(block, size) {
    return SIZES.includes(size) ? size : block.size;
  }

  function limitOf(block, size) {
    return block[sizeOf(block, size)];
  }

  function normaliseBlocks(raw) {
    const kept = [];
    const seen = new Set();
    for (const entry of Array.isArray(raw) ? raw : []) {
      const key = entry && typeof entry === "object" ? entry.key : entry;
      const block = typeof key === "string" ? blockOf(key) : null;
      if (!block || seen.has(block.key)) continue;
      seen.add(block.key);
      kept.push({ key: block.key, size: sizeOf(block, entry && typeof entry === "object" ? entry.size : null) });
    }
    return kept;
  }

  function unknownBlockOf(raw) {
    for (const entry of Array.isArray(raw) ? raw : []) {
      const key = entry && typeof entry === "object" ? entry.key : entry;
      if (typeof key !== "string" || !blockOf(key) || !blockOf(key).surfaces.includes("card")) return String(key);
    }
    return "";
  }

  function blocksOfLegacy(config) {
    const view = config && config.view ? String(config.view) : DEFAULT_VIEW;
    const keys = LEGACY_BLOCKS[view] || LEGACY_BLOCKS[DEFAULT_VIEW];
    return keys.map((key) => ({ key, size: view === "family" && key === "today" ? SIZE_COMPACT : blockOf(key).size }));
  }

  function schoolModules(hass, school) {
    const state = stateOf(hass, school.entities[KEY_CONNECTION]);
    return state && state.attributes && typeof state.attributes.modules === "object" && state.attributes.modules ? state.attributes.modules : null;
  }

  function moduleOffered(hass, registry, name) {
    const schools = registry.schools.length ? registry.schools : [];
    if (!schools.length) return true;
    return schools.some((school) => {
      const modules = schoolModules(hass, school);
      return !modules || modules[name] !== false;
    });
  }

  function offeredBlocks(hass, registry) {
    return CARD_BLOCKS.filter((block) => moduleOffered(hass, registry, block.module));
  }

  function ingressPathOf(hass, registry) {
    for (const school of registry.schools) {
      const state = stateOf(hass, school.entities[KEY_CONNECTION]);
      const path = state && state.attributes ? String(state.attributes.ingress_path || "") : "";
      if (path) return path;
    }
    return "";
  }

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function iconSvg(name, size) {
    const shape = ICON_SHAPES[name];
    if (!shape) return "";
    const sized = size ? ` style="width:${size}px;height:${size}px"` : "";
    return `<svg class="ico" viewBox="0 0 24 24" stroke="currentColor" fill="none" aria-hidden="true"${sized}>${shape}</svg>`;
  }

  function icon(name, size) {
    return `<span class="ico-slot">${iconSvg(name, size)}</span>`;
  }

  function localeOf(hass) {
    return (hass && (hass.locale?.language || hass.language)) || FALLBACK_LANGUAGE;
  }

  function languageOf(hass) {
    const primary = String(localeOf(hass)).toLowerCase().split(/[-_]/)[0];
    return TEXTS[primary] ? primary : FALLBACK_LANGUAGE;
  }

  function translator(hass) {
    const table = TEXTS[languageOf(hass)];
    return (key, vars = {}) => {
      const template = table[key] ?? TEXTS[FALLBACK_LANGUAGE][key] ?? key;
      return template.replace(/\{([a-z]+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
    };
  }

  function zoneOf(hass) {
    return (hass && hass.config && hass.config.time_zone) || Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  function directionOf() {
    const dir = document.dir || document.documentElement.getAttribute("dir") || "";
    return dir.toLowerCase() === "rtl" ? "rtl" : "ltr";
  }

  function themeOf(hass) {
    const themes = hass && hass.themes;
    if (!themes || typeof themes.darkMode !== "boolean") return "";
    return themes.darkMode ? "dark" : "light";
  }

  function slugify(value) {
    return String(value)
      .toLowerCase()
      .normalize("NFKD")
      .replace(/\p{M}/gu, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function dateKey(date, zone) {
    return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  }

  function offsetMinutes(date, zone) {
    const part = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "longOffset" })
      .formatToParts(date)
      .find((item) => item.type === "timeZoneName");
    const match = /GMT([+-])(\d{1,2}):?(\d{2})?/.exec(part ? part.value : "");
    if (!match) return 0;
    const sign = match[1] === "-" ? -1 : 1;
    return sign * (Number(match[2]) * 60 + Number(match[3] || 0));
  }

  function zonedMidnight(key, zone) {
    const [year, month, day] = key.split("-").map(Number);
    const guess = Date.UTC(year, month - 1, day);
    const first = guess - offsetMinutes(new Date(guess), zone) * 60000;
    return new Date(guess - offsetMinutes(new Date(first), zone) * 60000);
  }

  function shiftKey(key, days, zone) {
    const noon = zonedMidnight(key, zone).getTime() + days * DAY_MS + DAY_MS / 2;
    return dateKey(new Date(noon), zone);
  }

  function weekdayOf(key) {
    const [year, month, day] = key.split("-").map(Number);
    return (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
  }

  function mondayOf(key, zone) {
    const weekday = weekdayOf(key);
    const shift = weekday >= SCHOOL_DAYS ? 7 - weekday : -weekday;
    return shiftKey(key, shift, zone);
  }

  function plainDigits(text) {
    return text.replace(BIDI_MARKS, "");
  }

  function dateFormatter(locale, options) {
    try {
      return new Intl.DateTimeFormat(locale, options);
    } catch (error) {
      return new Intl.DateTimeFormat(FALLBACK_LANGUAGE, options);
    }
  }

  function formatTime(date, locale, zone) {
    return plainDigits(dateFormatter(locale, { timeZone: zone, hour: "2-digit", minute: "2-digit" }).format(date));
  }

  function formatDate(date, locale, zone) {
    return plainDigits(dateFormatter(locale, { timeZone: zone, day: "2-digit", month: "2-digit", year: "numeric" }).format(date));
  }

  function formatDateTime(date, locale, zone) {
    return `${formatDate(date, locale, zone)} ${formatTime(date, locale, zone)}`;
  }

  function slotKey(date, zone) {
    return new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
  }

  function formatShortDate(key, locale, zone) {
    return plainDigits(dateFormatter(locale, { timeZone: zone, day: "2-digit", month: "2-digit" }).format(zonedMidnight(key, zone)));
  }

  function formatWeekdayShort(key, locale, zone) {
    return dateFormatter(locale, { timeZone: zone, weekday: "short" }).format(zonedMidnight(key, zone));
  }

  function formatDayNumber(key, locale, zone) {
    return plainDigits(dateFormatter(locale, { timeZone: zone, day: "2-digit" }).format(zonedMidnight(key, zone)));
  }

  function formatWeekdayDay(key, locale, zone) {
    return plainDigits(dateFormatter(locale, { timeZone: zone, weekday: "short", day: "2-digit", month: "2-digit" }).format(zonedMidnight(key, zone)));
  }

  function formatNumber(value, locale) {
    try {
      return new Intl.NumberFormat(locale).format(value);
    } catch (error) {
      return String(value);
    }
  }

  function stateOf(hass, entityId) {
    return entityId ? hass.states[entityId] : undefined;
  }

  function numberOf(hass, entityId) {
    const state = stateOf(hass, entityId);
    const value = state ? Number(state.state) : NaN;
    return Number.isFinite(value) ? value : 0;
  }

  function isMissing(state) {
    return !state || MISSING_STATES.has(String(state.state));
  }

  function deviceLabel(device, fallback) {
    const raw = String((device && (device.name_by_user || device.name)) || "");
    return raw.replace(/^Ranzenpost\s+/i, "").trim() || fallback;
  }

  function splitUniqueId(uniqueId, key) {
    const inner = uniqueId.slice(DOMAIN.length + 1);
    if (!inner.endsWith(`_${key}`)) return null;
    const cut = inner.indexOf("_");
    if (cut <= 0) return null;
    const entryId = inner.slice(0, cut);
    const owner = inner.slice(cut + 1, -(key.length + 1));
    if (owner.startsWith("school_")) return { entryId, schoolId: owner.slice("school_".length), childKey: "" };
    return { entryId, schoolId: schoolOfKey(owner), childKey: owner };
  }

  function schoolOfKey(childKey) {
    const cut = String(childKey || "").indexOf(":");
    return cut > 0 ? childKey.slice(0, cut) : "";
  }

  async function loadRegistry(hass) {
    const [entities, devices] = await Promise.all([
      hass.callWS({ type: "config/entity_registry/list" }),
      hass.callWS({ type: "config/device_registry/list" }),
    ]);
    const deviceById = new Map((devices || []).map((device) => [device.id, device]));
    const children = new Map();
    const schools = new Map();
    const schoolOf = (entryId, schoolId, device) => {
      const id = `${entryId}:${schoolId}`;
      let school = schools.get(id);
      if (!school) {
        school = { id, entryId, schoolId, deviceId: device ? device.id : "", name: deviceLabel(device, schoolId), entities: {} };
        schools.set(id, school);
      }
      if (device && !school.deviceId) {
        school.deviceId = device.id;
        school.name = deviceLabel(device, schoolId);
      }
      return school;
    };
    for (const entry of entities || []) {
      const uniqueId = String(entry.unique_id || "");
      if (entry.platform !== DOMAIN || !uniqueId.startsWith(`${DOMAIN}_`)) continue;
      const key = entry.translation_key || uniqueId.slice(uniqueId.lastIndexOf("_") + 1);
      const parts = splitUniqueId(uniqueId, key);
      if (!parts) continue;
      const device = deviceById.get(entry.device_id);
      if (!parts.childKey) {
        schoolOf(parts.entryId, parts.schoolId, device).entities[key] = entry.entity_id;
        continue;
      }
      let child = children.get(parts.childKey);
      if (!child) {
        const schoolDevice = device && device.via_device_id ? deviceById.get(device.via_device_id) : null;
        const school = schoolOf(parts.entryId, parts.schoolId, schoolDevice);
        const label = deviceLabel(device, parts.childKey).replace(/\s*\([^)]*\)\s*$/, "").trim() || parts.childKey;
        child = {
          id: parts.childKey,
          entryId: parts.entryId,
          schoolId: school.id,
          deviceId: entry.device_id || "",
          name: label,
          slug: slugify(label),
          entities: {},
        };
        children.set(parts.childKey, child);
      }
      child.entities[key] = entry.entity_id;
    }
    const listed = [...schools.values()];
    for (const child of children.values()) {
      const school = schools.get(child.schoolId);
      child.school = school ? school.name : "";
      child.fullSlug = slugify(`${child.name} ${child.school}`);
    }
    const ordered = [...children.values()].sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: "base" }));
    return { children: ordered, schools: listed };
  }

  function schoolOfChild(registry, child) {
    return registry.schools.find((school) => school.id === child.schoolId) || { entities: {}, name: "" };
  }

  function nameIsShared(children, child) {
    return children.some((other) => other !== child && other.slug === child.slug);
  }

  function childLabel(registry, child) {
    return nameIsShared(registry.children, child) && child.school ? `${child.name} (${child.school})` : child.name;
  }

  function childReference(children, child) {
    return nameIsShared(children, child) && child.school ? `${child.name} (${child.school})` : child.slug;
  }

  function discover(hass, again = false) {
    const stale = Date.now() - registryAt > REGISTRY_TTL_MS;
    if (!registryPromise || (again && stale)) {
      registryAt = Date.now();
      registryPromise = loadRegistry(hass).catch((error) => {
        registryPromise = null;
        throw error;
      });
    }
    return registryPromise;
  }

  function findChild(children, reference) {
    if (reference === undefined || reference === null || reference === "") return null;
    const wanted = String(reference).trim().toLowerCase();
    const wantedSlug = slugify(wanted);
    const exact = children.find((child) => child.id.toLowerCase() === wanted || child.deviceId.toLowerCase() === wanted);
    if (exact) return exact;
    const withSchool = children.find(
      (child) =>
        child.school &&
        (`${child.name} (${child.school})`.toLowerCase() === wanted || (child.fullSlug && child.fullSlug === wantedSlug))
    );
    if (withSchool) return withSchool;
    return children.find((child) => child.slug === wanted || child.name.toLowerCase() === wanted || wantedSlug === child.slug) || null;
  }

  function childColor(registry, child) {
    const index = registry.children.indexOf(child);
    return CHILD_COLORS[(index < 0 ? 0 : index) % CHILD_COLORS.length];
  }

  function ownKeyOf(child) {
    return `${OWN_PREFIX}${child.deviceId}`;
  }

  function loadEvents(hass, request, zone) {
    const { entityId, start, end } = request;
    if (entityId.startsWith(OWN_PREFIX)) {
      return hass.callWS({
        type: WS_OWN_ENTRIES,
        device_id: entityId.slice(OWN_PREFIX.length),
        start: dateKey(start, zone),
        end: dateKey(end, zone),
      });
    }
    const path = `calendars/${entityId}?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
    return hass.callApi("GET", path);
  }

  function fetchEvents(hass, request, zone) {
    const key = `${request.entityId}|${request.start.toISOString()}|${request.end.toISOString()}`;
    const now = Date.now();
    const hit = eventCache.get(key);
    if (hit && now - hit.at < CACHE_TTL_MS) return hit.promise;
    const promise = Promise.resolve()
      .then(() => loadEvents(hass, request, zone))
      .catch((error) => {
        eventCache.delete(key);
        throw error;
      });
    for (const [other, entry] of eventCache) {
      if (now - entry.at >= CACHE_TTL_MS) eventCache.delete(other);
    }
    eventCache.set(key, { at: now, promise });
    return promise;
  }

  function forgetEvents(entityIds) {
    for (const key of [...eventCache.keys()]) {
      if (entityIds.includes(key.split("|")[0])) eventCache.delete(key);
    }
  }

  function boundOf(bound, zone) {
    if (!bound) return null;
    if (bound.dateTime) return new Date(bound.dateTime);
    if (bound.date) return zonedMidnight(bound.date, zone);
    return null;
  }

  function normaliseEvent(raw, zone) {
    const start = boundOf(raw.start, zone);
    const end = boundOf(raw.end, zone);
    if (!start || !end || Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    const allDay = !!(raw.start && raw.start.date);
    return {
      uid: raw.uid || `${raw.summary}|${start.toISOString()}`,
      summary: raw.summary || "",
      description: raw.description || "",
      location: raw.location || "",
      start,
      end,
      allDay,
      cancelled: !!raw.cancelled,
      color: /^#[0-9a-fA-F]{6}$/.test(raw.color || "") ? raw.color : "",
      subjectCode: String(raw.subject_code || ""),
      subjectName: String(raw.subject || ""),
      dayKey: dateKey(start, zone),
      firstDay: allDay ? raw.start.date : dateKey(start, zone),
      lastDay: allDay ? raw.end.date : dateKey(end, zone),
    };
  }

  function normaliseAll(list, zone) {
    return (Array.isArray(list) ? list : [])
      .map((raw) => normaliseEvent(raw, zone))
      .filter(Boolean)
      .sort((left, right) => left.start - right.start || left.summary.localeCompare(right.summary));
  }

  function cleanSummary(event) {
    if (!event.cancelled) return event.summary;
    const match = /^[^:]{1,24}:\s+(.+)$/.exec(event.summary);
    return match ? match[1] : event.summary;
  }

  function firstLine(text) {
    return String(text || "").split(/\r?\n/)[0].trim();
  }

  function changeOf(changes, event) {
    const at = event.start.getTime();
    return changes.find((change) => change && change.start && new Date(change.start).getTime() === at) || null;
  }

  function overlaps(left, right) {
    return left.start < right.end && right.start < left.end;
  }

  function buildLessons(events, exams, changes, now) {
    const lessons = events.map((event) => {
      const change = changeOf(changes, event);
      const cancelled = event.cancelled || !!(change && change.cancelled);
      const meta = change
        ? [change.teacher, change.room].filter(Boolean).join(" · ")
        : firstLine(event.description) || event.location;
      return {
        ...event,
        cancelled,
        substitution: !!(change && change.substitution && !cancelled),
        subject: (change && change.subject) || event.subjectName || cleanSummary(event),
        code: (change && change.subject_code) || event.subjectCode || "",
        meta,
        exam: exams.some((exam) => overlaps(exam, event)),
        now: false,
        next: false,
        done: false,
      };
    });
    if (now === null) return lessons;
    const current = lessons.find((lesson) => !lesson.cancelled && lesson.start <= now && now < lesson.end);
    const upcoming = lessons.find((lesson) => !lesson.cancelled && lesson.start > now);
    for (const lesson of lessons) {
      lesson.now = lesson === current;
      lesson.next = lesson === upcoming;
      lesson.done = lesson.end <= now;
    }
    return lessons;
  }

  function holidayOn(holidays, dayKey) {
    return holidays.find((event) => event.allDay && event.firstDay <= dayKey && dayKey < event.lastDay) || null;
  }

  function subjectDot(lesson) {
    return lesson.color ? `<i style="background: ${esc(lesson.color)}"></i>` : "<i></i>";
  }

  function examTag(t) {
    return `<span class="tag exam"><span class="ico-slot">${iconSvg("exam", 11)}</span><span>${esc(t("lesson.exam"))}</span></span>`;
  }

  function changeTag(lesson, t) {
    if (lesson.cancelled) return `<span class="tag no">${esc(t("lesson.cancelled"))}</span>`;
    if (lesson.substitution) return `<span class="tag open">${esc(t("lesson.substitution"))}</span>`;
    return "";
  }

  function whenTag(lesson, t) {
    if (lesson.now) return `<span class="row-when now">${esc(t("lesson.now"))}</span>`;
    if (lesson.next) return `<span class="row-when next">${esc(t("lesson.next"))}</span>`;
    return "";
  }

  function lessonRow(lesson, t, locale, zone, compact) {
    const classes = ["row"];
    if (compact) classes.push("compact");
    if (lesson.done) classes.push("past");
    if (lesson.exam) classes.push("marked");
    const current = lesson.now ? ' aria-current="true"' : "";
    const strike = lesson.cancelled ? ' style="text-decoration: line-through"' : "";
    const sub = lesson.meta && !compact ? `<div class="row-sub" dir="auto">${esc(lesson.meta)}</div>` : "";
    const main = `<div class="row-main"><div class="row-title" dir="auto"${strike}>${esc(lesson.subject)}</div>${sub}${lesson.exam && !compact ? examTag(t) : ""}</div>`;
    const side = `<div class="row-side">${whenTag(lesson, t)}<span class="row-meta" dir="ltr">${esc(formatTime(lesson.start, locale, zone))}</span>${changeTag(lesson, t)}</div>`;
    return `<div class="${classes.join(" ")}" data-uid="${esc(lesson.uid)}"${current}><span class="row-dot">${subjectDot(lesson)}</span>${main}${side}</div>`;
  }

  function byStart(lessons, own) {
    return lessons.concat(own).sort((left, right) => left.start - right.start || (left.own ? 1 : 0) - (right.own ? 1 : 0));
  }

  function ownRow(event, t, locale, zone, compact) {
    const classes = ["row", "own"];
    if (compact) classes.push("compact");
    if (event.done) classes.push("past");
    const sub = compact ? "" : `<div class="row-sub" dir="auto">${esc(t("own.until", { time: formatTime(event.end, locale, zone) }))}</div>`;
    const main = `<div class="row-main"><div class="row-title" dir="auto">${esc(event.summary)}</div>${sub}</div>`;
    const side = `<div class="row-side"><span class="row-meta" dir="ltr">${esc(formatTime(event.start, locale, zone))}</span></div>`;
    return `<div class="${classes.join(" ")}" data-uid="${esc(event.uid)}"><span class="row-dot"><i class="ring"></i></span>${main}${side}</div>`;
  }

  function noteRow(html) {
    return `<div class="row row-note"><p class="dlg-text">${html}</p></div>`;
  }

  function rowsBlock(inner, dayKey) {
    const day = dayKey ? ` data-day="${esc(dayKey)}"` : "";
    return `<div class="rows flat"${day}>${inner}</div>`;
  }

  function panelHead(label, meta, extra = "") {
    const metaHtml = meta ? `<span class="panel-meta">${esc(meta)}</span>` : "";
    return `<div class="panel-head"><h2 class="section-label" dir="auto">${esc(label)}</h2>${metaHtml}${extra}</div>`;
  }

  function emptyBlock(iconName, title, text) {
    const paragraph = text ? `<p>${esc(text)}</p>` : "";
    return `<div class="empty">${icon(iconName)}<b>${esc(title)}</b>${paragraph}</div>`;
  }

  function childHead(registry, child, label) {
    const initial = (child.name || "?").trim().charAt(0).toUpperCase();
    return `<div class="tt-child-head"><span class="avatar" style="background: ${childColor(registry, child)}">${esc(initial)}</span><span class="who" dir="auto">${esc(label)}</span></div>`;
  }

  function absenceInWindow(absence, todayKey, limitKey) {
    if (!absence || !absence.end) return false;
    const endsBeforeToday = absence.end.localeCompare(todayKey) < 0;
    const startsAfterWindow = !!absence.start && limitKey.localeCompare(absence.start) < 0;
    return !endsBeforeToday && !startsAfterWindow;
  }

  function relativeDays(days, locale) {
    try {
      return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(days, "day");
    } catch (error) {
      return formatNumber(days, locale);
    }
  }

  function relativeMinutes(minutes, locale) {
    try {
      const format = new Intl.RelativeTimeFormat(locale, { numeric: "always" });
      return minutes >= 120 ? format.format(Math.round(minutes / 60), "hour") : format.format(minutes, "minute");
    } catch (error) {
      return formatNumber(minutes, locale);
    }
  }

  function badgeText(count, locale) {
    return count > 9 ? `${formatNumber(9, locale)}+` : formatNumber(count, locale);
  }

  function changesOf(hass, child) {
    const state = stateOf(hass, child.entities[KEY_CHANGES]);
    return state && Array.isArray(state.attributes.changes) ? state.attributes.changes : [];
  }

  function stateKeyOf(state) {
    return state ? [state.entity_id, state.state, state.last_updated] : null;
  }

  class RanzenpostCard extends HTMLElement {
    static get texts() {
      return TEXTS;
    }

    static resetCaches() {
      eventCache.clear();
      registryPromise = null;
      registryAt = 0;
    }

    static getConfigElement() {
      return document.createElement(EDITOR_TAG);
    }

    static async getStubConfig(hass) {
      try {
        const registry = await discover(hass);
        const blocks = offeredBlocks(hass, registry).slice(0, 2).map((block) => block.key);
        return registry.children.length ? { blocks, children: [registry.children[0].slug] } : { blocks };
      } catch (error) {
        return { blocks: ["today"] };
      }
    }

    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = null;
      this._hass = null;
      this._signature = "";
      this._serial = 0;
      this._settled = Promise.resolve();
      this._stamps = new Map();
    }

    setConfig(config) {
      const t = translator(this._hass);
      if (config && Array.isArray(config.blocks)) {
        const unknown = unknownBlockOf(config.blocks);
        if (unknown) throw new Error(t("block.unknown", { block: unknown }));
        this._config = { ...config, view: null, blocks: normaliseBlocks(config.blocks), days: DEFAULT_DAYS };
        this._signature = "";
        this._schedule();
        return;
      }
      const view = config && config.view ? String(config.view) : DEFAULT_VIEW;
      if (!VIEWS.includes(view)) throw new Error(t("config.view"));
      const days = Number(config && config.days) === 1 ? 1 : DEFAULT_DAYS;
      this._config = { ...config, view, days };
      this._signature = "";
      this._schedule();
    }

    set hass(hass) {
      this._hass = hass;
      this._applyTheme();
      this._schedule();
    }

    get hass() {
      return this._hass;
    }

    get settled() {
      return this._settled;
    }

    connectedCallback() {
      this._schedule();
    }

    getCardSize() {
      if (this._config && this._config.blocks) return Math.max(2, this._config.blocks.length * 2);
      const view = this._config ? this._config.view : DEFAULT_VIEW;
      return view === "week" ? 6 : view === "family" ? 5 : 4;
    }

    _applyTheme() {
      const theme = themeOf(this._hass);
      if (theme) this.setAttribute("data-theme", theme);
      else this.removeAttribute("data-theme");
    }

    _schedule() {
      if (!this._config || !this._hass || !this.isConnected) return;
      const serial = ++this._serial;
      this._settled = this._refresh(serial).catch((error) => {
        if (serial === this._serial) this._renderError(error);
      });
    }

    async _refresh(serial) {
      const hass = this._hass;
      let registry = await discover(hass);
      if (serial !== this._serial) return;
      let plan = this._plan(registry, hass);
      if (plan.missing && Date.now() - registryAt > REGISTRY_TTL_MS) {
        registry = await discover(hass, true);
        if (serial !== this._serial) return;
        plan = this._plan(registry, hass);
      }
      const signature = JSON.stringify([this._config, languageOf(hass), zoneOf(hass), directionOf(), plan.minute, plan.stateKeys]);
      if (signature === this._signature) return;
      this._forgetUpdatedChildren(plan.children, hass);
      const events = await Promise.all(plan.requests.map((request) => fetchEvents(hass, request, plan.zone)));
      if (serial !== this._serial) return;
      const byEntity = new Map();
      plan.requests.forEach((request, index) => byEntity.set(request.entityId, normaliseAll(events[index], plan.zone)));
      this._signature = signature;
      this._render(plan, byEntity);
    }

    _plan(registry, hass) {
      const zone = zoneOf(hass);
      const now = new Date();
      const todayKey = dateKey(now, zone);
      const config = this._config;
      const t = translator(hass);
      const plan = {
        zone,
        now,
        todayKey,
        minute: Math.floor(now.getTime() / 60000),
        t,
        locale: localeOf(hass),
        registry,
        children: [],
        requests: [],
        stateKeys: [],
        message: null,
        missing: false,
        blocks: null,
      };
      if (config.blocks) return this._planBlocks(plan, registry, hass, config);
      if (config.view === "family") {
        const wanted = Array.isArray(config.children) ? config.children : [];
        plan.children = wanted.length
          ? wanted.map((reference) => findChild(registry.children, reference)).filter(Boolean)
          : registry.children;
        if (!registry.children.length) plan.message = t("children.none");
        plan.missing = plan.children.length < (wanted.length || 1);
        plan.dayKeys = [todayKey];
        if (config.days === 2) plan.dayKeys.push(shiftKey(todayKey, 1, zone));
        plan.start = zonedMidnight(todayKey, zone);
        plan.end = zonedMidnight(shiftKey(todayKey, config.days, zone), zone);
      } else {
        if (config.child === undefined || config.child === null || config.child === "") {
          plan.message = t("child.missing");
        } else {
          const child = findChild(registry.children, config.child);
          if (child) plan.children = [child];
          else plan.message = t("child.unknown", { child: config.child });
          plan.missing = !child;
        }
        if (config.view === "week") {
          const mondayKey = mondayOf(todayKey, zone);
          plan.dayKeys = Array.from({ length: SCHOOL_DAYS }, (item, index) => shiftKey(mondayKey, index, zone));
          plan.start = zonedMidnight(mondayKey, zone);
          plan.end = zonedMidnight(shiftKey(mondayKey, SCHOOL_DAYS, zone), zone);
        } else {
          plan.dayKeys = [todayKey];
          plan.start = zonedMidnight(todayKey, zone);
          plan.end = zonedMidnight(shiftKey(todayKey, 1, zone), zone);
        }
      }
      const withOwn = config.view !== "week";
      for (const child of plan.children) {
        this._pushDayRequests(plan, child, withOwn);
        for (const key of [KEY_CHANGES, KEY_LETTERS, KEY_POSTS, KEY_SCHOOL_END, KEY_STAMP]) {
          plan.stateKeys.push(stateKeyOf(stateOf(hass, child.entities[key])));
        }
      }
      for (const school of registry.schools) {
        const holidayCalendar = school.entities[KEY_HOLIDAYS];
        const wanted = plan.children.some((child) => child.schoolId === school.id && child.entities[KEY_LESSONS]);
        if (holidayCalendar && wanted) plan.requests.push({ entityId: holidayCalendar, start: plan.start, end: plan.end });
        plan.stateKeys.push(stateKeyOf(stateOf(hass, school.entities[KEY_HOLIDAY])));
      }
      return plan;
    }

    _planBlocks(plan, registry, hass, config) {
      const { zone, todayKey } = plan;
      const wanted = Array.isArray(config.children) ? config.children : [];
      plan.children = wanted.length
        ? wanted.map((reference) => findChild(registry.children, reference)).filter(Boolean)
        : registry.children;
      plan.missing = plan.children.length < (wanted.length || 1);
      if (!registry.children.length) plan.message = plan.t("children.none");
      plan.blocks = config.blocks.filter((entry) => moduleOffered(hass, registry, blockOf(entry.key).module));
      if (!config.blocks.length) plan.message = plan.t("block.noBlocks");
      const keys = new Set(plan.blocks.map((entry) => entry.key));
      const mondayKey = mondayOf(todayKey, zone);
      plan.dayKeys = keys.has("week")
        ? Array.from({ length: SCHOOL_DAYS }, (item, index) => shiftKey(mondayKey, index, zone))
        : [todayKey];
      plan.start = zonedMidnight(keys.has("week") && mondayKey < todayKey ? mondayKey : todayKey, zone);
      plan.end = zonedMidnight(shiftKey(keys.has("week") ? mondayKey : todayKey, keys.has("week") ? SCHOOL_DAYS : 1, zone), zone);
      const needsDays = DAY_BLOCKS.some((key) => keys.has(key));
      const withOwn = keys.has("today");
      for (const child of plan.children) {
        if (needsDays) this._pushDayRequests(plan, child, withOwn);
        for (const key of [KEY_CHANGES, KEY_LETTERS, KEY_POSTS, KEY_SCHOOL_END, KEY_STAMP, KEY_NEXT_LESSON, KEY_ABSENCES]) {
          plan.stateKeys.push(stateKeyOf(stateOf(hass, child.entities[key])));
        }
      }
      for (const school of registry.schools) {
        const holidayCalendar = school.entities[KEY_HOLIDAYS];
        const wantedSchool = plan.children.some((child) => child.schoolId === school.id && child.entities[KEY_LESSONS]);
        if (holidayCalendar && wantedSchool && needsDays) plan.requests.push({ entityId: holidayCalendar, start: plan.start, end: plan.end });
        for (const key of [KEY_HOLIDAY, KEY_CONFERENCE, KEY_CONNECTION]) {
          plan.stateKeys.push(stateKeyOf(stateOf(hass, school.entities[key])));
        }
      }
      return plan;
    }

    _pushDayRequests(plan, child, withOwn) {
      for (const key of [KEY_LESSONS, KEY_EXAMS]) {
        const entityId = child.entities[key];
        if (entityId) plan.requests.push({ entityId, start: plan.start, end: plan.end });
      }
      if (withOwn && child.deviceId && this._hasTimetable(child)) {
        plan.requests.push({ entityId: ownKeyOf(child), start: plan.start, end: plan.end });
      }
    }

    _forgetUpdatedChildren(children, hass) {
      for (const child of children) {
        const state = stateOf(hass, child.entities[KEY_STAMP]);
        const stamp = state ? String(state.state) : "";
        const known = this._stamps.get(child.id);
        if (known !== undefined && known !== stamp) {
          forgetEvents([...CHILD_CALENDARS.map((key) => child.entities[key]).filter(Boolean), ownKeyOf(child)]);
        }
        this._stamps.set(child.id, stamp);
      }
    }

    _render(plan, byEntity) {
      const title = this._config.title ? String(this._config.title) : "";
      let inner;
      if (plan.message) {
        inner = emptyBlock("alert", plan.message);
      } else if (plan.blocks) {
        inner = this._renderBlocks(plan, byEntity, title);
      } else if (this._config.view === "today") {
        inner = this._renderToday(plan, byEntity, title);
      } else if (this._config.view === "week") {
        inner = this._renderWeek(plan, byEntity, title);
      } else {
        inner = this._renderFamily(plan, byEntity, title);
      }
      this._paint(inner);
    }

    _renderError(error) {
      if (error && typeof console !== "undefined" && console.warn) console.warn(`${CARD_TAG}:`, error);
      this._signature = "";
      const t = translator(this._hass);
      this._paint(emptyBlock("alert", t("error.title"), t("state.unavailable")));
    }

    _paint(inner) {
      const language = languageOf(this._hass);
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card dir="${directionOf()}" lang="${language}">${inner}</ha-card>`;
    }

    _hasTimetable(child) {
      return Boolean(child.entities[KEY_LESSONS]);
    }

    _holidays(plan, byEntity, child) {
      return byEntity.get(schoolOfChild(plan.registry, child).entities[KEY_HOLIDAYS]) || [];
    }

    _childLessons(plan, byEntity, child, dayKey, withNow) {
      const events = (byEntity.get(child.entities[KEY_LESSONS]) || []).filter((event) => event.dayKey === dayKey);
      const exams = (byEntity.get(child.entities[KEY_EXAMS]) || []).filter((event) => event.dayKey === dayKey);
      const changes = dayKey === plan.todayKey ? changesOf(this._hass, child) : [];
      return buildLessons(events, exams, changes, withNow ? plan.now : null);
    }

    _ownEvents(plan, byEntity, child, dayKey, withNow) {
      const events = (byEntity.get(ownKeyOf(child)) || []).filter((event) => event.dayKey === dayKey && !event.allDay);
      return events.map((event) => ({ ...event, own: true, done: withNow ? event.end <= plan.now : false }));
    }

    _dayRows(plan, byEntity, child, dayKey, withNow, freeKey) {
      const { t, locale, zone } = plan;
      const holiday = holidayOn(this._holidays(plan, byEntity, child), dayKey);
      const lessons = this._childLessons(plan, byEntity, child, dayKey, withNow);
      const own = this._ownEvents(plan, byEntity, child, dayKey, withNow);
      const ownRows = own.map((event) => ownRow(event, t, locale, zone, false)).join("");
      if (holiday && !lessons.length) return { lessons, rows: noteRow(`<b dir="auto">${esc(holiday.summary)}</b>`) + ownRows };
      if (!lessons.length) return { lessons, rows: noteRow(esc(t(freeKey))) + ownRows };
      return { lessons, rows: byStart(lessons, own).map((item) => (item.own ? ownRow(item, t, locale, zone, false) : lessonRow(item, t, locale, zone))).join("") };
    }

    _schoolEndNote(plan, child, lessons) {
      const { t, locale, zone } = plan;
      if (!lessons.length) return "";
      const endState = stateOf(this._hass, child.entities[KEY_SCHOOL_END]);
      if (isMissing(endState)) return "";
      const end = new Date(endState.state);
      if (Number.isNaN(end.getTime())) return "";
      if (plan.now >= end) return noteRow(esc(t("school.over")));
      return noteRow(esc(t("school.end", { time: formatTime(end, locale, zone) })));
    }

    _renderToday(plan, byEntity, title) {
      const { t, locale, zone } = plan;
      const child = plan.children[0];
      const changes = numberOf(this._hass, child.entities[KEY_CHANGES]);
      const badge = changes > 0 ? `<span class="badge">${esc(badgeText(changes, locale))}</span>` : "";
      const head = panelHead(title || childLabel(plan.registry, child), formatWeekdayDay(plan.todayKey, locale, zone), badge);
      if (!this._hasTimetable(child)) return head + emptyBlock("timetable", t("timetable.none"));
      const day = this._dayRows(plan, byEntity, child, plan.todayKey, true, "today.free");
      return head + rowsBlock(day.rows + this._schoolEndNote(plan, child, day.lessons), plan.todayKey);
    }

    _weekGrid(plan, byEntity, child) {
      const { t, locale, zone } = plan;
      const holidays = this._holidays(plan, byEntity, child);
      const blocked = plan.dayKeys.map((dayKey) => holidayOn(holidays, dayKey));
      const fullWeek = blocked.every(Boolean) && blocked.every((entry) => entry.uid === blocked[0].uid) ? blocked[0] : null;
      const parts = [`<div style="grid-column:1;grid-row:1"></div>`];
      plan.dayKeys.forEach((dayKey, index) => {
        const today = dayKey === plan.todayKey ? "tt-head today" : "tt-head";
        const number = blocked[index] ? "n off" : "n";
        parts.push(
          `<div class="${today}" style="grid-column:${index + 2};grid-row:1"><span class="d">${esc(formatWeekdayShort(dayKey, locale, zone))}</span><span class="${number}">${esc(formatDayNumber(dayKey, locale, zone))}</span></div>`
        );
      });
      if (fullWeek) {
        parts.push(this._holidayField(plan, fullWeek, 0, SCHOOL_DAYS, 1, true));
        return { grid: `<div class="tt">${parts.join("")}</div>`, fullWeek };
      }
      const days = plan.dayKeys.map((dayKey, index) => (blocked[index] ? [] : this._childLessons(plan, byEntity, child, dayKey, false)));
      const slots = new Map();
      for (const lessons of days) {
        for (const lesson of lessons) {
          const key = slotKey(lesson.start, zone);
          if (!slots.has(key)) slots.set(key, { key, start: lesson.start, end: lesson.end });
        }
      }
      const rows = [...slots.values()].sort((left, right) => left.key.localeCompare(right.key));
      const rowCount = rows.length || DEFAULT_PERIODS;
      for (let index = 0; index < rowCount; index += 1) {
        const row = rows[index];
        const gridRow = index + 2;
        const hour = row ? `<b>${esc(formatTime(row.start, locale, zone))}</b><span>${esc(formatTime(row.end, locale, zone))}</span>` : "";
        parts.push(`<div class="tt-hour" style="grid-column:1;grid-row:${gridRow}">${hour}</div>`);
        plan.dayKeys.forEach((dayKey, dayIndex) => {
          if (blocked[dayIndex]) return;
          const place = `grid-column:${dayIndex + 2};grid-row:${gridRow}`;
          const lessons = row ? days[dayIndex].filter((lesson) => slotKey(lesson.start, zone) === row.key) : [];
          if (!lessons.length) {
            parts.push(`<div class="tt-cell free" data-day="${esc(dayKey)}" style="${place}"></div>`);
            return;
          }
          if (lessons.length === 1) {
            parts.push(this._lessonCell(lessons[0], t, dayKey, place, false));
            return;
          }
          const inner = lessons.map((lesson) => this._lessonCell(lesson, t, dayKey, "", true)).join("");
          parts.push(`<div class="tt-stack" style="${place}">${inner}</div>`);
        });
      }
      let index = 0;
      while (index < SCHOOL_DAYS) {
        const entry = blocked[index];
        if (!entry) {
          index += 1;
          continue;
        }
        let last = index;
        while (last + 1 < SCHOOL_DAYS && blocked[last + 1] && blocked[last + 1].uid === entry.uid) last += 1;
        parts.push(this._holidayField(plan, entry, index, last - index + 1, rowCount, false));
        index = last + 1;
      }
      return { grid: `<div class="tt">${parts.join("")}</div>`, fullWeek };
    }

    _holidayField(plan, holiday, index, span, rowCount, full) {
      const { t, locale, zone } = plan;
      const monday = plan.dayKeys[0];
      const friday = plan.dayKeys[SCHOOL_DAYS - 1];
      const lastDay = shiftKey(holiday.lastDay, -1, zone);
      let meta = "";
      if (span > 1 || full) {
        if (lastDay <= friday) meta = t("holiday.until", { date: formatShortDate(lastDay, locale, zone) });
        else if (holiday.firstDay >= monday) meta = t("holiday.from", { date: formatShortDate(holiday.firstDay, locale, zone) });
        else meta = t("date.range", { from: formatShortDate(holiday.firstDay, locale, zone), till: formatShortDate(lastDay, locale, zone) });
      }
      const metaHtml = meta ? `<span class="meta" dir="auto">${esc(meta)}</span>` : "";
      const name = `<span class="name" dir="auto">${esc(holiday.summary)}</span>`;
      if (full) {
        return `<div class="tt-hol full" data-uid="${esc(holiday.uid)}" style="grid-column:2 / span ${SCHOOL_DAYS};grid-row:2">${icon("upcoming", 20)}<span class="tt-hol-text">${name}${metaHtml}</span></div>`;
      }
      return `<div class="tt-hol" data-uid="${esc(holiday.uid)}" style="grid-column:${index + 2} / span ${span};grid-row:2 / span ${rowCount}">${name}${metaHtml}</div>`;
    }

    _lessonCell(lesson, t, dayKey, place, compact) {
      const classes = ["tt-cell"];
      if (lesson.cancelled) classes.push("out");
      else if (lesson.substitution) classes.push("subbed");
      if (compact) classes.push("compact");
      if (lesson.exam) classes.push("marked");
      const styles = place ? [place] : [];
      const colour = !lesson.cancelled && !lesson.substitution ? RanzenpostColour.cellVars(lesson.color) : null;
      if (colour) {
        classes.push("subject", "subject-bar");
        styles.push(`--subject-cell-fill:${colour.fill}`);
        styles.push(`--subject-cell-ink:${colour.ink}`);
        styles.push(`--subject-bar:${colour.bar}`);
      }
      const bar = lesson.substitution ? '<span class="bar"></span>' : "";
      const roomLabel = lesson.cancelled ? t("lesson.cancelled") : lesson.substitution ? t("lesson.substitutionShort") : "";
      const room = roomLabel ? `<span class="room">${esc(roomLabel)}</span>` : "";
      const flag = lesson.exam ? `<span class="exam-flag" title="${esc(t("lesson.exam"))}">${iconSvg("exam", 11)}</span>` : "";
      const style = styles.length ? ` style="${styles.join(";")}"` : "";
      return `<div class="${classes.join(" ")}" data-uid="${esc(lesson.uid)}" data-day="${esc(dayKey)}"${style}>${bar}<span class="sub" dir="auto">${esc(lesson.code || lesson.subject)}</span>${room}${flag}</div>`;
    }

    _legend(t) {
      return `<div class="legend"><span><i class="dot" style="background: var(--warn)"></i><span>${esc(t("lesson.substitution"))}</span></span><span><i class="sym" style="color: var(--danger)">${CROSS}</i><span>${esc(t("lesson.cancelled"))}</span></span></div>`;
    }

    _stamp(plan, child) {
      const { t, locale, zone } = plan;
      const state = stateOf(this._hass, child.entities[KEY_STAMP]);
      if (isMissing(state)) return "";
      const date = new Date(state.state);
      if (Number.isNaN(date.getTime())) return "";
      return `<div class="stamp">${esc(t("stamp", { time: formatDateTime(date, locale, zone) }))}</div>`;
    }

    _renderWeek(plan, byEntity, title) {
      const { t } = plan;
      const child = plan.children[0];
      const head = childHead(plan.registry, child, title || childLabel(plan.registry, child));
      if (!this._hasTimetable(child)) return head + emptyBlock("timetable", t("timetable.none"));
      const week = this._weekGrid(plan, byEntity, child);
      const legend = week.fullWeek ? "" : this._legend(t);
      return head + week.grid + legend + this._stamp(plan, child);
    }

    _counts(plan, child) {
      const { t, locale } = plan;
      return [
        ["count.letters", numberOf(this._hass, child.entities[KEY_LETTERS])],
        ["count.posts", numberOf(this._hass, child.entities[KEY_POSTS])],
        ["count.changes", numberOf(this._hass, child.entities[KEY_CHANGES])],
      ]
        .map(([key, count]) => {
          const badge = count > 0 ? `<span class="badge">${esc(badgeText(count, locale))}</span>` : "";
          return `<span class="count" data-count="${count}">${badge}<span>${esc(t(key))}</span></span>`;
        })
        .join("");
    }

    _nextHoliday(plan, school, schoolName) {
      const { t, locale, zone } = plan;
      const holiday = stateOf(this._hass, school.entities[KEY_HOLIDAY]);
      if (isMissing(holiday)) return "";
      const { start, end } = holiday.attributes || {};
      const range = start && end ? t("date.range", { from: formatShortDate(start, locale, zone), till: formatShortDate(end, locale, zone) }) : "";
      const metaText = [schoolName || "", range].filter(Boolean).join(" · ");
      const meta = metaText ? `<span class="meta" dir="auto">${esc(metaText)}</span>` : "";
      return `<div class="tt-hol full">${icon("upcoming", 20)}<span class="tt-hol-text"><span class="name" dir="auto">${esc(holiday.state)}</span>${meta}</span></div>`;
    }

    _familyMember(plan, byEntity, child) {
      const { t, locale, zone } = plan;
      const labels = ["day.today", "day.tomorrow"];
      const days = this._hasTimetable(child)
        ? plan.dayKeys
            .map((dayKey, index) => {
              const day = this._dayRows(plan, byEntity, child, dayKey, index === 0, "day.free");
              return panelHead(t(labels[index]), formatWeekdayDay(dayKey, locale, zone)) + rowsBlock(day.rows, dayKey);
            })
            .join("")
        : emptyBlock("timetable", t("timetable.none"));
      return `<div class="tt-child" data-child="${esc(child.id)}">${childHead(plan.registry, child, childLabel(plan.registry, child))}${days}<div class="counts">${this._counts(plan, child)}</div></div>`;
    }

    _familyHolidays(plan) {
      const shown = plan.registry.schools.filter((school) => plan.children.some((child) => child.schoolId === school.id));
      return shown.map((school) => this._nextHoliday(plan, school, shown.length > 1 ? school.name : "")).join("");
    }

    _renderFamily(plan, byEntity, title) {
      const { t } = plan;
      const head = panelHead(title || t("view.family"), "");
      if (!plan.children.length) return head + emptyBlock("alert", t("children.none"));
      const columns = plan.children.length >= SCROLL_FROM_CHILDREN ? "tt-multi scrolls" : "tt-multi";
      const body = `<div class="${columns}">${plan.children.map((child) => this._familyMember(plan, byEntity, child)).join("")}</div>`;
      return head + body + this._familyHolidays(plan);
    }

    _blockLink(plan, key, labelKey) {
      const path = ingressPathOf(this._hass, plan.registry);
      if (!path) return "";
      return `<a class="panel-link" href="${esc(path)}" data-block-link="${esc(key)}">${esc(plan.t(labelKey || "block.showAll"))}</a>`;
    }

    _blockHead(plan, entry, meta, count, fresh, linkKey) {
      const countHtml = count > 0 ? `<span class="count${fresh ? " fresh" : ""}">${esc(formatNumber(count, plan.locale))}</span>` : "";
      return panelHead(plan.t(`block.${entry.key}`), meta, countHtml + this._blockLink(plan, entry.key, linkKey));
    }

    _blockShell(entry, inner) {
      return `<div class="block" data-block="${esc(entry.key)}" data-size="${esc(entry.size)}">${inner}</div>`;
    }

    _listBlock(plan, entry, items, build, meta, fresh, linkKey) {
      const block = blockOf(entry.key);
      const shown = items.slice(0, limitOf(block, entry.size));
      const compact = entry.size === SIZE_COMPACT;
      const rows = shown.map((item) => build(item, compact)).join("");
      const path = ingressPathOf(this._hass, plan.registry);
      const more = items.length > shown.length && path
        ? `<a class="row row-all" href="${esc(path)}"><span class="row-dot"></span><div class="row-main"><div class="row-title">${esc(plan.t("block.showAll"))}</div></div></a>`
        : "";
      return this._blockShell(entry, this._blockHead(plan, entry, meta, items.length, fresh, linkKey) + rowsBlock(rows + more));
    }

    _listRow(title, sub, meta, unread, compact, tags, extra) {
      const chips = (tags || []).filter(Boolean);
      const extraHtml = extra || "";
      const tagHtml = !compact && chips.length ? `<div class="row-tags">${chips.map((tag) => `<span class="tag" dir="auto">${esc(tag)}</span>`).join("")}</div>` : "";
      const subHtml = !compact && sub ? `<div class="row-sub" dir="auto">${esc(sub)}</div>` : "";
      const metaHtml = meta ? `<span class="row-meta" dir="auto">${esc(meta)}</span>` : "";
      const sideInner = metaHtml + (compact ? extraHtml : "");
      const side = sideInner ? `<div class="row-side">${sideInner}</div>` : "";
      return `<div class="row${compact ? " compact" : ""}${unread ? "" : " read"}"><span class="row-dot">${unread ? "<i></i>" : ""}</span><div class="row-main">${tagHtml}<div class="row-title" dir="auto">${esc(title)}</div>${subHtml}${compact ? "" : extraHtml}</div>${side}</div>`;
    }

    _childTag(plan, child) {
      return plan.children.length > 1 ? childLabel(plan.registry, child) : "";
    }

    _renderBlocks(plan, byEntity, title) {
      const { t } = plan;
      if (!plan.children.length) return (title ? `<h2 class="card-title" dir="auto">${esc(title)}</h2>` : "") + emptyBlock("alert", t("children.none"));
      const parts = [];
      if (title) parts.push(`<h2 class="card-title" dir="auto">${esc(title)}</h2>`);
      const childBlocks = plan.blocks.filter((entry) => blockOf(entry.key).scope === "child");
      const restBlocks = plan.blocks.filter((entry) => blockOf(entry.key).scope !== "child");
      if (plan.children.length === 1) {
        for (const entry of plan.blocks) parts.push(this._renderBlock(plan, byEntity, entry, plan.children[0]));
      } else {
        const members = plan.children
          .map((child) => {
            const inner = childBlocks.map((entry) => this._renderBlock(plan, byEntity, entry, child)).join("");
            if (!inner) return "";
            return `<div class="member" data-child="${esc(child.id)}">${childHead(plan.registry, child, childLabel(plan.registry, child))}${inner}</div>`;
          })
          .filter(Boolean);
        if (members.length) parts.push(`<div class="family">${members.join("")}</div>`);
        for (const entry of restBlocks) parts.push(this._renderBlock(plan, byEntity, entry, null));
      }
      return parts.filter(Boolean).join("");
    }

    _renderBlock(plan, byEntity, entry, child) {
      switch (entry.key) {
        case "today": return this._todayBlock(plan, byEntity, entry, child);
        case "next_lesson": return this._nextLessonBlock(plan, entry, child);
        case "week": return this._weekBlock(plan, byEntity, entry, child);
        case "letters": return this._noticesBlock(plan, entry, child, KEY_LETTERS, "letters");
        case "noticeboard": return this._noticesBlock(plan, entry, child, KEY_POSTS, "posts");
        case "absences": return this._absencesBlock(plan, entry, child);
        case "conferences": return this._conferencesBlock(plan, entry);
        case "holidays": return this._holidaysBlock(plan, entry);
        case "changes": return this._changesBlock(plan, entry, child);
        default: return "";
      }
    }

    _todayBlock(plan, byEntity, entry, child) {
      const { t, locale, zone } = plan;
      if (!this._hasTimetable(child)) return "";
      const holiday = holidayOn(this._holidays(plan, byEntity, child), plan.todayKey);
      const all = this._childLessons(plan, byEntity, child, plan.todayKey, true);
      const own = this._ownEvents(plan, byEntity, child, plan.todayKey, true);
      if (!all.length && !holiday && !own.length) return "";
      const compact = entry.size === SIZE_COMPACT;
      const limit = limitOf(blockOf("today"), entry.size);
      const merged = byStart(all, own);
      const shown = (compact ? merged.filter((item) => !item.done) : merged).slice(0, limit);
      const render = (item) => (item.own ? ownRow(item, t, locale, zone, compact) : lessonRow(item, t, locale, zone, compact));
      let rows = "";
      if (!all.length) rows = noteRow(holiday ? `<b dir="auto">${esc(holiday.summary)}</b>` : esc(t("today.free"))) + shown.map(render).join("");
      else if (!shown.length) rows = noteRow(esc(t("school.over")));
      else rows = shown.map(render).join("") + (compact ? "" : this._schoolEndNote(plan, child, all));
      const changes = numberOf(this._hass, child.entities[KEY_CHANGES]);
      const head = this._blockHead(plan, entry, formatWeekdayDay(plan.todayKey, locale, zone), changes, changes > 0, "block.toTimetable");
      return this._blockShell(entry, head + rowsBlock(rows, plan.todayKey));
    }

    _nextLessonBlock(plan, entry, child) {
      const { t, locale, zone } = plan;
      const state = stateOf(this._hass, child.entities[KEY_NEXT_LESSON]);
      if (isMissing(state) || !state.attributes || !state.attributes.start) return "";
      const start = new Date(state.attributes.start);
      if (Number.isNaN(start.getTime()) || start <= plan.now) return "";
      const dayKey = dateKey(start, zone);
      const day = dayKey === plan.todayKey ? t("day.today") : dayKey === shiftKey(plan.todayKey, 1, zone) ? t("day.tomorrow") : formatWeekdayDay(dayKey, locale, zone);
      const minutes = Number(state.attributes.minutes_until) || 0;
      const details = [state.attributes.room, state.attributes.teacher, minutes > 0 ? relativeMinutes(minutes, locale) : ""].filter(Boolean).join(" · ");
      const row = this._listRow(String(state.state), details, `${day} · ${formatTime(start, locale, zone)}`, false, entry.size === SIZE_COMPACT, []);
      return this._blockShell(entry, this._blockHead(plan, entry, "", 0, false, "block.toTimetable") + rowsBlock(row));
    }

    _weekBlock(plan, byEntity, entry, child) {
      if (!this._hasTimetable(child)) return "";
      const lessons = (byEntity.get(child.entities[KEY_LESSONS]) || []).filter((event) => plan.dayKeys.includes(event.dayKey));
      if (!lessons.length) return "";
      const week = this._weekGrid(plan, byEntity, child);
      const grid = entry.size === SIZE_COMPACT ? week.grid.replace('class="tt"', 'class="tt compact-cells"') : week.grid;
      return this._blockShell(entry, this._blockHead(plan, entry, "", 0, false, "block.toTimetable") + grid + (week.fullWeek ? "" : this._legend(plan.t)));
    }

    _noticesBlock(plan, entry, child, key, attribute) {
      const { locale, zone } = plan;
      const children = child ? [child] : plan.children;
      const items = [];
      const seen = new Set();
      for (const member of children) {
        const state = stateOf(this._hass, member.entities[key]);
        const listed = state && Array.isArray(state.attributes[attribute]) ? state.attributes[attribute] : [];
        for (const notice of listed) {
          const title = String((notice && notice.title) || "");
          const date = String((notice && notice.date) || "");
          const id = `${title}|${date}|${String((notice && notice.sender) || "")}`;
          if (!title || seen.has(id)) continue;
          seen.add(id);
          items.push({ title, date, sender: String((notice && notice.sender) || ""), child: String((notice && notice.child) || "") || this._childTag(plan, member) });
        }
      }
      if (!items.length) return "";
      return this._listBlock(plan, entry, items, (item, compact) => this._listRow(
        item.title,
        item.sender,
        item.date ? formatShortDate(item.date, locale, zone) : "",
        true,
        compact,
        [plan.children.length > 1 ? item.child : ""]
      ), "", true);
    }

    _absencesBlock(plan, entry, child) {
      const { t, locale, zone } = plan;
      const state = stateOf(this._hass, child.entities[KEY_ABSENCES]);
      const listed = state && Array.isArray(state.attributes.absences) ? state.attributes.absences : [];
      const limitKey = shiftKey(plan.todayKey, ABSENCE_DAYS_AHEAD, zone);
      const items = listed
        .filter((absence) => absenceInWindow(absence, plan.todayKey, limitKey))
        .sort((left, right) => String(left.start).localeCompare(String(right.start)));
      if (!items.length) return "";
      return this._listBlock(plan, entry, items, (item, compact) => {
        const range = item.start && item.end && item.start !== item.end
          ? t("date.range", { from: formatShortDate(item.start, locale, zone), till: formatShortDate(item.end, locale, zone) })
          : formatShortDate(item.start || item.end, locale, zone);
        const statusKey = `status.${item.status}`;
        const status = item.status && TEXTS.en[statusKey] ? t(statusKey) : "";
        const who = this._childTag(plan, child);
        return this._listRow(who ? `${who} · ${range}` : range, [item.summary, status].filter(Boolean).join(" · "), "", false, compact, []);
      }, "", false);
    }

    _schoolsOf(plan) {
      return plan.registry.schools.filter((school) => plan.children.some((child) => child.schoolId === school.id));
    }

    _conferencesBlock(plan, entry) {
      const { locale, zone } = plan;
      const schools = this._schoolsOf(plan);
      const items = [];
      for (const school of schools) {
        const state = stateOf(this._hass, school.entities[KEY_CONFERENCE]);
        if (isMissing(state) || !state.attributes || !state.attributes.date) continue;
        items.push({ date: String(state.attributes.date), title: String(state.attributes.title || ""), details: Array.isArray(state.attributes.details) ? state.attributes.details : [], school: schools.length > 1 ? school.name : "" });
      }
      items.sort((left, right) => left.date.localeCompare(right.date));
      if (!items.length) return "";
      return this._listBlock(plan, entry, items, (item, compact) => this._listRow(
        item.title || formatShortDate(item.date, locale, zone),
        item.details.slice(0, 3).join(" · "),
        formatShortDate(item.date, locale, zone),
        false,
        compact,
        [item.school]
      ), "", false);
    }

    _holidaysBlock(plan, entry) {
      const { t, locale, zone } = plan;
      const schools = this._schoolsOf(plan);
      const items = [];
      for (const school of schools) {
        const state = stateOf(this._hass, school.entities[KEY_HOLIDAY]);
        if (isMissing(state) || !state.attributes || !state.attributes.start) continue;
        items.push({ name: String(state.state), start: String(state.attributes.start), end: String(state.attributes.end || state.attributes.start), days: Number(state.attributes.days_until) || 0, school: schools.length > 1 ? school.name : "" });
      }
      items.sort((left, right) => left.start.localeCompare(right.start));
      if (!items.length) return "";
      return this._listBlock(plan, entry, items, (item, compact) => this._listRow(
        item.name,
        t("date.range", { from: formatShortDate(item.start, locale, zone), till: formatShortDate(item.end, locale, zone) }),
        item.days > 0 ? relativeDays(item.days, locale) : t("day.today"),
        false,
        compact,
        [item.school]
      ), "", false);
    }

    _changesBlock(plan, entry, child) {
      const { t, locale, zone } = plan;
      const changes = changesOf(this._hass, child).filter((change) => change && change.start);
      if (!changes.length) return "";
      return this._listBlock(plan, entry, changes, (change, compact) => {
        const start = new Date(change.start);
        const kind = change.cancelled ? t("lesson.cancelled") : t("lesson.substitution");
        const detail = [change.period ? formatNumber(change.period, locale) : "", Number.isNaN(start.getTime()) ? "" : formatTime(start, locale, zone), change.cancelled ? "" : [change.teacher, change.room].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
        const title = String(change.subject || change.subject_code || "");
        const tag = `<span class="tag ${change.cancelled ? "no" : "open"}">${esc(kind)}</span>`;
        return this._listRow(title, detail, t("day.today"), false, compact, [this._childTag(plan, child)], tag);
      }, "", true, "block.toTimetable");
    }
  }

  class RanzenpostCardEditor extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = { blocks: [] };
      this._hass = null;
      this._registry = { children: [], schools: [] };
      this._settled = Promise.resolve();
      this._form = null;
      this._built = false;
      this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
      this.shadowRoot.addEventListener("value-changed", (event) => this._onFormValue(event));
    }

    setConfig(config) {
      const given = { ...(config || {}) };
      const blocks = Array.isArray(given.blocks) ? normaliseBlocks(given.blocks) : blocksOfLegacy(given);
      const children = Array.isArray(given.children) ? given.children.slice() : given.child ? [given.child] : [];
      this._config = { title: given.title || "", blocks, children };
      if (this._built) this._update();
      else this._render();
    }

    get _children() {
      return this._registry.children;
    }

    _label(child) {
      return nameIsShared(this._children, child) && child.school ? `${child.name} (${child.school})` : child.name;
    }

    set hass(hass) {
      this._hass = hass;
      if (this._form) this._form.hass = hass;
      this._settled = discover(hass, true)
        .then((registry) => {
          this._registry = registry;
          if (this._built) this._update();
          else this._render();
        })
        .catch(() => {
          if (!this._built) this._render();
        });
    }

    get hass() {
      return this._hass;
    }

    get settled() {
      return this._settled;
    }

    _offered() {
      return offeredBlocks(this._hass, this._registry);
    }

    _missingNames(t) {
      const offered = new Set(this._offered().map((block) => block.key));
      return CARD_BLOCKS.filter((block) => !offered.has(block.key)).map((block) => t(`block.${block.key}`));
    }

    _emit() {
      const config = { type: `custom:${CARD_TAG}` };
      if (this._config.title) config.title = this._config.title;
      config.blocks = this._config.blocks.map((entry) => (entry.size === blockOf(entry.key).size ? entry.key : { key: entry.key, size: entry.size }));
      if (this._config.children.length) config.children = this._config.children.slice();
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
    }

    _setBlocks(keys) {
      const known = new Map(this._config.blocks.map((entry) => [entry.key, entry]));
      const kept = this._config.blocks.filter((entry) => keys.includes(entry.key));
      for (const key of keys) {
        if (!known.has(key) && blockOf(key)) kept.push({ key, size: blockOf(key).size });
      }
      this._config.blocks = kept;
    }

    _onFormValue(event) {
      if (!this._form || event.target !== this._form) return;
      event.stopPropagation();
      const value = event.detail && event.detail.value ? event.detail.value : {};
      this._config.title = String(value.title || "").trim();
      this._config.children = Array.isArray(value.children) ? value.children.filter(Boolean) : [];
      this._setBlocks(Array.isArray(value.blocks) ? value.blocks : []);
      for (const entry of this._config.blocks) {
        const size = value[`size_${entry.key}`];
        if (SIZES.includes(size)) entry.size = size;
      }
      this._emit();
      this._update();
    }

    _onChange(event) {
      const field = event.target;
      if (!field || !field.name) return;
      if (field.name === "title") {
        this._config.title = field.value.trim();
      } else if (field.name === "children") {
        this._config.children = [...this.shadowRoot.querySelectorAll("input[name=children]:checked")].map((input) => input.value);
      } else if (field.name === "blocks") {
        this._setBlocks([...this.shadowRoot.querySelectorAll("input[name=blocks]:checked")].map((input) => input.value));
      } else if (field.name.startsWith("size_")) {
        const entry = this._config.blocks.find((item) => item.key === field.name.slice(5));
        if (entry && SIZES.includes(field.value)) entry.size = field.value;
      } else {
        return;
      }
      this._emit();
      this._update();
    }

    _schema(t) {
      const children = this._children.map((child) => ({ value: childReference(this._children, child), label: this._label(child) }));
      const blocks = this._offered().map((block) => ({ value: block.key, label: t(`block.${block.key}`), description: t(`block.${block.key}.explain`) }));
      const schema = [
        { name: "title", selector: { text: {} } },
        { name: "children", selector: { select: { multiple: true, mode: "list", options: children } } },
        { name: "blocks", selector: { select: { multiple: true, mode: "list", options: blocks } } },
      ];
      for (const entry of this._config.blocks) {
        schema.push({
          name: `size_${entry.key}`,
          selector: { select: { mode: "dropdown", options: SIZES.map((size) => ({ value: size, label: t(`editor.size.${size}`) })) } },
        });
      }
      return schema;
    }

    _formData() {
      const data = { title: this._config.title, children: this._config.children.slice(), blocks: this._config.blocks.map((entry) => entry.key) };
      for (const entry of this._config.blocks) data[`size_${entry.key}`] = entry.size;
      return data;
    }

    _labelOf(t, schema) {
      if (schema.name === "title") return t("editor.title");
      if (schema.name === "children") return t("editor.children");
      if (schema.name === "blocks") return t("editor.blocks");
      return t("editor.size", { name: t(`block.${schema.name.slice(5)}`) });
    }

    _helperOf(t, schema) {
      if (schema.name === "children") return t("editor.allChildren");
      if (schema.name === "blocks") {
        const missing = this._missingNames(t);
        return missing.length ? `${t("editor.blocks.helper")} ${t("editor.blocks.missing", { names: missing.join(", ") })}` : t("editor.blocks.helper");
      }
      if (schema.name.startsWith("size_")) return t(`block.${schema.name.slice(5)}.explain`);
      return "";
    }

    _render() {
      const t = translator(this._hass);
      this._built = !!this._hass;
      if (customElements.get("ha-form")) {
        const form = document.createElement("ha-form");
        form.hass = this._hass;
        form.schema = this._schema(t);
        form.data = this._formData();
        form.computeLabel = (schema) => this._labelOf(t, schema);
        form.computeHelper = (schema) => this._helperOf(t, schema);
        this._form = form;
        this.shadowRoot.innerHTML = `<style>${EDITOR_STYLE}</style>`;
        this.shadowRoot.appendChild(form);
        return;
      }
      this._form = null;
      this.shadowRoot.innerHTML = `<style>${EDITOR_STYLE}</style><div class="form" dir="${directionOf()}">${this._fallbackFields(t)}</div>`;
    }

    _fallbackFields(t) {
      const chosenChildren = new Set(this._config.children.map((item) => String(item).toLowerCase()));
      const childBoxes = this._children
        .map((child) => {
          const reference = childReference(this._children, child);
          const checked = [reference, child.slug, child.id, child.deviceId, child.name].some((item) => chosenChildren.has(String(item).toLowerCase()));
          return `<label><input type="checkbox" name="children" value="${esc(reference)}"${checked ? " checked" : ""}>${esc(this._label(child))}</label>`;
        })
        .join("");
      const chosenBlocks = new Set(this._config.blocks.map((entry) => entry.key));
      const blockBoxes = this._offered()
        .map((block) => `<label><input type="checkbox" name="blocks" value="${esc(block.key)}"${chosenBlocks.has(block.key) ? " checked" : ""}>${esc(t(`block.${block.key}`))}<span class="hint">${esc(t(`block.${block.key}.explain`))}</span></label>`)
        .join("");
      const missing = this._missingNames(t);
      const helper = missing.length ? `${t("editor.blocks.helper")} ${t("editor.blocks.missing", { names: missing.join(", ") })}` : t("editor.blocks.helper");
      let fields = `<div class="field"><label for="title">${esc(t("editor.title"))}</label><input id="title" name="title" type="text" value="${esc(this._config.title || "")}"></div>`;
      fields += `<div class="field"><span class="hint">${esc(t("editor.children"))}: ${esc(t("editor.allChildren"))}</span><div class="children">${childBoxes}</div></div>`;
      fields += `<div class="field"><span class="hint">${esc(t("editor.blocks"))}: ${esc(helper)}</span><div class="blocks">${blockBoxes}</div></div>`;
      fields += `<div class="field sizes"><span class="hint">${esc(t("editor.sizes"))}</span><div class="size-list">${this._fallbackSizes(t)}</div></div>`;
      return fields;
    }

    _fallbackSizes(t) {
      const option = (value, label, selected) => `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;
      return this._config.blocks
        .map((entry) => {
          const options = SIZES.map((size) => option(size, t(`editor.size.${size}`), size === entry.size)).join("");
          return `<div class="size-row" data-block="${esc(entry.key)}"><label for="size_${esc(entry.key)}">${esc(t("editor.size", { name: t(`block.${entry.key}`) }))}</label><select id="size_${esc(entry.key)}" name="size_${esc(entry.key)}">${options}</select></div>`;
        })
        .join("");
    }

    _update() {
      const t = translator(this._hass);
      if (this._form) {
        this._form.schema = this._schema(t);
        this._form.data = this._formData();
        return;
      }
      const root = this.shadowRoot;
      const active = root.activeElement;
      const title = root.querySelector("input[name=title]");
      if (title && title !== active && title.value !== (this._config.title || "")) title.value = this._config.title || "";
      const childrenContainer = root.querySelector(".children");
      if (childrenContainer) {
        const chosen = new Set(this._config.children.map((item) => String(item).toLowerCase()));
        const existing = new Set([...childrenContainer.querySelectorAll("input[name=children]")].map((input) => input.value));
        for (const child of this._children) {
          const reference = childReference(this._children, child);
          if (existing.has(reference)) continue;
          const checked = [reference, child.slug, child.id, child.deviceId, child.name].some((item) => chosen.has(String(item).toLowerCase()));
          const label = document.createElement("label");
          label.innerHTML = `<input type="checkbox" name="children" value="${esc(reference)}"${checked ? " checked" : ""}>${esc(this._label(child))}`;
          childrenContainer.appendChild(label);
        }
      }
      const blocksContainer = root.querySelector(".blocks");
      if (blocksContainer) {
        const offered = new Set(this._offered().map((block) => block.key));
        for (const input of blocksContainer.querySelectorAll("input[name=blocks]")) {
          input.closest("label").hidden = !offered.has(input.value);
        }
      }
      const sizes = root.querySelector(".size-list");
      if (sizes) {
        const wanted = this._config.blocks.map((entry) => entry.key);
        const rows = new Map([...sizes.querySelectorAll(".size-row")].map((row) => [row.dataset.block, row]));
        for (const [key, row] of rows) {
          if (!wanted.includes(key)) row.remove();
        }
        for (const entry of this._config.blocks) {
          if (rows.has(entry.key)) {
            const select = rows.get(entry.key).querySelector("select");
            if (select !== active && select.value !== entry.size) select.value = entry.size;
            continue;
          }
          const holder = document.createElement("div");
          holder.innerHTML = this._fallbackSizes(t);
          const fresh = holder.querySelector(`.size-row[data-block="${entry.key}"]`);
          if (fresh) sizes.appendChild(fresh);
        }
      }
    }
  }

  if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, RanzenpostCard);
  if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, RanzenpostCardEditor);

  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === CARD_TAG)) {
    window.customCards.push({
      type: CARD_TAG,
      name: "Ranzenpost",
      description: translator(null)("card.description"),
      preview: true,
      documentationURL: "https://github.com/githuber110/ranzenpost",
    });
  }
})();
