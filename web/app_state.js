"use strict";
// app_state.js: Einstellungs-Zustand, Aussehen, Remote-/Gast-Modus, Abmelden. Gemeinsam fuer Besitzer und Gast.
let settings = {};
let about = { version: "", system: "" };
let abilitiesInfo = [];
let usageInfo = null;
let currentPage = "Appearance";

function applyAppearance() {
  const theme = (settings.appearance && settings.appearance.theme) || "Dark";
  const size = settings.appearance && settings.appearance.font_size;
  const light =
    theme === "Light" || (theme === "System" && matchMedia("(prefers-color-scheme: light)").matches);

  if (light) document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;

  const green = settings.appearance && settings.appearance.accent_color === "British Racing Green";
  if (green) document.documentElement.dataset.accent = "green";
  else delete document.documentElement.dataset.accent;

  if (Number.isInteger(size) && size >= 11 && size <= 20) {
    document.documentElement.style.fontSize = size + "px";
  }

  try {
    localStorage.setItem("jarvis.theme", theme);
    localStorage.setItem("jarvis.accent", green ? "green" : "blue");
    if (Number.isInteger(size)) localStorage.setItem("jarvis.fontsize", String(size));
  } catch (error) {
    /* ohne Speicher funktioniert die Seite trotzdem */
  }
}

matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyAppearance);

// Handy (nach R6): Design, Farbe und Sprachausgabe stehen im Browser des Handys und ueberdecken die Werte des PC
let serverSettings = {};
let phonePrefs = null;      // die Wuensche dieses Handys; einmal aus dem Browser-Speicher geladen, danach im Speicher gefuehrt

function mergePhonePrefs() {
  if (phonePrefs === null) phonePrefs = window.JarvisRemotePrefs.load(localStorage);
  settings = remoteMode ? window.JarvisRemotePrefs.apply(serverSettings, phonePrefs) : serverSettings;
}

function applySettingsState(data) {
  serverSettings = data.settings;
  settings = serverSettings;
  about = data.about;
  abilitiesInfo = Array.isArray(data.abilities) ? data.abilities : [];
  usageInfo = data.usage || null;
  guestMode = data.guest === true;
  document.body.classList.toggle("guest", guestMode);
  setRemoteMode(data.remote === true);
  setTesterMode(data.remote === true && data.tester === true);
  mergePhonePrefs();
  if (guestMode) setStatus("ready", "GAST");
  applyAppearance();
  applyVoice();
  applyWidgets();
}

// Remote (R5): Streifen "Remote (eingeschraenkt)" und weniger Bedienung. Die Sperre steht im Server, das hier ist nur Anzeige.
const remoteBanner = byId("remote-banner");

async function refreshRemoteBanner() {
  let info = null;
  try {
    info = await api("GET", "/api/remote/whoami");
  } catch (error) {
    info = { remote: true, levels: {}, device: "nicht angemeldet" };
  }
  const view = window.JarvisRemoteMode.bannerView(info);
  remoteBanner.hidden = !view.show;
  remoteBanner.replaceChildren();
  if (view.show) {
    remoteBanner.append(el("strong", "remote-banner-title", view.title), el("span", "remote-banner-detail", view.detail));
  }
}

function setRemoteMode(value) {
  const changed = value !== remoteMode;
  remoteMode = value;
  document.body.classList.toggle("remote", value);
  byId("open-phone-prefs").hidden = !value;
  byId("logout-button").hidden = !value;
  if (value && changed) refreshRemoteBanner();
  if (!value) remoteBanner.hidden = true;
}
function setTesterMode(value) {
  const changed = value !== testerMode;
  testerMode = value;
  document.body.classList.toggle("tester", value);
  const view = window.JarvisRemoteMode.testerSidebarView(value);
  newConversationButton.lastChild.textContent = " " + view.newLabel;
  if (changed) renderTree();
}
document.addEventListener("visibilitychange", () => { if (!document.hidden && remoteMode) refreshRemoteBanner(); });

// Abmelden (nur ueber Remote): der Server loescht den Zugang dieses Geraets, danach geht es zur Kopplungsseite
byId("logout-button").addEventListener("click", () => {
  openDialog({
    title: "Abmelden?",
    text: "Dieses Gerät wird abgemeldet. Zum Wiederkommen brauchst du einen neuen Code.",
    okLabel: "Abmelden",
    danger: true,
    onSubmit: async () => {
      await api("POST", "/api/remote/logout", {});
      window.location.href = "/pair";
    },
  });
});

async function loadSettings() {
  try {
    applySettingsState(await api("GET", "/api/settings"));
  } catch (error) {
    /* Standard-Design bleibt */
  }
}