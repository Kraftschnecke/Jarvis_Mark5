"""Rechner (Mark 5, Step 2.3): exakte Dezimalrechnung, die KI rechnet nie selbst.

Das Sprachmodell uebersetzt die Frage nur in einen Rechenausdruck ("15 Prozent von 80" -> "80*15%"),
gerechnet wird hier im Code. Erlaubt: Zahlen, + - * / ** (und ^), Klammern, Minus/Plus vor Zahlen,
und ``%`` direkt hinter einer Zahl (15% = 0.15). Alles andere (Namen, Aufrufe, Text) wird abgelehnt.

Warum ``decimal`` statt Fliesskomma: 0.1 + 0.2 ist hier genau 0.3, nicht 0.30000000000000004.
Das Ergebnis kommt als ganze Zahl (wenn es eine ist) oder als Zahl mit bis zu 15 gueltigen Stellen.
"""

import ast
import decimal
import operator
import re
from decimal import Decimal

MAX_EXPRESSION_CHARS = 200
MAX_EXPONENT = 1000
RESULT_DIGITS = 15

# Eigener Rechenkontext: genug Stellen fuer exakte ganze Zahlen (2**100), Fehler statt stiller Unendlichkeit
_CONTEXT = decimal.Context(
    prec=60, Emax=2000, Emin=-2000,
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)

_BINARY = {ast.Add: _CONTEXT.add, ast.Sub: _CONTEXT.subtract, ast.Mult: _CONTEXT.multiply, ast.Div: _CONTEXT.divide}
_UNARY = {ast.USub: _CONTEXT.minus, ast.UAdd: _CONTEXT.plus}

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def normalize(expression):
    """Schreibweisen aus Sprache und Text vereinheitlichen. Wirft ValueError bei ungueltiger Eingabe."""
    if not isinstance(expression, str):
        raise ValueError("Der Rechenausdruck ist kein Text.")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError("Der Rechenausdruck ist zu lang.")
    text = expression.strip()
    if not text:
        raise ValueError("Der Rechenausdruck ist leer.")
    text = _DECIMAL_COMMA.sub(".", text)            # 1,5 -> 1.5
    text = text.replace("^", "**").replace("×", "*").replace("÷", "/").replace("−", "-")
    return _PERCENT.sub(lambda m: f"({m.group(1)}/100)", text)    # 15% -> (15/100)


def _number(node):
    value = node.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Ungültiger Rechenausdruck.")
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ValueError("Ungültige Zahl.")
    return Decimal(repr(value))


def _power(base, exponent):
    if abs(exponent) > MAX_EXPONENT:
        raise ValueError("Der Exponent ist zu groß.")
    try:
        return _CONTEXT.power(base, exponent)
    except decimal.InvalidOperation as error:
        raise ValueError("Diese Potenz ist nicht berechenbar.") from error


def _evaluate(node):
    if isinstance(node, ast.Constant):
        return _number(node)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp):
        if type(node.op) is ast.Pow:
            return _power(_evaluate(node.left), _evaluate(node.right))
        if type(node.op) in _BINARY:
            return _BINARY[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    raise ValueError("Ungültiger Rechenausdruck.")


def to_plain(value):
    """Decimal -> ganze Zahl (bis 50 Stellen exakt) oder Zahl mit hoechstens 15 gueltigen Stellen."""
    if value == value.to_integral_value() and abs(value) < Decimal(10) ** 50:
        return int(value)
    rounded = decimal.Context(prec=RESULT_DIGITS).plus(value)
    if rounded == rounded.to_integral_value() and abs(rounded) < Decimal(10) ** 50:
        return int(rounded)                 # 10/3*3 = 9.99999... -> 10
    return float(rounded)


def calculate(expression):
    """Ergebnis des Ausdrucks (int oder float). ValueError bei ungueltigem Ausdruck,
    ZeroDivisionError bei Division durch null."""
    text = normalize(expression)
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, MemoryError, RecursionError) as error:
        raise ValueError("Ungültiger Rechenausdruck.") from error
    try:
        result = _evaluate(tree.body)
    except decimal.Overflow as error:
        raise ValueError("Das Ergebnis ist zu groß.") from error
    except decimal.InvalidOperation as error:
        raise ValueError("Ungültiger Rechenausdruck.") from error
    except RecursionError as error:
        raise ValueError("Der Rechenausdruck ist zu verschachtelt.") from error
    return to_plain(result)
