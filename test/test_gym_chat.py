"""Gym im Chat und im Briefing: nur lesen, richtiger Text, Aufgabe/Faehigkeit/Risiko/Remote-Stufe stimmen."""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import abilities
import action_executor
import briefing
import gym
import guest
import remote_policy
import risk
from action import Action
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools import gym_tool

tmp = Path(tempfile.mkdtemp())
store = gym.GymStore(tmp / "gym.json", today=lambda: date(2026, 11, 23))        # Montag

# Ohne Plan
res = gym_tool.gym_today(store)
assert res.success and res.data == {"has_plan": False, "weekday": "Montag"}
assert briefing.gym_sentence(store.today_view()) == ""

# Mit Plan
plan = store.set_plan([{"weekday": 0, "name": "Push", "exercises": [
    {"name": "Bankdrücken", "weight": 60, "sets": 3, "reps": 8, "note": "Pause 2 min"},
    {"name": "Dips", "weight": 0, "sets": 3, "reps": 10}]}, {"weekday": 1, "name": "Pull", "exercises": [{"name": "Rudern", "weight": 50, "sets": 3, "reps": 8}]}])
bench = plan["days"][0]["exercises"][0]["id"]
res = gym_tool.gym_today(store)
assert res.success and res.data["name"] == "Push" and res.data["offday"] is False and res.data["total"] == 2 and res.data["logged"] == 0
assert res.data["exercises"][0] == {"name": "Bankdrücken", "goal": {"weight": 60, "sets": 3, "reps": 8}, "note": "Pause 2 min"}
assert res.data["exercises"][1] == {"name": "Dips", "goal": {"weight": 0, "sets": 3, "reps": 10}}
assert "id" not in str(res.data) and "last" not in res.data["exercises"][0]
store.log(bench, 62.5, [8, 8, 8])
res = gym_tool.gym_today(store)
assert res.data["logged"] == 1 and res.data["exercises"][0]["done"] == {"weight": 62.5, "reps": [8, 8, 8]} and res.data["exercises"][0]["goal"]["weight"] == 62.5
assert briefing.gym_sentence(store.today_view()) == "Heute steht Push an, 2 Übungen."
store.set_plan([{"weekday": 0, "name": "Push", "exercises": [{"name": "Bank", "weight": 60, "sets": 3, "reps": 8}]}])
assert briefing.gym_sentence(store.today_view()) == "Heute steht Push an, 1 Übung."
store.set_plan([{"weekday": 0, "name": "Cardio", "exercises": []}])
assert briefing.gym_sentence(store.today_view()) == "Heute steht Cardio an."
store.set_plan([{"weekday": 1, "name": "Pull", "exercises": [{"name": "Rudern", "weight": 50, "sets": 3, "reps": 8}]}])
assert gym_tool.gym_today(store).data["offday"] is True and briefing.gym_sentence(store.today_view()) == "Heute ist Offday."
assert briefing.gym_sentence(None) == "" and briefing.gym_sentence("x") == ""

# Fehler: ehrliche Meldung ohne Pfade
class Broken:
    def today_view(self):
        raise OSError("/geheim/pfad")
res = gym_tool.gym_today(Broken())
assert not res.success and "OSError" in res.error and "geheim" not in res.error

# Briefing: eigener Satz, das feste Ziel taucht nicht doppelt als "offenes Ziel" auf
now = datetime(2026, 11, 23, 7, 30)
store.set_plan([{"weekday": 0, "name": "Push", "exercises": [{"name": "Bank", "weight": 60, "sets": 3, "reps": 8}]}])
goals = [{"text": "Gym: Push", "done": False, "daily": True, "managed": "gym"}, {"text": "Lesen", "done": False, "daily": True}]
text = briefing.build_briefing(now, "Sir", gym=lambda: store.today_view(), goals=lambda: goals)
assert "Heute steht Push an, 1 Übung." in text and "Offenes Ziel für heute: Lesen." in text and "Gym: Push" not in text, text
assert text.index("Heute steht Push") < text.index("Offenes Ziel")
only = briefing.build_briefing(now, "Sir", goals=lambda: goals[:1])
assert "Offene" not in only and "Ziel" not in only, only
assert "Heute steht" not in briefing.build_briefing(now, "Sir", goals=lambda: goals)
# Abendfrage nennt das Gym-Ziel weiterhin als offen
assert "Gym: Push" in briefing.evening_text(goals, "Sir", datetime(2026, 11, 23, 20, 5))

# Aufgabe, Fahigkeit, Risiko, Remote-Stufe
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("GYM_TODAY")
assert [a.name for a in task.actions] == ["gym_today"] and task.actions[0].parameters == {}
assert risk.task_risk(task) == risk.SAFE and risk.ACTION_RISK["gym_today"] == risk.SAFE
ab = next(a for a in abilities.ABILITIES if a.id == "gym")
assert ab.tasks == ("GYM_TODAY",) and ab.default is True and "GYM_TODAY" not in guest.GUEST_TASKS
assert "gym" in remote_policy.LEVEL_ABILITIES["daily"]
gym.set_default_store(store)
assert action_executor.execute_action(Action("gym_today", {})).data["name"] == "Push"
src = open(PROJECT_DIR / "tools" / "gym_tool.py", encoding="utf-8").read().split('"""', 2)[2]
assert ".log(" not in src and "set_plan" not in src and "clear_log" not in src and "_save" not in src
print("ALL TESTS PASSED")
