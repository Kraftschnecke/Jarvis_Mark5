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


def create_media_control_task():
    task = Task(
        "MEDIA_CONTROL",
        "Die Musik auf dem Computer mit den Medientasten steuern: abspielen oder pausieren, nächster oder vorheriger Titel (Pause die Musik. Nächstes Lied. Spiel weiter. Zurück zum letzten Titel). Kann keinen bestimmten Titel oder Künstler starten"
    )
    task.add_action(
        Action(
            "media_control",
            {
                "command": {
                    "description": "play_pause für abspielen, pausieren, stoppen oder weiterspielen (eine Taste), next für nächster Titel, previous für vorheriger Titel",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_system_control_task():
    task = Task(
        "SYSTEM_CONTROL",
        "Den Computer kurz steuern: Ton stumm schalten, Bildschirm sperren, alle Fenster minimieren (Desktop zeigen), die Helligkeit des Bildschirms ändern (Stell den Ton stumm. Sperr den Bildschirm. Zeig den Desktop. Mach den Bildschirm dunkler. Helligkeit auf 50 Prozent). Nicht für die Lautstärke in Prozent und nicht für Musik"
    )
    task.add_action(
        Action(
            "system_control",
            {
                "command": {
                    "description": "mute für stumm schalten oder Ton wieder an, lock für Bildschirm sperren, show_desktop für alle Fenster minimieren oder Desktop zeigen, brightness_set für Helligkeit auf einen Wert, brightness_up für heller, brightness_down für dunkler",
                    "type": "string"
                },
                "value": {
                    "description": "Nur bei brightness_set: die Prozentzahl von 0 bis 100 als Ziffern (50). Sonst schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_read_clipboard_task():
    task = Task(
        "READ_CLIPBOARD",
        "Den Text lesen, der gerade in der Zwischenablage liegt, um ihn zusammenzufassen, zu übersetzen oder eine Frage dazu zu beantworten (Fasse zusammen, was in meiner Zwischenablage steht. Übersetze, was ich kopiert habe. Was habe ich gerade kopiert?). Kann nichts in die Zwischenablage schreiben"
    )
    task.add_action(
        Action(
            "read_clipboard",
            {
                "question": {
                    "description": "Was der Nutzer mit dem Text will, in seinen Worten (zusammenfassen, auf Englisch übersetzen, Gibt es darin ein Datum?). Will er nur wissen, was dort steht, schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_describe_screen_task():
    task = Task(
        "DESCRIBE_SCREEN",
        "Den Bildschirm des Nutzers ansehen und sagen, was darauf zu sehen ist, oder eine Frage dazu beantworten (Was siehst du auf meinem Bildschirm? Was steht da gerade? Was bedeutet diese Fehlermeldung auf dem Bildschirm? Schau mal, was ich offen habe). Kann nur ansehen, nicht klicken oder tippen"
    )
    task.add_action(
        Action(
            "describe_screen",
            {
                "question": {
                    "description": "Was der Nutzer über den Bildschirm wissen will, in seinen Worten (Was bedeutet die Fehlermeldung? Welche Programme sind offen?). Fragt er nur allgemein, was zu sehen ist, schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_open_website_task():
    task = Task(
        "OPEN_WEBSITE",
        "Eine Webseite im Browser des Nutzers öffnen oder im Browser nach etwas suchen, wenn er ausdrücklich will, dass sich etwas im Browser öffnet (Öffne youtube.com. Mach Wikipedia auf. Such im Browser nach Katzenvideos. Zeig mir das im Browser). Nicht für Fragen, die Jarvis selbst aus dem Internet beantworten soll, und nicht für lokale Programme oder Dateien"
    )
    task.add_action(
        Action(
            "open_website",
            {
                "url": {
                    "description": "Die Adresse oder der Seitenname, genau wie genannt (youtube.com, https://www.wikipedia.org). Soll nur gesucht werden, schreibe leer",
                    "type": "string"
                },
                "query": {
                    "description": "Der Suchbegriff, wenn der Nutzer im Browser suchen will und keine Seite nennt (Katzenvideos). Sonst schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_search_history_task():
    task = Task(
        "SEARCH_HISTORY",
        "In früheren Gesprächen mit Jarvis nachschlagen: wonach wurde gefragt, was wurde besprochen, in einem Zeitraum oder bei einem Projekt (Worüber haben wir letzte Woche beim Projekt Jarvis gesprochen? Was hatte ich zu den Hausaufgaben gefragt? Wann ging es um den Zahnarzt?). Nur für Gespräche mit Jarvis, nicht für das Internet und nicht für Dokumente oder Mails"
    )
    task.add_action(
        Action(
            "search_history",
            {
                "query": {
                    "description": "Die Suchwörter zum Thema, ohne Füllwörter (Hausaufgaben Python). Geht es nur um einen Zeitraum oder ein Projekt ohne Thema, schreibe leer",
                    "type": "string"
                },
                "project": {
                    "description": "Name oder Teil des Projektnamens, wenn der Nutzer ein Projekt nennt. Sonst schreibe leer",
                    "type": "string"
                },
                "days": {
                    "description": "Wie viele Tage zurück als Zahl: heute oder gestern = 2, diese Woche oder letzte Woche = 7, letzter Monat = 30. Nennt der Nutzer keinen Zeitraum, schreibe 0",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_goal_overview_task():
    task = Task(
        "GOAL_OVERVIEW",
        "Die Tagesziele und Gewohnheiten des Nutzers ansehen: was ist heute offen oder erledigt, wie lang ist die Serie eines täglichen Ziels (Wie lange gehe ich schon ins Fitnessstudio? Wie laufen meine Ziele? Wie war meine Woche?). Nur ansehen; Ziele anlegen oder abhaken macht der Nutzer in der Seitenleiste"
    )
    task.add_action(Action("goal_overview", {}))
    return task


def create_check_mail_task():
    task = Task(
        "CHECK_MAIL",
        "E-Mails im eingerichteten Postfach auflisten: nur Absender, Betreff und Datum, nummeriert, ohne den Text zu lesen (Habe ich neue Mails? Welche Mail habe ich zuletzt bekommen? Zeig meine letzten 20 Mails). Kann keine Mails schreiben, senden, beantworten oder löschen"
    )
    task.add_action(
        Action(
            "check_mail",
            {
                "account": {
                    "description": "Der Name des Postfachs (z. B. strato), wenn der Nutzer eines nennt. Sonst schreibe leer",
                    "type": "string"
                },
                "unread_only": {
                    "description": "true nur, wenn der Nutzer ausdrücklich neue oder ungelesene Mails meint (Habe ich neue Mails?). false bei letzte, zuletzt, neueste, die letzten Mails, Posteingang oder wenn gelesene Mails mitgemeint sind (Welche Mail habe ich zuletzt bekommen?)",
                    "type": "string"
                },
                "count": {
                    "description": "Wie viele Mails höchstens (1 bis 20). Nennt der Nutzer keine Zahl, schreibe 10; bei die letzten 20 Mails schreibe 20",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_read_mail_task():
    task = Task(
        "READ_MAIL",
        "Den Text einer E-Mail aus der zuletzt gezeigten Mail-Liste lesen, um sie zusammenzufassen oder eine Frage dazu zu beantworten (Fass mir die dritte Mail zusammen. Was steht in der Mail vom Chef? Lies Mail 2). Nur nach einer gezeigten Liste; kann nicht antworten oder senden"
    )
    task.add_action(
        Action(
            "read_mail",
            {
                "which": {
                    "description": "Welche Mail aus der Liste: die Nummer als Ziffer (die dritte = 3, Mail 2 = 2; die neueste oder letzte = 1, denn die Liste beginnt mit der neuesten), oder ein Teil des Absenders oder Betreffs (vom Chef = chef). Meint der Nutzer keine bestimmte, schreibe leer",
                    "type": "string"
                },
                "question": {
                    "description": "Die Frage des Nutzers zur Mail, wenn er etwas Bestimmtes wissen will (Was will der Absender? Bis wann soll ich antworten?). Bei Zusammenfassen schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_find_contact_task():
    task = Task(
        "FIND_CONTACT",
        "Zu einem Kontakt aus dem Adressbuch den Geburtstag, die Telefonnummer oder die E-Mail-Adresse nennen (Wann hat Anna Geburtstag? Wie ist die Nummer von Max? Welche Mailadresse hat Julia?). Kann keine Kontakte anlegen oder ändern"
    )
    task.add_action(
        Action(
            "find_contact",
            {
                "name": {
                    "description": "Name oder Teil des Namens des Kontakts, genau wie genannt (Anna, Max Müller)",
                    "type": "string"
                },
                "topic": {
                    "description": "birthday bei Geburtstag, phone bei Telefonnummer oder Handynummer, email bei E-Mail-Adresse. Fragt der Nutzer allgemein nach dem Kontakt, schreibe leer",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_upcoming_birthdays_task():
    task = Task(
        "UPCOMING_BIRTHDAYS",
        "Die nächsten Geburtstage aus dem Adressbuch auflisten (Wer hat bald Geburtstag? Hat diese Woche jemand Geburtstag? Geburtstage im nächsten Monat). Nur für Geburtstage vieler Kontakte, nicht für eine bestimmte Person"
    )
    task.add_action(
        Action(
            "upcoming_birthdays",
            {
                "days": {
                    "description": "Wie viele Tage voraus als Zahl: diese Woche = 7, nächster Monat = 30, Nennt der Nutzer keinen Zeitraum, schreibe 30",
                    "type": "string"
                }
            }
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
        "Etwas in Wikipedia nachschlagen: eine Person, einen Ort, ein Ereignis oder einen Begriff erklären (Wer war ..., Was ist ...). Keine Wortbedeutungen und keine Fragen zur Sprache (Was bedeutet das Wort ...?): die beantwortet der normale Chat"
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


def create_start_focus_task():
    task = Task(
        "START_FOCUS",
        "Eine Fokus-Sitzung (Pomodoro) starten: Fokusphasen mit Pausen dazwischen und Meldung bei jedem Wechsel"
    )
    task.add_action(
        Action(
            "start_focus",
            {
                "work_minutes": {
                    "description": "Länge einer Fokusphase in Minuten als Zahl. Nennt der Nutzer keine, schreibe standard",
                    "type": "string"
                },
                "break_minutes": {
                    "description": "Länge der Pause in Minuten als Zahl. Nennt der Nutzer keine, schreibe standard",
                    "type": "string"
                },
                "rounds": {
                    "description": "Anzahl der Fokusphasen (Runden) als Zahl. Nennt der Nutzer keine, schreibe standard",
                    "type": "string"
                },
                "label": {
                    "description": "Woran gearbeitet wird, z.B. Lernen. Nennt der Nutzer nichts, schreibe ohne",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_focus_status_task():
    task = Task(
        "FOCUS_STATUS",
        "Zeigen, wie weit die laufende Fokus-Sitzung (Pomodoro) ist: welche Phase, welche Runde und wie lange es noch bis zur Pause oder bis zum Ende dauert (Wie lange noch bis zur Pause? Wie weit bin ich im Pomodoro? Läuft noch eine Fokus-Sitzung?)"
    )
    task.add_action(Action("focus_status"))
    return task


def create_stop_focus_task():
    task = Task(
        "STOP_FOCUS",
        "Die laufende Fokus-Sitzung (Pomodoro) beenden"
    )
    task.add_action(Action("stop_focus"))
    return task


def create_list_folders_task():
    task = Task(
        "LIST_FOLDERS",
        "Zeigen, in welchen freigegebenen Ordnern Jarvis Dateien lesen darf (Welche Ordner darfst du lesen? Auf welche Ordner hast du Zugriff?). Ordner kann nur der Nutzer selbst in den Einstellungen freigeben, nicht per Chat"
    )
    task.add_action(Action("list_folders"))
    return task


def create_find_files_task():
    task = Task(
        "FIND_FILES",
        "Dateien auf dem Computer in den freigegebenen Ordnern nach Name oder Inhalt finden (Finde meine Steuerunterlagen. Welche Dateien enthalten das Wort Kündigung? Suche PDFs mit Rechnung im Namen). Nicht für das Internet und nicht zum Öffnen oder Lesen einer Datei"
    )
    task.add_action(
        Action(
            "find_files",
            {
                "query": {
                    "description": "Die Suchwörter (Teil des Dateinamens oder Wort im Inhalt), höchstens 5. Sucht der Nutzer nur nach einem Dateityp oder Ordner, schreibe leer",
                    "type": "string"
                },
                "mode": {
                    "description": "name (im Dateinamen, Standard), content (im Inhalt: Nutzer sagt enthalten, steht drin, im Text) oder both (Nutzer meint unklar, wo es steht)",
                    "type": "string"
                },
                "file_type": {
                    "description": "Der Dateityp: pdf, word, excel, text, bild, präsentation oder eine Endung wie docx. Nennt der Nutzer keinen, schreibe alle",
                    "type": "string"
                },
                "folder": {
                    "description": "Ein Teil des Ordnernamens, wenn der Nutzer einen Ordner nennt (im Ordner Dokumente). Sonst schreibe alle",
                    "type": "string"
                },
                "count": {
                    "description": "Wie viele Treffer (1 bis 20). Nennt der Nutzer keine Zahl, schreibe 8",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_read_document_task():
    task = Task(
        "READ_DOCUMENT",
        "Eine Datei aus den freigegebenen Ordnern lesen, um sie zusammenzufassen oder Fragen zum Inhalt zu beantworten (Fass die zweite Datei zusammen. Wann ist die Rechnung fällig? Was steht im Vertrag über die Kündigungsfrist? Fasse es zusammen, nachdem Dateien gefunden wurden. Lies Lebenslauf.docx. Worum geht es im Brief?). Nicht zum Öffnen im Programm (das ist OPEN_FILE) und nicht für Webseiten"
    )
    task.add_action(
        Action(
            "read_document",
            {
                "file": {
                    "description": "Die Datei: die Nummer aus der zuletzt genannten Trefferliste (zweite Datei = 2) oder der Dateiname oder der volle Pfad. Sagt der Nutzer nur es, sie oder die Datei ohne Namen und Nummer, oder meint er die zuletzt gelesene Datei (weiter, nächster Teil), schreibe leer",
                    "type": "string"
                },
                "question": {
                    "description": "Die Frage des Nutzers zum Inhalt in einem Satz (Wann ist die Rechnung fällig?). Will er nur eine Zusammenfassung oder weiterlesen, schreibe leer",
                    "type": "string"
                },
                "part": {
                    "description": "Der Teil bei langen Dateien (1, 2, 3 …). Nennt der Nutzer keinen, schreibe 1; bei weiterlesen den nächsten Teil",
                    "type": "string"
                }
            }
        )
    )
    return task


def create_write_note_task():
    task = Task(
        "WRITE_NOTE",
        "Text als Notiz in eine Textdatei (.txt oder .md) in einem freigegebenen Ordner speichern (Schreib eine Notiz Einkaufen: Milch, Brot. Speichere das als Notiz. Leg die Datei ideen.txt an. Hänge das an meine Datei tagebuch.txt an). Nicht für Termine oder Erinnerungen und nicht für andere Dateiarten"
    )
    task.add_action(
        Action(
            "write_note",
            {
                "filename": {
                    "description": "Der Dateiname oder Titel der Notiz (nur der Name, kein Pfad, höchstens .txt oder .md). Steht in der Nachricht ein kurzer Titel vor dem Doppelpunkt (Schreib eine Notiz Einkaufen: Milch, Brot), ist das der Name: schreibe Einkaufen hierher und nur den Text danach in content. Nennt der Nutzer weder Namen noch Titel, schreibe leer",
                    "type": "string"
                },
                "content": {
                    "description": "Der Text für die Datei, so wie der Nutzer ihn nennt oder diktiert, ohne den Titel vor dem Doppelpunkt (bei einer Liste eine Zeile pro Eintrag). Meint der Nutzer deine letzte Antwort (Speichere das, die Zusammenfassung, das eben), schreibe leer",
                    "type": "string"
                },
                "folder": {
                    "description": "Ein Teil des Ordnernamens, wenn der Nutzer einen Ordner nennt (im Ordner Dokumente). Sonst schreibe leer",
                    "type": "string"
                },
                "mode": {
                    "description": "append, wenn der Nutzer an eine bestehende Datei anhängen oder ergänzen will, sonst new",
                    "type": "string"
                }
            }
        )
    )
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
    registry.register(create_media_control_task())
    registry.register(create_system_control_task())
    registry.register(create_read_clipboard_task())
    registry.register(create_describe_screen_task())
    registry.register(create_open_website_task())
    registry.register(create_search_history_task())
    registry.register(create_goal_overview_task())
    registry.register(create_check_mail_task())
    registry.register(create_read_mail_task())
    registry.register(create_find_contact_task())
    registry.register(create_upcoming_birthdays_task())
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
    registry.register(create_start_focus_task())
    registry.register(create_focus_status_task())
    registry.register(create_stop_focus_task())
    registry.register(create_list_folders_task())
    registry.register(create_find_files_task())
    registry.register(create_read_document_task())
    registry.register(create_write_note_task())
    registry.register(create_cancel_alarm_task())
    registry.register(create_stop_ringing_task())
    registry.register(create_search_web_task())
