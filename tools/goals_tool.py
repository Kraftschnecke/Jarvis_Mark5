"""Gewohnheiten und Ziele (Mark 5, Step 2.28). NUR LESEN.

"Wie laufen meine Ziele?" / "Wie lange gehe ich schon ins Fitnessstudio?": die Ziele von heute, die Serie (Streak) der
taeglichen Ziele (wie viele Tage in Folge erledigt) und die letzten 7 Tage. Die Daten stammen aus widgets.json, also genau
das, was das Ziele-Widget zeigt. Geaendert wird hier nichts: Haken setzen und Ziele anlegen geht in der Seitenleiste.
"""

from datetime import date

import widgets
from briefing import WEEKDAYS
from tools.tool_result import ToolResult


def goal_overview(store=None):
    """Aktion goal_overview: Ziele heute mit Serie, dazu die letzten 7 Tage."""
    store = store or widgets.default_store()
    try:
        data = store.get()
    except Exception as error:
        return ToolResult(success=False, error=f"Die Ziele ließen sich nicht lesen ({type(error).__name__}).")
    goals = [{"text": g["text"], "daily": g["daily"], "done": g["done"], "streak": g.get("streak", 0)} for g in data["goals"]]
    week = [{"date": d["date"], "weekday": WEEKDAYS[date.fromisoformat(d["date"]).weekday()], "done": d["done"], "total": d["total"]}
            for d in data["week"]]
    return ToolResult(success=True, data={"date": data["date"], "goals": goals,
                                          "open": sum(1 for g in goals if not g["done"]), "week": week})
