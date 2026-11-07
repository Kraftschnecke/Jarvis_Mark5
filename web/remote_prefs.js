// Handy-Einstellungen (Mark 5, nach R6): Design, Akzentfarbe und Sprachausgabe gelten nur auf diesem Handy.
// Sie liegen im Speicher des Browsers (nicht auf dem PC) und ueberdecken am Handy die Werte des PC.
(function (root) {
  "use strict";

  const KEY = "jarvis.remote.prefs";
  const THEMES = ["Dark", "Light", "System"];
  const ACCENTS = ["J.A.R.V.I.S. Blue", "British Racing Green"];
  const FONT_SIZES = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20];      // wie am PC (11 bis 20 px)
  // Felder der Seitenleiste am Handy: nur, was es dort gibt (PC Facts, Performance und Eishockey fragen Adressen, die Remote nicht hat)
  const SLOTS = {
    top: ["Off", "Clock", "Date", "Calendar"],
    middle: ["Off", "Notes", "Goals", "Lists"],
    fourth: ["Off", "Lists"],
    fifth: ["Off", "Lists"],
  };

  // Nur gueltige Werte bleiben; alles andere (kaputter Speicher, fremde Schluessel) faellt weg
  function normalize(raw) {
    const prefs = {};
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return prefs;
    if (THEMES.indexOf(raw.theme) >= 0) prefs.theme = raw.theme;
    if (ACCENTS.indexOf(raw.accent_color) >= 0) prefs.accent_color = raw.accent_color;
    if (typeof raw.speech === "boolean") prefs.speech = raw.speech;
    if (FONT_SIZES.indexOf(raw.font_size) >= 0) prefs.font_size = raw.font_size;
    if (raw.widgets && typeof raw.widgets === "object" && !Array.isArray(raw.widgets)) {
      const widgets = {};
      Object.keys(SLOTS).forEach((slot) => {
        if (SLOTS[slot].indexOf(raw.widgets[slot]) >= 0) widgets[slot] = raw.widgets[slot];
      });
      if (Object.keys(widgets).length) prefs.widgets = widgets;
    }
    return prefs;
  }

  function load(storage) {
    try {
      return normalize(JSON.parse(storage.getItem(KEY)));
    } catch (error) {
      return {};
    }
  }

  // false, wenn der Speicher nicht geht (die Auswahl gilt dann nur bis zum Neuladen)
  function save(storage, prefs) {
    try {
      storage.setItem(KEY, JSON.stringify(normalize(prefs)));
      return true;
    } catch (error) {
      return false;
    }
  }

  // Die Einstellungen des PC mit den Wuenschen des Handys ueberdeckt. Das Original bleibt unveraendert.
  function apply(settings, prefs) {
    const base = settings && typeof settings === "object" ? settings : {};
    const wanted = normalize(prefs);
    const merged = Object.assign({}, base);
    merged.appearance = Object.assign({}, base.appearance);
    merged.voice = Object.assign({}, base.voice);
    merged.widgets = Object.assign({}, base.widgets);
    if (wanted.theme !== undefined) merged.appearance.theme = wanted.theme;
    if (wanted.accent_color !== undefined) merged.appearance.accent_color = wanted.accent_color;
    if (wanted.speech !== undefined) merged.voice.output = wanted.speech;
    if (wanted.font_size !== undefined) merged.appearance.font_size = wanted.font_size;
    if (wanted.widgets !== undefined) Object.assign(merged.widgets, wanted.widgets);
    return merged;
  }

  // Was der Dialog zeigt: der Wunsch des Handys, sonst der Wert des PC
  function view(settings, prefs) {
    const merged = apply(settings, prefs);
    return {
      theme: THEMES.indexOf(merged.appearance.theme) >= 0 ? merged.appearance.theme : "Dark",
      accent_color: ACCENTS.indexOf(merged.appearance.accent_color) >= 0 ? merged.appearance.accent_color : ACCENTS[0],
      speech: merged.voice.output === true,
      font_size: FONT_SIZES.indexOf(merged.appearance.font_size) >= 0 ? merged.appearance.font_size : 13,
      widgets: Object.keys(SLOTS).reduce((shown, slot) => {
        shown[slot] = SLOTS[slot].indexOf(merged.widgets[slot]) >= 0 ? merged.widgets[slot] : "Off";
        return shown;
      }, {}),
    };
  }

  const api = { KEY, THEMES, ACCENTS, FONT_SIZES, SLOTS, normalize, load, save, apply, view };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisRemotePrefs = api;
})(typeof window !== "undefined" ? window : this);