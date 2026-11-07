"""Aktionsprotokoll (Mark 4, Step 4.3): was hat Jarvis wann getan, mit welchem Ergebnis?

Jede Aufgabe, die Jarvis ausfuehrt, ablehnt oder die du abgelehnt hast, wird
als eine Zeile in der Tabelle action_log festgehalten und im Web unter
Settings > Activity angezeigt.

Eintrag (eine Zeile):
    created_at  Zeitpunkt
    task_type   z.B. START_PROGRAM
    goal        Beschreibung der Aufgabe ("Ein Programm ... oeffnen")
    details     Parameter, z.B. der Programmname oder Dateipfad
    risk        safe / confirm / forbidden (aus risk.py)
    decision    auto       Stufe safe, lief ohne Rueckfrage
                confirmed  du hast die Rueckfrage mit Ja beantwortet
                declined   du hast Nein / Abbrechen gewaehlt (nichts ausgefuehrt)
                refused    Stufe forbidden: Jarvis hat nein gesagt
                blocked    der Executor hat die Ausfuehrung verweigert
    status      COMPLETED / FAILED / BLOCKED / DECLINED
    summary     kurzes Ergebnis oder die Fehlermeldung (hoechstens 200 Zeichen)

Regeln:
- Das Protokoll ist nur zum Ansehen. Es gibt in der Oberflaeche absichtlich
  keine Loeschfunktion: Wer etwas Unerwartetes ausgeloest hat, soll es
  nicht ueber dieselbe Oberflaeche verwischen koennen.
- Inhalte von Tool-Ergebnissen (z.B. Webtreffer) werden NICHT gespeichert,
  nur eine Kurzfassung ("10 Eintraege"). Das haelt das Protokoll klein und
  haelt fremden Text daraus heraus.
- Ein Fehler beim Protokollieren darf nie eine Aktion verhindern oder
  verfaelschen: record() faengt alles ab und meldet es nur im Terminal.
- Aus Sicherheitsgruenden schreibt das Protokoll erst, wenn enable() aufgerufen
  wurde (macht Jarvis beim Start). Tests schreiben so nie in die echte Datenbank.
- Es werden hoechstens KEEP_ROWS Zeilen aufgehoben, aeltere fallen weg.
"""

import re
import threading

import risk

KEEP_ROWS = 2000
MAX_TEXT = 200
MAX_DETAILS = 5

_enabled = False
_table_ready = False
_lock = threading.Lock()

_CONTROL = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩﻿]")


def enable():
    global _enabled
    _enabled = True


def disable():
    global _enabled, _table_ready
    _enabled = False
    _table_ready = False


def _clean(value, limit=MAX_TEXT):
    text = _CONTROL.sub(" ", str(value)).strip()

    if len(text) > limit:
        text = text[: limit - 1] + "…"

    return text


def summarize(task):
    """Kurzfassung des Ergebnisses. Speichert nie ganze Tool-Daten."""
    if task.error:
        return _clean(task.error)

    results = task.result if isinstance(task.result, list) else []

    if not results:
        return ""

    last = results[-1]
    data = getattr(last, "data", last)

    if isinstance(data, (list, tuple)):
        return f"{len(data)} Einträge"

    if isinstance(data, dict):
        return "Daten erhalten"

    if isinstance(data, bool) or data is None:
        return ""

    return _clean(data)


def _ensure_table(connection):
    global _table_ready

    if _table_ready:
        return

    connection.cursor().execute(
        """
        CREATE TABLE IF NOT EXISTS action_log (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            task_type TEXT NOT NULL,
            goal TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            risk TEXT NOT NULL,
            decision TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT ''
        )
        """
    )
    _table_ready = True


def _insert(row):
    import db   # erst hier: Wer nur Tasks ausfuehrt, braucht die Datenbank nicht

    with _lock, db.connect() as connection:
        _ensure_table(connection)
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO action_log
                (task_type, goal, details, risk, decision, status, summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            row,
        )
        cursor.execute(
            "DELETE FROM action_log WHERE id <= "
            "(SELECT COALESCE(MAX(id), 0) FROM action_log) - %s",
            (KEEP_ROWS,),
        )


def record_remote(device_name, text, outcome):
    """Eine Nachricht vom Handy (Remote R3): wer, was, und ob sie beantwortet oder abgelehnt wurde. Wirft nie einen Fehler."""
    if not _enabled:
        return

    try:
        _insert((
            "REMOTE",
            _clean("Nachricht vom Handy: " + str(device_name), 120),
            _clean(text),
            "safe",
            "remote",
            _clean(outcome, 60),
            "",
        ))
    except Exception as error:
        print(f"[aktionslog] Konnte nicht protokollieren: {error}")


def record(task, decision, status=None):
    """Haelt eine Aufgabe im Protokoll fest. Wirft nie einen Fehler."""
    if not _enabled:
        return

    try:
        goal, details = risk.describe_task(task)
        row = (
            _clean(task.task_type, 60),
            _clean(goal),
            "\n".join(_clean(d) for d in details[:MAX_DETAILS]),
            risk.task_risk(task),
            decision,
            status or task.status,
            summarize(task),
        )

        _insert(row)
    except Exception as error:
        print(f"[aktionslog] Konnte nicht protokollieren: {error}")


def recent(limit=100):
    """Die neuesten Eintraege, neueste zuerst."""
    import db

    limit = max(1, min(int(limit), 500))

    with _lock, db.connect() as connection:
        _ensure_table(connection)
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, created_at, task_type, goal, details, risk, decision, status, summary
            FROM action_log
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "time": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "task_type": row[2],
            "goal": row[3],
            "details": [d for d in (row[4] or "").split("\n") if d],
            "risk": row[5],
            "decision": row[6],
            "status": row[7],
            "summary": row[8] or "",
        }
        for row in rows
    ]
