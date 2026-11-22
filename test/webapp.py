"""Hilfe fuer die Tests: der Browser-Code der App besteht aus mehreren Dateien (siehe DESIGN_ROLLEN.md).

app_text() gibt sie in Ladereihenfolge als einen Text zurueck, damit die bisherigen Pruefungen ("steht im Code") weiter gelten.
"""
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
APP_FILES = ("app_base.js", "app_state.js", "app_owner.js", "app_start.js")
GUEST_APP_FILES = ("app_base.js", "app_state.js", "app_start.js")      # ohne app_owner.js: das laden Gaeste nie


def app_text(files=APP_FILES):
    return "\n".join((WEB / name).read_text(encoding="utf-8") for name in files)
