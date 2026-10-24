from timer import (
    start_timer, convert_to_seconds, list_timers, cancel_timer, clean_name,
    format_duration, TimerError,
)
import reminders
import widgets
from tools.volume_tool import set_volume
from tools.time_tool import get_current_time, get_current_date
from tools.process_tool import get_running_programs
from tools.file_tool import open_file
from tools.program_tool import find_program, launch_program
from tools.system_info_tool import get_system_info
from tools.web_search_tool import search_web
from tools.calc_tool import calculate
from tools.convert_tool import convert
from tools.news_tool import get_news
from tools.page_tool import read_page
from tools.weather_tool import get_weather
from tools.wiki_tool import wiki_lookup
from tools.world_time_tool import get_world_time
from tools.translate_tool import prepare_translation
from tools.tool_result import ToolResult

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def describe_day(iso_date):
    """'2026-10-23' -> 'Freitag, 23.10.2026' (so liest Jarvis das Datum auch vor)."""
    from datetime import date
    day = date.fromisoformat(iso_date)
    return f"{WEEKDAYS[day.weekday()]}, {day.day:02d}.{day.month:02d}.{day.year}"


def execute_action(action):
    if action.name == "get_current_time":
        return get_current_time()

    if action.name == "get_current_date":
        return get_current_date()

    if action.name == "calculate":
        return calculate(action.parameters["expression"])

    if action.name == "convert":
        return convert(
            action.parameters.get("value", "1"),
            action.parameters.get("from_unit", ""),
            action.parameters.get("to_unit", ""),
        )

    if action.name == "get_system_info":
        return get_system_info()
    
    if action.name == "open_file":
        return open_file(action.parameters["path"])

    if action.name == "get_running_programs":
        return get_running_programs()

    if action.name == "set_volume":
        return set_volume(action.parameters["percentage"])

    if action.name == "find_program":
        return find_program(action.parameters["program"])

    if action.name == "open_program":
        return launch_program(action.parameters["path"])

    if action.name == "search_web":
        return search_web(action.parameters["query"])

    if action.name == "read_page":
        return read_page(action.parameters.get("url", ""), action.parameters.get("item", ""))

    if action.name == "get_news":
        return get_news(action.parameters["source"], action.parameters["topic"], action.parameters["count"])

    if action.name == "translate":
        return prepare_translation(action.parameters.get("text", ""), action.parameters.get("target_language", ""),
                                   action.parameters.get("source_language", ""))

    if action.name == "wiki_lookup":
        return wiki_lookup(action.parameters.get("topic", ""), action.parameters.get("language", "de"))

    if action.name == "get_world_time":
        return get_world_time(action.parameters.get("place", ""))

    if action.name == "get_weather":
        return get_weather(action.parameters["place"], action.parameters["day"])

    if action.name == "start_timer":
        value = action.parameters["value"]
        unit = action.parameters["unit"]
        seconds = convert_to_seconds(value, unit)
        name = clean_name(action.parameters.get("name"))
        try:
            start_timer(seconds, name)
        except TimerError as error:
            return ToolResult(success=False, error=str(error))
        return ToolResult(success=True, data={"seconds": seconds, "name": name})

    if action.name == "list_timers":
        timers = [
            {"number": number, "name": t["name"], "remaining": format_duration(t["remaining"])}
            for number, t in enumerate(list_timers(), start=1)
        ]
        return ToolResult(success=True, data={"timers": timers} if timers else {"timers": [], "info": "Es läuft kein Timer."})

    if action.name == "cancel_timer":
        try:
            cancelled = cancel_timer(action.parameters.get("name"))
        except TimerError as error:
            return ToolResult(success=False, error=str(error))
        return ToolResult(success=True, data={"cancelled": cancelled})

    if action.name == "add_calendar_event":
        store = widgets.default_store()
        raw_time = action.parameters.get("time")
        at = raw_time.strip() if isinstance(raw_time, str) else ""
        if at.lower() in ("ganztaegig", "ganztägig", "all-day", "all day", "none", "null", "-"):
            at = ""
        try:
            created = store.add_series(
                action.parameters.get("title"), action.parameters.get("date"), at,
                action.parameters.get("repeat"), action.parameters.get("interval"),
                action.parameters.get("count"), action.parameters.get("until"))
        except ValueError as error:
            return ToolResult(success=False, error=str(error))
        event = created[0]
        data = {"title": event["title"], "date": describe_day(event["date"]), "time": event["time"] or "ganztägig"}
        if event.get("series"):
            data["repeat"] = event["repeat"]
            data["events_created"] = len(created)
            data["last_date"] = describe_day(created[-1]["date"])
            data["open_ended"] = bool(event.get("open_ended"))
        return ToolResult(success=True, data=data)

    if action.name == "set_reminder":
        try:
            entry = reminders.default_store().add(
                action.parameters.get("text"), action.parameters.get("date"), action.parameters.get("time"),
                action.parameters.get("repeat"), action.parameters.get("interval"),
                action.parameters.get("count"), action.parameters.get("until"))
        except reminders.ReminderError as error:
            return ToolResult(success=False, error=str(error))
        data = {"text": entry["text"], "when": reminders.describe_due(entry["due"]),
                "date": describe_day(entry["due"][:10]), "time": entry["due"][11:16],
                "in_calendar": entry["event_id"] is not None}
        data.update({k: v for k, v in reminders.ReminderStore.repeat_info(entry).items() if v is not None})
        if entry["rolled"]:
            data["note"] = "Die Uhrzeit war heute schon vorbei, deshalb gilt die Erinnerung für morgen."
        return ToolResult(success=True, data=data)

    if action.name == "list_reminders":
        items = reminders.default_store().list()
        shown = [dict({"number": n, "text": r["text"], "when": reminders.describe_due(r["due"])},
                      **{k: v for k, v in reminders.ReminderStore.repeat_info(r).items() if v is not None})
                 for n, r in enumerate(items, start=1)]
        return ToolResult(success=True, data={"reminders": shown} if shown else {"reminders": [], "info": "Keine offenen Erinnerungen."})

    if action.name == "cancel_reminder":
        try:
            removed = reminders.default_store().cancel(action.parameters.get("which"), action.parameters.get("scope") or "next")
        except reminders.ReminderError as error:
            return ToolResult(success=False, error=str(error))
        data = {"cancelled": [r["text"] for r in removed if not r["next_due"]]}
        continues = [{"text": r["text"], "next": reminders.describe_due(r["next_due"])} for r in removed if r["next_due"]]
        if continues:
            data["only_next_removed_series_continues"] = continues
        return ToolResult(success=True, data=data)

    if action.name == "list_calendar_events":
        store = widgets.default_store()
        wanted = action.parameters.get("date")
        if isinstance(wanted, str) and wanted.strip().lower() in ("naechste", "nächste", "upcoming", "next"):
            events = store.upcoming_events(10)
        elif isinstance(wanted, str) and widgets._valid_date(wanted.strip()):
            events = store.events_on(wanted.strip())
        else:
            return ToolResult(success=False, error="Das Datum habe ich nicht verstanden.")
        shown = [dict({"date": describe_day(e["date"]), "time": e["time"] or "ganztägig", "title": e["title"]},
                      **({"repeat": e["repeat"]} if e.get("repeat") else {}))
                 for e in events]
        return ToolResult(success=True, data={"events": shown} if shown else {"events": [], "info": "Keine Termine."})

    raise ValueError(f"Unknown action: {action.name}")
