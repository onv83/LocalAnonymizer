"""Rebuild the B72 generic given-name resource from a pinned upstream JSONL.

Offline conversion only. See assets/given_names/README.md for acquisition/license.
Never pass a full-person dataset: only upstream names.jsonl is accepted by hash.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SOURCE_SHA256 = "edf0bbe77afcfb121fa5a8a50b089cdf73b9b2cb51c0f876562b6f3476472cd0"
# Ambiguous technical/common vocabulary must not become person anchors.
EXCLUDED = frozenset("сервер кабинет антенна мета".split())


def build(source: Path, destination: Path) -> dict:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected pinned upstream names.jsonl")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    names = set()
    for row in rows:
        count = row["count"]
        if isinstance(count, dict):
            count = count["$numberLong"]
        name = row["text"].casefold()
        if (row.get("gender") in {"m", "f"} and int(count) >= 2
                and re.fullmatch(r"[а-яё]{3,30}", name)
                and name.replace("ё", "е") not in EXCLUDED):
            names.add(name)
    data = ("\n".join(sorted(names)) + "\n").encode("utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "names.txt").write_bytes(data)
    genders = {}
    for row in rows:
        name = row["text"].casefold()
        if name in names and row.get("gender") in {"m", "f"}:
            key = name.replace("ё", "е")
            genders.setdefault(key, set()).add(row["gender"])
    (destination / "genders.json").write_text(json.dumps(
        {key: "".join(sorted(value)) for key, value in sorted(genders.items())},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    stats = {
        "source_rows": len(rows), "source_sha256": SOURCE_SHA256,
        "spellings": len(names),
        "normalized_keys": len({name.replace("ё", "е") for name in names}),
        "yo_spellings": sum("ё" in name for name in names),
        "resource_bytes": len(data), "resource_sha256": hashlib.sha256(data).hexdigest(),
        "excluded_ambiguous_words": sorted(EXCLUDED),
    }
    (destination / "manifest.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.destination), ensure_ascii=False, indent=2))
