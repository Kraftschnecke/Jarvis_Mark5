"""Die feste Liste der Auftraege an ein Geraet (S6, DESIGN_GERAET.md). Server UND Agent benutzen genau diese Datei.

Es gibt keine Befehlszeile: Ein Auftrag ist ein Name aus COMMANDS plus Parameter, die hier geprueft werden. Alles andere ist ein Fehler.
Auch das Ergebnis, das ein Geraet zurueckschickt, wird hier geprueft (Typen, Laengen, Groesse): Es sind fuer den Server unvertraute Daten.
"""
import json

AGENT_VERSION = 1
MAX_RESULT_BYTES = 64 * 1024
MAX_TEXT = 200


class CommandError(ValueError):
    """Unbekannter Auftrag, falsche Parameter oder ein Ergebnis, das nicht zur Liste passt."""


def _text(value, limit=MAX_TEXT):
    if not isinstance(value, str) or len(value) > limit:
        raise CommandError("Ergebnis passt nicht.")
    return value


def _no_args(args):
    if args not in (None, {}):
        raise CommandError("Dieser Auftrag hat keine Parameter.")
    return {}


def _ping_result(data):
    if not isinstance(data, dict) or set(data) != {"name", "time", "version"}:
        raise CommandError("Ergebnis passt nicht.")
    version = data["version"]
    if not isinstance(version, int) or isinstance(version, bool) or not 0 < version < 1000:
        raise CommandError("Ergebnis passt nicht.")
    return {"name": _text(data["name"], 40), "time": _text(data["time"], 40), "version": version}


# Auftrag -> (Parameter pruefen, Ergebnis pruefen). Neue Auftraege kommen als neue Zeilen, auf beiden Seiten.
COMMANDS = {
    "ping": (_no_args, _ping_result),
}


def check_args(command, args):
    """Die geprueften Parameter eines Auftrags (Kopie), sonst CommandError."""
    if not isinstance(command, str) or command not in COMMANDS:
        raise CommandError("Unbekannter Auftrag.")
    return COMMANDS[command][0](args)


def check_result(command, data):
    """Das gepruefte Ergebnis (neue Kopie), sonst CommandError. Zu grosse Antworten werden abgelehnt, bevor sie weiterverarbeitet werden."""
    if not isinstance(command, str) or command not in COMMANDS:
        raise CommandError("Unbekannter Auftrag.")
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise CommandError("Ergebnis passt nicht.")
    if size > MAX_RESULT_BYTES:
        raise CommandError("Ergebnis zu gross.")
    return COMMANDS[command][1](data)
