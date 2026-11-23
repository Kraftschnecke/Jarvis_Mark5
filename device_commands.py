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


# --- Muster fuer Ergebnisse -----------------------------------------------------------------------------
# Jedes Muster ist eine Funktion: Wert -> gepruefte Kopie, sonst CommandError. Woerterbuecher behalten nur die genannten Schluessel
# (Fremdes wird verworfen, nicht weitergegeben), alle genannten muessen da sein. Zahlen muessen endlich sein, Texte sind begrenzt.
BAD = "Ergebnis passt nicht."


def STR(limit=MAX_TEXT):
    def check(value):
        if not isinstance(value, str) or len(value) > limit:
            raise CommandError(BAD)
        return value
    return check


def _number(value, whole):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value) > 10 ** 12:
        raise CommandError(BAD)
    if whole:
        if isinstance(value, float) and not value.is_integer():
            raise CommandError(BAD)
        return int(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise CommandError(BAD)
    return value


def INT(value):
    return _number(value, True)


def NUM(value):
    return _number(value, False)


def BOOL(value):
    if not isinstance(value, bool):
        raise CommandError(BAD)
    return value


def OPT(inner):
    return lambda value: None if value is None else inner(value)


def LIST(inner, limit):
    def check(value):
        if not isinstance(value, list) or len(value) > limit:
            raise CommandError(BAD)
        return [inner(item) for item in value]
    return check


def DICT(**fields):
    def check(value):
        if not isinstance(value, dict) or any(key not in value for key in fields):
            raise CommandError(BAD)
        return {key: inner(value[key]) for key, inner in fields.items()}
    return check


NOW = DICT(cpu_percent=NUM, ram_percent=NUM, ram_used_gb=NUM, ram_total_gb=NUM, disk_percent=NUM, disk_used_gb=NUM, disk_total_gb=NUM,
           battery=OPT(DICT(percent=NUM, plugged=BOOL)), network=DICT(down_kb_s=NUM, up_kb_s=NUM), uptime_seconds=OPT(INT))
DRIVE = DICT(name=STR(260), total_gb=NUM, free_gb=NUM, used_percent=NUM)
DRIVE_FULL = DICT(name=STR(260), total_gb=NUM, free_gb=NUM, used_percent=NUM, letter=STR(1), media=STR(20), health=STR(20),
                  health_state=STR(20), model=STR(60), system=BOOL, busy_percent=OPT(NUM), read_mb_s=OPT(NUM), write_mb_s=OPT(NUM))
FACTS = DICT(os=STR(80), os_version=STR(120), architecture=STR(40), cpu_name=STR(120), cpu_cores=OPT(INT), cpu_threads=OPT(INT),
             cpu_max_mhz=OPT(INT), ram_total_gb=NUM, drives=LIST(DRIVE, 6), computer_name=STR(80), python_version=STR(20), has_battery=BOOL)
TOP = LIST(DICT(name=STR(60), ram_mb=NUM, count=INT), 10)
SNAPSHOT = DICT(
    now=NOW, drives=LIST(DRIVE_FULL, 6),
    programs=DICT(ram=LIST(DICT(name=STR(60), mb=NUM, count=INT), 5), cpu=LIST(DICT(name=STR(60), percent=NUM, count=INT), 5),
                  disk=LIST(DICT(name=STR(60), mb_s=NUM, count=INT), 5)),
    autostart=LIST(STR(60), 100))


def _ping_result(data):
    return DICT(name=STR(40), time=STR(40), version=lambda v: _version(v))(data)


def _version(value):
    value = INT(value)
    if not 0 < value < 1000:
        raise CommandError(BAD)
    return value


def _no_args(args):
    if args not in (None, {}):
        raise CommandError("Dieser Auftrag hat keine Parameter.")
    return {}


def _performance_args(args):
    """Optional {"fresh": true}: CPU 0,3 s lang frisch messen (fuer einzelne Chat-Fragen)."""
    if args in (None, {}):
        return {"fresh": False}
    if not isinstance(args, dict) or set(args) != {"fresh"} or not isinstance(args["fresh"], bool):
        raise CommandError("Falsche Parameter.")
    return {"fresh": args["fresh"]}


# Auftrag -> (Parameter pruefen, Ergebnis pruefen). Neue Auftraege kommen als neue Zeilen, auf beiden Seiten.
COMMANDS = {
    "ping": (_no_args, _ping_result),
    "pc.facts": (_no_args, FACTS),
    "pc.performance": (_performance_args, NOW),
    "pc.top": (_no_args, TOP),
    "pc.snapshot": (_no_args, SNAPSHOT),
}

# Wie lange der Server auf ein Ergebnis wartet (Sekunden); der Rest nimmt DEFAULT_TIMEOUT. Die PC-Lage misst Programme und Laufwerke und braucht laenger.
DEFAULT_TIMEOUT = 8
TIMEOUTS = {"pc.snapshot": 30}


def timeout_for(command):
    return TIMEOUTS.get(command, DEFAULT_TIMEOUT)


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
        raise CommandError(BAD)
    if size > MAX_RESULT_BYTES:
        raise CommandError("Ergebnis zu gross.")
    return COMMANDS[command][1](data)
