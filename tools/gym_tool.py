"""Gym-Plan fuer den Chat (Etappe G). NUR LESEN.

"Was steht heute im Training an?": der Tag (Push/Pull/Offday) mit den Uebungen, ihren Zielen und dem, was heute schon eingetragen ist.
Eintragen und den Plan aendern geht nur im Gym-Fenster der Seite, nie ueber den Chat.
"""

import gym
from tools.tool_result import ToolResult


def _level(entry):
    return {"weight": entry["weight"], "sets": entry["sets"], "reps": entry["reps"]}


def gym_today(store=None):
    """Aktion gym_today: der heutige Trainingstag mit Zielen."""
    store = store or gym.default_store()
    try:
        view = store.today_view()
    except Exception as error:
        return ToolResult(success=False, error=f"Der Gym-Plan ließ sich nicht lesen ({type(error).__name__}).")
    if not view["has_plan"]:
        return ToolResult(success=True, data={"has_plan": False, "weekday": view["label"]})
    exercises = []
    for item in view["exercises"]:
        row = {"name": item["name"], "goal": _level(item)}
        if item["note"]:
            row["note"] = item["note"]
        if item["today"]:
            row["done"] = {"weight": item["today"]["weight"], "reps": item["today"]["reps"]}
        exercises.append(row)
    return ToolResult(success=True, data={"has_plan": True, "weekday": view["label"], "name": view["name"], "offday": view["offday"],
                                          "exercises": exercises, "logged": view["logged"], "total": view["total"]})
