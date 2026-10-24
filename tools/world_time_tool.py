"""Weltuhr (Mark 5, Step 2.4): "Wie spaet ist es in Edmonton?"

Die Uhrzeit rechnet Python mit der Zeitzonen-Datenbank (zoneinfo, inkl. Sommerzeit). Welche Zeitzone zu einem
Ort gehoert, sagt entweder du selbst ("Europe/Stockholm", "UTC") oder die Ortssuche von Open-Meteo, die schon
fuers Wetter benutzt wird (der Ortsname geht dorthin, sonst nichts). Unter Windows braucht zoneinfo das Paket
``tzdata`` (steht in requirements.txt).
"""

import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from net_fetch import NetError
from tools import weather_tool
from tools.tool_result import ToolResult
from untrusted import clean_text

_ZONE_ID = re.compile(r"[A-Za-z][A-Za-z_]*(/[A-Za-z0-9_+\-]+){1,2}|UTC|GMT|Etc/GMT[+-]\d{1,2}")
_HOME_WORDS = ("", "heimat", "home", "hier", "lokal", "local", "bei mir")


def load_zone(key):
    """ZoneInfo oder None (unbekannt / Datenbank fehlt)."""
    if not isinstance(key, str) or not _ZONE_ID.fullmatch(key):
        return None
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def format_offset(minutes):
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def describe_difference(minutes):
    if minutes == 0:
        return "Dort ist es genauso spät wie bei dir."
    hours, rest = divmod(abs(minutes), 60)
    amount = f"{hours} Stunde{'n' if hours != 1 else ''}" if hours else ""
    if rest:
        amount += (" und " if amount else "") + f"{rest} Minuten"
    return f"Dort ist es {amount} {'später' if minutes > 0 else 'früher'} als bei dir."


class WorldTimeService:
    def __init__(self, locate=None, clock=lambda: datetime.now(timezone.utc), local_zone=None):
        self.locate = locate or (lambda text: weather_tool.default_service().locate(text))
        self.clock = clock
        self.local_zone = local_zone        # None: Zeitzone des Rechners

    def _zone_for(self, place):
        """(ZoneInfo, Anzeigename, Fehlertext)."""
        text = clean_text(place, 100).strip() if isinstance(place, str) else ""
        if text.casefold() in _HOME_WORDS:
            return None, None, "Für welchen Ort soll ich die Uhrzeit nennen?"
        zone = load_zone(text)
        if zone is not None:
            return zone, text, None
        try:
            found = self.locate(text)
        except NetError as error:
            return None, None, f"Die Ortssuche ist gerade nicht erreichbar: {error}"
        if not found:
            return None, None, f"Den Ort „{text}“ habe ich nicht gefunden."
        zone = load_zone(found.get("timezone"))
        if zone is None:
            return None, None, (f"Für „{found['label']}“ kenne ich keine Zeitzone. "
                                "Falls die Zeitzonen-Datenbank fehlt: pip install tzdata.")
        return zone, found["label"], None

    def get_world_time(self, place):
        zone, label, problem = self._zone_for(place)
        if problem:
            return ToolResult(success=False, error=problem)
        now = self.clock()
        there = now.astimezone(zone)
        here = now.astimezone(self.local_zone) if self.local_zone else now.astimezone()
        difference = int((there.utcoffset() - here.utcoffset()).total_seconds() // 60)
        return ToolResult(success=True, data={
            "place": label,
            "timezone": zone.key,
            "time": there.strftime("%H:%M"),
            "date": weather_tool.describe_day(there.date()),
            "utc_offset": format_offset(int(there.utcoffset().total_seconds() // 60)),
            "your_time": here.strftime("%H:%M"),
            "difference": describe_difference(difference),
            "difference_minutes": difference,
        })


_default_service = None


def default_service():
    global _default_service
    if _default_service is None:
        _default_service = WorldTimeService()
    return _default_service


def set_default_service(service):
    global _default_service
    _default_service = service


def get_world_time(place):
    return default_service().get_world_time(place)
