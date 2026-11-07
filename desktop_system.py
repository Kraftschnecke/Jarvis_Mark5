"""Systemanbindung der Desktop-App (Mark 5, Step 4B.4): globaler Hotkey, Fenster nach vorn, Benachrichtigungen.

Alles Windows-spezifische (ctypes) steckt in kleinen Klassen, die sich in den Tests durch Attrappen ersetzen lassen.
Der Hotkey nutzt RegisterHotKey von Windows: Windows meldet nur genau diese Tastenkombination. Es wird nichts
mitgelesen (kein Tastatur-Hook) und es braucht kein zusaetzliches Paket.
Der Hotkey bringt nur das Fenster nach vorn. Er sendet nichts und fuehrt nichts aus.
"""
import json
import threading
import urllib.request

APP_TITLE = "J.A.R.V.I.S."

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "strg": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}
OFF_WORDS = ("", "off", "aus", "none")
MAX_NOTE_LENGTH = 60


def parse_hotkey(text):
    """'ctrl+space' -> (Modifier-Maske, virtueller Tastencode); None, wenn ausgeschaltet. ValueError bei Unsinn.

    Erlaubt sind Strg/Alt/Shift/Win plus eine Taste (Buchstabe, Ziffer, space, F1-F12). Mindestens ein Modifier,
    damit nie eine einzelne Taste abgefangen wird.
    """
    text = (text or "").strip().lower()
    if text in OFF_WORDS:
        return None
    parts = [part.strip() for part in text.split("+")]
    if len(parts) < 2 or "" in parts:
        raise ValueError("Hotkey braucht mindestens einen Modifier und eine Taste, z. B. ctrl+space")
    *modifier_names, key = parts
    mods = 0
    for name in modifier_names:
        if name not in MODIFIERS:
            raise ValueError(f"Unbekannter Modifier: {name}")
        mods |= MODIFIERS[name]
    if len(key) == 1 and key.isascii() and key.isalnum():
        code = ord(key.upper())
    elif key == "space":
        code = 0x20
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        code = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"Unbekannte Taste: {key}")
    return mods, code


class Win32Hotkeys:
    """RegisterHotKey + Nachrichtenschleife. Muss im selben Thread erzeugt und benutzt werden (ausser stop)."""

    HOTKEY_ID = 1

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.thread_id = None

    def register(self, mods, code):
        self.thread_id = self.kernel32.GetCurrentThreadId()
        return bool(self.user32.RegisterHotKey(None, self.HOTKEY_ID, mods | MOD_NOREPEAT, code))

    def next_event(self):
        """Blockiert bis der Hotkey gedrueckt wird (True) oder stop() aufgerufen wurde (False)."""
        message = self.wintypes.MSG()
        while True:
            result = self.user32.GetMessageW(self.ctypes.byref(message), None, 0, 0)
            if result <= 0:
                return False
            if message.message == WM_HOTKEY:
                return True

    def unregister(self):
        self.user32.UnregisterHotKey(None, self.HOTKEY_ID)

    def stop(self):
        if self.thread_id is not None:
            self.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


class HotkeyListener:
    def __init__(self, hotkey, callback, api_factory=Win32Hotkeys, log=print):
        self.parsed = parse_hotkey(hotkey)
        self.hotkey = hotkey
        self.callback = callback
        self.api_factory = api_factory
        self.log = log
        self.registered = False
        self.error = None
        self._api = None
        self._ready = threading.Event()
        self._thread = None

    def start(self):
        """Startet den Lauscher. True, wenn Windows die Kombination vergeben hat (False: ausgeschaltet oder belegt)."""
        if self.parsed is None:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self.registered

    def _run(self):
        try:
            self._api = self.api_factory()
            self.registered = bool(self._api.register(*self.parsed))
        except Exception as error:
            self.registered, self.error = False, error
        finally:
            self._ready.set()
        if not self.registered:
            return
        try:
            while self._api.next_event():
                try:
                    self.callback()
                except Exception as error:     # ein Fehler im Fenster-Code darf den Hotkey nicht beenden
                    self.log(f"Hotkey-Aktion fehlgeschlagen: {error}")
        finally:
            self._api.unregister()

    def stop(self):
        if self.registered and self._api is not None:
            self._api.stop()
            if self._thread is not None:
                self._thread.join(2)
        self.registered = False


class Win32Windows:
    """Fenster suchen und nach vorn holen."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.EnumWindows.argtypes = [self.enum_proc, wintypes.LPARAM]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    def title(self, hwnd):
        buffer = self.ctypes.create_unicode_buffer(256)
        self.user32.GetWindowTextW(hwnd, buffer, 256)
        return buffer.value

    def find(self, title):
        found = []

        def visit(hwnd, _):
            if self.user32.IsWindowVisible(hwnd) and self.title(hwnd) == title:
                found.append(hwnd)
                return False
            return True

        self.user32.EnumWindows(self.enum_proc(visit), 0)
        return found[0] if found else None

    def foreground_title(self):
        hwnd = self.user32.GetForegroundWindow()
        return self.title(hwnd) if hwnd else ""

    def bring_to_front(self, hwnd):
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        # Windows erlaubt "nach vorn" nur nach einer Eingabe: ein kurzer Alt-Tastendruck genuegt als Freigabe
        self.user32.keybd_event(0x12, 0, 0, 0)
        self.user32.keybd_event(0x12, 0, 2, 0)
        self.user32.SetForegroundWindow(hwnd)


def focus_window(title=APP_TITLE, windows=None):
    """Holt das Jarvis-Fenster nach vorn. True, wenn es eins gab."""
    windows = windows or Win32Windows()
    hwnd = windows.find(title)
    if not hwnd:
        return False
    windows.bring_to_front(hwnd)
    return True


def is_foreground(title=APP_TITLE, windows=None):
    windows = windows or Win32Windows()
    return windows.foreground_title() == title


def short_label(label):
    label = " ".join(str(label or "").split())
    return label if len(label) <= MAX_NOTE_LENGTH else label[:MAX_NOTE_LENGTH - 1] + "…"


def notification_for(ring):
    """(Titel, Text) fuer einen laeutenden Wecker/Timer. Nur der kurze Name, nie andere Inhalte."""
    label = short_label(ring.get("label"))
    if ring.get("kind") == "timer":
        return "Timer", f"Timer abgelaufen: {label}" if label else "Timer abgelaufen"
    return "Wecker", label or "Wecker"


class RingWatcher:
    """Fragt den eigenen Server (wie die Seite) nach laeutenden Weckern/Timern und meldet neue per Benachrichtigung."""

    def __init__(self, fetch, notify, is_foreground=lambda: False, interval=2.0):
        self.fetch = fetch
        self.notify = notify
        self.is_foreground = is_foreground
        self.interval = interval
        self.seen = set()
        self.stop_event = threading.Event()
        self._thread = None

    def check(self):
        rings = (self.fetch() or {}).get("ringing") or []
        current = {ring["id"] for ring in rings if isinstance(ring, dict) and "id" in ring}
        fresh = [ring for ring in rings if isinstance(ring, dict) and ring.get("id") in current - self.seen]
        self.seen = current                    # beendete Eintraege vergessen, damit der Satz klein bleibt
        if fresh and not self.is_foreground():  # Ist das Fenster vorn, zeigt die Seite es schon selbst
            for ring in fresh:
                self.notify(*notification_for(ring))
        return fresh

    def _run(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.check()
            except Exception:                  # Server kurz weg oder Benachrichtigung abgelehnt: naechste Runde
                pass

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.stop_event.set()


def fetch_ringing(base_url):
    def fetch():
        with urllib.request.urlopen(f"{base_url}/api/ringing", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    return fetch
