from task import Task
from action import Action


def create_get_time_task():
    task = Task(
        "GET_TIME",
        "Aktuelle Uhrzeit ermitteln"
    )

    task.add_action(
        Action("get_current_time")
    )

    return task


def create_search_web_task():
    task = Task(
        "SEARCH_WEB",
        "Eine Websuche durchführen"
    )

    task.add_action(
        Action(
            "search_web",
            {"query": None}
        )
    )

    return task


def create_get_date_task():
    task = Task(
        "GET_DATE",
        "Aktuelles Datum ermitteln"
    )

    task.add_action(
        Action("get_current_date")
    )

    return task


def create_calculate_task():
    task = Task(
        "CALCULATE",
        "Eine mathematische Berechnung durchführen (Grundrechenarten, Potenzen, Klammern, Prozent)"
    )

    task.add_action(
        Action(
            "calculate",
            {
                "expression": {
                    "description": "Der Rechenausdruck mit Zahlen, + - * / ** (Potenz), Klammern und % direkt hinter einer Zahl, z.B. 15 Prozent von 80 als 80*15% und 80 plus 19 Prozent als 80*(1+19%). Nur Zahlen und Rechenzeichen, kein Text",
                    "type": "string"
                }
            }
        )
    )

    return task


def create_get_system_info_task():
    task = Task(
        "GET_SYSTEM_INFO",
        "Informationen über den eigenen Computer ermitteln: Prozessor, Arbeitsspeicher, Festplatten, aktuelle Auslastung (CPU, RAM), Akku, Laufzeit und die größten laufenden Programme"
    )

    task.add_action(
        Action(
            "get_system_info"
        )
    )

    return task


def create_open_file_task():
    task = Task(
        "OPEN_FILE",
        "Eine Datei auf dem Computer öffnen"
    )

    task.add_action(
        Action(
            "open_file",
            {"path": None}
        )
    )

    return task


def create_get_running_programs_task():
    task = Task(
        "GET_RUNNING_PROGRAMS",
        "Laufende Programme auf dem Computer ermitteln"
    )

    task.add_action(
        Action(
            "get_running_programs"
        )
    )

    return task


def create_set_volume_task():
    task = Task(
        "SET_VOLUME",
        "Die Systemlautstärke einstellen"
    )

    task.add_action(
        Action(
            "set_volume",
            {"percentage": None}
        )
    )

    return task


def create_find_program_task():
    task = Task(
        "FIND_PROGRAM",
        "Ein Programm auf dem Computer finden"
    )

    task.add_action(
        Action(
            "find_program",
            {"program": None}
        )
    )

    return task


def create_start_program_task():
    task = Task(
        "START_PROGRAM",
        "Ein Programm auf dem Computer öffnen oder starten"
    )

    task.add_action(
        Action(
            "find_program",
            {"program": None}
        )
    )

    task.add_action(
        Action(
            "open_program",
            {
                "path": {
                    "source": "previous_result"
                }
            }
        )
    )

    return task


def create_start_timer_task():
    task = Task(
        "START_TIMER",
        "Einen Timer starten"
    )
    task.add_action(
        Action(
            "start_timer",
            {
                "value": {
                    "description": "Die Dauer des Timers als Zahl",
                    "type": "number"
                },
                "unit": {
                    "description": "Die Zeiteinheit, z.B.: seconds, minutes oder hours",
                    "type": "string"
                },
                "name": {
                    "description": "Kurzer Name des Timers, z.B. Nudeln. Nennt der Nutzer keinen, nimm Timer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_list_timers_task():
    task = Task(
        "LIST_TIMERS",
        "Zeigen, welche Timer gerade laufen und wie lange noch"
    )
    task.add_action(Action("list_timers", {}))
    return task


def create_cancel_timer_task():
    task = Task(
        "CANCEL_TIMER",
        "Einen laufenden Timer abbrechen"
    )
    task.add_action(
        Action(
            "cancel_timer",
            {
                "name": {
                    "description": "Name des Timers, der abgebrochen werden soll. Sagt der Nutzer stattdessen die Nummer, kuerzester, laengster oder alle, schreibe genau das (z.B. 2, kuerzester). Nennt er nichts, nimm Timer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_add_calendar_event_task():
    task = Task(
        "ADD_CALENDAR_EVENT",
        "Einen Termin in den Kalender eintragen, auch wiederkehrend (jeden Dienstag, für die nächsten 8 Wochen, jährlich zum Geburtstag)"
    )
    task.add_action(
        Action(
            "add_calendar_event",
            {
                "title": {
                    "description": "Kurzer Titel des Termins, z.B. Zahnarzt",
                    "type": "string"
                },
                "date": {
                    "description": "Das Datum als YYYY-MM-DD. Rechne Angaben wie morgen, uebermorgen oder Freitag anhand des heutigen Datums aus",
                    "type": "string"
                },
                "time": {
                    "description": "Die Uhrzeit als HH:MM (24 Stunden). Nennt der Nutzer keine, schreibe ganztaegig",
                    "type": "string"
                },
                "repeat": {
                    "description": "Nur wenn sich der Eintrag wiederholt: daily, weekly, monthly oder yearly. Jeden Dienstag ist weekly, das Datum ist dann der erste Dienstag. Sonst leer lassen",
                    "type": "string"
                },
                "interval": {
                    "description": "Abstand der Wiederholung, z.B. 2 für alle zwei Wochen. Leer lassen für jedes Mal",
                    "type": "string"
                },
                "count": {
                    "description": "Wie oft der Eintrag insgesamt stattfindet, der erste mitgezählt, z.B. 8 bei für die nächsten 8 Wochen. Leer lassen, wenn der Nutzer ein Enddatum oder gar kein Ende nennt",
                    "type": "string"
                },
                "until": {
                    "description": "Letzter Tag der Wiederholung als YYYY-MM-DD, nur wenn der Nutzer ein Enddatum nennt (bis Weihnachten). Sonst leer lassen",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_list_calendar_events_task():
    task = Task(
        "LIST_CALENDAR_EVENTS",
        "Kalender-Termine zeigen: was an einem Tag ansteht oder die naechsten Termine"
    )
    task.add_action(
        Action(
            "list_calendar_events",
            {
                "date": {
                    "description": "Das Datum als YYYY-MM-DD (Angaben wie heute oder morgen anhand des heutigen Datums ausrechnen). Fragt der Nutzer allgemein nach den naechsten Terminen, schreibe naechste",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_get_weather_task():
    task = Task(
        "GET_WEATHER",
        "Das Wetter für einen Ort nennen: aktuell, heute oder die Vorhersage für die nächsten Tage"
    )
    task.add_action(
        Action(
            "get_weather",
            {
                "place": {
                    "description": "Name des Ortes, z.B. Vaxjo. Nennt der Nutzer keinen Ort, schreibe heimat",
                    "type": "string"
                },
                "day": {
                    "description": "Der Tag: heute, morgen, uebermorgen oder ein Datum als YYYY-MM-DD (hoechstens 7 Tage voraus, anhand des heutigen Datums ausrechnen). Nennt der Nutzer keinen Tag, schreibe heute",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_get_news_task():
    task = Task(
        "GET_NEWS",
        "Aktuelle Schlagzeilen aus den eingeschalteten News-Quellen nennen (auf Wunsch zu einem Thema) und auf Nachfrage zusammenfassen"
    )
    task.add_action(
        Action(
            "get_news",
            {
                "source": {
                    "description": "Die Quelle: tagesschau, heise, spiegel, sportschau, espn_nhl (NHL, englisch), oilersnation (Oilers, englisch), gnews (Google-News-Suche zu einem Thema) oder bbc. Nennt der Nutzer keine, schreibe alle",
                    "type": "string"
                },
                "topic": {
                    "description": "Ein Stichwort, nach dem die Schlagzeilen gefiltert werden. Fragt der Nutzer allgemein nach den News, schreibe alle",
                    "type": "string"
                },
                "count": {
                    "description": "Wie viele Schlagzeilen (1 bis 10). Nennt der Nutzer keine Zahl, schreibe 5",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_read_page_task():
    task = Task(
        "READ_PAGE",
        "Den Text einer Webseite oder eines Nachrichten-Artikels lesen, um ihn zusammenzufassen oder Fragen dazu zu beantworten"
    )
    task.add_action(
        Action(
            "read_page",
            {
                "item": {
                    "description": "Die Nummer eines Artikels aus der zuletzt genannten Nachrichten-Liste, z.B. 3 für den dritten Artikel. Nennt der Nutzer keine Nummer, schreibe leer",
                    "type": "string"
                },
                "url": {
                    "description": "Ein Link (https://...), den der Nutzer selbst genannt hat. Erfinde nie einen Link. Wird eine Nummer benutzt oder nennt der Nutzer keinen Link, schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_convert_task():
    task = Task(
        "CONVERT",
        "Einheiten oder Währungen umrechnen, z.B. Kilometer in Meilen, Celsius in Fahrenheit, Euro in Dollar"
    )
    task.add_action(
        Action(
            "convert",
            {
                "value": {
                    "description": "Die Zahl, die umgerechnet werden soll, nur als Ziffern, z.B. 100 oder 36.6. Nennt der Nutzer keine Zahl, schreibe 1",
                    "type": "string"
                },
                "from_unit": {
                    "description": "Die Ausgangseinheit oder Währung, z.B. km, Meilen, Celsius, Pfund, Euro oder USD",
                    "type": "string"
                },
                "to_unit": {
                    "description": "Die Zieleinheit oder Währung, z.B. mi, Kilometer, Fahrenheit, Gramm, Dollar oder EUR",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_get_world_time_task():
    task = Task(
        "GET_WORLD_TIME",
        "Die aktuelle Uhrzeit und das Datum an einem anderen Ort der Welt nennen (Zeitzonen, Zeitunterschied)"
    )
    task.add_action(
        Action(
            "get_world_time",
            {
                "place": {
                    "description": "Name des Ortes oder der Stadt, z.B. Edmonton oder Tokio. Statt eines Ortes geht auch eine Zeitzone wie UTC oder Europe/Stockholm",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_wiki_lookup_task():
    task = Task(
        "WIKI_LOOKUP",
        "Etwas in Wikipedia nachschlagen: eine Person, einen Ort, ein Ereignis oder einen Begriff erklären (Wer war ..., Was ist ...)"
    )
    task.add_action(
        Action(
            "wiki_lookup",
            {
                "topic": {
                    "description": "Der Begriff, die Person oder der Ort, nur das Stichwort ohne Fragewort, z.B. Hermann Hesse oder Quasar",
                    "type": "string"
                },
                "language": {
                    "description": "Die Sprache der Wikipedia: de oder en. Nennt der Nutzer keine, schreibe de",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_translate_task():
    task = Task(
        "TRANSLATE",
        "Einen Text oder eine Wendung in eine andere Sprache übersetzen (Wie sagt man ... auf Japanisch, Übersetze ins Englische)"
    )
    task.add_action(
        Action(
            "translate",
            {
                "text": {
                    "description": "Der Text, der übersetzt werden soll, genau so wie der Nutzer ihn nennt, ohne die Übersetzungsaufforderung",
                    "type": "string"
                },
                "target_language": {
                    "description": "Die Zielsprache, z.B. Englisch, Japanisch oder en",
                    "type": "string"
                },
                "source_language": {
                    "description": "Die Ausgangssprache, nur wenn der Nutzer sie nennt, sonst leer lassen",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_set_reminder_task():
    task = Task(
        "SET_REMINDER",
        "Eine Erinnerung zu einer Uhrzeit stellen, auch wiederkehrend (Erinnere mich um 19 Uhr an ..., jeden Montag um 8 Uhr). Für Zeiträume wie in 10 Minuten nimm stattdessen einen Timer"
    )
    task.add_action(
        Action(
            "set_reminder",
            {
                "text": {
                    "description": "Woran erinnert werden soll, kurz, z.B. Wäsche aufhängen",
                    "type": "string"
                },
                "date": {
                    "description": "Das Datum als YYYY-MM-DD (Angaben wie morgen oder Freitag anhand des heutigen Datums ausrechnen). Nennt der Nutzer kein Datum, lass es leer",
                    "type": "string"
                },
                "time": {
                    "description": "Die Uhrzeit als HH:MM (24 Stunden). 1900 oder 19 Uhr bedeutet 19:00",
                    "type": "string"
                },
                "repeat": {
                    "description": "Nur wenn sich der Eintrag wiederholt: daily, weekly, monthly oder yearly. Jeden Dienstag ist weekly, das Datum ist dann der erste Dienstag. Sonst leer lassen",
                    "type": "string"
                },
                "interval": {
                    "description": "Abstand der Wiederholung, z.B. 2 für alle zwei Wochen. Leer lassen für jedes Mal",
                    "type": "string"
                },
                "count": {
                    "description": "Wie oft der Eintrag insgesamt stattfindet, der erste mitgezählt, z.B. 8 bei für die nächsten 8 Wochen. Leer lassen, wenn der Nutzer ein Enddatum oder gar kein Ende nennt",
                    "type": "string"
                },
                "until": {
                    "description": "Letzter Tag der Wiederholung als YYYY-MM-DD, nur wenn der Nutzer ein Enddatum nennt (bis Weihnachten). Sonst leer lassen",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_list_reminders_task():
    task = Task(
        "LIST_REMINDERS",
        "Die offenen Erinnerungen zeigen (Welche Erinnerungen habe ich?)"
    )
    task.add_action(Action("list_reminders"))
    return task


def create_cancel_reminder_task():
    task = Task(
        "CANCEL_REMINDER",
        "Eine Erinnerung löschen (nach Nummer oder Stichwort) oder alle Erinnerungen löschen"
    )
    task.add_action(
        Action(
            "cancel_reminder",
            {
                "which": {
                    "description": "Die Nummer aus der Liste der Erinnerungen (1 = die nächste), ein Stichwort aus dem Text oder alle",
                    "type": "string"
                },
                "scope": {
                    "description": "Bei einer wiederkehrenden Erinnerung: series, wenn die ganze Serie enden soll (nicht mehr wiederholen, alle Termine). Sonst next, das löscht nur den kommenden Termin",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_set_alarm_task():
    task = Task(
        "SET_ALARM",
        "Einen Wecker auf eine Uhrzeit stellen, auch täglich oder werktags (Weck mich um 6:30, Wecker jeden Werktag um 7). Er läutet, bis der Nutzer ihn ausschaltet. Für Zeiträume wie in 10 Minuten nimm stattdessen einen Timer"
    )
    task.add_action(
        Action(
            "set_alarm",
            {
                "time": {
                    "description": "Die Uhrzeit als HH:MM (24 Stunden). 630 oder 6:30 Uhr bedeutet 06:30",
                    "type": "string"
                },
                "date": {
                    "description": "Das Datum als YYYY-MM-DD (morgen, Freitag usw. anhand des heutigen Datums ausrechnen). Nennt der Nutzer kein Datum, lass es leer: dann gilt die nächste passende Uhrzeit",
                    "type": "string"
                },
                "label": {
                    "description": "Nur wenn der Nutzer dem Wecker einen Namen gibt (zum Beispiel Zug erwischen). Sonst leer lassen",
                    "type": "string"
                },
                "repeat": {
                    "description": "Nur wenn der Wecker sich wiederholt: daily (jeden Tag), weekdays (werktags, Montag bis Freitag), weekly, monthly oder yearly. Sonst leer lassen",
                    "type": "string"
                },
                "interval": {
                    "description": "Abstand der Wiederholung, z.B. 2 für jede zweite Woche. Leer lassen für jedes Mal",
                    "type": "string"
                },
                "count": {
                    "description": "Wie oft der Wecker insgesamt klingelt, der erste mitgezählt (für die nächsten 5 Tage ist 5). Leer lassen bei Enddatum oder ohne Ende",
                    "type": "string"
                },
                "until": {
                    "description": "Letzter Tag der Wiederholung als YYYY-MM-DD, nur wenn der Nutzer ein Enddatum nennt. Sonst leer lassen",
                    "type": "string"
                },
                "briefing": {
                    "description": "ja, wenn der Nutzer beim Ausschalten Termine und Wetter vorgelesen haben will, nein, wenn ausdrücklich nicht. Sonst leer lassen",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_get_briefing_task():
    task = Task(
        "GET_BRIEFING",
        "Das Tagesbriefing geben: Datum, Termine, Erinnerungen, Wetter, Ziele, offene Timer und Schlagzeilen (Briefing, Guten-Morgen-Überblick, Was steht heute an?)"
    )
    task.add_action(Action("get_briefing"))
    return task


def create_list_alarms_task():
    task = Task(
        "LIST_ALARMS",
        "Die gestellten Wecker zeigen (Welche Wecker habe ich gestellt?)"
    )
    task.add_action(Action("list_alarms"))
    return task


def create_cancel_alarm_task():
    task = Task(
        "CANCEL_ALARM",
        "Einen gestellten Wecker löschen (nach Nummer oder Name) oder alle Wecker löschen. Das ist nicht das Ausschalten eines läutenden Weckers"
    )
    task.add_action(
        Action(
            "cancel_alarm",
            {
                "which": {
                    "description": "Die Nummer aus der Liste der Wecker (1 = der nächste), ein Name oder alle",
                    "type": "string"
                },
                "scope": {
                    "description": "Bei einem wiederkehrenden Wecker: series, wenn der Wecker gar nicht mehr klingeln soll. Sonst next, das löscht nur das nächste Klingeln",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_stop_ringing_task():
    task = Task(
        "STOP_RINGING",
        "Einen gerade läutenden Wecker oder Timer ausschalten (Wecker aus, Timer aus, Stopp) oder schlummern lassen (noch 10 Minuten). Nur für das, was gerade klingelt"
    )
    task.add_action(
        Action(
            "stop_ringing",
            {
                "what": {
                    "description": "alarm für einen Wecker, timer für einen Timer. Leer lassen, wenn alles ausgehen soll",
                    "type": "string"
                },
                "snooze_minutes": {
                    "description": "Nur wenn der Nutzer weiterschlafen will (schlummern, noch 10 Minuten): nach so vielen Minuten klingelt es wieder. Sonst leer lassen",
                    "type": "string"
                }
            }
        )
    )
    return task


def register_all_tasks(registry):
    registry.register(create_get_time_task())
    registry.register(create_get_date_task())
    registry.register(create_calculate_task())
    registry.register(create_convert_task())
    registry.register(create_get_system_info_task())
    registry.register(create_open_file_task())
    registry.register(create_get_running_programs_task())
    registry.register(create_set_volume_task())
    registry.register(create_find_program_task())
    registry.register(create_start_program_task())
    registry.register(create_start_timer_task())
    registry.register(create_list_timers_task())
    registry.register(create_cancel_timer_task())
    registry.register(create_add_calendar_event_task())
    registry.register(create_list_calendar_events_task())
    registry.register(create_get_world_time_task())
    registry.register(create_get_weather_task())
    registry.register(create_get_news_task())
    registry.register(create_read_page_task())
    registry.register(create_wiki_lookup_task())
    registry.register(create_translate_task())
    registry.register(create_set_reminder_task())
    registry.register(create_list_reminders_task())
    registry.register(create_cancel_reminder_task())
    registry.register(create_set_alarm_task())
    registry.register(create_list_alarms_task())
    registry.register(create_get_briefing_task())
    registry.register(create_cancel_alarm_task())
    registry.register(create_stop_ringing_task())
    registry.register(create_search_web_task())
