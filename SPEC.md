# Локальный обезличиватель документов — MVP

Windows 11 desktop application, Russian UI, fully local at runtime, no HTTP/network server and no network requests. Python 3.11 backend + pywebview with bundled local HTML/CSS/JS (no CDN), python-docx, pywin32, SQLite. Build to a one-folder PyInstaller distribution with a launcher. The interface should closely retain the supplied corporate-portal layout: light grey page, white bordered cards, blue primary actions, two synchronized text columns, yellow review warning/candidates, category counters, collapsible mapping/reverse/settings sections, and the same Russian labels where applicable. Add a left/local-library selector or compact library strip without disrupting the familiar work area.

## Required user flow
1. Import one or more `.docx`, legacy `.doc`, `.xlsx`, `.txt`, `.csv`, `.md`, or `.log` files by file picker or drag-and-drop. Keep a local library and remember each imported file. Text formats are UTF-8-first with a clear encoding error/fallback; XLSX processes text and contextual numeric cells while preserving workbook structure as much as possible.
2. Click anonymize. Create an anonymized copy in the corresponding safe output format (`.docx`, `.xlsx`, or the same text extension) containing stable markers such as `[ФИО-1]`; irreversible secrets become `(удалено)` and are never stored in mappings.
3. Persist a separate mapping per document, encrypted for the current Windows user with DPAPI. Store library metadata in SQLite under `%LOCALAPPDATA%/LocalAnonymizer`; copied original documents and generated files are under the same app data root. Never store sensitive mapping or original values in plaintext logs/database.
4. Let the user export an anonymized document and a human-readable mapping table CSV on explicit request. Warn that exported CSV is sensitive.
5. Later import/select an edited anonymized `.docx`, `.xlsx`, or supported text file, associate it with the remembered document, and restore markers into a new `.restored.<ext>` file. Unknown markers remain unchanged and are reported. Secrets cannot be restored.
6. Show document list, status, source/output paths, detected replacements and warnings. Add delete action that removes the remembered record and app-owned files.
7. Preserve the existing workflow text in the UI: “Вставьте текст или перетащите файл…” and the sequence import → review replacements/yellow hints → copy/download → reverse replacement. “Справка” generates a short local processing summary suitable for attaching to a transfer or showing information security staff, containing counts/warnings but no mapping values or original sensitive text.
8. Settings accordion mirrors the supplied screenshot: category checkboxes (secrets always enabled; vulnerabilities; contacts; network; customer security products; requisites; finance; people; organizations/systems; tasks/IDs; custom dictionary; yellow hints), paranoid mode, monospaced editor toggle, reset defaults, and “Проверка движка”.
9. Dictionary profiles: default “Общий”, create/delete profile, export/import JSON file, multiline “Скрывать дополнительно” rules (`фраза` or `фраза => МЕТКА`, case-insensitive), multiline whitelist, all persisted locally. Imported profile files are validated and versioned; no executable content.

## Detector behavior (deterministic offline rules, best-effort MVP)
Use stable canonical matching so repeated values and aliases reuse markers. Preserve punctuation. Implement tests first (strict RED/GREEN).
- Email including Cyrillic domains -> `[ПОЧТА-n]`
- Russian/international phone formats -> `[ТЕЛЕФОН-n]`
- Telegram handles -> `[АККАУНТ-n]`
- IPv4/CIDR and IPv6 -> `[IP-n]`; MAC -> `[MAC-n]`; URLs including optional literal prefix `@url:` -> `[ССЫЛКА-n]`; host/domain -> `[ДОМЕН-n]` (avoid matching version 1.7.5.16)
- CVE/БДУ -> `[уязвимость]` (no mapping)
- Jira key and UUID/hash -> `[ЗАДАЧА-n]` / `[ID-n]`
- INN (10/12 digits), OGRN, SNILS, bank cards only if real checksum valid. Contextual KPP, account, cadastral number, Russian license plate, employee ID, contract/order numbers.
- Financial sums and financial percentages -> `[СУММА-n]`, `[СТАВКА-n]`; do not redact SLA, VAT, ports, versions.
- Secrets: password contexts, *_PASSWORD/*_PSWD assignments, obvious login:password pairs, API tokens/private-key blocks -> `(удалено)` or contextual variant, never mapping.
- Dates of birth only when context says it -> `[ДАТА-РОЖДЕНИЯ-n]`.
- Russian full names, initials + surname, Latin names; repeated surname after full-name detection should reuse same person marker. Role-context single names. Practical dictionaries/heuristics are acceptable and customizable.
- Organizations with Russian legal forms or LLC/GmbH and quoted system names after АС/система; later short aliases reuse marker.
- Security product names at minimum Secret Net Studio with version and ViPNet Client -> `[СЗИ-n]`.
- Yellow review candidates: role+department, cities, likely capitalized names. UI allows converting candidate to a marker or marking keep. A paranoid checkbox converts candidates automatically.
- User dictionary and whitelist persisted locally and export/import JSON.

## DOCX handling
- Process body paragraphs and nested table cells. Preserve paragraph/run formatting as much as possible, including replacements spanning multiple runs: replacement uses formatting of first covered run and unrelated runs survive.
- Also process headers/footers on anonymization rather than silently leaving PII. Remove comments, document core/custom properties, and tracked-deletion content. Accept visible inserted text. Remove hidden metadata where practical.
- Reverse markers across run boundaries in body, tables, headers/footers.
- Legacy `.doc`: use installed Microsoft Word COM to convert to `.docx`; show a clear error if Word automation unavailable. Never overwrite input files.

## Quality and security
- No eval, no network, no telemetry. Logging contains IDs/counts only, never original text or mappings.
- Atomic output writes. Path traversal safe. Clear errors in Russian.
- Unit tests for engine/checksums/storage, integration tests creating DOCX with body/table/header and split-run values; end-to-end anonymize/edit/restore roundtrip using the supplied example below.
- README in Russian with install/run/build instructions, limitations, security model, and explicit statement that final human review is mandatory.
- Include `run.bat`, `build.bat`, and `pyproject.toml`/lock or requirements.

## Acceptance sample
Use the full sample from the user when practical. At minimum assertions must cover: Иванов Сергей Петрович reused later for Иванов; ООО «Альфа» reused later for Альфа; emails, two phones, telegram, host, IPv4/CIDR, MAC, URL, Secret Net Studio 8.10, ViPNet Client, platform version left, CVE generalized, validated INN/SNILS/card, cadastral/license plate/employee ID, contract, sums, discount, SLA/VAT/port left, password forms irreversibly deleted, DOB, Latin name.

If a detector cannot safely meet a broad linguistic requirement without ML, implement conservative deterministic behavior, surface yellow candidates, document the limitation, and never claim full NER quality.
