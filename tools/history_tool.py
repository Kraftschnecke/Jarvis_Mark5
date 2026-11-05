"""Fruehere Gespraeche durchsuchen (Mark 5, Step 2.27). NUR LESEN.

Zwei Arten von Fragen:
  - mit Suchwoertern ("Was hatten wir zu Python-Hausaufgaben besprochen?"): die Nachrichten, in denen ALLE Woerter vorkommen,
    neueste zuerst, mit einem kurzen Ausschnitt um die Fundstelle;
  - ohne Suchwoerter, aber mit Zeitraum und/oder Projekt ("Worueber haben wir letzte Woche beim Projekt X gesprochen?"):
    eine Uebersicht der Gespraeche in dem Zeitraum mit den ersten Nutzernachrichten.
Gelesen wird nur die eigene Datenbank (Tabellen projects, conversations, messages), nichts wird geaendert. Die Suchwoerter
gehen nie in den SQL-Text, sondern nur als Parameter (LIKE-Zeichen werden maskiert). Der Text frueherer Nachrichten kann alte
Ergebnisse aus dem Internet enthalten und ist unvertraut: gesaeubert, gekuerzt, nur als Daten an das Sprachmodell.
Nachrichten der letzten Minute werden uebersprungen, damit die gerade gestellte Frage nicht sich selbst findet.
"""

import re
from datetime import datetime

from tools.tool_result import ToolResult
from untrusted import clean_text

MAX_HITS = 8
MAX_WORDS = 6
MIN_WORD = 2
MAX_QUERY = 200
MAX_PROJECT = 80
MAX_DAYS = 3650
SNIPPET = 220
OVERVIEW_FIRST_MESSAGES = 3
RECENT_GUARD_SECONDS = 60
FETCH_LIMIT = 40


def escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_words(query):
    """Die Suchwoerter (hoechstens MAX_WORDS, mindestens MIN_WORD Zeichen). Kein Text -> []."""
    if not isinstance(query, str):
        return []
    text = clean_text(query, MAX_QUERY + 1)
    words = []
    for word in re.split(r"\s+", text.strip()):
        word = word.strip("\"'„“”‚‘’.,;:!?()[]{}")
        if len(word) >= MIN_WORD and word.casefold() not in (w.casefold() for w in words):
            words.append(word)
    return words[:MAX_WORDS]


def clamp_days(value):
    """Zeitraum in Tagen (0 = ohne Begrenzung)."""
    if isinstance(value, bool):
        return 0
    try:
        days = int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_DAYS, days))


def clean_project(value):
    return clean_text(value, MAX_PROJECT).strip() if isinstance(value, str) else ""


class DbStore:
    """Liest aus der Datenbank. Alle Werte gehen als Parameter, nie in den SQL-Text."""

    def __init__(self, connect=None):
        self._connect = connect

    def _conn(self):
        if self._connect is not None:
            return self._connect()
        import db
        return db.connect()

    @staticmethod
    def _filters(project, days, alias_time):
        sql, params = "", []
        if project:
            sql += " AND p.name ILIKE %s"
            params.append(f"%{escape_like(project)}%")
        if days:
            sql += f" AND {alias_time} >= NOW() - make_interval(days => %s)"
            params.append(days)
        return sql, params

    def search_messages(self, words, project, days, limit=FETCH_LIMIT):
        where = "".join(" AND m.content ILIKE %s" for _ in words)
        params = [f"%{escape_like(word)}%" for word in words]
        extra, extra_params = self._filters(project, days, "m.timestamp")
        sql = ("SELECT m.role, m.content, m.timestamp, c.title, p.name "
               "FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN projects p ON p.id = c.project_id "
               f"WHERE m.timestamp < NOW() - make_interval(secs => %s){where}{extra} "
               "ORDER BY m.timestamp DESC, m.id DESC LIMIT %s")
        with self._conn() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, [RECENT_GUARD_SECONDS, *params, *extra_params, limit])
            return list(cursor.fetchall())

    def list_conversations(self, project, days, limit=MAX_HITS):
        extra, extra_params = self._filters(project, days, "c.last_active")
        sql = ("SELECT c.id, p.name, c.title, c.started_at, c.last_active, "
               "(SELECT COUNT(*) FROM messages mm WHERE mm.conversation_id = c.id) "
               "FROM conversations c JOIN projects p ON p.id = c.project_id "
               f"WHERE c.last_active < NOW() - make_interval(secs => %s){extra} "
               "ORDER BY c.last_active DESC, c.id DESC LIMIT %s")
        with self._conn() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, [RECENT_GUARD_SECONDS, *extra_params, limit])
            return list(cursor.fetchall())

    def first_user_messages(self, conversation_id, limit=OVERVIEW_FIRST_MESSAGES):
        with self._conn() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' "
                           "ORDER BY timestamp ASC, id ASC LIMIT %s", [conversation_id, limit])
            return [row[0] for row in cursor.fetchall()]


_store = None


def default_store():
    global _store
    if _store is None:
        _store = DbStore()
    return _store


def set_default_store(store):
    """Nur fuer Tests."""
    global _store
    _store = store


def _day(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return clean_text(str(value), 20) if value is not None else ""


def snippet(text, words, limit=SNIPPET):
    """Ein Ausschnitt um die erste Fundstelle (einzeilig, gesaeubert)."""
    flat = " ".join(clean_text(str(text), 20000).split())
    if len(flat) <= limit:
        return flat
    positions = [flat.casefold().find(w.casefold()) for w in words]
    positions = [p for p in positions if p >= 0]
    start = max(0, (min(positions) if positions else 0) - limit // 3)
    piece = flat[start:start + limit]
    return ("... " if start else "") + piece.strip() + (" ..." if start + limit < len(flat) else "")


def search_history(query="", project="", days=0, store=None):
    store = store or default_store()
    words = parse_words(query)
    project = clean_project(project)
    limit_days = clamp_days(days)

    if isinstance(query, str) and query.strip() and not words:
        return ToolResult(success=False, error="Mit so kurzen Suchwörtern finde ich nichts. Nenne ein ganzes Wort.")
    if not words and not project and not limit_days:
        return ToolResult(success=False, error="Wonach soll ich suchen, oder für welchen Zeitraum oder welches Projekt?")

    try:
        if words:
            rows = store.search_messages(words, project, limit_days)
            hits = []
            for role, content, when, title, project_name in rows[:MAX_HITS]:
                hits.append({"project": clean_text(str(project_name), 80), "conversation": clean_text(str(title or ""), 80),
                             "date": _day(when), "who": "Nutzer" if role == "user" else "Jarvis", "text": snippet(content, words)})
            data = {"mode": "search", "words": words, "hits": hits}
            if len(rows) > MAX_HITS:
                data["more"] = True
            if not hits:
                data["info"] = "In den früheren Gesprächen steht dazu nichts."
        else:
            conversations = store.list_conversations(project, limit_days)
            items = []
            for conv_id, project_name, title, started, last_active, count in conversations[:MAX_HITS]:
                first = [snippet(text, [], 140) for text in store.first_user_messages(conv_id)]
                items.append({"project": clean_text(str(project_name), 80), "conversation": clean_text(str(title or ""), 80),
                              "date": _day(last_active), "messages": int(count or 0), "first_questions": first})
            data = {"mode": "overview", "conversations": items}
            if not items:
                data["info"] = "Aus diesem Zeitraum gibt es keine Gespräche."
        if project:
            data["project_filter"] = project
        if limit_days:
            data["days"] = limit_days
    except Exception as error:
        return ToolResult(success=False, error=f"Die früheren Gespräche ließen sich nicht lesen ({type(error).__name__}).")

    return ToolResult(success=True, data=data)
