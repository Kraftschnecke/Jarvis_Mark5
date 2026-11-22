// Willkommensseite: der Inhalt der kleinen Fenster auf der Seite (nur Anzeige).
// Jedes Fenster hat einen Titel, eine Zeile rechts neben dem Titel (extra) und eine Zeichen-Funktion (draw).
// Alles, was aus Daten kommt (Termine, Ziele, Listen), wird nur als Text eingesetzt, nie als HTML.
(function (root) {
  "use strict";

  function create(app) {
    const { el, L } = app;

    const empty = (text) => el("div", "wempty", text);

    function row(parts) {
      const r = el("div", "wrow");
      parts.forEach((p) => r.append(p));
      return r;
    }

    // ---- Tagesziele
    const goals = {
      title: "Tagesziele",
      extra() {
        const p = L.goalProgress(app.data && app.data.goals);
        return p.total ? p.done + "/" + p.total : "";
      },
      draw(body) {
        const list = (app.data && app.data.goals) || [];
        if (!list.length) return body.append(empty("Noch keine Ziele für heute."));
        list.slice(0, 5).forEach((g) => body.append(row([el("span", "wbox" + (g.done ? " d" : "")), el("span", "", g.text)])));
        if (list.length > 5) body.append(el("div", "wempty small", "+ " + (list.length - 5) + " weitere"));
        const bar = el("div", "bar");
        const fill = el("i");
        fill.style.width = L.goalProgress(list).percent + "%";
        bar.append(fill);
        body.append(bar);
      },
    };

    // ---- Fokus und Timer (die Zeiten zaehlen jede Sekunde, siehe app.onTick)
    const focus = {
      title: "Fokus & Timer",
      extra: () => "",
      draw(body) {
        const f = app.focusNow();
        const timers = app.timersNow();
        if (!f.active && !timers.length) return body.append(empty("Kein Timer, keine Fokus-Sitzung."));
        if (f.active) {
          const name = f.label ? f.label : "Fokus";
          body.append(row([el("span", "t wide", L.formatRemaining(f.remaining)), el("span", "", name + " · " + f.phase_name)]));
        }
        timers.slice(0, f.active ? 2 : 3).forEach((t) => body.append(row([el("span", "t wide", L.formatRemaining(t.remaining)), el("span", "", t.name || "Timer")])));
      },
    };

    // ---- Listen
    const lists = {
      title: "Listen",
      extra() {
        const first = app.data && app.data.lists && app.data.lists[0];
        return first ? first.name : "";
      },
      draw(body) {
        const first = app.data && app.data.lists && app.data.lists[0];
        if (!first) return body.append(empty("Noch keine Listen."));
        const open = first.items.filter((i) => !i.done);
        if (!open.length) return body.append(empty(first.items.length ? "Alles erledigt." : "Die Liste ist leer."));
        open.slice(0, 3).forEach((i) => body.append(row([el("span", "wbox"), el("span", "", i.text)])));
        if (open.length > 3) body.append(el("div", "wempty small", "+ " + (open.length - 3) + " weitere"));
      },
    };

    // ---- Kalender: heute und morgen
    const calendar = {
      title: "Kalender",
      extra: () => "Heute · Morgen",
      draw(body) {
        const events = (app.data && app.data.events) || [];
        const today = new Date();
        const todays = L.eventsOn(events, L.dayKey(today));
        const tomorrows = L.eventsOn(events, L.dayKey(L.addDays(today, 1)));
        if (!todays.length) body.append(empty("Heute keine Termine."));
        todays.slice(0, 3).forEach((e) => body.append(row([el("span", "t", e.time || "ganztags"), el("span", "", e.title)])));
        if (todays.length > 3) body.append(el("div", "wempty small", "+ " + (todays.length - 3) + " weitere heute"));
        const first = tomorrows.find((e) => e.time);
        const line = tomorrows.length
          ? tomorrows.length + (tomorrows.length === 1 ? " Termin" : " Termine") + (first ? " · ab " + first.time : "")
          : "keine Termine";
        body.append(row([el("span", "muted small", "Morgen"), el("span", "muted small", line)]));
      },
    };

    // ---- Wetter: der Satz vom Server (Heimatort)
    const weather = {
      title: "Wetter",
      extra: () => "",
      draw(body) {
        body.append(app.weather ? el("div", "temp", app.weather) : empty("Kein Wetter verfügbar."));
      },
    };

    // Zustand von Daten, die vom Server geholt werden (app.extra[name] = { status, data, error }): true, wenn sie da sind
    function loaded(name, body) {
      const e = app.extra[name];
      if (!e || e.status === "loading") { body.append(empty("Lade …")); return false; }
      if (e.status === "disabled") { body.append(empty("In den Einstellungen ausgeschaltet.")); return false; }
      if (e.status === "error") { body.append(empty(e.error || "Gerade nicht verfügbar.")); return false; }
      return true;
    }

    // So viele Zeilen passen: in vollen Spalten (compact) weniger
    const lines = (full, compact) => (app.compact ? compact : full);

    function rows(body, items, limit, make) {
      items.slice(0, limit).forEach((item) => body.append(make(item)));
      if (items.length > limit) body.append(el("div", "wempty small", "+ " + (items.length - limit) + " weitere"));
    }

    // ---- Notizen: die gemeinsame Notiz (erste Zeilen)
    const notes = {
      title: "Notizen",
      extra: () => "",
      draw(body) {
        const text = ((app.data && app.data.notes) || "").trim();
        body.append(text ? el("div", "temp clamp", text) : empty("Noch keine Notiz."));
      },
    };

    // ---- News: die ersten drei Schlagzeilen
    const news = {
      title: "News",
      extra: () => "",
      draw(body) {
        if (!loaded("news", body)) return;
        const items = app.extra.news.data;
        if (!items.length) return body.append(empty("Keine Schlagzeilen."));
        rows(body, items, lines(3, 2), (i) => row([el("span", "", i.title)]));
      },
    };

    // ---- Briefing: Anfang des Tagesbriefings
    const briefing = {
      title: "Briefing",
      extra: () => "",
      draw(body) {
        if (!loaded("briefing", body)) return;
        const text = app.extra.briefing.data;
        body.append(text ? el("div", "temp clamp", text) : empty("Kein Briefing."));
      },
    };

    // ---- Weltuhr: bis zu vier Staedte
    const worldtime = {
      title: "Weltuhr",
      extra: () => "",
      draw(body) {
        const now = new Date();
        const cities = app.cities.map((id) => L.cityOf(id)).filter(Boolean);
        if (!cities.length) return body.append(empty("Keine Stadt gewählt."));
        rows(body, cities, lines(4, 3), (c) => row([el("span", "t wide", L.cityTime(now, c.tz)), el("span", "", c.name + " · " + L.cityDayLabel(now, c.tz))]));
      },
    };

    // ---- Musik: drei Tasten (nur am PC); ein Klick darauf oeffnet nicht das grosse Fenster
    const music = {
      title: "Musik & Lautstärke",
      extra: () => "",
      draw(body) {
        if (!app.local) return body.append(empty("Nur am PC."));
        const bar = el("div", "wtransport");
        [["⏮", "previous", "Vorheriger Titel"], ["⏯", "play_pause", "Abspielen / Pause"], ["⏭", "next", "Nächster Titel"]].forEach(([glyph, action, label]) => {
          const b = el("button", "wkey", glyph);
          b.type = "button";
          b.setAttribute("aria-label", label);
          b.title = label;
          b.addEventListener("click", (event) => { event.stopPropagation(); app.media(action); });
          b.addEventListener("keydown", (event) => event.stopPropagation());
          bar.append(b);
        });
        body.append(bar, el("div", "wempty small", "Klick auf das Fenster: Lautstärke"));
      },
    };

    // ---- PC-Status: CPU, RAM, Laufwerk als Balken (nur am PC)
    function meter(label, percent) {
      const wrap = el("div", "wmeter");
      const level = app.W.loadLevel(percent);
      const bar = el("div", "bar " + level);
      const fill = el("i");
      fill.style.width = Math.min(100, Math.max(0, Number(percent) || 0)) + "%";
      bar.append(fill);
      wrap.append(el("span", "muted small", label), bar, el("span", "small", Math.round(Number(percent) || 0) + " %"));
      return wrap;
    }
    const system = {
      title: "PC-Status",
      extra: () => "",
      draw(body) {
        if (!app.local) return body.append(empty("Nur am PC."));
        if (!loaded("perf", body)) return;
        const d = app.extra.perf.data;
        body.append(meter("CPU", d.cpu_percent), meter("RAM", d.ram_percent), meter("Disk", d.disk_percent));
        if (d.battery) body.append(el("div", "wempty small", "Akku " + Math.round(d.battery.percent) + " %" + (d.battery.plugged ? " · lädt" : "")));
      },
    };

    // ---- Erinnerungen: die naechsten drei
    const reminders = {
      title: "Erinnerungen",
      extra: () => "",
      draw(body) {
        if (!loaded("reminders", body)) return;
        const items = app.extra.reminders.data;
        if (!items.length) return body.append(empty("Keine Erinnerungen."));
        const now = new Date();
        rows(body, items, lines(3, 2), (r) => row([el("span", "t long", L.describeDue(r.due, now)), el("span", "", r.text)]));
      },
    };

    return { goals, focus, lists, calendar, weather, notes, news, briefing, worldtime, music, system, reminders };
  }

  const api = { create };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WelcomePanels = api;
})(typeof window !== "undefined" ? window : this);