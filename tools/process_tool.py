import psutil
from tools.tool_result import ToolResult


_remote = None


def set_remote(remote):
    """Server-Betrieb (S6, G6): die Liste kommt vom PC-Agent ("processes.list"); None = dieser Rechner."""
    global _remote
    _remote = remote


def get_running_programs():
    if _remote is not None:
        return _remote.call("processes.list", {})
    programs = []

    for process in psutil.process_iter(["name"]):
        try:
            name = process.info["name"]
            if name and name not in programs:
                programs.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return ToolResult(
        success=True,
        data=programs
    )