"""Offline generic surnames with bounded Russian-form recognition.

Dictionary hits are used only with person context in the engine. No arbitrary
capitalized token is treated as a surname merely because it is capitalized.
"""
import re
from importlib.resources import files

from .given_names import normalize_given_name

_ROOT = files("local_anonymizer").joinpath("assets/given_names")
SURNAMES = frozenset(
    normalize_given_name(line)
    for line in _ROOT.joinpath("surnames.txt").read_text(encoding="utf-8").splitlines()
)


def canonical_surname(value: str) -> str | None:
    key = normalize_given_name(value)
    if key in SURNAMES:
        return key
    nominal = re.fullmatch(r"(.+(?:ов|ев|ин|ын))(?:а|у|ым|ом|е|ой|ою|ы|ами|ах)", key)
    if nominal and nominal.group(1) in SURNAMES:
        return nominal.group(1)
    adjective = re.fullmatch(r"(.+(?:ск|цк))(?:ий|ая|ую|ой|ого|ому|им|ом|ие|их|ими)", key)
    if adjective:
        base = adjective.group(1) + "ий"
        if base in SURNAMES:
            return base
    return None


def is_surname(value: str) -> bool:
    return canonical_surname(value) is not None
