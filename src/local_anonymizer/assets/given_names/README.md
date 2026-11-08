# B72 offline generic given-name vocabulary

Source: Ivan Begtin / datacoon, **russiannames**, BSD 3-Clause (see LICENSE.txt).
Pinned revision: `e4e7e687b9d53db9bca815c26c2a13f8bc66c4b0`.

- Repository: https://github.com/datacoon/russiannames
- License: https://github.com/datacoon/russiannames/blob/e4e7e687b9d53db9bca815c26c2a13f8bc66c4b0/LICENSE
- Archive: https://raw.githubusercontent.com/datacoon/russiannames/e4e7e687b9d53db9bca815c26c2a13f8bc66c4b0/data/jsonl/russiannames_db_jsonl.zip
- Member used: **names.jsonl only**. No surnames, full-person lists, original
  user documents, identifiers, frequencies or ethnic classifications are shipped.
  Upstream supplies separate generic lexical collections; its README documents
  32,134 first-name records and Slavic, Turkic, Arabic, Armenian, Georgian,
  German, Greek, Jewish and Polish traditions. Its historical primary collection
  methodology is not documented; this is not an authoritative civil registry.
- The pinned repository's BSD license covers the repository; no separate data
  license is present in that snapshot. Copyright (c) 2018, Ivan Begtin.

Second source: **Mimesis**, MIT (see LICENSE-MIMESIS.txt), pinned revision
`8897e1c879cba8ec3088246c0cf1e79d6888d0d9`.

- Repository: https://github.com/lk-geimfari/mimesis
- Archive: https://github.com/lk-geimfari/mimesis/archive/8897e1c879cba8ec3088246c0cf1e79d6888d0d9.zip
- Archive SHA-256: `8be7d058fee2b716a84bf94cd3abc6aa261f787a00fe57d18b904da828aa4d57`.
- Only `mimesis/datasets/*/person.json → names.female/names.male` is read.
  Surnames, full-person combinations, employers, addresses and other fields are
  not emitted. Contributing Cyrillic locales are `kk`, `ru`, `uk`; other naming
  traditions remain covered by the datacoon lexical collection.

Generic surnames come from the same pinned datacoon archive, member
`surnames.jsonl` (SHA-256 `8c7a263eb0e1886f9482f01fd0f2d22e5132d51ff45266e3b592902abc8f8c6d`).
Only `text`, `f_form` and `m_form` with upstream count >= 5 are retained; ethnic
classifications and full-person combinations are not emitted. This yields
**109,477 generic Russian-written surname/base forms** (109,329 normalized keys,
1,845,697 bytes), including
Tatar, Slavic, Turkic and other traditions present upstream. The count threshold
is a precision/coverage trade-off, not a civil-registry claim.

## Reproducible filtering

Extract names.jsonl locally and run:

```
python scripts/build_given_names.py PATH_TO_NAMES_JSONL src/local_anonymizer/assets/given_names PATH_TO_MIMESIS_ZIP PATH_TO_SURNAMES_JSONL
```

The converter rejects mismatched SHA-256 values. It accepts gender-labelled m/f
records with count >= 2 and 3–30 Unicode Cyrillic letters, casefolds and dedupes;
excludes ambiguous technical vocabulary `сервер кабинет антенна мета`. The
upstream count is only a quality filter, not evidence of spelling correctness.
Mimesis contributes 2,163 generic spellings (1,436 new), including 644 with
letters beyond `а-яё`. Combined result: **11,719 spellings / 11,711 ё→е
normalized keys**, 8 ё spellings, 163,585 bytes UTF-8 names.txt. Hashes are in
manifest.json. genders.json contains only generic lexical gender metadata used
to choose conservative paradigms; declensions.json marks Ukrainian-specific
forms without assigning ethnicity to any person.

## Detection and morphology

Runtime is entirely offline using importlib.resources; no MongoDB or downloaded
package is needed. Dictionary entries are exact tokens, not arbitrary stems.
Existing small-name morphology remains separate. The bounded pair rule
requires a known given name/case form, or a known generic surname plus explicit
person context, next to an adjacent capitalized Cyrillic candidate (both orders).
Unknown-given + known-surname matching is deliberately blocked in legal,
geographic and technical prose without person context. It does not cross
punctuation, newline or DOCX cell/paragraph boundaries. Both-known-name pairs,
patronymics and selected organization/product/title contexts are excluded.
Role-labelled single surnames support DOCX cell/run boundaries; unlabelled
surnames are not globally masked merely because they occur in the dictionary.
Existing suffix-based surname rules are retained rather than indiscriminately
broadened.

Gender-aware paradigms cover -а/-я (including -ия/-ья), masculine
consonants/-й/-ий/-ь and feminine -ь, with explicit Лев/Павел irregulars and
Ukrainian -ій/-ія forms. Female consonant-final and other vowel-final names stay
indeclinable. This creates **54,436 exact accepted base/case keys**. These are
conservative spelling rules, not a universal morphological analyser: stress,
foreign -а exceptions, rare irregulars, compound names and Cyrillic beyond
U+04FF are incomplete.
Both detection and canonical identity normalize ё/е; source spelling and offsets
remain untouched for restoration. Exact lexical bases win over generated forms;
colliding generated forms are detected but retain separate identity keys rather
than merging different people. For example Романа is also a lexical base,
Роману can belong to Роман or Романа, and upstream has Игор and Дмитрии.

## Limits and distribution

The vocabulary includes noisy historical spellings; it is not every name in
Russia. Rare/singleton and unlabelled entries are intentionally omitted. A
capitalized noun adjacent to a name can still be ambiguous, and an atypical
surname that is itself a known given name is deliberately not inferred by the
new rule. Name-only mentions and arbitrary lowercase surnames are not universally
covered. Review remains necessary; no all-document or installed-release claim.

The complete directory (including license and attribution) lives under assets,
already recursively bundled by LocalAnonymizer.spec and inside the Hatch wheel
package path. Frozen-resource verification is recorded in the unified backlog.
