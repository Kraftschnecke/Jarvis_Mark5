import secrets
import threading
import time
import traceback

from openai import OpenAI
import action_log
import ai_log
from parallel import Job
from config import OPENAI_TIMEOUT, TIMING_ENABLED
from memory import Memory
from settings_manager import SettingsManager
from personality import get_address, set_address, DEFAULT_ADDRESS
import abilities
import reminders
from tools import news_tool, weather_tool
import cost_guard
from task_registry import TaskRegistry
import plan_view
from capabilities import describe_capabilities
import risk
from task_executor import (
    execute_registered_task, execute_task, prepare_registered_task
)
from brain import respond_to_task, respond_to_plan, ask_jarvis
from planner import create_plan
from plan_executor import confirmable_steps, execute_plan, find_blocker
from plan import step_risk, prepare_step
from project_context import (
    get_project_context,
    add_to_project_section
)
from project_analyzer import process_project_context
from router import route_message
from background_tasks import get_results
from timer import (
    DEFAULT_NAME as DEFAULT_TIMER_NAME, format_duration, answer_pending as answer_timer_choice,
    clear_choice as clear_timer_choice,
)
from workspace import Workspace
from tasks import (
    register_all_tasks
)
from project import save_message


YES_ANSWERS = {
    "ja", "yes", "y", "okay", "ok", "genau", "klar", "gerne",
    "do it", "speichern", "mach das", "yep", "jo"
}

NO_ANSWERS = {
    "nein", "no", "n", "nope", "nee", "nicht speichern", "lieber nicht"
}


def normalize_answer(message):
    """Macht aus 'Ja!' oder ' ja. ' ein vergleichbares 'ja'."""
    return message.strip().lower().strip(" .!?,;:")


def build_confirmation_question(section, content):
    return (
        f"{get_address()}, soll ich das im Project Context unter \"{section}\" "
        f"festhalten?\n"
        f"-> {content}\n"
        f"(ja / nein)"
    )


PENDING_ACTION_SECONDS = 120
PENDING_PLAN_SECONDS = 300


class Jarvis:
    # Klassen-Standard: es gibt nie eine offene Rueckfrage, bevor eine entsteht
    pending_action = None
    pending_plan = None
    _plan_abort = None
    _plan_running = False

    def __init__(self):
        # Tageslimit fuer kostenpflichtige Aufrufe (cost_guard.py); die Limits stehen in den Einstellungen
        self.cost_counter = cost_guard.UsageCounter("usage.json", self._cost_limits)
        self.client = cost_guard.guard(OpenAI(timeout=OPENAI_TIMEOUT), self.cost_counter)

        # Nur wenn JARVIS_TIMING=1: jeder KI-Aufruf wird gemessen (ai_log.py)
        if TIMING_ENABLED:
            self.client = ai_log.wrap(self.client)

        action_log.enable()
        self.workspace = Workspace()
        self.pending_project_confirmation = None
        self.settings_manager = SettingsManager()
        weather_tool.set_default_service(weather_tool.WeatherService(
            home=lambda: self.settings_manager.get("jarvis", "home_place", "")
        ))
        news_tool.set_default_service(news_tool.NewsService(
            enabled=lambda: [f for f in news_tool.FEEDS if self.settings_manager.get("news", f, False)]
        ))
        self.apply_settings()
        self.memory = Memory()
        self.memory.load()
        # Ausgeschaltete Faehigkeiten (Einstellungen -> Abilities) sind fuer Router, Planer und Ausfuehrung unsichtbar
        self.task_registry = TaskRegistry(
            is_enabled=lambda task_type: abilities.task_enabled(task_type, self.settings_manager)
        )
        register_all_tasks(self.task_registry)

    def _cost_limits(self):
        return {
            "ai": self.settings_manager.get("limits", "ai_calls_per_day", 500),
            "speech": self.settings_manager.get("limits", "speech_calls_per_day", 200),
        }

    def apply_settings(self):
        """Uebernimmt Einstellungen, die im Programm gebraucht werden (Anrede)."""
        set_address(
            self.settings_manager.get("jarvis", "address", DEFAULT_ADDRESS)
        )

    def memory_enabled(self):
        return bool(
            self.settings_manager.get("memory", "enabled", True)
        )

    def get_memory_context(self):
        # Ist Memory aus, lernt Jarvis nichts Neues und nutzt auch nichts Altes.
        if not self.memory_enabled():
            return Memory.EMPTY_CONTEXT

        return self.memory.get_context()

    # --- Projekte und Konversationen: Verwaltung liegt in workspace.py ---

    @property
    def project_state(self):
        return self.workspace.project_state

    @property
    def conversation(self):
        return self.workspace.conversation

    def open_project(self, name):
        return self.workspace.open_project(name)

    def create_project(self, name, description=None):
        return self.workspace.create_project(name, description)

    def open_conversation(self, name):
        return self.workspace.open_conversation(name)

    def create_conversation(self, name):
        return self.workspace.create_conversation(name)

    def get_conversations(self):
        return self.workspace.get_conversations()

    def get_conversation(self, name):
        return self.workspace.get_conversation(name)

    def rename_conversation(self, old_name, new_name):
        return self.workspace.rename_conversation(old_name, new_name)

    def close_project(self):
        result = self.workspace.close_project()
        # Eine offene Rueckfrage gehoert zum geschlossenen Projekt.
        self.clear_pending()
        return result

    def reset_conversation(self):
        return self.workspace.reset_conversation()

    def delete_conversation(self, name):
        return self.workspace.delete_conversation(name)

    # --- Seitenleiste der Web-Oberflaeche (Aktionen ueber IDs) ---

    def get_tree(self):
        return self.workspace.get_tree()

    def get_active(self):
        return self.workspace.get_active()

    def select_conversation(self, project_id, conversation_id):
        messages = self.workspace.select_conversation(
            project_id, conversation_id
        )
        # Eine offene Rueckfrage gehoert zur vorherigen Konversation.
        self.clear_pending()
        return messages

    def select_project(self, project_id):
        changed = self.workspace.select_project(project_id)
        if changed:
            self.clear_pending()
        return changed

    def add_project(self, name):
        project_id = self.workspace.add_project(name)
        # Das neue Projekt ist aktiv: alte Rueckfragen gelten nicht mehr.
        self.clear_pending()
        return project_id

    def rename_project_by_id(self, project_id, new_name):
        self.workspace.rename_project_by_id(project_id, new_name)

    def delete_project_by_id(self, project_id):
        self.workspace.delete_project_by_id(project_id)
        self.clear_pending()

    def add_conversation(self, title, project_id=None):
        conversation_id = self.workspace.add_conversation(title, project_id)
        if project_id is not None:
            self.clear_pending()
        return conversation_id

    def rename_conversation_by_id(self, project_id, conversation_id, new_title):
        self.workspace.rename_conversation_by_id(
            project_id, conversation_id, new_title
        )

    def reset_conversation_by_id(self, project_id, conversation_id):
        self.workspace.reset_conversation_by_id(project_id, conversation_id)

    def delete_conversation_by_id(self, project_id, conversation_id):
        self.workspace.delete_conversation_by_id(project_id, conversation_id)

    def process_normal_message(self, message):
        # Momentaufnahme VOR den Hintergrund-Jobs: Die Antwort bekommt Memory und
        # Projekt-Kontext im Zustand vor dieser Nachricht (siehe DESIGN_PARALLEL.md).
        memory_context = self.get_memory_context()
        active_project = self.project_state.active_project

        project_context = (
            get_project_context(active_project[0])
            if active_project is not None
            else None
        )

        # Memory- und Projekt-Pruefung laufen gleichzeitig mit der Antwort.
        memory_job = None
        project_job = None

        if self.memory_enabled():
            memory_job = Job(self.memory.process, self.client, message)

        if active_project is not None:
            project_job = Job(self.process_project_context, message)

        try:
            self.conversation.add_message("user", message)

            if self.project_state.active_conversation is not None:
                save_message(
                    self.project_state.active_conversation[0],
                    "user",
                    message
                )

            answer = ask_jarvis(
                self.client,
                self.conversation,
                memory_context,
                project_context
            )
        finally:
            # Nach einer Nachricht darf nichts mehr im Hintergrund schreiben,
            # auch nicht, wenn die Antwort gescheitert ist.
            for job in (memory_job, project_job):
                if job is not None:
                    job.wait()

        self.conversation.add_message("assistant", answer)

        if self.project_state.active_conversation is not None:
            save_message(
                self.project_state.active_conversation[0],
                "assistant",
                answer
            )

        if memory_job is not None:
            try:
                memory_job.result()
            except Exception as error:
                # Memory ist Nebensache: ein Fehler dort darf die
                # eigentliche Antwort nicht verhindern.
                print(f"[memory] Konnte nichts speichern: {error}")

        project_result = None

        if project_job is not None:
            try:
                project_result = project_job.result()
            except Exception as error:
                # Ebenso die Projekt-Pruefung: Antwort ohne Rueckfrage.
                print(f"[projekt] Pruefung fehlgeschlagen: {error}")

        # Eine neue Nachricht macht jede alte offene Rueckfrage ungueltig.
        self.clear_pending()
        confirmation_question = None

        if (
            project_result is not None
            and project_result.get("status") == "confirmation_required"
        ):
            self.pending_project_confirmation = {
                "project_id": active_project[0],
                "section": project_result["section"],
                "content": project_result["content"]
            }

            confirmation_question = build_confirmation_question(
                project_result["section"],
                project_result["content"]
            )

        # Die Rueckfrage gehoert nicht in den Chatverlauf, nur in die Anzeige.
        if confirmation_question is not None:
            answer = f"{answer}\n\n{confirmation_question}"

        return {
            "status": "response",
            "content": answer
        }

    def process_project_context(self, message):
        if self.project_state.active_project is None:
            return None

        return process_project_context(
            self.client,
            self.project_state.active_project[0],
            message
        )

    def clear_pending(self):
        """Verwirft jede offene Rueckfrage (Projekt-Info und Aktion)."""
        self.pending_project_confirmation = None
        self.pending_action = None
        self.pending_plan = None
        clear_timer_choice()

    # ---------- Plaene (Step 5.3) ----------

    def run_plan_request(self, message):
        """Der Router sagt PLAN: Plan holen, pruefen, ANZEIGEN. Ausgefuehrt wird erst nach deinem Ja."""
        plan, reason = create_plan(self.client, message, self.task_registry)

        if plan is None:
            return {
                "status": "response",
                "content": f"Das kann ich so nicht als Plan umsetzen, {get_address()}: {reason}"
            }

        approvable = set(confirmable_steps(plan, self.task_registry))
        blocker = find_blocker(plan, self.task_registry, approvable)

        if blocker is not None:
            number, _, text = blocker

            # Verbotene Schritte stehen im Protokoll wie verbotene Einzelaufgaben
            for index, step in enumerate(plan.steps, start=1):
                if step_risk(self.task_registry, step) == risk.FORBIDDEN:
                    action_log.record(prepare_step(self.task_registry, step), "refused", "BLOCKED")

            return {
                "status": "response",
                "content": (
                    f"Diesen Plan fuehre ich nicht aus, {get_address()}. {text}"
                )
            }

        plan_id = secrets.token_hex(8)
        view = plan_view.view_plan(plan, self.task_registry, approvable)

        self.pending_plan = {
            "id": plan_id,
            "plan": plan,
            "approved": approvable,
            "message": message,
            "expires": time.monotonic() + PENDING_PLAN_SECONDS,
        }

        view["id"] = plan_id

        return {
            "status": "plan",
            "content": plan_view.plan_text(view, get_address()),
            "plan": view,
        }

    def abort_event(self):
        if self._plan_abort is None:
            self._plan_abort = threading.Event()

        return self._plan_abort

    def abort_plan(self):
        """Stoppt einen laufenden Plan vor dem naechsten Schritt. True, wenn gerade einer laeuft."""
        self.abort_event().set()

        return self._plan_running

    def _finish_pending_plan(self, pending, approve):
        if not approve:
            for number, step in enumerate(pending["plan"].steps, start=1):
                if number in pending["approved"]:
                    action_log.record(
                        prepare_step(self.task_registry, step), "declined", "DECLINED"
                    )

            return f"Verstanden, {get_address()}. Ich habe nichts ausgefuehrt."

        abort = self.abort_event()
        abort.clear()
        self._plan_running = True

        try:
            run = execute_plan(
                pending["plan"], self.task_registry,
                approved=pending["approved"], should_abort=abort.is_set,
            )
        finally:
            self._plan_running = False

        return respond_to_plan(self.client, pending["message"], run)

    def handle_pending_plan(self, message):
        """Chat-Antwort (ja/nein) auf einen angezeigten Plan, z.B. im CLI."""
        pending = self.pending_plan

        if pending is None:
            return None

        self.pending_plan = None

        if time.monotonic() > pending["expires"]:
            return None

        answer = normalize_answer(message)

        if answer in YES_ANSWERS:
            return self._finish_pending_plan(pending, True)

        if answer in NO_ANSWERS:
            return self._finish_pending_plan(pending, False)

        return None

    def confirm_plan(self, plan_id, approve):
        """Antwort per Knopf im Web. Nur der angezeigte Plan mit genau dieser Nummer zaehlt."""
        pending = self.pending_plan
        self.pending_plan = None

        if (
            pending is None
            or not isinstance(plan_id, str)
            or not secrets.compare_digest(pending["id"], plan_id)
            or time.monotonic() > pending["expires"]
        ):
            return {
                "status": "response",
                "content": (
                    f"Dieser Plan ist nicht mehr gueltig, {get_address()}. "
                    "Bitte sage mir noch einmal, was ich tun soll."
                )
            }

        try:
            content = self._finish_pending_plan(pending, approve is True)
        except Exception as error:
            traceback.print_exc()
            content = (
                f"{get_address()}, bei der Ausfuehrung des Plans ist ein Fehler aufgetreten "
                f"({type(error).__name__}: {str(error)[:200]})."
            )

        return {"status": "response", "content": content}

    # ---------- Aktionen mit Rueckfrage (Step 4.2) ----------

    def disabled_message(self, task_type):
        """Feste Antwort (kein Modell): die Faehigkeit ist in den Einstellungen ausgeschaltet."""
        ability = abilities.ability_of(task_type)
        name = ability.label if ability else task_type

        return (
            f"Die Fähigkeit „{name}“ ist ausgeschaltet, {get_address()}. "
            "Du kannst sie in den Einstellungen unter Abilities einschalten."
        )

    def run_task(self, message, route):
        """Fuehrt eine Aufgabe aus - je nach Risikostufe sofort, nach Rueckfrage oder gar nicht."""
        prepared = prepare_registered_task(
            self.task_registry, route["task_type"], route["parameters"]
        )
        level = risk.task_risk(prepared) if prepared is not None else risk.SAFE

        if level == risk.FORBIDDEN:
            goal, _ = risk.describe_task(prepared)
            action_log.record(prepared, "refused", "BLOCKED")

            # Feste Antwort, kein Modell: Es gibt nichts zu verhandeln.
            return {
                "status": "response",
                "content": (
                    f"Das darf ich nicht tun, {get_address()}: {goal}. "
                    "Diese Aktion ist bei mir grundsaetzlich gesperrt."
                )
            }

        if level == risk.CONFIRM:
            goal, details = risk.describe_task(prepared)
            action_id = secrets.token_hex(8)

            self.pending_action = {
                "id": action_id,
                "task": prepared,
                "message": message,
                "expires": time.monotonic() + PENDING_ACTION_SECONDS,
            }

            lines = [f"{get_address()}, soll ich das wirklich tun?", "", f"**{goal}**"]
            lines += [f"`{d.replace(chr(96), chr(39))}`" for d in details]
            lines += ["", "Antworte mit **ja** oder **nein**."]

            return {
                "status": "confirmation",
                "content": "\n".join(lines),
                "confirmation": {"id": action_id, "title": goal, "details": details},
            }

        task = execute_registered_task(
            self.task_registry, route["task_type"], route["parameters"]
        )

        return {
            "status": "response",
            "content": respond_to_task(self.client, message, task)
        }

    def _finish_pending_action(self, pending, approve):
        if not approve:
            action_log.record(pending["task"], "declined", "DECLINED")

            return f"Verstanden, {get_address()}. Ich habe nichts ausgefuehrt."

        task = pending["task"]

        # Wurde die Faehigkeit seit der Rueckfrage ausgeschaltet, wird nichts mehr ausgefuehrt
        if self.task_registry.is_disabled(task.task_type):
            action_log.record(task, "refused", "BLOCKED")

            return self.disabled_message(task.task_type)

        execute_task(task, confirmed=True)

        return respond_to_task(self.client, pending["message"], task)

    def handle_pending_action(self, message):
        """Chat-Antwort (ja/nein) auf eine offene Aktions-Rueckfrage, z.B. im CLI."""
        pending = self.pending_action

        if pending is None:
            return None

        # Gilt nur fuer die direkt folgende Nachricht, egal was sie ist.
        self.pending_action = None

        if time.monotonic() > pending["expires"]:
            return None

        answer = normalize_answer(message)

        if answer in YES_ANSWERS:
            return self._finish_pending_action(pending, True)

        if answer in NO_ANSWERS:
            return self._finish_pending_action(pending, False)

        return None

    def confirm_action(self, action_id, approve):
        """Antwort per Button im Web. Nur die offene Rueckfrage mit genau dieser Nummer zaehlt."""
        pending = self.pending_action
        self.pending_action = None

        if (
            pending is None
            or not isinstance(action_id, str)
            or not secrets.compare_digest(pending["id"], action_id)
            or time.monotonic() > pending["expires"]
        ):
            return {
                "status": "response",
                "content": (
                    f"Diese Rueckfrage ist nicht mehr gueltig, {get_address()}. "
                    "Bitte sage mir noch einmal, was ich tun soll."
                )
            }

        try:
            content = self._finish_pending_action(pending, approve is True)
        except Exception as error:
            traceback.print_exc()
            content = (
                f"{get_address()}, bei der Ausfuehrung ist ein Fehler aufgetreten "
                f"({type(error).__name__}: {str(error)[:200]})."
            )

        return {"status": "response", "content": content}

    def handle_project_confirmation(self, message):
        pending = self.pending_project_confirmation

        if pending is None:
            return None

        # Eine Rueckfrage gilt nur fuer die direkt folgende Nachricht.
        # Egal was der User antwortet: danach ist sie verbraucht.
        self.clear_pending()

        active_project = self.project_state.active_project

        if active_project is None or active_project[0] != pending["project_id"]:
            return None

        answer = normalize_answer(message)

        if answer in YES_ANSWERS:
            saved = add_to_project_section(
                pending["project_id"],
                pending["section"],
                pending["content"]
            )

            if not saved:
                return (
                    f"Das konnte ich nicht speichern, {get_address()}. "
                    "Vielleicht steht es schon im Project Context."
                )

            return (
                f"Verstanden, {get_address()}. "
                "Ich habe die Information in Project Context gespeichert."
            )

        if answer in NO_ANSWERS:
            return (
                f"Verstanden, {get_address()}. "
                "Ich habe diese Information nicht gespeichert."
            )

        return None

    def handle_command(self, command):
        if command["intent"] == "SHOW_CAPABILITIES":
            return describe_capabilities(
                self.task_registry, get_address(), self.memory_enabled()
            )

        if command["intent"] == "RESET_CONVERSATION":
            return self.reset_conversation()

        if command["intent"] == "OPEN_PROJECT":
            return self.open_project(
                command["project_name"]
            )

        if command["intent"] == "CLOSE_PROJECT":
            return self.close_project()

        if command["intent"] == "OPEN_CONVERSATION":
            return self.open_conversation(
                command["conversation_name"]
            )

        if command["intent"] == "RENAME_CONVERSATION":
            return self.rename_conversation(
                command["conversation_name"],
                command["new_conversation_name"]
            )

        if command["intent"] == "CREATE_CONVERSATION":
            return self.create_conversation(
                command["conversation_name"]
            )

        if command["intent"] == "CREATE_PROJECT":
            return self.create_project(
                command["project_name"]
            )

        return None

    def process_message(self, message):
        """Einziger Einstiegspunkt fuer CLI und GUI.

        Faengt Fehler ab (z.B. Netzwerkausfall bei der Modell-Anfrage). Ohne
        das wuerde das CLI abstuerzen und die GUI fuer immer auf
        "THINKING..." haengen bleiben, weil der Worker nie fertig meldet.
        Strg+C (KeyboardInterrupt) wird bewusst nicht abgefangen.
        """
        ai_log.start_message(message)

        try:
            return self._process_message(message)
        except cost_guard.LimitReached as error:
            # Erwartbar, kein Fehler im Programm: kein Traceback, feste Meldung
            self.clear_pending()

            text = str(error)

            return {"status": "response", "content": f"{get_address()}, {text[0].lower()}{text[1:]}"}
        except Exception as error:
            if type(error).__name__ in ("APIConnectionError", "APITimeoutError"):
                # Kein Internet / KI nicht erreichbar: erwartbar, eine Zeile statt Traceback
                print(f"[FEHLER] Keine Verbindung zur KI: {type(error).__name__}")
            else:
                traceback.print_exc()

            # Eine halb verarbeitete Nachricht darf keine Rueckfrage offen lassen
            self.clear_pending()

            return {
                "status": "response",
                "content": (
                    f"{get_address()}, bei der Verarbeitung ist ein Fehler aufgetreten "
                    f"({type(error).__name__}: {str(error)[:200]}). "
                    "Bitte versuche es noch einmal."
                )
            }
        finally:
            ai_log.finish_message()

    def _process_message(self, message):

        # "Welchen Timer meinst du?" gilt nur fuer die direkt folgende Nachricht
        timer_answer = answer_timer_choice(message)

        if timer_answer is not None:
            return {
                "status": "response",
                "content": timer_answer
            }

        plan_result = self.handle_pending_plan(message)

        if plan_result is not None:
            return {
                "status": "response",
                "content": plan_result
            }

        action_result = self.handle_pending_action(message)

        if action_result is not None:
            return {
                "status": "response",
                "content": action_result
            }

        confirmation_result = self.handle_project_confirmation(
            message
        )

        if confirmation_result is not None:
            return {
                "status": "response",
                "content": confirmation_result
            }

        # Ein einziger KI-Aufruf entscheidet: Befehl, Aufgabe oder Chat
        route = route_message(
            self.client,
            message,
            self.task_registry
        )

        if route["kind"] == "COMMAND":
            command = route["command"]

            if command["intent"] == "EXIT":
                return {
                    "status": "exit",
                    "content": f"Shutting down, {get_address()}"
                }

            command_result = self.handle_command(
                command
            )

            if command_result is not None:
                return {
                    "status": "response",
                    "content": command_result
                }

        if route["kind"] == "DISABLED":
            return {"status": "response", "content": self.disabled_message(route["task_type"])}

        if route["kind"] == "TASK":
            return self.run_task(message, route)

        if route["kind"] == "PLAN":
            return self.run_plan_request(message)

        return self.process_normal_message(message)

    def get_background_results(self):
        return get_results()

    def process_background_result(self, result):
        if result["type"] == "TIMER_FINISHED":
            seconds = result["data"]["seconds"]
            name = result["data"].get("name")
            label = f" „{name}“" if name and name != DEFAULT_TIMER_NAME else ""

            return (
                f"{get_address()}, der Timer{label} ist nach "
                f"{format_duration(seconds)} abgelaufen."
            )

        if result["type"] == "REMINDER_DUE":
            return self.reminder_message(result["data"])

    def reminder_message(self, data):
        message = f"{get_address()}, Erinnerung: {data.get('text', '')}"
        notes = []
        if data.get("missed"):
            notes.append(f"fällig war sie {reminders.describe_due(data['due'])}, da war ich nicht aktiv")
        if data.get("next_due"):
            notes.append(f"die nächste kommt {reminders.describe_due(data['next_due'])}")
        elif data.get("last_of_series"):
            notes.append("das war die letzte dieser Serie")
        return message + (f" ({'; '.join(notes)})" if notes else "")

    def check_background_results(self):
        results = self.get_background_results()
        responses = []

        for result in results:
            response = self.process_background_result(result)

            if response is not None:
                responses.append(response)

        return responses
