"""Rebuild generic given-name resources from pinned public sources.

Offline conversion only. See assets/given_names/README.md for acquisition/license.
Only upstream first-name collections are accepted by hash; surnames and full-person
records are never emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import unicodedata
from zipfile import ZipFile

SOURCE_SHA256 = "edf0bbe77afcfb121fa5a8a50b089cdf73b9b2cb51c0f876562b6f3476472cd0"
MIMESIS_REVISION = "8897e1c879cba8ec3088246c0cf1e79d6888d0d9"
MIMESIS_ARCHIVE_SHA256 = "8be7d058fee2b716a84bf94cd3abc6aa261f787a00fe57d18b904da828aa4d57"
SURNAMES_SOURCE_SHA256 = "8c7a263eb0e1886f9482f01fd0f2d22e5132d51ff45266e3b592902abc8f8c6d"
SURNAME_MIN_COUNT = 5
# Ambiguous technical/common vocabulary must not become person anchors.
EXCLUDED = frozenset("сервер кабинет антенна мета".split())
RUSSIAN_LETTERS = frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
UKRAINIAN_LETTERS = frozenset("іїєґ")


def _is_cyrillic_name(name: str) -> bool:
    return (
        3 <= len(name) <= 30
        and all("CYRILLIC" in unicodedata.name(character, "") for character in name)
        and name.replace("ё", "е") not in EXCLUDED
    )


def _is_cyrillic_surname(name: str) -> bool:
    return (
        2 <= len(name) <= 40
        and all("CYRILLIC" in unicodedata.name(character, "") for character in name)
        and name.replace("ё", "е") not in EXCLUDED
    )


def _surname_names(source: Path) -> tuple[set[str], dict]:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SURNAMES_SOURCE_SHA256:
        raise ValueError("Expected pinned upstream surnames.jsonl")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    names: set[str] = set()
    for row in rows:
        count = row.get("count", 0)
        if isinstance(count, dict):
            count = count.get("$numberLong", 0)
        if int(count) < SURNAME_MIN_COUNT:
            continue
        for field in ("text", "f_form", "m_form"):
            name = row.get(field, "").casefold()
            if _is_cyrillic_surname(name):
                names.add(name)
    return names, {"surnames_source_rows": len(rows)}


def _mimesis_names(archive: Path) -> tuple[set[str], dict[str, set[str]], dict[str, str], dict]:
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MIMESIS_ARCHIVE_SHA256:
        raise ValueError("Expected pinned Mimesis archive")
    names: set[str] = set()
    genders: dict[str, set[str]] = {}
    declensions: dict[str, str] = {}
    locales: set[str] = set()
    extended: set[str] = set()
    with ZipFile(archive) as package:
        for member in package.namelist():
            parts = PurePosixPath(member).parts
            if len(parts) != 5 or parts[-1] != "person.json" or parts[-3] != "datasets":
                continue
            locale = parts[-2]
            data = json.loads(package.read(member))
            accepted_before = len(names)
            for gender, short_gender in (("female", "f"), ("male", "m")):
                for value in data.get("names", {}).get(gender, []):
                    name = value.casefold()
                    if not _is_cyrillic_name(name):
                        continue
                    names.add(name)
                    genders.setdefault(name, set()).add(short_gender)
                    if locale == "uk" and UKRAINIAN_LETTERS.intersection(name):
                        declensions[name] = "uk"
                    if any(character not in RUSSIAN_LETTERS for character in name):
                        extended.add(name)
            if len(names) > accepted_before:
                locales.add(locale)
        license_member = next(
            (member for member in package.namelist()
             if len(PurePosixPath(member).parts) == 2 and member.endswith("/LICENSE")),
            None,
        )
        if license_member is None:
            raise ValueError("Pinned Mimesis archive has no LICENSE")
        license_bytes = package.read(license_member)
    stats = {
        "mimesis_revision": MIMESIS_REVISION,
        "mimesis_archive_sha256": MIMESIS_ARCHIVE_SHA256,
        "mimesis_locales": sorted(locales),
        "mimesis_spellings": len(names),
        "mimesis_extended_cyrillic_spellings": len(extended),
        "mimesis_license_sha256": hashlib.sha256(license_bytes).hexdigest(),
    }
    return names, genders, declensions, {"stats": stats, "license": license_bytes}


def build(source: Path, destination: Path, mimesis_archive: Path | None = None,
          surnames_source: Path | None = None) -> dict:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected pinned upstream names.jsonl")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    names: set[str] = set()
    genders: dict[str, set[str]] = {}
    declensions: dict[str, str] = {}
    for row in rows:
        count = row["count"]
        if isinstance(count, dict):
            count = count["$numberLong"]
        name = row["text"].casefold()
        if row.get("gender") in {"m", "f"} and int(count) >= 2 and _is_cyrillic_name(name):
            names.add(name)
            genders.setdefault(name, set()).add(row["gender"])
    datacoon_names = set(names)
    mimesis_stats = {}
    mimesis_license = None
    if mimesis_archive is not None:
        extra_names, extra_genders, declensions, metadata = _mimesis_names(mimesis_archive)
        names.update(extra_names)
        for name, values in extra_genders.items():
            genders.setdefault(name, set()).update(values)
        mimesis_stats = metadata["stats"]
        mimesis_stats["mimesis_new_spellings"] = len(extra_names - datacoon_names)
        mimesis_license = metadata["license"]
    destination.mkdir(parents=True, exist_ok=True)
    surname_stats = {}
    if surnames_source is not None:
        surnames, surname_stats = _surname_names(surnames_source)
        surname_data = ("\n".join(sorted(surnames)) + "\n").encode("utf-8")
        (destination / "surnames.txt").write_bytes(surname_data)
        surname_stats.update({
            "surnames_source_sha256": SURNAMES_SOURCE_SHA256,
            "surname_min_count": SURNAME_MIN_COUNT,
            "surname_spellings": len(surnames),
            "surname_normalized_keys": len({name.replace("ё", "е") for name in surnames}),
            "surname_resource_bytes": len(surname_data),
            "surname_resource_sha256": hashlib.sha256(surname_data).hexdigest(),
        })
    data = ("\n".join(sorted(names)) + "\n").encode("utf-8")
    (destination / "names.txt").write_bytes(data)
    (destination / "genders.json").write_text(json.dumps(
        {name.replace("ё", "е"): "".join(sorted(values)) for name, values in sorted(genders.items())},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (destination / "declensions.json").write_text(json.dumps(
        declensions, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if mimesis_license is not None:
        (destination / "LICENSE-MIMESIS.txt").write_bytes(mimesis_license)
    stats = {
        "source_rows": len(rows), "source_sha256": SOURCE_SHA256,
        "datacoon_spellings": len(datacoon_names),
        "spellings": len(names),
        "normalized_keys": len({name.replace("ё", "е") for name in names}),
        "yo_spellings": sum("ё" in name for name in names),
        "resource_bytes": len(data), "resource_sha256": hashlib.sha256(data).hexdigest(),
        "excluded_ambiguous_words": sorted(EXCLUDED),
        **mimesis_stats,
        **surname_stats,
    }
    (destination / "manifest.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("mimesis_archive", type=Path, nargs="?")
    parser.add_argument("surnames_source", type=Path, nargs="?")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.destination, args.mimesis_archive, args.surnames_source), ensure_ascii=False, indent=2))
