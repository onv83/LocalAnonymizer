"""Offline generic given names and conservative, gender-aware case paradigms.

Exact dictionary spellings win over generated cases. Ambiguous generated forms
are detected but not merged with a guessed base. No substring/stem matching.
"""
import json
from importlib.resources import files


def normalize_given_name(value: str) -> str:
    return value.casefold().replace("ё", "е")


_ROOT = files("local_anonymizer").joinpath("assets/given_names")
GIVEN_NAMES = frozenset(normalize_given_name(line) for line in
                        _ROOT.joinpath("names.txt").read_text(encoding="utf-8").splitlines())
_GENDERS = json.loads(_ROOT.joinpath("genders.json").read_text(encoding="utf-8"))


def _case_forms(name: str, gender: str) -> set[str]:
    # Foreign vowel-final names and female consonant-final names stay unchanged.
    # These paradigms deliberately do not claim accent/ethnicity-complete morphology.
    if name == "лев":
        return {"льва", "льву", "львом", "льве"}
    if name == "павел":
        return {"павла", "павлу", "павлом", "павле"}
    if name.endswith("ия"):
        return {name[:-1] + end for end in ("и", "ю", "ей", "ею")}
    if name.endswith("ья"):
        return {name[:-1] + end for end in ("и", "е", "ю", "ей", "ею")}
    if name.endswith("а"):
        gen = "и" if name[-2] in "гкхжчшщ" else "ы"
        return {name[:-1] + end for end in (gen, "е", "у", "ой", "ою")}
    if name.endswith("я"):
        return {name[:-1] + end for end in ("и", "е", "ю", "ей", "ею")}
    if gender == "m" and name.endswith("ий"):
        return {name[:-1] + end for end in ("я", "ю", "ем", "и")}
    if gender == "m" and name.endswith(("й", "ь")):
        return {name[:-1] + end for end in ("я", "ю", "ем", "е")}
    if gender == "f" and name.endswith("ь"):
        return {name[:-1] + "и", name + "ю"}
    if gender == "m" and name[-1] in "бвгджзклмнпрстфхцчшщ":
        return {name + end for end in ("а", "у", "ом", "е")}
    return set()


_candidates: dict[str, set[str]] = {}
for _base, _gender in _GENDERS.items():
    for _form in _case_forms(_base, _gender):
        _candidates.setdefault(_form, set()).add(_base)
GIVEN_NAME_FORMS = GIVEN_NAMES | _candidates.keys()
_CANONICAL = {form: next(iter(bases)) for form, bases in _candidates.items()
              if len(bases) == 1 and form not in GIVEN_NAMES}


def canonical_given_name(value: str) -> str | None:
    key = normalize_given_name(value)
    if key in GIVEN_NAMES:
        return key
    if key in GIVEN_NAME_FORMS:
        return _CANONICAL.get(key, key)
    return None
