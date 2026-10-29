"""Finite offline Russian geography dictionary, independent of engine categories."""
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import re
import unicodedata
from collections.abc import Iterator


@dataclass(frozen=True)
class LocationMatch:
    """Half-open Python string offsets; IDs may be plural for namesakes."""
    start: int
    end: int
    surface: str
    location_ids: tuple[str, ...]
    canonical_names: tuple[str, ...]
    kinds: tuple[str, ...]


# Deliberately not \\s: tabs, line breaks and Office sentinels are barriers.
_SPACES = ' \u00a0\u2007\u2009\u202f'
_DASHES = '-\u2010\u2011\u2012\u2013\u2014\u2212'
_CONTEXT = re.compile(r'(?:\bг\.|\bгород(?:а|е|у|ом)?|\bг\b|\bгород\s*:)[' + _SPACES + r']*$', re.IGNORECASE)


def _normalize(text: str):
    """One output char per physical char; preserve offset coordinates exactly."""
    table = {ord(c): ' ' for c in _SPACES}
    table.update({ord(c): '-' for c in _DASHES})
    table.update({ord('ё'): 'е', ord('Ё'): 'е'})
    # Cyrillic and ASCII folds only: Unicode lower() can expand characters.
    table.update({ord(chr(c)): chr(c + 32) for c in range(ord('А'), ord('Я') + 1)})
    table.update({ord(chr(c)): chr(c + 32) for c in range(ord('A'), ord('Z') + 1)})
    return text.translate(table)


def _continuation(c: str) -> bool:
    return bool(c) and (c in '_-' or unicodedata.category(c)[0] in 'LMN' or c in '\u200c\u200d')


@lru_cache(maxsize=1)
def _trie():
    root = {}
    for row in (*load_locations(), Location(
            'legacy:berlin', 'city', 'Берлин',
            ('Берлин', 'Берлина', 'Берлину', 'Берлином', 'Берлине'), False)):
        for form in row.forms:
            node = root
            for c in _normalize(form):
                node = node.setdefault(c, {})
            node.setdefault(None, {})[row.id] = row
    return root


def find_locations(text: str, *, location_context: bool = False) -> Iterator[LocationMatch]:
    """Yield non-overlapping longest matches, without I/O other than local resources.

    `location_context` is ONLY for a caller-verified location field/cell, not an
    entire document. Ambiguous ordinary words otherwise require an immediately
    preceding city label. Case and е/ё do not change identity. Keep `surface` as
    the reversible mapping key, never use canonical IDs as a replacement value.
    Tabs, newlines and ALL Office sentinels are barriers. To match split runs,
    pass the caller's already mapped logical text for one paragraph/cell, then
    map these offsets back; never concatenate cells here.
    """
    normalized = _normalize(text)
    root = _trie()
    start = 0
    while start < len(text):
        if start and _continuation(normalized[start - 1]):
            start += 1
            continue
        node = root
        end = start
        best = None
        while end < len(text) and normalized[end] in node:
            char = normalized[end]
            node = node[char]
            end += 1
            if char == ' ':
                while end < len(text) and normalized[end] == ' ':
                    end += 1
            if None in node and (end == len(text) or not _continuation(normalized[end])):
                context = location_context or bool(_CONTEXT.search(text[max(0, start - 40):start]))
                candidates = tuple(sorted((r for r in node[None].values()
                    if not r.requires_context or context), key=lambda r: r.id))
                if candidates:
                    best = (end, candidates)
        if best is None:
            start += 1
            continue
        end, candidates = best
        yield LocationMatch(start, end, text[start:end], tuple(r.id for r in candidates),
                            tuple(r.canonical for r in candidates), tuple(r.kind for r in candidates))
        start = end


@dataclass(frozen=True)
class Location:
    id: str
    kind: str
    canonical: str
    forms: tuple[str, ...]
    requires_context: bool


@lru_cache(maxsize=1)
def _resource():
    return json.loads(files('local_anonymizer').joinpath(
        'assets/russian_geography/locations.json').read_text(encoding='utf-8'))


def resource_manifest() -> dict:
    """Return a copy of the pinned source provenance."""
    return dict(_resource()['manifest'])


@lru_cache(maxsize=1)
def load_locations() -> tuple[Location, ...]:
    return tuple(Location(**{**r, 'forms': tuple(r['forms'])}) for r in _resource()['locations'])
