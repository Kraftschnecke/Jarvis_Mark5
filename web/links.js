// Links im Chat (Mark 5, Step 2.2): aus [Text](https://adresse) wird ein anklickbarer Link.
// Reine Textfunktion ohne Zugriff auf die Seite, damit sie ohne Browser testbar ist.
//
// Der Text einer Antwort kann Inhalte aus dem Internet enthalten (Schlagzeilen, Suchtreffer).
// Darum gilt: nur https, keine Adressen mit Benutzername/Passwort, und hinter jedem Link steht
// der Rechnername der echten Adresse, damit ein Link-Text nicht eine andere Seite vortauschen kann.
// Geklickt wird immer von dir; Jarvis ruft diese Adressen nie selbst auf.
(function (root) {
  "use strict";

  const PATTERN = /\[([^\]\n]{1,200})\]\((https:\/\/[^\s()]{1,800})\)/g;

  // Gibt {url, host} zurueck, wenn die Adresse erlaubt ist, sonst null.
  function safeLink(raw) {
    let url;
    try {
      url = new URL(raw);
    } catch (e) {
      return null;
    }
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return null;
    if (url.port && url.port !== "443") return null;
    return { url: url.href, host: url.hostname };
  }

  // "Text [Titel](https://x.de/a) mehr" -> [{text}, {label, url, host}, {text}]
  function splitLinks(text) {
    const parts = [];
    let last = 0;
    String(text).replace(PATTERN, (match, label, raw, index) => {
      const link = safeLink(raw);
      if (!link) return match;                       // bleibt normaler Text
      if (index > last) parts.push({ text: text.slice(last, index) });
      parts.push({ label: label, url: link.url, host: link.host });
      last = index + match.length;
      return match;
    });
    if (last < text.length) parts.push({ text: text.slice(last) });
    return parts;
  }

  const api = { splitLinks, safeLink };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisLinks = api;
})(typeof window !== "undefined" ? window : this);
