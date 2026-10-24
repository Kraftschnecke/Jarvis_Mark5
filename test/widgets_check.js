// Prueft web/widgets.js ohne Browser (wird von test_widgets_ui.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const W = require(path.join(__dirname, "..", "web", "widgets.js"));

assert.strictEqual(W.formatClock(new Date(2026, 9, 21, 7, 5, 9)), "07:05:09");
assert.strictEqual(W.formatClock(new Date(2026, 9, 21, 23, 59, 0)), "23:59:00");
assert.strictEqual(W.formatDateLong(new Date(2026, 9, 21)), "Mittwoch, 21. Oktober 2026");
assert.strictEqual(W.monthTitle(2026, 9), "Oktober 2026");
assert.strictEqual(W.monthTitle(2026, 11), "Dezember 2026");
assert.deepStrictEqual(W.weekdayNames(), ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]);

// Kalender: Oktober 2026 beginnt an einem Donnerstag, hat 31 Tage
let weeks = W.calendarWeeks(2026, 9);
assert.deepStrictEqual(weeks[0], [null, null, null, 1, 2, 3, 4]);
assert.deepStrictEqual(weeks[weeks.length - 1], [26, 27, 28, 29, 30, 31, null]);
assert.strictEqual(weeks.length, 5);
weeks.forEach((w) => assert.strictEqual(w.length, 7));
// Februar 2027: beginnt Montag, 28 Tage = genau 4 Wochen
weeks = W.calendarWeeks(2027, 1);
assert.strictEqual(weeks.length, 4);
assert.deepStrictEqual(weeks[0], [1, 2, 3, 4, 5, 6, 7]);
// Schaltjahr Februar 2028 hat 29 Tage; Sonntag als erster Tag landet in der letzten Spalte
weeks = W.calendarWeeks(2028, 1);
assert.strictEqual(weeks.flat().filter((d) => d !== null).length, 29);
weeks = W.calendarWeeks(2026, 7);            // August 2026 beginnt an einem Samstag
assert.deepStrictEqual(weeks[0], [null, null, null, null, null, 1, 2]);
// Jeder Monat: alle Tage genau einmal, in Reihenfolge
for (let year = 2024; year <= 2030; year++) {
  for (let month = 0; month < 12; month++) {
    const flat = W.calendarWeeks(year, month).flat().filter((d) => d !== null);
    assert.deepStrictEqual(flat, Array.from({ length: new Date(year, month + 1, 0).getDate() }, (_, i) => i + 1));
  }
}

// Spiele
const side = (abbrev, name, score) => ({ abbrev, name, score: score === undefined ? null : score });
const base = { start: "2026-10-22T02:00:00Z", state: "future" };
let g = W.describeGame(Object.assign({}, base, { home: side("EDM", "Oilers"), away: side("CGY", "Flames"), team_is_home: true }), { timeZone: "UTC" });
assert.deepStrictEqual(g, { teamName: "Oilers", opponent: "Flames", home: true, score: null, outcome: null, when: g.when, live: false });
assert(/Do/.test(g.when) && /02:00/.test(g.when), g.when);
g = W.describeGame(Object.assign({}, base, { state: "final", home: side("CGY", "Flames", 2), away: side("EDM", "Oilers", 4), team_is_home: false }), { timeZone: "UTC" });
assert.strictEqual(g.score, "2 : 4");
assert.strictEqual(g.outcome, "win");
assert.strictEqual(g.home, false);
g = W.describeGame(Object.assign({}, base, { state: "final", home: side("EDM", "Oilers", 1), away: side("VAN", "Canucks", 3), team_is_home: true }), { timeZone: "UTC" });
assert.strictEqual(g.outcome, "loss");
g = W.describeGame(Object.assign({}, base, { state: "live", home: side("EDM", "Oilers", 1), away: side("VAN", "Canucks", 1), team_is_home: true }), { timeZone: "UTC" });
assert.strictEqual(g.live, true);
assert.strictEqual(g.outcome, null);
assert.strictEqual(g.score, "1 : 1");
// Ohne Punktestand oder mit kaputtem Datum: keine Abstuerze
g = W.describeGame({ start: "kaputt", state: "final", home: side("EDM", "Oilers"), away: side("VAN", "Canucks"), team_is_home: true });
assert.strictEqual(g.score, null);
assert.strictEqual(g.when, "");
assert.strictEqual(g.outcome, null);

// Termine
assert.strictEqual(W.dateKey(2026, 9, 3), "2026-10-03");
assert.strictEqual(W.dateKey(2026, 11, 31), "2026-12-31");
assert.strictEqual(W.formatDayLong("2026-10-23"), "Freitag, 23. Oktober");
assert.deepStrictEqual(W.eventsByDate([{ date: "2026-10-23", title: "a" }, { date: "2026-10-23", title: "b" }, { date: "2026-10-24", title: "c" }, null, { title: "ohne" }]),
  { "2026-10-23": [{ date: "2026-10-23", title: "a" }, { date: "2026-10-23", title: "b" }], "2026-10-24": [{ date: "2026-10-24", title: "c" }] });
assert.deepStrictEqual(W.eventsByDate(undefined), {});
// Wecker nach Tag: je Tag nach Uhrzeit, ein taeglicher Wecker steht an jedem seiner Tage
const alarmA = { id: "a", label: "Wecker", time: "06:30", dates: ["2026-10-26", "2026-10-27"] };
const alarmB = { id: "b", label: "Zug", time: "05:15", dates: ["2026-10-26"] };
assert.deepStrictEqual(W.alarmsByDate([alarmA, alarmB]), { "2026-10-26": [alarmB, alarmA], "2026-10-27": [alarmA] });
assert.deepStrictEqual(W.alarmsByDate([null, {}, { dates: "x" }, { time: "1", label: "x", dates: [5, null] }]), {});
assert.deepStrictEqual(W.alarmsByDate(undefined), {});
assert.deepStrictEqual(W.alarmsByDate("x"), {});
assert.deepStrictEqual(W.eventsByDate("x"), {});

// Leistungs-Widget: Formate und Farbstufen
assert.strictEqual(W.formatGb(13.24), "13,2 GB");
assert.strictEqual(W.formatGb(null), "–");
assert.strictEqual(W.formatGb(undefined), "–");
assert.strictEqual(W.formatGb("x"), "–");
assert.strictEqual(W.formatRate(0), "0 KB/s");
assert.strictEqual(W.formatRate(512.4), "512 KB/s");
assert.strictEqual(W.formatRate(1536), "1,5 MB/s");
assert.strictEqual(W.formatRate(-1), "–");
assert.strictEqual(W.formatRate("abc"), "–");
assert.strictEqual(W.formatUptime(59), "0 Min");
assert.strictEqual(W.formatUptime(300), "5 Min");
assert.strictEqual(W.formatUptime(3 * 3600 + 12 * 60), "3 Std 12 Min");
assert.strictEqual(W.formatUptime(86400 + 4 * 3600), "1 Tag 4 Std");
assert.strictEqual(W.formatUptime(2 * 86400 + 4 * 3600 + 59), "2 Tage 4 Std");
assert.strictEqual(W.formatUptime(null), "–");
assert.strictEqual(W.formatUptime(-5), "–");
assert.strictEqual(W.loadLevel(0), "ok");
assert.strictEqual(W.loadLevel(69.9), "ok");
assert.strictEqual(W.loadLevel(70), "warn");
assert.strictEqual(W.loadLevel(89.9), "warn");
assert.strictEqual(W.loadLevel(90), "high");
assert.strictEqual(W.loadLevel(100), "high");
assert.strictEqual(W.loadLevel(undefined), "ok");
assert.strictEqual(W.clampPercent(150), 100);
assert.strictEqual(W.clampPercent(-3), 0);
assert.strictEqual(W.clampPercent("x"), 0);
assert.strictEqual(W.clampPercent(42.5), 42.5);

console.log("widgets.js OK");
