"""Einkaufs- und Packlisten (Mark 5, Step 2.30): per Chat auf eine Liste setzen, ansehen, abhaken oder streichen.

Die Listen liegen in widgets.json (dieselbe Datei wie Notizen und Ziele) und sind im Widget "Lists" der Seitenleiste
sichtbar und dort von Hand aenderbar. Alles bleibt lokal; es gibt kein Netz und keine Konten. Mehrere Eintraege kommen als
ein Text mit Kommas (Milch, Eier, Brot).
"""

import re

import widgets
from tools.tool_result import ToolResult

MAX_ADD = 20
_SPLIT = re.compile(r"[,;\n]+")


def split_items(text):
    """"Milch, Eier; Brot" -> ["Milch", "Eier", "Brot"] (leere Teile fallen weg, hoechstens MAX_ADD)."""
    if isinstance(text, list):
        parts = [str(p) for p in text]
    elif isinstance(text, str):
        parts = _SPLIT.split(text)
    else:
        return []
    return [" ".join(p.split()) for p in parts if " ".join(p.split())][:MAX_ADD]


def _store(store):
    return store or widgets.default_store()


def add_to_list(list_name="", items="", store=None):
    try:
        data = _store(store).add_list_items(list_name, split_items(items))
    except ValueError as error:
        return ToolResult(success=False, error=str(error))
    except OSError as error:
        return ToolResult(success=False, error=f"Die Liste ließ sich nicht speichern ({type(error).__name__}).")
    return ToolResult(success=True, data=data)


def show_list(list_name="", store=None):
    try:
        lists = _store(store).get_lists(list_name)
    except ValueError as error:
        return ToolResult(success=False, error=str(error))
    if not lists:
        return ToolResult(success=True, data={"lists": [], "info": "Es gibt noch keine Liste."})
    return ToolResult(success=True, data={"lists": [
        {"name": l["name"], "open": [i["text"] for i in l["items"] if not i["done"]],
         "done": [i["text"] for i in l["items"] if i["done"]]} for l in lists]})


def remove_from_list(list_name="", item="", mode="done", store=None):
    mode = "remove" if str(mode or "").strip().lower() in ("remove", "streichen", "delete", "entfernen", "loeschen", "löschen") else "done"
    try:
        data = _store(store).change_list_item(list_name, item, mode)
    except ValueError as error:
        return ToolResult(success=False, error=str(error))
    except OSError as error:
        return ToolResult(success=False, error=f"Die Liste ließ sich nicht speichern ({type(error).__name__}).")
    return ToolResult(success=True, data=data)
