# Offline Russian geography — provenance and integration

Prepared 2026-10-29. This is a dated recognition dictionary, not a definitive or current administrative register.

## Attribution and licensing

Source: **HFLabs, city**, https://github.com/hflabs/city , revision `ae661bffe572880472249097c9b29c42b09650ea` (2021-10-11).
Pinned CSV: https://raw.githubusercontent.com/hflabs/city/ae661bffe572880472249097c9b29c42b09650ea/city.csv
CSV SHA-256: `aefd11fd133881c348e0138b273a300ec6b3909c8f61d8d1d5ffc5e85021ec0d`.
Upstream credits DaData.ru for fields other than population/year, which come from Wikipedia. The original upstream README is preserved as HFLABS-README.md.

The vendored CSV and derived locations.json are licensed **Creative Commons Attribution-ShareAlike 4.0 International**: https://creativecommons.org/licenses/by-sa/4.0/ . Full terms are bundled in CC-BY-SA-4.0.txt. Preserve attribution, license, and this modification notice when redistributing the data; do not re-label it as the application code license. No endorsement is implied.

Modifications: build-time finite case forms, curated compound and irregular forms, normalized region titles, IDs and ordinary-word ambiguity flags. No third-party morphology dictionary is used. Runtime and offline rebuilding use Python's standard library only.

## Scope and limitations

The snapshot has **1,117 city-source records and 85 distinct region pairs**. Region IDs are deterministic hashes of the upstream type/name; city IDs retain upstream FIAS UUIDs. Namesakes retain multiple IDs rather than being silently merged. Includes upstream Crimea/Sevastopol naming without any sovereignty assertion. No post-snapshot changes or independent coverage reconciliation are claimed.

The finite rule generator supports common noun/adjective cases and selected compound irregularities; it is not a fully validated Russian morphology engine. Some unhandled plurals/irregular forms remain nominative-only, and heuristic generated cases can require further linguistic review. Snapshot inventory tests do not prove linguistic completeness. Bare nominal republic names (for example Татарстан/Татарстане and Башкортостан/Башкортостаном) share the official title's identity; indeclinable Коми and Марий Эл are retained. Bare adjective republic titles are not added as aliases. Alias coverage is selective; abbreviations and every colloquial region name are not covered. Ambiguity guards are conservative and intentionally reduce recall for ordinary-word cities; they cannot guarantee absence of all homonym errors.

## Integration API

`from local_anonymizer.russian_geography import find_locations, load_locations, resource_manifest`

`find_locations(text, *, location_context=False)` yields frozen `LocationMatch` objects with `start`, `end` (half-open Python string offsets), exact `surface`, `location_ids`, `canonical_names`, and `kinds` tuples. Longest complete phrase wins; Cyrillic case, е/ё, selected horizontal spaces and dash variants preserve physical offsets. Identifiers and combining-mark continuations are rejected. No suffix wildcards run against document text.

Use `location_context=True` only for a caller-verified location field/cell, never globally because one city appeared elsewhere. Otherwise ambiguous words require an immediately preceding city label such as `г.` or `городе`.

For existing anonymization, retain category ГОРОД and stronger full-address priority. Preserve whitelist, disabled-category, review, overlap, and exact reversible surface behavior. Canonical IDs identify entities, not replacement/restoration strings: different cases must keep distinct exact-surface mappings. This module does not modify engine behavior itself.

Tabs, newlines and Office sentinels are barriers. For split Word runs, callers must pass their existing mapped logical text within one paragraph/cell and map the returned offsets back. Do not concatenate distinct cells. `load_locations()` returns immutable location records; `resource_manifest()` returns a metadata copy.

## Rebuild and delivery

From repository root: `.venv/Scripts/python.exe scripts/build_russian_geography.py` (offline, deterministic; no install).
Tests: `.venv/Scripts/python.exe -m pytest tests/test_russian_geography.py -q`.

Bundle this entire assets/russian_geography directory, including license and notice. Engine integration, wheel and frozen-app execution are separate acceptance gates; this isolated change does not claim they have been verified.
