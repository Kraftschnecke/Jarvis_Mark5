// Willkommensseite: die grossen Fenster (Kalender, Ziele, Listen, Wetter, Fokus & Timer) und die Fenster-Verwaltung.
// Jede Funktion oeffnet ein Fenster ueber app.openWindow(einstellungen, aufbau). Im Aufbau:
//   win.onData(fn) = fn laeuft, wenn neue Daten da sind; win.onTick(fn) = jede Sekunde; win.close() schliesst.
// Daten aus dem Server (Termine, Ziele, ...) werden nur als Text eingesetzt (textContent), nie als HTML.
(function (root) {
  "use strict";

  function create(app) {
    const { el, L, W } = app;

    function button(text, className, onClick) {
      const b = el("button", "btn" + (className ? " " + className : ""), text);
      b.type = "button";
      if (onClick) b.addEventListener("click", onClick);
      return b;
    }

    function field(placeholder, className) {
      const input = el("input", "field" + (className ? " " + className : ""));
      input.type = "text";
      input.placeholder = placeholder;
      return input;
    }

    // Aenderungen nacheinander speichern; erst die Antwort der letzten wird uebernommen,
    // sonst wuerde eine alte Antwort ein gerade hinzugefuegtes Element wieder ausblenden.
    function makeSaver(path, buildBody, note) {
      let chain = Promise.resolve();
      let queued = 0;
      return {
        busy: () => queued > 0,
        save(onDone) {
          queued += 1;
          chain = chain.then(async () => {
            let data = null;
            try {
              data = await app.api("POST", path, buildBody());
              note.textContent = "";
            } catch (error) {
              note.textContent = "Nicht gespeichert: " + error.message;
            }
            queued -= 1;
            if (queued === 0 && data) { app.setData(data); if (onDone) onDone(); }
          });
        },
      };
    }

    // ---- Kalender
    function calendar() {
      app.openWindow({ title: "Kalender", wide: true }, (body, win) => {
        const now = new Date();
        let year = now.getFullYear();
        let month = now.getMonth();
        let selected = L.dayKey(now);

        const wrap = el("div", "cal");
        const left = el("div");
        const right = el("div");
        wrap.append(left, right);
        body.append(wrap);

        const title = el("span");
        const nav = el("span", "wl-tools");
        const prev = button("‹", "", () => { month -= 1; if (month < 0) { month = 11; year -= 1; } drawGrid(); });
        const todayButton = button("Heute", "", () => { year = now.getFullYear(); month = now.getMonth(); selected = L.dayKey(now); drawGrid(); drawList(); });
        const next = button("›", "", () => { month += 1; if (month > 11) { month = 0; year += 1; } drawGrid(); });
        prev.setAttribute("aria-label", "Voriger Monat");
        next.setAttribute("aria-label", "Nächster Monat");
        nav.append(prev, todayButton, next);
        const head = el("div", "cal-month");
        head.append(title, nav);
        const grid = el("div", "cal-grid");
        left.append(head, grid);

        function drawGrid() {
          title.textContent = W.monthTitle(year, month);
          grid.replaceChildren();
          W.weekdayNames().forEach((n) => grid.append(el("span", "wd", n)));
          const byDate = W.eventsByDate(app.data && app.data.events);
          W.calendarWeeks(year, month).forEach((week) => week.forEach((day) => {
            if (day === null) return grid.append(el("span", "cal-blank"));
            const key = W.dateKey(year, month, day);
            const cell = el("button", "cal-day" + (key === L.dayKey(now) ? " today" : "") + (key === selected ? " selected" : "") + (byDate[key] ? " has" : ""), String(day));
            cell.type = "button";
            cell.addEventListener("click", () => { selected = key; drawGrid(); drawList(); });
            grid.append(cell);
          }));
        }

        const form = el("form", "form");
        const titleField = field("Termin …", "grow");
        titleField.maxLength = 100;
        const timeField = el("input", "field");
        timeField.type = "time";
        timeField.setAttribute("aria-label", "Uhrzeit");
        const note = el("div", "note");
        form.append(titleField, timeField, button("+ Termin", "primary"));
        form.lastChild.type = "submit";
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const text = titleField.value.trim();
          if (!text) return;
          try {
            app.setData(await app.api("POST", "/api/widgets/events", { title: text, date: selected, time: timeField.value }));
            titleField.value = "";
            timeField.value = "";
            note.textContent = "";
          } catch (error) {
            note.textContent = error.message;
          }
        });

        const list = el("div");
        right.append(list);
        if (app.local) right.append(form);
        else right.append(el("div", "note", "Termine trägst du am PC ein. Hier siehst du sie nur."));
        right.append(note);

        function section(label, key, first) {
          list.append(el("div", "section-title" + (first ? " first" : ""), label));
          const events = L.eventsOn(app.data && app.data.events, key);
          if (!events.length) return list.append(el("div", "wempty", "Keine Termine."));
          events.forEach((e) => {
            const r = el("div", "cal-times");
            r.append(el("span", "t", e.time || "ganztags"), el("span", "", e.title));
            list.append(r);
          });
        }

        function drawList() {
          list.replaceChildren();
          const todayKey = L.dayKey(now);
          const tomorrowKey = L.dayKey(L.addDays(now, 1));
          section("Heute · " + W.formatDayLong(todayKey), todayKey, true);
          section("Morgen · " + W.formatDayLong(tomorrowKey), tomorrowKey);
          if (selected !== todayKey && selected !== tomorrowKey) section(W.formatDayLong(selected), selected);
        }

        drawGrid();
        drawList();
        win.onData(() => { drawGrid(); drawList(); });
      });
    }

    // ---- Tagesziele
    function goals() {
      app.openWindow({ title: "Tagesziele" }, (body, win) => {
        let items = [];
        const note = el("div", "note");
        const top = el("div", "goal-top");
        const rows = el("div");
        const week = el("div", "week");
        const form = el("form", "form");
        const input = field("Neues Ziel …", "grow");
        input.maxLength = 200;
        const daily = el("input");
        daily.type = "checkbox";
        daily.id = "goal-daily";
        const dailyLabel = el("label", "muted small", " täglich");
        dailyLabel.htmlFor = "goal-daily";
        dailyLabel.prepend(daily);
        const add = button("+ Ziel", "primary");
        add.type = "submit";
        form.append(input, dailyLabel, add);
        body.append(top, rows, form, note, el("div", "section-title", "Diese Woche"), week);

        const saver = makeSaver("/api/widgets/goals", () => ({ items }), note);
        const persist = () => { draw(); saver.save(); };

        function drawWeek() {
          week.replaceChildren();
          const days = (app.data && app.data.week) || [];
          const names = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
          days.forEach((d) => {
            const cell = el("div", d.total && d.done === d.total ? "wfull" : "");
            const bar = el("i");
            bar.style.height = (d.total ? Math.max(4, Math.round((d.done / d.total) * 70)) : 4) + "px";
            cell.title = d.date + ": " + (d.total ? d.done + " von " + d.total + " täglichen Zielen erledigt" : "keine täglichen Ziele");
            cell.append(bar, el("span", "", names[new Date(d.date + "T12:00:00").getDay()]));
            week.append(cell);
          });
        }

        function draw() {
          const p = L.goalProgress(items);
          top.replaceChildren();
          const ring = el("div", "ring-chart");
          ring.style.background = "conic-gradient(var(--accent) 0 " + p.percent * 3.6 + "deg, var(--line) " + p.percent * 3.6 + "deg 360deg)";
          ring.append(el("span", "", p.done + "/" + p.total));
          const text = el("div");
          text.append(el("div", "", p.total ? "Heute " + p.percent + " % geschafft" : "Noch keine Ziele für heute"));
          const streak = L.bestStreak(items);
          if (streak > 0) text.append(el("div", "muted small", "Serie: " + streak + (streak === 1 ? " Tag" : " Tage") + " in Folge"));
          top.append(ring, text);

          rows.replaceChildren();
          items.forEach((goal, index) => {
            const r = el("div", "goal-row" + (goal.done ? " done" : ""));
            const box = el("input");
            box.type = "checkbox";
            box.checked = goal.done;
            box.setAttribute("aria-label", goal.text);
            box.addEventListener("change", () => { items[index].done = box.checked; persist(); });
            const repeat = button("↻", "", () => { items[index].daily = !items[index].daily; persist(); });
            repeat.setAttribute("aria-pressed", String(goal.daily));
            repeat.title = goal.daily ? "Täglich: klicken, um nur für heute zu behalten" : "Nur heute: klicken, damit es täglich wiederkommt";
            if (goal.daily) repeat.classList.add("primary");
            const remove = button("×", "", () => { items.splice(index, 1); persist(); });
            remove.setAttribute("aria-label", "Ziel löschen");
            r.append(box, el("span", "goal-text", goal.text));
            if (goal.daily && goal.streak > 0) r.append(el("span", "goal-streak", goal.streak + (goal.streak === 1 ? " Tag" : " Tage")));
            r.append(repeat, remove);
            rows.append(r);
          });
          drawWeek();
        }

        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const text = input.value.trim();
          if (!text) return;
          items.push({ text, done: false, daily: daily.checked });
          input.value = "";
          persist();
        });

        const fromData = () => { items = JSON.parse(JSON.stringify((app.data && app.data.goals) || [])); draw(); };
        fromData();
        win.onData(() => { if (!saver.busy()) fromData(); });
      });
    }

    // ---- Listen
    function lists() {
      app.openWindow({ title: "Listen" }, (body, win) => {
        let all = [];
        let current = 0;
        const note = el("div", "note");
        const tabs = el("div", "wl-tools");
        const rows = el("div");
        const itemForm = el("form", "form");
        const itemInput = field("Eintrag …", "grow");
        itemInput.maxLength = 100;
        const itemAdd = button("+ Eintrag", "primary");
        itemAdd.type = "submit";
        itemForm.append(itemInput, itemAdd);
        const listForm = el("form", "form");
        const listInput = field("Neue Liste …", "grow");
        listInput.maxLength = 40;
        const listAdd = button("+ Liste", "");
        listAdd.type = "submit";
        listForm.append(listInput, listAdd);
        body.append(tabs, rows, itemForm, el("div", "section-title", "Neue Liste"), listForm, note);

        const saver = makeSaver("/api/widgets/lists", () => ({ lists: all }), note);
        const persist = () => { draw(); saver.save(); };

        function draw() {
          if (current >= all.length) current = Math.max(0, all.length - 1);
          tabs.replaceChildren();
          all.forEach((l, i) => {
            const t = button(l.name, i === current ? "primary" : "", () => { current = i; draw(); });
            tabs.append(t);
          });
          rows.replaceChildren();
          itemForm.hidden = !all.length;
          if (!all.length) return rows.append(el("div", "wempty", "Noch keine Listen. Lege unten die erste an."));
          const list = all[current];
          if (!list.items.length) rows.append(el("div", "wempty", "Die Liste ist leer."));
          list.items.forEach((item, index) => {
            const r = el("div", "goal-row" + (item.done ? " done" : ""));
            const box = el("input");
            box.type = "checkbox";
            box.checked = item.done;
            box.setAttribute("aria-label", item.text);
            box.addEventListener("change", () => { list.items[index].done = box.checked; persist(); });
            const remove = button("×", "", () => { list.items.splice(index, 1); persist(); });
            remove.setAttribute("aria-label", "Eintrag löschen");
            r.append(box, el("span", "goal-text", item.text), remove);
            rows.append(r);
          });
        }

        itemForm.addEventListener("submit", (event) => {
          event.preventDefault();
          const text = itemInput.value.trim();
          if (!text || !all[current]) return;
          all[current].items.push({ text, done: false });
          itemInput.value = "";
          persist();
        });
        listForm.addEventListener("submit", (event) => {
          event.preventDefault();
          const name = listInput.value.trim();
          if (!name) return;
          all.push({ name, items: [] });
          current = all.length - 1;
          listInput.value = "";
          persist();
        });

        const fromData = () => { all = JSON.parse(JSON.stringify((app.data && app.data.lists) || [])); draw(); };
        fromData();
        win.onData(() => { if (!saver.busy()) fromData(); });
      });
    }

    // ---- Wetter: Heimatort oder ein gesuchter Ort, jeweils jetzt und die Woche
    function weather() {
      app.openWindow({ title: "Wetter", wide: true }, (body, win) => {
        let search = null;                          // gesuchter Ort: { name, status: loading|ok|error, data, error } oder null = Heimatort

        const input = field("Ort suchen, zum Beispiel Lissabon", "grow");
        input.setAttribute("aria-label", "Ort suchen");
        const go = button("Suchen", "primary", () => runSearch(input.value));
        const back = button("Zurück zum Heimatort", "", () => { search = null; input.value = ""; draw(); });
        const reload = button("Aktualisieren", "", () => { if (search) runSearch(search.name); else app.loadExtra("forecast", true); });
        const tools = el("div", "form wxsearch");
        tools.append(input, go, back, reload);
        const result = el("div", "wxresult");
        body.append(tools, result);
        input.addEventListener("keydown", (event) => { if (event.key === "Enter") runSearch(input.value); });

        async function runSearch(text) {
          const name = String(text || "").trim();
          if (!name) return;
          const mine = { name, status: "loading" };
          search = mine;
          draw();
          try {
            const data = await app.searchForecast(name);
            if (search === mine) search = { name, status: "ok", data };
          } catch (error) {
            if (search === mine) search = { name, status: "error", error: error.message };
          }
          draw();
        }

        const fact = (label, value) => {
          const box = el("div", "wxfact");
          box.append(el("span", "muted small", label), el("span", "", value));
          return box;
        };

        function drawNow(now) {
          const box = el("div", "wxbignow");
          box.append(app.icon(now.icon, 52));
          const main = el("div");
          main.append(el("div", "wxbigtemp", L.celsius(now.temperature)), el("div", "muted", now.condition || ""));
          box.append(main);
          const facts = el("div", "wxfacts");
          facts.append(fact("gefühlt", L.celsius(now.feels_like)), fact("Luftfeuchte", now.humidity_percent === null || now.humidity_percent === undefined ? "–" : Math.round(now.humidity_percent) + " %"),
            fact("Wind", now.wind_kmh === null || now.wind_kmh === undefined ? "–" : Math.round(now.wind_kmh) + " km/h"));
          box.append(facts);
          return box;
        }

        function drawWeek(days) {
          const list = el("div", "wxweek");
          const clock = new Date();
          days.forEach((d, i) => {
            const day = L.forecastDay(d.date, clock);
            const line = el("div", "wxrow" + (i === 0 ? " today" : ""));
            const name = el("span", "wxname");
            name.append(el("b", "", day.label), el("span", "muted small", day.date));
            const track = el("span", "wxtrack");
            const fill = el("i");
            const span = L.barSpan(days, d);
            fill.style.left = span.left + "%";
            fill.style.width = span.width + "%";
            track.append(fill);
            line.append(name, app.icon(d.icon, 24), el("span", "wxcond muted", d.condition || ""), track,
              el("span", "wxtemps", L.degrees(d.low) + " / " + L.degrees(d.high)), el("span", "wxrain muted", L.rainText(d.rain_chance_percent)));
            list.append(line);
          });
          return list;
        }

        function draw() {
          result.replaceChildren();
          back.hidden = !search;
          let state;
          if (search) state = search.status === "ok" ? { status: "ok", data: search.data } : search;
          else state = app.extra.forecast || { status: "loading" };
          if (state.status === "loading") return result.append(el("div", "wempty", "Lade …"));
          if (state.status === "disabled") return result.append(el("div", "wempty", "In den Einstellungen ausgeschaltet."));
          if (state.status === "error") return result.append(el("div", "wempty", state.error || "Gerade nicht verfügbar."));
          const f = state.data;
          const days = Array.isArray(f && f.days) ? f.days : [];
          const title = el("div", "wxplace");
          title.append(el("b", "", (f && f.place) || ""));
          if (search) title.append(el("span", "muted small", " · nicht dein Heimatort"));
          result.append(title);
          if (!days.length) return result.append(el("div", "wempty", "Keine Vorhersage verfügbar."));
          if (f.now && typeof f.now === "object") result.append(drawNow(f.now));
          result.append(drawWeek(days), el("div", "note", "Daten von Open-Meteo."));
        }

        app.loadExtra("forecast");
        draw();
        win.onData(draw);
      });
    }

    // ---- PC-Lage und Laufwerke: beide lesen /api/pc_lage (app.extra.pclage), nur am PC
    function pcReport(body) {
      if (!app.local) { body.append(el("div", "wempty", "Das siehst du nur am PC.")); return null; }
      return true;
    }
    function pcState() {
      const e = app.extra.pclage;
      if (!e || e.status === "loading") return { text: "Lade …" };
      if (e.status === "disabled") return { text: "In den Einstellungen ausgeschaltet." };
      if (e.status === "error") return { text: e.error || "Gerade nicht verfügbar." };
      return e.data ? { data: e.data } : { text: "Keine Auswertung verfügbar." };
    }

    function pclage() {
      app.openWindow({ title: "PC-Lage" }, (body, win) => {
        if (!pcReport(body)) return;
        const tools = el("div", "form wxsearch");
        tools.append(button("Aktualisieren", "", () => app.loadExtra("pclage", true)));
        const view = el("div");
        body.append(tools, view);

        const section = (title) => el("div", "section-title", title);
        function draw() {
          view.replaceChildren();
          const state = pcState();
          if (!state.data) return view.append(el("div", "wempty", state.text));
          const a = state.data.assessment || {};
          const head = el("div", "wlightrow big");
          head.append(el("span", "wlight " + L.lightLevel(a.level)), el("span", "", a.headline || ""));
          view.append(head, section("Hinweise"));
          const findings = Array.isArray(a.findings) ? a.findings : [];
          if (!findings.length) view.append(el("div", "wempty", "Keine Hinweise, alles ruhig."));
          findings.forEach((f) => {
            const item = el("div", "wfinding");
            item.append(el("span", "wlight " + L.lightLevel(f.level)));
            const text = el("div");
            text.append(el("div", "", f.text || ""), el("div", "muted small", "Tipp: " + (f.tip || "")));
            item.append(text);
            view.append(item);
          });
          view.append(section("Größte Verbraucher"));
          const programs = state.data.programs || {};
          const cols = el("div", "wcols3");
          [["ram", "Arbeitsspeicher"], ["cpu", "Prozessor"], ["disk", "Festplatte"]].forEach(([kind, title]) => {
            const col = el("div");
            col.append(el("div", "muted small", title));
            const list = Array.isArray(programs[kind]) ? programs[kind] : [];
            if (!list.length) col.append(el("div", "wempty small", "nichts Auffälliges"));
            list.forEach((p) => col.append(el("div", "wprog", L.programText(kind, p, W.formatNumber))));
            cols.append(col);
          });
          view.append(cols);
          const names = Array.isArray(state.data.autostart) ? state.data.autostart : [];
          view.append(section("Autostart"));
          view.append(el("div", "muted small pre", names.length ? names.length + " Einträge: " + names.join(", ") : "Keine Einträge gefunden."));
        }
        draw();
        win.onData(draw);
      });
    }

    function drives() {
      app.openWindow({ title: "Laufwerke", wide: true }, (body, win) => {
        if (!pcReport(body)) return;
        const tools = el("div", "form wxsearch");
        tools.append(button("Aktualisieren", "", () => app.loadExtra("pclage", true)));
        const view = el("div", "wdrives");
        body.append(tools, view);

        const meter = (label, percent, text) => {
          const row = el("div", "wmeter big");
          const bar = el("div", "bar " + W.loadLevel(percent));
          const fill = el("i");
          fill.style.width = Math.min(100, Math.max(0, Number(percent) || 0)) + "%";
          bar.append(fill);
          row.append(el("span", "muted", label), bar, el("span", "", text));
          return row;
        };
        function draw() {
          view.replaceChildren();
          const state = pcState();
          if (!state.data) return view.append(el("div", "wempty", state.text));
          const list = Array.isArray(state.data.drives) ? state.data.drives : [];
          if (!list.length) return view.append(el("div", "wempty", "Keine Laufwerke gefunden."));
          list.forEach((d) => {
            const card = el("div", "wdrivecard");
            const head = el("div", "wdrivehead");
            head.append(el("b", "", String(d.letter || "") + ": " + L.mediaLabel(d.media) + (d.system ? " · Windows" : "")),
              el("span", "wbadge " + L.healthLevel(d.health_state), L.healthText(d.health_state)));
            card.append(head);
            if (d.model) card.append(el("div", "muted small", d.model));
            card.append(meter("Belegt", d.used_percent, Math.round(Number(d.used_percent) || 0) + " %"));
            const busy = d.busy_percent;
            card.append(meter("Auslastung", busy, busy === null || busy === undefined ? "–" : Math.round(busy) + " %"));
            const rate = (v) => (v === null || v === undefined ? "–" : W.formatNumber(v, 1) + " MB/s");
            card.append(el("div", "muted small", W.formatGb(d.free_gb) + " frei von " + W.formatGb(d.total_gb) + " · Lesen " + rate(d.read_mb_s) + " · Schreiben " + rate(d.write_mb_s)));
            view.append(card);
          });
        }
        draw();
        win.onData(draw);
      });
    }

    // ---- Fokus und Timer (die Zeiten zaehlen jede Sekunde, die Knoepfe bleiben dabei stehen)
    function focus() {
      app.openWindow({ title: "Fokus & Timer" }, (body, win) => {
        const note = el("div", "note");
        const box = el("div");
        body.append(box, note);
        let clocks = [];

        function draw() {
          box.replaceChildren();
          clocks = [];
          const f = app.focusNow();
          const timers = app.timersNow();
          box.append(el("div", "section-title first", "Fokus"));
          if (f.active) {
            const r = el("div", "goal-row");
            const t = el("span", "t wide", L.formatRemaining(f.remaining));
            clocks.push(() => { t.textContent = L.formatRemaining(app.focusNow().remaining); });
            r.append(t, el("span", "goal-text", (f.label || "Fokus") + " · " + f.phase_name + " · Runde " + f.round + " von " + f.rounds));
            r.append(button("Beenden", "", async () => { try { await app.api("POST", "/api/focus/stop", {}); } catch (e) { note.textContent = e.message; } app.loadTimers(); }));
            box.append(r);
          } else {
            box.append(el("div", "wempty", "Keine Fokus-Sitzung."));
          }
          box.append(el("div", "section-title", "Timer"));
          if (!timers.length) box.append(el("div", "wempty", "Kein Timer läuft."));
          timers.forEach((timerItem) => {
            const r = el("div", "goal-row");
            const t = el("span", "t wide", L.formatRemaining(timerItem.remaining));
            clocks.push(() => {
              const live = app.timersNow().find((x) => x.id === timerItem.id);
              t.textContent = L.formatRemaining(live ? live.remaining : 0);
            });
            r.append(t, el("span", "goal-text", timerItem.name || "Timer"));
            r.append(button("Abbrechen", "", async () => { try { await app.api("POST", "/api/timer/cancel", { id: timerItem.id }); } catch (e) { note.textContent = e.message; } app.loadTimers(); }));
            box.append(r);
          });
          box.append(el("div", "note", "Neue Timer und Fokus-Sitzungen startest du per Sprache oder im Chat."));
        }

        draw();
        win.onData(draw);
        win.onTick(() => clocks.forEach((fn) => fn()));
      });
    }

    // ---- Notizen: die gemeinsame Notiz (wie in der Seitenleiste)
    function notes() {
      app.openWindow({ title: "Notizen" }, (body, win) => {
        const area = el("textarea", "field");
        area.rows = 10;
        area.maxLength = 5000;
        area.setAttribute("aria-label", "Notiz");
        area.style.width = "100%";
        const note = el("div", "note");
        let dirty = false;
        area.value = (app.data && app.data.notes) || "";
        area.addEventListener("input", () => { dirty = true; note.textContent = ""; });
        const tools = el("div", "form");
        tools.append(button("Speichern", "primary", async () => {
          try {
            const data = await app.api("POST", "/api/widgets/notes", { text: area.value });
            dirty = false;
            app.setData(data);
            note.textContent = "Gespeichert.";
          } catch (error) {
            note.textContent = "Nicht gespeichert: " + error.message;
          }
        }));
        body.append(area, tools, note);
        win.onData(() => { if (!dirty) area.value = (app.data && app.data.notes) || ""; });
      });
    }

    // Aus dem Netz oder aus dem Kalender kommende Adressen: nur normale Web-Adressen werden zu Links
    const isWebLink = (url) => typeof url === "string" && /^https?:\/\//i.test(url);

    // Gemeinsamer Aufbau fuer Fenster mit Daten vom Server (News, Briefing, Erinnerungen): Zustand zeigen, sonst zeichnen
    function remoteList(title, key, drawItems, extraNote) {
      app.openWindow({ title }, (body, win) => {
        const box = el("div");
        const note = el("div", "note", extraNote || "");
        const tools = el("div", "form");
        tools.append(button("Aktualisieren", "", () => app.loadExtra(key, true)));
        body.append(box, tools, note);
        const draw = () => {
          box.replaceChildren();
          const e = app.extra[key];
          if (!e || e.status === "loading") return box.append(el("div", "wempty", "Lade …"));
          if (e.status === "disabled") return box.append(el("div", "wempty", "In den Einstellungen ausgeschaltet."));
          if (e.status === "error") return box.append(el("div", "wempty", e.error || "Gerade nicht verfügbar."));
          drawItems(box, e.data);
        };
        draw();
        win.onData(draw);
        app.loadExtra(key);
      });
    }

    function news() {
      remoteList("News", "news", (box, items) => {
        if (!items.length) return box.append(el("div", "wempty", "Keine Schlagzeilen."));
        items.forEach((i) => {
          const r = el("div", "newsitem");
          if (isWebLink(i.url)) {
            const link = el("a", "wlink", i.title);
            link.href = i.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            r.append(link);
          } else {
            r.append(el("div", "", i.title));
          }
          r.append(el("div", "muted small", [i.source, i.published].filter(Boolean).join(" · ")));
          if (i.summary) r.append(el("div", "small", i.summary));
          box.append(r);
        });
      });
    }

    function briefing() {
      remoteList("Briefing", "briefing", (box, text) => {
        box.append(text ? el("div", "temp pre", text) : el("div", "wempty", "Kein Briefing."));
      }, "Das Briefing wird bei jedem Öffnen frisch aus Terminen, Wetter, Zielen und News zusammengestellt.");
    }

    function reminders() {
      remoteList("Erinnerungen", "reminders", (box, items) => {
        if (!items.length) return box.append(el("div", "wempty", "Keine Erinnerungen."));
        const now = new Date();
        items.forEach((r) => {
          const row = el("div", "goal-row");
          row.append(el("span", "t long", L.describeDue(r.due, now)), el("span", "goal-text", r.text));
          if (r.repeat) row.append(el("span", "goal-streak", r.repeat));
          box.append(row);
        });
      }, "Neue Erinnerungen sagst du Jarvis, zum Beispiel: „Erinnere mich morgen um 9 Uhr an den Zahnarzt“.");
    }

    // ---- Weltuhr: Uhrzeiten der gewaehlten Staedte (Zeitzonen kennt der Browser) und die Auswahl
    function worldtime() {
      app.openWindow({ title: "Weltuhr" }, (body, win) => {
        const clocks = el("div");
        const picker = el("div", "wl-tools");
        picker.style.flexWrap = "wrap";
        const note = el("div", "note");
        body.append(clocks, el("div", "section-title", "Städte wählen"), picker, note);

        function drawClocks() {
          const now = new Date();
          clocks.replaceChildren();
          const cities = app.cities.map((id) => L.cityOf(id)).filter(Boolean);
          if (!cities.length) clocks.append(el("div", "wempty", "Keine Stadt gewählt."));
          cities.forEach((c) => {
            const row = el("div", "goal-row");
            row.append(el("span", "t wide", L.cityTime(now, c.tz)), el("span", "goal-text", c.name), el("span", "goal-streak", L.cityDayLabel(now, c.tz)));
            clocks.append(row);
          });
        }

        function drawPicker() {
          picker.replaceChildren();
          L.CITIES.forEach((c) => {
            const on = app.cities.includes(c.id);
            const b = button(c.name, on ? "primary" : "", () => {
              const next = L.toggleCity(app.cities, c.id);
              if (!on && next.length === app.cities.length) { note.textContent = "Höchstens " + L.MAX_CITIES + " Städte."; return; }
              note.textContent = "";
              app.setCities(next);
              drawClocks();
              drawPicker();
            });
            b.setAttribute("aria-pressed", String(on));
            picker.append(b);
          });
        }

        drawClocks();
        drawPicker();
        win.onTick(drawClocks);
      });
    }

    // ---- Musik und Lautstaerke (nur am PC): Windows-Medientasten und Systemlautstaerke
    function music() {
      app.openWindow({ title: "Musik & Lautstärke" }, (body, win) => {
        const note = el("div", "note");
        if (!app.local) {
          body.append(el("div", "wempty", "Musik und Lautstärke steuerst du nur am PC."));
          return;
        }
        const transport = el("div", "wtransport big");
        [["⏮", "previous", "Vorheriger Titel"], ["⏯", "play_pause", "Abspielen / Pause"], ["⏭", "next", "Nächster Titel"]].forEach(([glyph, action, label]) => {
          const b = el("button", "wkey", glyph);
          b.type = "button";
          b.title = label;
          b.setAttribute("aria-label", label);
          b.addEventListener("click", async () => { note.textContent = (await app.media(action)) || ""; });
          transport.append(b);
        });
        const slider = el("input");
        slider.type = "range";
        slider.min = "0";
        slider.max = "100";
        slider.value = "50";
        slider.setAttribute("aria-label", "Lautstärke");
        slider.style.flex = "1";
        const label = el("span", "t", "50 %");
        slider.addEventListener("input", () => { label.textContent = slider.value + " %"; });
        const row = el("div", "form");
        row.append(el("span", "muted small", "Lautstärke"), slider, label, button("Setzen", "primary", async () => { note.textContent = (await app.setVolume(Number(slider.value))) || ""; }));
        const quick = el("div", "wl-tools");
        [0, 25, 50, 75, 100].forEach((v) => quick.append(button(v + " %", "", async () => { slider.value = String(v); label.textContent = v + " %"; note.textContent = (await app.setVolume(v)) || ""; })));
        body.append(el("div", "section-title first", "Wiedergabe"), transport, el("div", "section-title", "Lautstärke"), row, quick, note,
          el("div", "note", "Play und Pause sind bei Windows dieselbe Taste. Jarvis sieht nicht, was gerade spielt, und kennt die aktuelle Lautstärke nicht."));
      });
    }

    // ---- PC-Status: Fakten und Live-Werte (nur am PC)
    function system() {
      app.openWindow({ title: "PC-Status" }, (body, win) => {
        if (!app.local) { body.append(el("div", "wempty", "Den PC-Status siehst du nur am PC.")); return; }
        const live = el("div");
        const facts = el("div");
        body.append(live, el("div", "section-title", "Dieser Rechner"), facts);

        function drawLive() {
          live.replaceChildren();
          const e = app.extra.perf;
          if (!e || e.status !== "ok") return live.append(el("div", "wempty", e && e.error ? e.error : "Lade …"));
          const d = e.data;
          const meter = (name, percent) => {
            const row = el("div", "wmeter big");
            const bar = el("div", "bar " + W.loadLevel(percent));
            const fill = el("i");
            fill.style.width = Math.min(100, Math.max(0, Number(percent) || 0)) + "%";
            bar.append(fill);
            row.append(el("span", "muted", name), bar, el("span", "", Math.round(Number(percent) || 0) + " %"));
            return row;
          };
          live.append(meter("CPU", d.cpu_percent), meter("RAM", d.ram_percent + 0), meter("Laufwerk", d.disk_percent));
          const lines = [];
          lines.push("RAM " + W.formatGb(d.ram_used_gb) + " von " + W.formatGb(d.ram_total_gb));
          if (d.network) lines.push("Netzwerk ↓ " + W.formatRate(d.network.down_kb_s) + " ↑ " + W.formatRate(d.network.up_kb_s));
          if (d.battery) lines.push("Akku " + Math.round(d.battery.percent) + " %" + (d.battery.plugged ? " (lädt)" : ""));
          lines.push("Laufzeit " + W.formatUptime(d.uptime_seconds));
          lines.forEach((t) => live.append(el("div", "muted small", t)));
        }

        drawLive();
        win.onData(drawLive);
        app.api("GET", "/api/system").then((f) => {
          const add = (k, v) => { const r = el("div", "goal-row"); r.append(el("span", "muted", k), el("span", "goal-text", v)); facts.append(r); };
          add("Rechner", f.computer_name || "–");
          add("System", f.os || "–");
          add("Prozessor", (f.cpu_name || "–") + " · " + f.cpu_cores + " Kerne, " + f.cpu_threads + " Threads");
          add("Arbeitsspeicher", W.formatGb(f.ram_total_gb));
          (f.drives || []).forEach((dr) => add("Laufwerk " + dr.name, W.formatGb(dr.free_gb) + " frei von " + W.formatGb(dr.total_gb)));
        }).catch((error) => facts.append(el("div", "wempty", error.message)));
      });
    }

    // ---- Fenster-Verwaltung: Karten an/aus, Vorschau der Anordnung
    function manage() {
      app.openWindow({ title: "Fenster", wide: true }, (body, win) => {
        const legend = el("div", "legend");
        [["dot-g", "Aktiv (Schalter an)"], ["dot-r", "Aus (Schalter aus)"], ["dot-y", "Jarvis kann es, Fenster fehlt noch"], ["dot-y", "┅ Noch keine Jarvis-Fähigkeit"]].forEach(([cls, text]) => {
          const item = el("span");
          item.append(el("b", cls, "●"), " " + text.replace("┅ ", ""));
          legend.append(item);
        });
        legend.append(el("span", "", "Klick auf eine Karte = Fenster an/aus"));
        const tiles = el("div", "tiles");
        const preview = el("div", "preview");
        const note = el("div", "note", "Die Auswahl gilt für dieses Gerät und diesen Browser.");
        body.append(legend, tiles, preview, note);

        function draw() {
          tiles.replaceChildren();
          L.WINDOWS.forEach((def) => {
            const state = L.cardState(def, app.enabled);
            const tile = el("button", "tile " + state);
            tile.type = "button";
            tile.append(el("span", "tg"), el("div", "nm", def.title), el("div", "ds", def.desc));
            const st = el("div", "st");
            st.append(el("b", state === "g" ? "dot-g" : state === "r" ? "dot-r" : "dot-y", "●"), " " + L.CARD_TEXT[state]);
            tile.append(st);
            if (state === "g" || state === "r") {
              tile.setAttribute("aria-pressed", String(state === "g"));
              tile.addEventListener("click", () => { app.setEnabled(L.toggleWindow(app.enabled, def.id)); draw(); });
            } else {
              tile.setAttribute("aria-disabled", "true");
              tile.title = state === "y" ? "Jarvis kann das schon, das Fenster dafür ist noch nicht gebaut." : "Das kann Jarvis noch nicht.";
            }
            tiles.append(tile);
          });
          const cols = L.splitColumns(app.enabled);
          preview.replaceChildren(el("span", "", "Vorschau:"));
          const mini = el("div", "mini");
          const colBox = (ids) => { const c = el("div", "mc"); ids.forEach(() => c.append(el("i"))); return c; };
          mini.append(colBox(cols.left), el("div", "mo"), colBox(cols.right));
          preview.append(mini);
        }
        draw();
      });
    }

    return { calendar, goals, lists, weather, focus, notes, news, briefing, worldtime, music, system, pclage, drives, reminders, manage };
  }

  const api = { create };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WelcomeDialogs = api;
})(typeof window !== "undefined" ? window : this);