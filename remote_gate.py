"""Pforte fuer Anfragen vom Handy (Mark 5, Remote R2). Siehe DESIGN_REMOTE.md.

Der Server hoert nur auf 127.0.0.1. Tailscale (`tailscale serve`) reicht Anfragen aus dem privaten Netz lokal durch, mit dem
Namen des PCs im Host-Header. Diese Pforte entscheidet pro Anfrage:
    "local"  -> normaler Zugriff am PC (localhost), wie bisher
    "remote" -> Anfrage ueber den eingetragenen Remote-Namen: nur mit Cookie eines gekoppelten Geraets
    None     -> abgelehnt (fremder Name, Remote aus, Anfrage nicht von dieser Maschine)
"""
import re
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlparse

import remote_policy
from remote_auth import TOKEN_LIFETIME, UsageLimits

COOKIE_NAME = "jarvis_device"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")
LOCAL_ORIGIN_HOSTS = ("localhost", "127.0.0.1", "::1")
LOOPBACK_PEERS = ("127.0.0.1", "::1")
PAIRING_SOURCE = "remote-pairing"        # ein gemeinsamer Zaehler: die Quelle hinter dem Proxy laesst sich nicht faelschungssicher erkennen
MAX_COOKIE_HEADER = 2000

# Einstellungen, die das Handy sehen darf (Darstellung, Anrede, Stimme, Anzeige). Alles andere bleibt am PC.
SETTINGS_FOR_REMOTE = ("appearance", "voice", "widgets", "alarm", "focus", "briefing", "goals", "hints", "news")


class RemoteGate:
    def __init__(self, host, store, settings_manager):
        self.host = (host or "").strip().lower()
        self.store = store
        self.settings = settings_manager
        self.limits = UsageLimits()

    # --- Schalter ---------------------------------------------------------
    def active(self):
        """Remote ist nur an, wenn ein Name eingetragen ist UND es in den Einstellungen eingeschaltet wurde."""
        return bool(self.host) and self.settings.get("remote", "enabled", False) is True

    def levels(self):
        return remote_policy.normalize_levels({level: self.settings.get("remote", level) for level in remote_policy.LEVELS})

    def refresh_limits(self):
        """Grenzen live aus den Einstellungen uebernehmen (0 = unbegrenzt)."""
        for attribute, key in (("max_messages", "max_messages"), ("max_daily", "max_ai_per_day")):
            value = self.settings.get("remote", key, 0)
            setattr(self.limits, attribute, value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0)

    # --- Anfrage einordnen ---------------------------------------------------
    def request_kind(self, host_header, peer_ip):
        name = (host_header or "").rsplit(":", 1)[0].lower()
        if name in LOCAL_HOSTS:
            return "local"
        if self.active() and name == self.host and peer_ip in LOOPBACK_PEERS:
            return "remote"
        return None

    def origin_ok(self, kind, origin):
        """Eine fremde Webseite darf Jarvis nicht fernsteuern. Remote verlangt den Origin der eigenen Adresse."""
        if kind == "remote":
            if not origin:
                return False
            try:
                parsed = urlparse(origin)
                port = parsed.port
            except ValueError:
                return False
            return parsed.scheme == "https" and parsed.hostname == self.host and port in (None, 443)
        if origin is None:
            return True
        try:
            return urlparse(origin).hostname in LOCAL_ORIGIN_HOSTS
        except ValueError:
            return False

    def device_from_cookie(self, cookie_header):
        """Das gekoppelte Geraet zum Cookie dieser Anfrage, sonst None."""
        if not cookie_header or len(cookie_header) > MAX_COOKIE_HEADER:
            return None
        try:
            jar = SimpleCookie()
            jar.load(cookie_header)
        except CookieError:
            return None
        morsel = jar.get(COOKIE_NAME)
        return self.store.authenticate(morsel.value) if morsel else None

    # --- Cookie -------------------------------------------------------------
    @staticmethod
    def set_cookie_header(token):
        return f"{COOKIE_NAME}={token}; Path=/; Max-Age={TOKEN_LIFETIME}; Secure; HttpOnly; SameSite=Strict"

    # --- gefilterte Einstellungen fuers Handy -----------------------------------
    def settings_for_remote(self, state):
        """Aus der vollen Einstellungsantwort das machen, was das Handy sehen darf."""
        full = state.get("settings") or {}
        visible = {category: full[category] for category in SETTINGS_FOR_REMOTE if category in full}
        visible["jarvis"] = {"address": (full.get("jarvis") or {}).get("address", "Sir")}
        return {
            "guest": False,
            "remote": True,
            "settings": visible,
            "abilities": [],
            "usage": None,
            "about": {"version": (state.get("about") or {}).get("version", ""), "system": ""},
        }
