"""Umrechnen (Mark 5, Step 2.3): Einheiten und Waehrungen, exakt im Code gerechnet.

Einheiten (Laenge, Gewicht, Volumen, Temperatur, Geschwindigkeit, Flaeche, Daten, Zeit) sind fest
eingebaut und brauchen kein Internet. Waehrungen nutzen die Referenzkurse der Europaeischen Zentralbank
(EZB): kostenlos, ohne Schluessel, einmal pro Werktag aktualisiert (kein Handelskurs, also nicht der Kurs,
den eine Bank oder PayPal abrechnet). Dabei geht nichts Persoenliches ins Netz, nur der Abruf der Kurstabelle.

Gerechnet wird mit ``decimal`` (kein Fliesskomma-Rauschen). Das Sprachmodell liefert nur Zahl und zwei
Namen; welche Einheit gemeint ist, entscheidet die Tabelle unten. Passen die Namen nicht zusammen
("Kilometer in Liter"), gibt es einen klaren Satz statt einer Zahl. Unterschiede im Alltag:
Pfund = 500 g (deutsch); "lb"/"pound" = 453,59 g (englisch). Gallone, Pint, Cup, fl oz sind US-Masse.
"""

import decimal
import re
import threading
import time
import xml.etree.ElementTree as ET
from decimal import Decimal

from net_fetch import NetError, fetch_text
from tools.tool_result import ToolResult

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_HOSTS = ("www.ecb.europa.eu",)
RATES_CACHE_SECONDS = 3600
MAX_VALUE = Decimal(10) ** 15
RESULT_DIGITS = 10

_CONTEXT = decimal.Context(prec=60, traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow])


def D(text):
    return Decimal(text)


# category -> [(unit id, symbol, factor to the base unit, aliases)]
UNITS = {
    "length": [   # Basis: Meter
        ("mm", "mm", D("0.001"), ("millimeter", "millimetre", "mm")),
        ("cm", "cm", D("0.01"), ("zentimeter", "centimeter", "centimetre", "cm")),
        ("m", "m", D("1"), ("meter", "metre", "meters", "metres", "m")),
        ("km", "km", D("1000"), ("kilometer", "kilometre", "kilometers", "kilometres", "km")),
        ("in", "in", D("0.0254"), ("zoll", "inch", "inches", "in", '"')),
        ("ft", "ft", D("0.3048"), ("fuß", "fuss", "foot", "feet", "ft", "'")),
        ("yd", "yd", D("0.9144"), ("yard", "yards", "yd")),
        ("mi", "mi", D("1609.344"), ("meile", "meilen", "mile", "miles", "mi")),
        ("nmi", "sm", D("1852"), ("seemeile", "seemeilen", "nautical mile", "nautical miles", "nmi")),
    ],
    "mass": [     # Basis: Gramm
        ("mg", "mg", D("0.001"), ("milligramm", "milligram", "mg")),
        ("g", "g", D("1"), ("gramm", "gram", "grams", "g")),
        ("kg", "kg", D("1000"), ("kilogramm", "kilogram", "kilograms", "kilo", "kilos", "kg")),
        ("t", "t", D("1000000"), ("tonne", "tonnen", "t")),
        ("oz", "oz", D("28.349523125"), ("unze", "unzen", "ounce", "ounces", "oz")),
        ("lb", "lb", D("453.59237"), ("pound", "pounds", "lb", "lbs")),
        ("pfund", "Pfund", D("500"), ("pfund", "pfd")),
    ],
    "volume": [   # Basis: Milliliter
        ("ml", "ml", D("1"), ("milliliter", "millilitre", "ml")),
        ("cl", "cl", D("10"), ("zentiliter", "centiliter", "cl")),
        ("dl", "dl", D("100"), ("deziliter", "deciliter", "dl")),
        ("l", "l", D("1000"), ("liter", "litre", "litres", "liters", "l")),
        ("m3", "m³", D("1000000"), ("kubikmeter", "cubic meter", "m3", "m³")),
        ("floz", "fl oz (US)", D("29.5735295625"), ("fluid ounce", "fluid ounces", "fl oz", "floz")),
        ("cup", "cup (US)", D("236.5882365"), ("cup", "cups")),
        ("pt", "pint (US)", D("473.176473"), ("pint", "pints", "pt")),
        ("qt", "quart (US)", D("946.352946"), ("quart", "quarts", "qt")),
        ("gal", "gallon (US)", D("3785.411784"), ("gallone", "gallonen", "gallon", "gallons", "gal")),
    ],
    "speed": [    # Basis: Meter pro Sekunde
        ("ms", "m/s", D("1"), ("m/s", "meter pro sekunde", "meter per second")),
        ("kmh", "km/h", D(1000) / D(3600), ("km/h", "kmh", "kph", "kilometer pro stunde", "stundenkilometer", "kilometers per hour")),
        ("mph", "mph", D("0.44704"), ("mph", "meilen pro stunde", "miles per hour")),
        ("kn", "kn", D(1852) / D(3600), ("knoten", "knot", "knots", "kn")),
    ],
    "area": [     # Basis: Quadratmeter
        ("cm2", "cm²", D("0.0001"), ("quadratzentimeter", "cm2", "cm²")),
        ("m2", "m²", D("1"), ("quadratmeter", "qm", "m2", "m²", "square meter", "square meters")),
        ("km2", "km²", D("1000000"), ("quadratkilometer", "km2", "km²")),
        ("ha", "ha", D("10000"), ("hektar", "ha", "hectare", "hectares")),
        ("acre", "acre", D("4046.8564224"), ("acre", "acres")),
        ("ft2", "ft²", D("0.09290304"), ("quadratfuß", "quadratfuss", "square feet", "square foot", "sq ft", "ft2", "ft²")),
        ("in2", "in²", D("0.00064516"), ("quadratzoll", "square inch", "square inches", "sq in", "in2", "in²")),
    ],
    "data": [     # Basis: Byte
        ("bit", "bit", D("0.125"), ("bit", "bits")),
        ("B", "B", D("1"), ("byte", "bytes")),
        ("kB", "kB", D("1000"), ("kilobyte", "kilobytes", "kb")),
        ("MB", "MB", D("1000000"), ("megabyte", "megabytes", "mb")),
        ("GB", "GB", D("1000000000"), ("gigabyte", "gigabytes", "gb")),
        ("TB", "TB", D("1000000000000"), ("terabyte", "terabytes", "tb")),
        ("KiB", "KiB", D("1024"), ("kibibyte", "kib")),
        ("MiB", "MiB", D("1048576"), ("mebibyte", "mib")),
        ("GiB", "GiB", D("1073741824"), ("gibibyte", "gib")),
        ("TiB", "TiB", D("1099511627776"), ("tebibyte", "tib")),
    ],
    "time": [     # Basis: Sekunde
        ("ms", "ms", D("0.001"), ("millisekunde", "millisekunden", "millisecond", "milliseconds", "ms")),
        ("s", "s", D("1"), ("sekunde", "sekunden", "second", "seconds", "sec", "s")),
        ("min", "min", D("60"), ("minute", "minuten", "minutes", "min")),
        ("h", "h", D("3600"), ("stunde", "stunden", "hour", "hours", "std", "h")),
        ("d", "d", D("86400"), ("tag", "tage", "tagen", "day", "days", "d")),
        ("wk", "Wochen", D("604800"), ("woche", "wochen", "week", "weeks")),
    ],
}

TEMPERATURE = [
    ("c", "°C", ("celsius", "grad celsius", "°c", "c")),
    ("f", "°F", ("fahrenheit", "grad fahrenheit", "°f", "f")),
    ("k", "K", ("kelvin", "k")),
]

# Von der EZB veroeffentlichte Waehrungen (Stand 2026, Codes aendern sich selten)
ECB_CODES = ("EUR", "USD", "JPY", "BGN", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK", "CHF", "ISK", "NOK",
             "TRY", "AUD", "BRL", "CAD", "CNY", "HKD", "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP",
             "SGD", "THB", "ZAR")
CURRENCY_NAMES = {
    "euro": "EUR", "€": "EUR", "euros": "EUR",
    "dollar": "USD", "us-dollar": "USD", "us dollar": "USD", "$": "USD", "dollars": "USD", "amerikanischer dollar": "USD",
    "pfund": "GBP", "pfund sterling": "GBP", "britisches pfund": "GBP", "pound sterling": "GBP", "£": "GBP",
    "franken": "CHF", "schweizer franken": "CHF", "swiss franc": "CHF",
    "yen": "JPY", "¥": "JPY", "japanischer yen": "JPY",
    "kanadischer dollar": "CAD", "australischer dollar": "AUD", "neuseeland-dollar": "NZD",
    "zloty": "PLN", "yuan": "CNY", "renminbi": "CNY", "lira": "TRY", "türkische lira": "TRY",
}

TEMPERATURE_IDS = {unit: symbol for unit, symbol, _ in TEMPERATURE}


def _build_aliases():
    """alias -> Liste von (Kategorie, Einheit). Ein Name kann mehrdeutig sein ('pfund': Gewicht oder Waehrung)."""
    aliases = {}

    def add(alias, category, unit):
        entry = (category, unit)
        bucket = aliases.setdefault(alias, [])
        if entry not in bucket:
            bucket.append(entry)

    for category, units in UNITS.items():
        for unit, _symbol, _factor, names in units:
            for name in names:
                add(name, category, unit)
    for unit, _symbol, names in TEMPERATURE:
        for name in names:
            add(name, "temperature", unit)
    for code in ECB_CODES:
        add(code.lower(), "currency", code)
    for name, code in CURRENCY_NAMES.items():
        add(name, "currency", code)
    return aliases


ALIASES = _build_aliases()
CATEGORY_NAMES = {"length": "eine Länge", "mass": "ein Gewicht", "volume": "ein Volumen", "temperature": "eine Temperatur",
                  "speed": "eine Geschwindigkeit", "area": "eine Fläche", "data": "eine Datenmenge", "time": "eine Zeitspanne",
                  "currency": "eine Währung"}


def clean_unit(text):
    if not isinstance(text, str):
        return ""
    cleaned = " ".join(text.strip().lower().split()).rstrip(".")
    return cleaned


def parse_value(raw):
    """Zahl aus Text oder Zahl. ValueError mit verstaendlichem Satz, wenn sie nicht passt."""
    if isinstance(raw, bool):
        raise ValueError("Die Zahl habe ich nicht verstanden.")
    if isinstance(raw, (int, float, Decimal)):
        text = repr(raw) if isinstance(raw, float) else str(raw)
    elif isinstance(raw, str):
        text = raw.strip().replace(" ", "").replace(" ", "")
        text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    else:
        raise ValueError("Die Zahl habe ich nicht verstanden.")
    if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d{1,3})?", text):
        raise ValueError("Die Zahl habe ich nicht verstanden.")
    try:
        value = Decimal(text)
    except decimal.InvalidOperation as error:
        raise ValueError("Die Zahl habe ich nicht verstanden.") from error
    if not value.is_finite() or abs(value) > MAX_VALUE:
        raise ValueError("Die Zahl ist zu groß.")
    return value


def format_number(value):
    """Hoechstens 10 gueltige Stellen, ohne Exponent und ohne ueberfluessige Nullen."""
    rounded = decimal.Context(prec=RESULT_DIGITS).plus(value)
    if rounded == 0:
        return "0"
    text = format(rounded.normalize(), "f")
    return text[:-2] if text.endswith(".0") else text


def find_pair(from_name, to_name):
    """(Kategorie, Einheit von, Einheit nach) oder ValueError mit einem Satz fuer den Nutzer."""
    a, b = clean_unit(from_name), clean_unit(to_name)
    if not a or not b:
        raise ValueError("Von welcher Einheit in welche soll ich umrechnen?")
    first, second = ALIASES.get(a), ALIASES.get(b)
    if not first:
        raise ValueError(f"Die Einheit „{a}“ kenne ich nicht.")
    if not second:
        raise ValueError(f"Die Einheit „{b}“ kenne ich nicht.")
    for category, unit_a in first:
        for category_b, unit_b in second:
            if category == category_b:
                return category, unit_a, unit_b
    raise ValueError(f"Das passt nicht zusammen: „{a}“ ist {CATEGORY_NAMES[first[0][0]]}, „{b}“ ist {CATEGORY_NAMES[second[0][0]]}.")


def _symbol(category, unit):
    if category == "currency":
        return unit
    if category == "temperature":
        return TEMPERATURE_IDS[unit]
    return next(symbol for u, symbol, _f, _n in UNITS[category] if u == unit)


def _factor(category, unit):
    return next(factor for u, _s, factor, _n in UNITS[category] if u == unit)


def _to_kelvin(unit, value):
    if unit == "k":
        return value
    if unit == "c":
        return value + D("273.15")
    return (value - 32) * 5 / 9 + D("273.15")


def _from_kelvin(unit, kelvin):
    if unit == "k":
        return kelvin
    if unit == "c":
        return kelvin - D("273.15")
    return (kelvin - D("273.15")) * 9 / 5 + 32


def parse_rates(text):
    """({Waehrung: Kurs je 1 EUR}, Datum) aus der EZB-Tabelle. Wirft NetError bei unlesbarer Antwort."""
    if not isinstance(text, str) or re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise NetError("Die Kurstabelle ist nicht lesbar.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise NetError("Die Kurstabelle ist nicht lesbar.") from error
    rates, day = {"EUR": D(1)}, None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag != "Cube":
            continue
        if element.get("time") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", element.get("time")):
            day = element.get("time")
        code, rate = element.get("currency"), element.get("rate")
        if code and rate and re.fullmatch(r"[A-Z]{3}", code):
            try:
                value = Decimal(rate)
            except decimal.InvalidOperation:
                continue
            if value.is_finite() and Decimal("0.000001") < value < Decimal(10) ** 9:
                rates[code] = value
    if len(rates) < 5 or day is None:
        raise NetError("Die Kurstabelle ist nicht lesbar.")
    return rates, day


class ConvertService:
    def __init__(self, fetch=fetch_text, clock=time.time):
        self.fetch = fetch
        self.clock = clock
        self._rates = None            # (Zeitpunkt, Kurse, Datum)
        self._lock = threading.Lock()

    def _load_rates(self):
        """(Kurse, Datum, veraltet?)"""
        with self._lock:
            cached = self._rates
        if cached and self.clock() - cached[0] < RATES_CACHE_SECONDS:
            return cached[1], cached[2], False
        try:
            rates, day = parse_rates(self.fetch(ECB_URL, ECB_HOSTS))
        except NetError:
            if cached:
                return cached[1], cached[2], True        # lieber der letzte bekannte Kurs als gar keiner
            raise
        with self._lock:
            self._rates = (self.clock(), rates, day)
        return rates, day, False

    def convert(self, value, from_unit, to_unit):
        """Umrechnung als ToolResult (Daten: Zahlen als Text, Einheiten, bei Waehrungen Kursdatum)."""
        try:
            amount = parse_value(value)
            category, unit_a, unit_b = find_pair(from_unit, to_unit)
            note = None
            if category == "currency":
                rates, rate_day, stale = self._load_rates()
                for code in (unit_a, unit_b):
                    if code not in rates:
                        raise ValueError(f"Für {code} gibt es keinen EZB-Referenzkurs.")
                result = _CONTEXT.multiply(_CONTEXT.divide(amount, rates[unit_a]), rates[unit_b])
                result = result.quantize(Decimal("0.01"), context=_CONTEXT)
                note = f"EZB-Referenzkurs vom {rate_day} (kein Handelskurs)"
                if stale:
                    note += "; die aktuelle Kurstabelle war nicht abrufbar"
            elif category == "temperature":
                kelvin = _to_kelvin(unit_a, amount)
                if kelvin < 0:
                    raise ValueError("Das liegt unter dem absoluten Nullpunkt.")
                result = _from_kelvin(unit_b, kelvin)
            else:
                result = _CONTEXT.divide(_CONTEXT.multiply(amount, _factor(category, unit_a)), _factor(category, unit_b))
        except NetError as error:
            return ToolResult(success=False, error=f"Die Wechselkurse sind gerade nicht abrufbar: {error}")
        except (ValueError, decimal.DecimalException) as error:
            text = str(error) if isinstance(error, ValueError) else "Das Ergebnis ist nicht berechenbar."
            return ToolResult(success=False, error=text)
        data = {
            "category": category,
            "value": format_number(amount), "from": _symbol(category, unit_a),
            "result": format_number(result) if category != "currency" else format(result, "f"),
            "to": _symbol(category, unit_b),
        }
        if note:
            data["note"] = note
        return ToolResult(success=True, data=data)


_default_service = None


def default_service():
    global _default_service
    if _default_service is None:
        _default_service = ConvertService()
    return _default_service


def set_default_service(service):
    global _default_service
    _default_service = service


def convert(value, from_unit, to_unit):
    return default_service().convert(value, from_unit, to_unit)
