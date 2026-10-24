"""Faehigkeitenliste (Mark 4, Step 5.4): "Was kannst du?" beantwortet Jarvis aus der Registry.

Der Text wird bei jeder Frage neu aus dem erzeugt, was WIRKLICH eingebaut ist:
- Aufgaben: aus der TaskRegistry (Ziel jeder Aufgabe), mit Hinweis, wenn Jarvis
  vorher nachfragt (Risikostufe confirm aus risk.py).
- Befehle: aus router.COMMAND_INTENTS. Jeder Befehl braucht einen Eintrag in
  COMMAND_TEXT; der Test schlaegt an, wenn einer fehlt.

Es ist KEIN Modell-Aufruf: Eine Faehigkeit, die es nicht gibt, kann so nie
genannt werden, und eine neue Aufgabe erscheint ohne weiteren Eingriff in der Liste.
"""

import abilities
import risk
from plan import MAX_STEPS
from plan_executor import MAX_SECONDS
from router import COMMAND_INTENTS

COMMAND_TEXT = {
    "CREATE_PROJECT": "ein neues Projekt anlegen",
    "OPEN_PROJECT": "ein Projekt öffnen",
    "CLOSE_PROJECT": "das aktuelle Projekt schließen",
    "CREATE_CONVERSATION": "eine neue Konversation im Projekt anlegen",
    "OPEN_CONVERSATION": "eine Konversation öffnen",
    "RENAME_CONVERSATION": "eine Konversation umbenennen",
    "RESET_CONVERSATION": "die aktuelle Konversation zurücksetzen",
    "SHOW_CAPABILITIES": "dir sagen, was ich kann (diese Liste)",
    "EXIT": "mich beenden",
}

# Reihenfolge in der Anzeige (Rest alphabetisch dahinter)
COMMAND_ORDER = [
    "CREATE_PROJECT", "OPEN_PROJECT", "CLOSE_PROJECT", "CREATE_CONVERSATION",
    "OPEN_CONVERSATION", "RENAME_CONVERSATION", "RESET_CONVERSATION",
    "SHOW_CAPABILITIES", "EXIT",
]


def task_lines(task_registry):
    lines = []

    for task in task_registry.get_all():
        line = f"- {task.goal}"

        if risk.task_risk(task) == risk.CONFIRM:
            line += " (ich frage vorher nach)"

        lines.append(line)

    return lines


def disabled_lines(task_registry):
    """Was in den Einstellungen unter Abilities ausgeschaltet ist (sonst nichts)."""
    labels = []

    for task in task_registry.get_disabled():
        ability = abilities.ability_of(task.task_type)
        label = ability.label if ability else task.goal

        if label not in labels:
            labels.append(label)

    if not labels:
        return []

    return ["", "**Ausgeschaltet** (einzuschalten in den Einstellungen unter Abilities)"] + [f"- {l}" for l in labels]


def command_lines():
    ordered = [c for c in COMMAND_ORDER if c in COMMAND_INTENTS]
    ordered += sorted(c for c in COMMAND_INTENTS if c not in COMMAND_ORDER)

    return [f"- {COMMAND_TEXT[c]}" for c in ordered]


def describe_capabilities(task_registry, address, memory_enabled=True):
    lines = [f"Das kann ich, {address}:", "", "**Aufgaben**"]
    lines += task_lines(task_registry)
    lines += disabled_lines(task_registry)

    lines += [
        "",
        "**Mehrere Aufgaben nacheinander**",
        f"Ich kann bis zu {MAX_STEPS} dieser Aufgaben zu einem Plan verbinden "
        f"(höchstens {MAX_SECONDS} Sekunden Laufzeit). Du siehst den Plan vor dem Start "
        "und kannst ihn ausführen, abbrechen oder währenddessen stoppen.",
        "",
        "**Projekte und Konversationen**",
    ]
    lines += command_lines()

    lines += [
        "",
        "**Gedächtnis**",
        "Ich merke mir Dinge, die du mir über dich sagst, und halte Entscheidungen "
        "zu deinem Projekt fest. Was ich gespeichert habe, kannst du in den "
        "Einstellungen unter Memory ansehen, ändern und löschen."
        + ("" if memory_enabled else " Das Gedächtnis ist gerade ausgeschaltet."),
        "",
        "**Sprache**",
        "In der Weboberfläche kann ich meine Antworten auf Deutsch und Englisch "
        "vorlesen (mit einer Stimme zur Auswahl), und du kannst mit gedrückter "
        "Mikrofon-Taste mit mir sprechen. Auf Wunsch höre ich auch auf das "
        "Weckwort „Jarvis“. Das alles ist aus, bis du es in den "
        "Einstellungen unter Voice einschaltest.",
        "",
        "**Sicherheit**",
        "Programme starte ich nur, wenn du sie in programs.json freigegeben hast, "
        "und Programme oder Dateien öffne ich erst nach deinem Ja. Programmdateien "
        "wie .exe öffne ich nie als Datei. Alles, was ich tue, steht in den "
        "Einstellungen unter Activity.",
        "",
        "Alles andere kann ich nicht, auch wenn es sich nach einer Unterhaltung "
        "so anhört. Ich unterhalte mich aber gern.",
    ]

    return "\n".join(lines)
