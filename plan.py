"""Plan-Format (Mark 4, Step 5.1).

Ein Plan ist KEIN Text, den Jarvis ausfuehrt, sondern eine gepruefte Liste von
Schritten. Jeder Schritt ist genau eine bekannte Aufgabe (Task) mit Parametern:

    {
        "goal": "Notepad starten und die Uhrzeit sagen",
        "steps": [
            {"task_type": "START_PROGRAM", "parameters": {"program": "notepad"}},
            {"task_type": "GET_TIME", "parameters": {}}
        ]
    }

Ein Parameter ist entweder ein einfacher Wert (Text oder Zahl) oder ein Verweis
auf das Ergebnis eines frueheren Schritts: {"from_step": 1} (Zaehlung ab 1).

parse_plan() ist das einzige Tor: Die rohe Antwort des Sprachmodells (unvertraute
Eingabe!) kommt hinein, heraus kommt ein Plan, der alle Regeln erfuellt, oder
ein PlanError mit einer verstaendlichen Begruendung. Es gibt keinen Weg, einen
ungepruefen Plan zu bauen, den die spaeteren Schritte (5.2 Ausfuehren, 5.3
Anzeigen) annehmen.

Regeln (jede wird getestet):
- hoechstens MAX_STEPS Schritte, mindestens einer
- jeder Schritt nennt eine REGISTRIERTE Aufgabe (sonst Fehler, nie raten)
- nur Parameter, die die Aufgabe kennt; alle muessen gesetzt sein
- Werte: Text (hoechstens MAX_TEXT Zeichen, ohne Steuer-/Unsichtbar-Zeichen),
  endliche Zahl, oder {"from_step": n} mit n kleiner als die Nummer des Schritts
- Parameter, die in der Aufgabe selbst aus dem vorherigen Ergebnis kommen
  (z.B. der Pfad bei START_PROGRAM), darf der Plan nicht setzen
- Alles andere (zusaetzliche Felder usw.) wird nicht uebernommen
"""

import math

from untrusted import clean_text
import risk
from task_executor import prepare_registered_task

MAX_STEPS = 6

# Diese Aufgaben gibt es nur einzeln: das Bild des Bildschirms reist nur mit der Antwort auf eine einzelne Frage (Step 2.25)
NOT_IN_PLANS = frozenset({"DESCRIBE_SCREEN"})
MAX_TEXT = 500
MAX_GOAL = 200
MAX_NUMBER = 1_000_000_000


class PlanError(ValueError):
    """Der Plan ist ungueltig. Die Meldung ist fuer Menschen gedacht."""


class Step:
    def __init__(self, task_type, parameters):
        self.task_type = task_type
        self.parameters = parameters

    def to_dict(self):
        return {"task_type": self.task_type, "parameters": dict(self.parameters)}


class Plan:
    def __init__(self, goal, steps):
        self.goal = goal
        self.steps = steps

    def to_dict(self):
        return {"goal": self.goal, "steps": [s.to_dict() for s in self.steps]}


def parameter_names(task):
    """Die Parameter, die ein Plan fuer diese Aufgabe setzen muss (und darf)."""
    names = []

    for action in task.actions:
        for name, definition in action.parameters.items():
            is_reference = (
                isinstance(definition, dict)
                and definition.get("source") == "previous_result"
            )

            if not is_reference and name not in names:
                names.append(name)

    return names


def is_step_reference(value):
    return isinstance(value, dict) and set(value) == {"from_step"}


def _clean_value(name, value, step_number):
    where = f"Schritt {step_number}, Parameter '{name}'"

    if is_step_reference(value):
        target = value["from_step"]

        if not isinstance(target, int) or isinstance(target, bool):
            raise PlanError(f"{where}: from_step muss eine ganze Zahl sein.")

        if not 1 <= target < step_number:
            raise PlanError(
                f"{where}: from_step muss auf einen frueheren Schritt zeigen "
                f"(1 bis {step_number - 1}), nicht auf {target}."
            )

        return {"from_step": target}

    if isinstance(value, bool) or value is None:
        raise PlanError(f"{where}: ungueltiger Wert.")

    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise PlanError(f"{where}: ungueltige Zahl.")

        if abs(value) > MAX_NUMBER:
            raise PlanError(f"{where}: Zahl ausserhalb des erlaubten Bereichs.")

        return value

    if isinstance(value, str):
        text = value.strip()

        if not text:
            raise PlanError(f"{where}: der Wert ist leer.")

        if len(text) > MAX_TEXT or clean_text(text, MAX_TEXT + 1) != text:
            raise PlanError(
                f"{where}: der Text ist zu lang (hoechstens {MAX_TEXT} Zeichen) "
                "oder enthaelt unzulaessige Zeichen."
            )

        return text

    raise PlanError(f"{where}: nur Text, Zahlen oder {{\"from_step\": n}} sind erlaubt.")


def parse_plan(raw, task_registry):
    """Prueft eine rohe Plan-Antwort und gibt einen Plan zurueck (oder wirft PlanError)."""
    if not isinstance(raw, dict):
        raise PlanError("Der Plan ist kein Objekt.")

    goal = raw.get("goal")

    if not isinstance(goal, str) or not goal.strip():
        raise PlanError("Der Plan braucht ein Ziel (goal).")

    goal = goal.strip()

    if len(goal) > MAX_GOAL or clean_text(goal, MAX_GOAL + 1) != goal:
        raise PlanError("Das Ziel ist zu lang oder enthaelt unzulaessige Zeichen.")

    raw_steps = raw.get("steps")

    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanError("Der Plan hat keine Schritte.")

    if len(raw_steps) > MAX_STEPS:
        raise PlanError(
            f"Der Plan hat {len(raw_steps)} Schritte, erlaubt sind hoechstens {MAX_STEPS}."
        )

    steps = []

    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            raise PlanError(f"Schritt {index} ist kein Objekt.")

        task_type = raw_step.get("task_type")
        task = (
            task_registry.get(task_type)
            if isinstance(task_type, str)
            else None
        )

        if task is None:
            raise PlanError(f"Schritt {index}: unbekannte Aufgabe.")

        if task_type in NOT_IN_PLANS:
            raise PlanError(f"Schritt {index}: diese Aufgabe gibt es nur einzeln, nicht in einem Plan.")

        raw_parameters = raw_step.get("parameters", {})

        if raw_parameters is None:
            raw_parameters = {}

        if not isinstance(raw_parameters, dict):
            raise PlanError(f"Schritt {index}: parameters muss ein Objekt sein.")

        allowed = parameter_names(task)

        for name in raw_parameters:
            if name not in allowed:
                raise PlanError(
                    f"Schritt {index} ({task_type}): unbekannter Parameter "
                    f"'{str(name)[:40]}'."
                )

        parameters = {}

        for name in allowed:
            if name not in raw_parameters:
                raise PlanError(
                    f"Schritt {index} ({task_type}): der Parameter '{name}' fehlt."
                )

            parameters[name] = _clean_value(name, raw_parameters[name], index)

        steps.append(Step(task_type, parameters))

    return Plan(goal, steps)


def prepare_step(task_registry, step):
    """Baut die (noch nicht ausgefuehrte) Task zu einem Schritt."""
    return prepare_registered_task(task_registry, step.task_type, step.parameters)


def step_risk(task_registry, step):
    return risk.task_risk(prepare_step(task_registry, step))


def plan_risk(plan, task_registry):
    """Hoechste Stufe aller Schritte (safe < confirm < forbidden).

    Wert, der erst aus einem frueheren Schritt kommt, ist hier noch unbekannt:
    Geprueft wird er trotzdem, naemlich in 5.2 unmittelbar vor der Ausfuehrung.
    """
    level = risk.SAFE

    for step in plan.steps:
        level = risk.higher(level, step_risk(task_registry, step))

    return level
