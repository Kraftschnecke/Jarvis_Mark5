"""J.A.R.V.I.S. als Server ohne Fenster (Mark 5, Server S1).

Fuer einen Rechner, der immer an ist (kleiner Server, Raspberry Pi). Kein Browser-Fenster, kein Tray-Symbol, keine
Windows-Teile. Der Server hoert weiter nur auf 127.0.0.1; von aussen kommt man nur ueber Tailscale (siehe DESIGN_REMOTE.md).
Erinnerungen, Wecker, Timer und Hinweise melden sich ohne offene Seite per Push aufs Handy (notify.py, server_loop.py).

Aufruf:  python server_main.py [--port 8000]
         python server_main.py --test-push     schickt eine Test-Nachricht aufs Handy und beendet sich (Einrichtung pruefen)
         python server_main.py --pair-owner "PC Moritz"
                                               Kopplungslink fuer ein Geraet mit Vollzugriff (wie am PC). Nur hier im Server-Terminal
                                               moeglich, nie ueber die Weboberflaeche. 5 Minuten gueltig, einmal benutzbar.
         python server_main.py --pair-agent "PC Moritz"
                                               Code fuer den PC-Agent (DESIGN_GERAET.md): Der Agent auf dem PC loest ihn mit
                                               ``python pc_agent.py --pair CODE --server https://...`` ein. 5 Minuten, einmal benutzbar.
"""
import sys

import notify
import server
from server_loop import ServerLoop


def test_push(notifier):
    """Eine Test-Nachricht schicken und sagen, ob sie angenommen wurde. 0 = ok, 1 = nicht gesendet."""
    if not notifier.enabled:
        print("Push ist aus: NTFY_TOPIC fehlt in der .env oder ist ungueltig (16-64 Zeichen: Buchstaben, Ziffern, - und _).")
        return 1
    if notifier.send("Jarvis", "Test: Wenn du das liest, funktioniert der Push.", priority="high"):
        print("Test-Nachricht gesendet. Sie sollte gleich auf dem Handy erscheinen.")
        return 0
    print("Die Test-Nachricht ging nicht raus (kein Internet, falscher NTFY_SERVER oder NTFY_TOKEN?).")
    return 1


def pair_owner(argv, store=None, host=None):
    """Kopplungslink fuer ein Geraet mit Vollzugriff. 0 = Link ausgegeben, 1 = nicht moeglich."""
    import config
    host = config.REMOTE_HOST if host is None else host
    if not host:
        print("JARVIS_REMOTE_HOST fehlt in der .env (der Tailscale-Name dieses Servers, z. B. jarvis.tailabc.ts.net).")
        return 1
    index = argv.index("--pair-owner")
    name = argv[index + 1] if index + 1 < len(argv) and not argv[index + 1].startswith("--") else "Besitzer-Gerät"
    if store is None:
        import remote_auth
        store = remote_auth.DeviceStore()
    try:
        pairing = store.create_pairing(name, full=True)
    except OSError as error:
        print(f"Der Code konnte nicht gespeichert werden ({type(error).__name__}).")
        return 1
    print(f"Kopplung mit Vollzugriff fuer \"{pairing['name']}\" (5 Minuten gueltig, nur einmal benutzbar):")
    print(f"  https://{host}/pair#{pairing['code']}")
    print("Oeffne den Link auf dem Geraet, das Vollzugriff bekommen soll (Tailscale muss dort laufen). Der Server muss dafuer laufen.")
    return 0


def pair_agent(argv, store=None, host=None):
    """Kopplungscode fuer den PC-Agent. 0 = Code ausgegeben, 1 = nicht moeglich."""
    import config
    host = config.REMOTE_HOST if host is None else host
    if not host:
        print("JARVIS_REMOTE_HOST fehlt in der .env (der Tailscale-Name dieses Servers, z. B. jarvis.tailabc.ts.net).")
        return 1
    index = argv.index("--pair-agent")
    name = argv[index + 1] if index + 1 < len(argv) and not argv[index + 1].startswith("--") else "PC"
    if store is None:
        import remote_auth
        store = remote_auth.DeviceStore()
    try:
        pairing = store.create_pairing(name, agent=True)
    except OSError as error:
        print(f"Der Code konnte nicht gespeichert werden ({type(error).__name__}).")
        return 1
    print(f"Kopplung fuer den PC-Agent \"{pairing['name']}\" (5 Minuten gueltig, nur einmal benutzbar). Auf dem PC im Jarvis-Ordner eingeben:")
    print(f"  py pc_agent.py --pair {pairing['code']} --server https://{host}")
    print("Der Server muss dafuer laufen, Tailscale auf dem PC auch.")
    return 0


def enable_remote(httpd):
    """Im Server-Betrieb ist Remote (Zugang ueber Tailscale) der einzige Weg zur Oberflaeche: einschalten, wenn der Name eingetragen ist."""
    gate = httpd.remote
    if gate is not None and gate.host and not gate.active():
        gate.settings.set("remote", "enabled", True)
        print("Remote ist im Server-Betrieb eingeschaltet (Zugang nur ueber Tailscale und gekoppelte Geraete).")


def run(argv=None, notifier=None):
    notifier = notifier or notify.default_notifier()
    if argv is None:
        argv = sys.argv[1:]                     # so wie sie in der Eingabeaufforderung getippt wurden
    if "--test-push" in argv:
        return test_push(notifier)
    if "--pair-owner" in argv:
        return pair_owner(argv)
    if "--pair-agent" in argv:
        return pair_agent(argv)
    holder = {}

    def on_ready(httpd):
        enable_remote(httpd)
        loop = ServerLoop(httpd, notifier)
        loop.start()
        holder["loop"] = loop

    print(f"J.A.R.V.I.S. Server-Betrieb: Push {'AN' if notifier.enabled else 'AUS (NTFY_TOPIC fehlt in der .env)'}")
    try:
        server.main(argv, on_ready=on_ready, open_browser=False)
    finally:
        if "loop" in holder:
            holder["loop"].stop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
