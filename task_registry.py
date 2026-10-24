class TaskRegistry:
    """Alle Aufgaben. Mit ``is_enabled`` (task_type -> bool) werden ausgeschaltete Aufgaben
    ueberall unsichtbar: ``get`` liefert sie nicht, ``get_all`` zaehlt sie nicht (Router, Planer,
    Faehigkeitenliste, Ausfuehrung). ``get_disabled`` zeigt sie getrennt."""

    def __init__(self, is_enabled=None):
        self.tasks = {}
        self.is_enabled = is_enabled

    def register(self, task):
        self.tasks[task.task_type] = task

    def _on(self, task_type):
        return self.is_enabled is None or bool(self.is_enabled(task_type))

    def get(self, task_type):
        task = self.tasks.get(task_type)
        return task if task is not None and self._on(task_type) else None

    def get_all(self):
        return [task for task in self.tasks.values() if self._on(task.task_type)]

    def get_disabled(self):
        return [task for task in self.tasks.values() if not self._on(task.task_type)]

    def is_disabled(self, task_type):
        return task_type in self.tasks and not self._on(task_type)
