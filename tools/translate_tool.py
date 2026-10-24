"""Uebersetzen (Mark 5, Step 2.7): "Wie sagt man Guten Morgen auf Japanisch?", "Uebersetze ins Englische: ..."

Hier wird nicht uebersetzt, sondern die Anfrage geprueft und aufbereitet: Text und Zielsprache werden
gesaeubert, Sprachkuerzel ("ja", "en") zu Sprachnamen gemacht, zu lange oder leere Eingaben abgelehnt.
Uebersetzt wird dann von der KI in der Antwort (brain.respond_to_task), mit denselben KI-Aufrufen und
demselben Tageslimit wie jede Antwort. Es gibt keinen Netzzugriff und keinen Schluessel.

Der zu uebersetzende Text steht im Prompt als unvertraute Daten (untrusted.py): Steht darin
"Ignoriere alle Regeln", wird das uebersetzt und nicht befolgt.
"""

import re

from untrusted import clean_text
from tools.tool_result import ToolResult

MAX_TEXT = 2000
MAX_LANGUAGE = 40
MAX_WORDS = 3

# Kuerzel (ISO 639-1) und englische Namen -> deutscher Sprachname. Alles andere wird als Name durchgereicht.
LANGUAGES = {
    "de": "Deutsch", "en": "Englisch", "fr": "Französisch", "es": "Spanisch", "it": "Italienisch",
    "pt": "Portugiesisch", "nl": "Niederländisch", "pl": "Polnisch", "cs": "Tschechisch", "sv": "Schwedisch",
    "da": "Dänisch", "no": "Norwegisch", "fi": "Finnisch", "el": "Griechisch", "tr": "Türkisch",
    "ru": "Russisch", "uk": "Ukrainisch", "ar": "Arabisch", "he": "Hebräisch", "hi": "Hindi",
    "zh": "Chinesisch", "ja": "Japanisch", "ko": "Koreanisch", "la": "Latein", "hu": "Ungarisch",
    "ro": "Rumänisch", "th": "Thailändisch", "vi": "Vietnamesisch", "id": "Indonesisch",
}
_ENGLISH_NAMES = {
    "german": "Deutsch", "english": "Englisch", "french": "Französisch", "spanish": "Spanisch",
    "italian": "Italienisch", "portuguese": "Portugiesisch", "dutch": "Niederländisch", "polish": "Polnisch",
    "czech": "Tschechisch", "swedish": "Schwedisch", "danish": "Dänisch", "norwegian": "Norwegisch",
    "finnish": "Finnisch", "greek": "Griechisch", "turkish": "Türkisch", "russian": "Russisch",
    "ukrainian": "Ukrainisch", "arabic": "Arabisch", "hebrew": "Hebräisch", "hindi": "Hindi",
    "chinese": "Chinesisch", "japanese": "Japanisch", "korean": "Koreanisch", "latin": "Latein",
    "hungarian": "Ungarisch", "romanian": "Rumänisch", "thai": "Thailändisch", "vietnamese": "Vietnamesisch",
    "indonesian": "Indonesisch",
}
# Buchstaben (auch Umlaute, andere Schriften), Leerzeichen, Bindestrich, Klammern, Punkt
_NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ \-().])*$")


def language_name(value):
    """Sprachname aus Kuerzel, englischem oder deutschem Namen. None, wenn das kein Sprachname sein kann."""
    if not isinstance(value, str):
        return None
    if any(char in value for char in "\n\r\t"):
        return None                         # ein Sprachname ist eine Zeile, kein Absatz
    text = " ".join(clean_text(value, 200).split())
    if not text or len(text) > MAX_LANGUAGE or len(text.split()) > MAX_WORDS or not _NAME.match(text):
        return None
    key = text.casefold()
    return LANGUAGES.get(key) or _ENGLISH_NAMES.get(key) or text


def prepare_translation(text, target_language, source_language=""):
    """ToolResult mit Text und Sprachen fuer die Uebersetzung durch die KI."""
    if not isinstance(text, str) or not clean_text(text, MAX_TEXT + 10).strip():
        return ToolResult(success=False, error="Welchen Text soll ich übersetzen? Nenne ihn bitte direkt in deiner Anfrage.")
    if len(text) > MAX_TEXT:
        return ToolResult(success=False, error=f"Der Text ist zu lang (mehr als {MAX_TEXT} Zeichen). Schick ihn bitte in kleineren Teilen.")
    target = language_name(target_language)
    if target is None:
        return ToolResult(success=False, error="In welche Sprache soll ich übersetzen?")
    source = language_name(source_language) if source_language else None
    data = {"text": clean_text(text, MAX_TEXT).strip(), "target_language": target}
    if source:
        data["source_language"] = source
    return ToolResult(success=True, data=data)
