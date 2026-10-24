"""Wetter (Mark 5, Step 2.1): aktuelles Wetter und Vorhersage fuer einen Ort.

Daten von open-meteo.com (kostenlos, ohne Schluessel). Zwei Abrufe, beide ueber ``net_fetch``:
1. Ortssuche ("Vaxjo" -> Koordinaten) bei geocoding-api.open-meteo.com
2. Vorhersage fuer diese Koordinaten bei api.open-meteo.com

Der Ortsname (und beim Start dein Heimatort) geht an Open-Meteo, sonst nichts.
Antworten werden zwischengespeichert (Orte dauerhaft im Speicher, Vorhersage 10 Minuten).
Alles, was von dort kommt, wird geprueft: Zahlen im sinnvollen Bereich, Texte gesaeubert.
Der Ortsname aus dem Netz ist unvertraute Eingabe (untrusted.py) und wird gekuerzt.
"""

import threading
import time
from datetime import date, timedelta

from net_fetch import NetError, fetch_json
from tools.tool_result import ToolResult
from untrusted import clean_text

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOSTS = ("geocoding-api.open-meteo.com", "api.open-meteo.com")

FORECAST_DAYS = 7
FORECAST_CACHE_SECONDS = 600
MAX_PLACE_CHARS = 100
MAX_CACHED_PLACES = 200

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# WMO-Wettercodes, wie Open-Meteo sie liefert
WEATHER_CODES = {
    0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt",
    45: "Nebel", 48: "Raureifnebel",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen",
    56: "leichter gefrierender Nieselregen", 57: "gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "leichter gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall", 77: "Schneegriesel",
    80: "leichte Regenschauer", 81: "Regenschauer", 82: "heftige Regenschauer",
    85: "leichte Schneeschauer", 86: "Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit starkem Hagel",
}

# Deutsche Namen, die Open-Meteo unter dem englischen/lokalen Namen fuehrt (klein geschrieben)
GERMAN_NAMES = {
    "kalkutta": "Kolkata", "bombay": "Mumbai", "neu delhi": "New Delhi", "peking": "Beijing", "tokio": "Tokyo",
    "hongkong": "Hong Kong", "singapur": "Singapore", "mailand": "Milan", "rom": "Rome", "neapel": "Naples",
    "venedig": "Venice", "florenz": "Florence", "turin": "Turin", "genua": "Genoa", "wien": "Vienna",
    "köln": "Cologne", "muenchen": "Munich", "münchen": "Munich", "nürnberg": "Nuremberg", "hannover": "Hanover",
    "prag": "Prague", "warschau": "Warsaw", "moskau": "Moscow", "sankt petersburg": "Saint Petersburg",
    "kopenhagen": "Copenhagen", "lissabon": "Lisbon", "athen": "Athens", "kairo": "Cairo", "genf": "Geneva",
    "brüssel": "Brussels", "bruessel": "Brussels", "mexiko-stadt": "Mexico City", "kapstadt": "Cape Town",
    "belgrad": "Belgrade", "bukarest": "Bucharest", "kiew": "Kyiv", "kiev": "Kyiv", "krakau": "Krakow",
    "danzig": "Gdansk", "breslau": "Wroclaw", "göteborg": "Gothenburg", "teheran": "Tehran", "bagdad": "Baghdad",
    "damaskus": "Damascus", "algier": "Algiers", "tunis": "Tunis", "neuseeland": "New Zealand",
}

_TODAY_WORDS = ("", "heute", "today", "jetzt", "now", "aktuell")
_TOMORROW_WORDS = ("morgen", "tomorrow")
_DAY_AFTER_WORDS = ("übermorgen", "uebermorgen", "day after tomorrow")


def _num(value, low, high):
    """Zahl im erlaubten Bereich, sonst None (kein Text, kein bool, kein NaN)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or not low <= value <= high:
        return None
    return value


def _round(value):
    return None if value is None else round(value)


def _condition(code):
    return WEATHER_CODES.get(code) if isinstance(code, int) and not isinstance(code, bool) else None


def describe_day(day):
    return f"{WEEKDAYS[day.weekday()]}, {day.day:02d}.{day.month:02d}.{day.year}"


def clean_place(value):
    """Ortsname fuer die Suche: Text ohne Steuerzeichen, gekuerzt. Sonst None."""
    if not isinstance(value, str):
        return None
    text = " ".join(clean_text(value, MAX_PLACE_CHARS).split())
    return text or None


class WeatherService:
    def __init__(self, fetch=fetch_json, clock=time.time, today=date.today, home=lambda: ""):
        self.fetch = fetch
        self.clock = clock
        self.today = today
        self.home = home           # liefert den Heimatort aus den Einstellungen
        self._places = {}
        self._forecasts = {}
        self._lock = threading.Lock()

    # ---- Abruf (mit Zwischenspeicher)

    def _search(self, name):
        """Erster Treffer der Ortssuche oder None. Deutscher Name -> englischer Name zuerst; Deutsch, dann Englisch."""
        candidates = [name]
        english = GERMAN_NAMES.get(name.casefold())
        if english:
            candidates.insert(0, english)
        for candidate in candidates:
            for language in ("de", "en"):
                data = self.fetch(GEOCODE_URL, HOSTS, params={"name": candidate, "count": 1, "language": language, "format": "json"})
                results = data.get("results") if isinstance(data, dict) else None
                if isinstance(results, list) and results and isinstance(results[0], dict):
                    return results[0]
        return None

    def _find_place(self, name):
        key = name.casefold()
        with self._lock:
            if key in self._places:
                return self._places[key]
        first = self._search(name)
        lat = _num(first.get("latitude"), -90, 90) if first else None
        lon = _num(first.get("longitude"), -180, 180) if first else None
        if lat is None or lon is None:
            return None
        parts = [clean_text(first.get(k), 60).strip() for k in ("name", "admin1", "country")]
        label = ", ".join(dict.fromkeys(p for p in parts if p))   # ohne doppelte Teile
        zone = first.get("timezone")
        place = {"label": label or name, "lat": lat, "lon": lon,
                 "timezone": clean_text(zone, 60).strip() if isinstance(zone, str) else None}
        with self._lock:
            if len(self._places) >= MAX_CACHED_PLACES:
                self._places.clear()
            self._places[key] = place
        return place

    def locate(self, text):
        """Ort suchen (fuer die Weltuhr): {"label", "lat", "lon", "timezone"} oder None. NetError bei Netzproblemen."""
        name = clean_place(text)
        return self._find_place(name) if name else None

    def _forecast(self, place):
        key = (place["lat"], place["lon"])
        with self._lock:
            cached = self._forecasts.get(key)
            if cached and self.clock() - cached[0] < FORECAST_CACHE_SECONDS:
                return cached[1]
        data = self.fetch(FORECAST_URL, HOSTS, params={
            "latitude": place["lat"], "longitude": place["lon"], "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
        })
        if not isinstance(data, dict):
            raise NetError("Die Antwort ist nicht lesbar.")
        with self._lock:
            if len(self._forecasts) >= MAX_CACHED_PLACES:
                self._forecasts.clear()
            self._forecasts[key] = (self.clock(), data)
        return data

    # ---- Tag aus dem Text

    def _resolve_day(self, text):
        """Welcher Tag gemeint ist: (date, Fehlertext)."""
        today = self.today()
        if text is not None and not isinstance(text, str):
            return None, "Den Tag habe ich nicht verstanden."
        word = (text or "").strip().lower()
        if word in _TODAY_WORDS:
            return today, None
        if word in _TOMORROW_WORDS:
            return today + timedelta(days=1), None
        if word in _DAY_AFTER_WORDS:
            return today + timedelta(days=2), None
        try:
            day = date.fromisoformat(word)
        except ValueError:
            return None, "Den Tag habe ich nicht verstanden."
        if day < today:
            return None, "Für vergangene Tage habe ich keine Vorhersage."
        if day > today + timedelta(days=FORECAST_DAYS - 1):
            return None, f"Die Vorhersage reicht höchstens {FORECAST_DAYS} Tage voraus."
        return day, None

    # ---- Auswertung

    @staticmethod
    def _day_block(forecast, day):
        daily = forecast.get("daily") if isinstance(forecast.get("daily"), dict) else {}
        times = daily.get("time")
        if not isinstance(times, list) or day.isoformat() not in times:
            return None
        i = times.index(day.isoformat())

        def at(name, low, high):
            values = daily.get(name)
            return _num(values[i], low, high) if isinstance(values, list) and i < len(values) else None

        code = daily.get("weather_code")
        code = code[i] if isinstance(code, list) and i < len(code) else None
        return {
            "condition": _condition(code),
            "high": _round(at("temperature_2m_max", -90, 70)),
            "low": _round(at("temperature_2m_min", -90, 70)),
            "rain_chance_percent": _round(at("precipitation_probability_max", 0, 100)),
            "rain_mm": at("precipitation_sum", 0, 2000),
        }

    @staticmethod
    def _now_block(forecast):
        current = forecast.get("current")
        if not isinstance(current, dict):
            return None
        return {
            "condition": _condition(current.get("weather_code")),
            "temperature": _round(_num(current.get("temperature_2m"), -90, 70)),
            "feels_like": _round(_num(current.get("apparent_temperature"), -120, 80)),
            "humidity_percent": _round(_num(current.get("relative_humidity_2m"), 0, 100)),
            "wind_kmh": _round(_num(current.get("wind_speed_10m"), 0, 500)),
        }

    def _place_from_text(self, text):
        """Ortsname aus der Frage, bei 'heimat' (oder keinem Ort) der Heimatort aus den Einstellungen."""
        name = clean_place(text)
        if name is None or name.casefold() in ("heimat", "home", "hier", "lokal", "local", "bei mir"):
            name = clean_place(self.home())
            if name is None:
                return None, "Für welchen Ort? Du kannst in den Einstellungen unter J.A.R.V.I.S. einen Heimatort eintragen."
        return name, None

    # ---- Aufgaben

    def get_weather(self, place, day="heute"):
        """Wetter fuer einen Ort und Tag als ToolResult (Daten: nur Zahlen und feste Woerter)."""
        name, problem = self._place_from_text(place)
        if problem:
            return ToolResult(success=False, error=problem)
        target, problem = self._resolve_day(day)
        if problem:
            return ToolResult(success=False, error=problem)
        try:
            found = self._find_place(name)
            if found is None:
                return ToolResult(success=False, error=f"Den Ort „{name}“ habe ich nicht gefunden.")
            forecast = self._forecast(found)
        except NetError as error:
            return ToolResult(success=False, error=f"Das Wetter ist gerade nicht abrufbar: {error}")

        block = self._day_block(forecast, target)
        if block is None:
            return ToolResult(success=False, error="Für diesen Tag liegt keine Vorhersage vor.")
        data = {"place": found["label"], "day": describe_day(target), **block}
        if target == self.today():
            data["now"] = self._now_block(forecast)
        return ToolResult(success=True, data=data)

    def summary(self):
        """Ein kurzer Satz fuer den Startbericht (Heimatort, heute) oder None, wenn es nicht geht."""
        result = self.get_weather("heimat", "heute")
        if not result.success:
            return None
        d = result.data
        now = d.get("now") or {}
        place = d["place"].split(",")[0]
        parts = []
        if now.get("temperature") is not None:
            parts.append(f"In {place} sind es {now['temperature']} °C" + (f", {now['condition']}" if now.get("condition") else ""))
        elif d.get("condition"):
            parts.append(f"In {place}: {d['condition']}")
        else:
            return None
        if d.get("high") is not None:
            parts[0] += f". Heute bis {d['high']} °C"
        if d.get("rain_chance_percent") is not None and d["rain_chance_percent"] >= 30:
            parts[0] += f", Regenwahrscheinlichkeit {d['rain_chance_percent']} %"
        return parts[0] + "."


_default_service = None


def default_service():
    """Der eine Wetterdienst (Zwischenspeicher gemeinsam fuer Aufgabe und Startbericht)."""
    global _default_service
    if _default_service is None:
        _default_service = WeatherService()
    return _default_service


def set_default_service(service):
    """Jarvis und Tests setzen hier den Dienst (mit Heimatort aus den Einstellungen)."""
    global _default_service
    _default_service = service


def get_weather(place, day="heute"):
    return default_service().get_weather(place, day)
