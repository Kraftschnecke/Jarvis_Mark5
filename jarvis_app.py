"""J.A.R.V.I.S. als Desktop-App (Mark 5, Step 4B.3).

Startet den Server im selben Prozess, oeffnet ein eigenes App-Fenster (Edge/Chrome im --app-Modus,
ohne Adressleiste) und legt ein Symbol in den Infobereich (Tray). Fenster schliessen = Jarvis laeuft weiter,
"Beenden" im Tray stoppt alles sauber. Die Sprachfunktionen bleiben die des Browsers (deshalb Edge/Chrome statt
eines eingebetteten Fensters). Alle Windows-Teile sind austauschbar, damit die Logik ohne Windows testbar ist.

Aufruf: pyw jarvis_app.py   (--background = ohne Fenster starten, so startet der Autostart)
"""
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = PROJECT_DIR / ".jarvis_app_profile"
ICON_FILE = PROJECT_DIR / "web" / "icon-192.png"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "JARVIS"


def find_browser(env=None, exists=os.path.isfile):
    """Edge (auf Windows immer da) oder Chrome; None, wenn keiner gefunden wird."""
    env = os.environ if env is None else env
    roots = [env.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA") if env.get(k)]
    relative = [
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Google/Chrome/Application/chrome.exe"),
    ]
    for rel in relative:
        for root in roots:
            candidate = str(Path(root) / rel)
            if exists(candidate):
                return candidate
    return None


def window_command(browser, url, profile_dir=PROFILE_DIR):
    """Eigenes Profil: Mikrofon-Freigabe bleibt gespeichert und das Fenster ist ein eigener Prozess."""
    return [browser, f"--app={url}", f"--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check"]


def port_in_use(host, port, connect=socket.create_connection):
    try:
        connection = connect((host, port), timeout=0.5)
    except OSError:
        return False
    connection.close()
    return True


def wait_until_up(url, timeout=30.0, fetch=None, sleep=time.sleep, clock=time.monotonic):
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=2).read(1))
    deadline = clock() + timeout
    while True:
        try:
            fetch(url)
            return True
        except Exception:
            if clock() >= deadline:
                return False
            sleep(0.3)


def autostart_command(python_exe=None, script=None, exists=os.path.isfile):
    """pythonw.exe (kein Konsolenfenster), wenn vorhanden."""
    python_exe = python_exe or sys.executable
    pythonw = str(Path(python_exe).with_name("pythonw.exe"))
    exe = pythonw if exists(pythonw) else python_exe
    script = script or str(PROJECT_DIR / "jarvis_app.py")
    return f'"{exe}" "{script}" --background'


class WindowsRegistry:
    """Run-Schluessel des aktuellen Benutzers (HKCU, braucht keine Adminrechte)."""

    def _key(self, write):
        import winreg
        access = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
        return winreg, winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)

    def get(self, name):
        winreg, key = self._key(False)
        try:
            return winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)

    def set(self, name, value):
        winreg, key = self._key(True)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(key)

    def delete(self, name):
        winreg, key = self._key(True)
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)


class Autostart:
    def __init__(self, registry, command):
        self.registry = registry
        self.command = command

    def is_enabled(self):
        return self.registry.get(RUN_NAME) == self.command

    def enable(self):
        self.registry.set(RUN_NAME, self.command)

    def disable(self):
        self.registry.delete(RUN_NAME)

    def toggle(self):
        if self.is_enabled():
            self.disable()
        else:
            self.enable()
        return self.is_enabled()


class ServerHandle:
    """Merkt sich den laufenden Server (aus server.main) und kann ihn sauber anhalten."""

    def __init__(self):
        self.httpd = None
        self.ready = threading.Event()

    def on_ready(self, httpd):
        self.httpd = httpd
        self.ready.set()

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()             # serve_forever endet, main() raeumt selbst auf


class DesktopApp:
    """Logik der App; Fenster, Server und Tray werden hineingereicht."""

    def __init__(self, url, browser, spawn, stop_server, autostart=None, focus=None):
        self.url = url
        self.browser = browser
        self.spawn = spawn
        self.stop_server = stop_server
        self.autostart = autostart
        self.focus = focus                    # callable() -> True, wenn ein Jarvis-Fenster nach vorn geholt wurde
        self.window = None
        self.on_quit = None                   # z. B. tray.stop
        self.quit_event = threading.Event()

    def open_window(self):
        if self.focus is not None and self.focus():
            return False                      # es gibt schon ein Fenster: nur nach vorn geholt
        if self.window is not None and self.window.poll() is None:
            return False                      # Fenster ist schon offen
        if self.browser is None:
            import webbrowser
            webbrowser.open(self.url)         # Notausgang: normaler Browser
            return True
        self.window = self.spawn(window_command(self.browser, self.url))
        return True

    def window_open(self):
        return self.window is not None and self.window.poll() is None

    def toggle_autostart(self):
        return self.autostart.toggle() if self.autostart else False

    def quit(self):
        if self.quit_event.is_set():
            return
        self.quit_event.set()
        self.stop_server()
        if self.on_quit is not None:
            self.on_quit()

    def menu(self):
        """Eintraege fuers Tray-Menue: (Text, Aktion, ist_angehakt_oder_None)."""
        items = [("Jarvis öffnen", self.open_window, None)]
        if self.autostart:
            items.append(("Mit Windows starten", self.toggle_autostart, self.autostart.is_enabled))
        items.append(("Beenden", self.quit, None))
        return items

    def wait_for_window_close(self, poll=0.5, sleep=time.sleep):
        """Ohne Tray: Fenster zu = Jarvis beenden."""
        while self.window_open() and not self.quit_event.is_set():
            sleep(poll)


def make_tray(app, icon_file=ICON_FILE):
    """pystray-Symbol oder None, wenn pystray/Pillow fehlen."""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return None
    # pystray prueft die Zahl der Parameter: Aktion = genau (icon, item), checked = genau (item). Keine Default-Argumente!
    def menu_action(action):
        return lambda icon, item: action()

    def menu_checked(check):
        return lambda item: check()

    items = []
    for text, action, checked in app.menu():
        kwargs = {"default": True} if action == app.open_window else {}
        if checked is not None:
            kwargs["checked"] = menu_checked(checked)
        items.append(pystray.MenuItem(text, menu_action(action), **kwargs))
    return pystray.Icon("jarvis", Image.open(icon_file), "J.A.R.V.I.S.", pystray.Menu(*items))


def wait_for_quit(app, wait=None):
    """Haelt den Hauptthread fuer Python wach, damit Strg+C in der Konsole sauber beendet."""
    wait = wait or (lambda: app.quit_event.wait(0.5))
    try:
        while not wait():
            pass
    except KeyboardInterrupt:
        app.quit()


def start_system_features(app, hotkey_text, notify, is_foreground, fetch,
                          listener_factory=None, watcher_factory=None, log=print):
    """Hotkey und Benachrichtigungen starten (Step 4B.4). Gibt die Stop-Funktionen zurueck; Fehler bremsen den Start nie."""
    import desktop_system
    listener_factory = listener_factory or desktop_system.HotkeyListener
    watcher_factory = watcher_factory or desktop_system.RingWatcher
    stoppers = []
    try:
        listener = listener_factory(hotkey_text, app.open_window)
    except ValueError as error:
        log(f"Hinweis: Hotkey '{hotkey_text}' ist ungueltig ({error}). Es gibt keinen Hotkey.")
        listener = None
    if listener is not None and listener.parsed is not None:
        if listener.start():
            log(f"Hotkey {hotkey_text} ist aktiv: bringt das Jarvis-Fenster nach vorn.")
            stoppers.append(listener.stop)
        else:
            log(f"Hinweis: Hotkey {hotkey_text} konnte nicht vergeben werden (von einem anderen Programm belegt?).")
    watcher = watcher_factory(fetch, notify, is_foreground)
    watcher.start()
    stoppers.append(watcher.stop)
    return stoppers


def run(argv=None):
    import argparse
    import server
    from config import HOTKEY, SERVER_HOST, SERVER_PORT
    import desktop_system

    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Desktop-App")
    parser.add_argument("--background", action="store_true", help="ohne Fenster starten (Autostart)")
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    args = parser.parse_args(argv)
    url = f"http://localhost:{args.port}"
    browser = find_browser()
    spawn = lambda cmd: subprocess.Popen(cmd)

    if port_in_use(SERVER_HOST, args.port):
        # Jarvis laeuft schon (zweiter Start): nur das Fenster oeffnen, nichts doppelt starten
        focus = desktop_system.focus_window if sys.platform == "win32" else None
        DesktopApp(url, browser, spawn, lambda: None, focus=focus).open_window()
        return 0

    handle = ServerHandle()
    stop_server = handle.stop

    thread = threading.Thread(
        target=server.main,
        kwargs={"argv": ["--port", str(args.port)], "on_ready": handle.on_ready, "open_browser": False},
    )
    thread.start()
    if not handle.ready.wait(60) or not wait_until_up(url):
        print("Jarvis konnte nicht gestartet werden.")
        stop_server()
        thread.join(10)
        return 1

    autostart = Autostart(WindowsRegistry(), autostart_command()) if sys.platform == "win32" else None
    focus = desktop_system.focus_window if sys.platform == "win32" else None
    app = DesktopApp(url, browser, spawn, stop_server, autostart, focus=focus)
    if not args.background:
        app.open_window()

    try:
        tray = make_tray(app)
    except Exception as error:                 # Tray ist nur Komfort: nie den Start verhindern
        print(f"Hinweis: Tray-Symbol konnte nicht erstellt werden ({error}).")
        tray = None
    stoppers = []
    if sys.platform == "win32":
        def notify(title, text):
            if tray is not None:
                tray.notify(text, title)

        stoppers = start_system_features(
            app, HOTKEY, notify, desktop_system.is_foreground, desktop_system.fetch_ringing(url))

    def on_quit():
        for stopper in stoppers:
            try:
                stopper()
            except Exception:
                pass
        if tray is not None:
            tray.stop()

    app.on_quit = on_quit
    if tray is not None:
        tray.run_detached()                    # Tray laeuft im eigenen Thread, der Hauptthread bleibt ansprechbar
        wait_for_quit(app)                     # bis "Beenden" im Tray oder Strg+C
    else:
        print("Hinweis: pystray/Pillow fehlen, kein Tray-Symbol. Fenster schliessen beendet Jarvis.")
        if args.background:
            app.open_window()
        app.wait_for_window_close()
        app.quit()
    thread.join(15)
    return 0


if __name__ == "__main__":
    sys.exit(run())
