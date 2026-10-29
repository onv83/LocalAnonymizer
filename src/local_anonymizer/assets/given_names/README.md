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

## Reproducible filtering

Extract names.jsonl locally and run:

```
python scripts/build_given_names.py PATH_TO_NAMES_JSONL src/local_anonymizer/assets/given_names
```

The converter rejects a mismatched SHA-256. It accepts gender-labelled m/f
records with count >= 2 and 3–30 Russian Cyrillic letters, casefolds and dedupes;
excludes ambiguous technical vocabulary `сервер кабинет антенна мета`. The
upstream count is only a quality filter, not evidence of spelling correctness.
Result: **10,283 spellings / 10,275 ё→е normalized keys**, 8 ё spellings,
142,779 bytes UTF-8 names.txt. Hashes are in manifest.json. genders.json contains
only generic lexical gender metadata used to choose conservative paradigms.

## Detection and morphology

Runtime is entirely offline using importlib.resources; no MongoDB or downloaded
package is needed. Dictionary entries are exact tokens, not arbitrary stems.
Existing small-name morphology remains separate. The new bounded pair rule
requires a known given name or generated case form and an adjacent capitalized
Cyrillic surname (both orders). It does not cross punctuation, newline or DOCX
cell/paragraph boundaries. Both-known-name pairs, patronymics and selected
organization/product/title contexts are excluded. Existing suffix-based surname
rules are retained rather than indiscriminately broadened.

Gender-aware Russian paradigms cover -а/-я (including -ия/-ья), masculine
consonants/-й/-ий/-ь and feminine -ь, with explicit Лев/Павел irregulars.
Female consonant-final and other vowel-final names remain indeclinable. This
creates **48,191 exact accepted base/case keys**. These are conservative spelling
rules, not a universal morphological analyser: stress, foreign -а exceptions,
rare irregulars, compound names and non-Russian Cyrillic letters are incomplete.
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
