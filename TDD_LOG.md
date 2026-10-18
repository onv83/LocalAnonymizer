# TDD log

Commands were executed in `C:\Users\Lenovo\Documents\LocalAnonymizer`.

## Slice 1 — detector/checksums/acceptance sample

RED:
```text
uv run --no-project python -m pytest tests/test_engine.py -q
ERROR tests/test_engine.py
ModuleNotFoundError: No module named 'local_anonymizer'
1 error in 0.28s
```

Intermediate RED after first implementation:
```text
F... [100%]
AssertionError: [IP-1]
1 failed, 3 passed in 0.09s
```

GREEN after offset-based global candidate collection and fixes:
```text
.... [100%]
4 passed in 0.05s
```

The literal-marker/idempotence regression test was added after the security addendum arrived. It passed immediately because marker reservation had already been included while replacing the mutating detector architecture:
```text
. [100%]
1 passed in 0.04s
```
This particular regression therefore is tests-after, not a strict RED/GREEN cycle; it is recorded rather than misrepresented.

## Slice 2 — pywebview runnable shell

RED:
```text
uv run --no-project python -m pytest tests/test_app.py -q
ModuleNotFoundError: No module named 'local_anonymizer.app'
1 error in 0.21s
```

GREEN:
```text
. [100%]
1 passed in 0.03s
```

`run.bat --smoke`:
```json
{"ok": true, "asset": "C:\\Users\\Lenovo\\Documents\\LocalAnonymizer\\src\\local_anonymizer\\assets\\index.html", "engine": {"ok": true, "replacement_count": 2, "secret_count": 1, "warnings": []}}
```

## Slice 3 — DPAPI storage, DOCX and XLSX/text processors

RED:
```text
ERROR tests/test_storage.py: ModuleNotFoundError: No module named 'local_anonymizer.storage'
ERROR tests/test_documents.py: ModuleNotFoundError: No module named 'local_anonymizer.documents'
ERROR tests/test_formats.py: ModuleNotFoundError: No module named 'local_anonymizer.formats'
3 errors in 0.46s
```

Intermediate RED:
```text
3 failed, 5 passed in 1.59s
```
Failures covered Windows fsync publication and XLSX creator metadata.

GREEN:
```text
..... [100%]
5 passed in 1.23s
```
Storage tests were green in the intermediate run (`3 passed`).

## Slice 4 — service E2E, CSV safety and Word conversion

RED:
```text
ERROR tests/test_service.py: ModuleNotFoundError: No module named 'local_anonymizer.service'
ERROR tests/test_word_com.py: ModuleNotFoundError: No module named 'local_anonymizer.word_com'
2 errors in 0.26s
```

GREEN:
```text
.... [100%]
4 passed in 0.77s
```

## Slice 5 — persistent library/profile API

RED:
```text
TypeError: AppApi.__init__() got an unexpected keyword argument 'root'
1 failed in 0.19s
```

GREEN for import/library/anonymization:
```text
.................. [100%]
18 passed in 2.71s
```

Profile extension RED:
```text
AttributeError: 'AppApi' object has no attribute 'save_profile'
1 failed in 0.78s
```

Profile extension GREEN:
```text
.. [100%]
2 passed in 1.27s
```

## Release verification defects

The real Word COM check first rejected an unsupported `UpdateLinks` keyword, then exposed a corrupt DOCX caused by over-broad removal of OOXML `name` attributes. Both were corrected; the final Word COM check opens anonymized and restored output without repair. These fixes are covered by the Word-conversion and DOCX sanitation tests, but the real COM failures were integration discoveries rather than newly-authored failing unit tests.

## Parity P0 — reference-compatible engine and structured output

RED (`tests/test_parity.py`): 7 failures covering secret variants, expanded people/org/system/contact/requisite/finance detection, structured parts, sample behavior, ZIP, and rich UI. The first focused run ended with `7 failed in 1.01s`.

GREEN: detector coverage now matches the reference sample's `42` replacement occurrences, `6` hints, and `33` legend entries. Secret whitelist/custom-rule bypass tests failed first, then passed after making `SECRET` mandatory and irreversible. The protected-marker bypass and serializable-secret leak test also failed first, then passed after secret-priority overlap handling and removal of secret plaintext from parts.

The two superseded baseline assertions were updated deliberately: contracts use typed `[ДОГОВОР-N]`, and paranoid city hints use `[ГОРОД-N]` rather than generic `[КАНДИДАТ-N]`. Exact `(удалено)` counting was updated to count all typed irreversible placeholders.

## File/UI parity and safety gates

RED→GREEN cycles were recorded for:

- batch ZIP export (`AttributeError: export_all_ready`) → ready existing outputs only, unique archive names, no mappings/DB/sources;
- preview API (`AttributeError: preview_document`) → DOCX body/tables/headers/footers, XLSX strings, and text preview;
- stop warnings (`KeyError: status`) → `Экспорт запрещён` and fail-closed single/ZIP export;
- duplicate-surname collision, DOCX hyperlink canary, numeric XLSX requisites, and operation commit (`4 failed`) → `4 passed` after canonical reconciliation, OOXML `w:t` processing, contextual numeric cells, and transactional output/mapping switch;
- file-preview dirty-state/export gating and exact file/document branch assertions in the UI.

Final unit/integration suite before packaging:

```text
.................................... [100%]
36 passed in 6.86s
```

## Security hardening after independent review

Additional RED→GREEN slices covered:

- complete removal of quoted multiword secrets and synthetic JWTs without plaintext in serialized `parts`;
- two- and three-component Cyrillic/Latin names, declined surnames, order variants, uniquely matching initials, and ambiguous same-surname anchors;
- mandatory dictionary `SECRET` rules, empty-key rejection, word-boundary matching, and oversized marker suffixes;
- XLSX separator cardinality, PII in formula string literals, irreversible blocking of network/DDE/external-workbook formulas, and hidden hyperlinks/headers/validation/names/external parts;
- DOCX images, non-empty custom XML, charts/diagrams/unknown XML and external relationships with fail-closed warnings and custom-XML removal;
- artifact-bound restoration, status-enforced exports, explicit text mappings, stale UI result suppression, atomic import/conversion/stamping and old-output cleanup.

The integrated suite after these slices passed with `68 passed`.

## Shared marker contract

RED:

```text
FF [100%]
2 failed
```

A custom profile label containing digits and an underscore generated `[CASE_ID2-1]`, but the next analysis reused `-1` and text restoration left the marker unchanged.

GREEN: every engine, UI, text, DOCX and XLSX path now imports one bounded marker grammar (`1..9` suffix digits; profile-compatible labels).

```text
.. [100%]
2 passed
```

Final integrated verification after the marker fix:

```text
........................................................................ [100%]
72 passed in 8.99s
```

## Final blocker fixes

- Boundary-scope RED: a contextual passport match crossed `U+FDD0` while its captured
  replacement span did not; the focused regression failed with
  `паспорт\ufdd0 [ПАСПОРТ-1]`. GREEN after carrying the complete regex scope on
  detections and applying boundary isolation to that scope.
- Same-document race RED: two file anonymizations resolved newest-first, then the stale
  response replaced the new mapping. GREEN after generation tickets guarded every
  post-await mutation in both file-anonymization branches.

Final integrated verification: `84 passed in 9.04s`; `node --check` also passed.

## Final UI blocker fixes

- `hideHint()` now increments the counter for the actual generated marker category instead of always incrementing `СКРЫТО`; the runtime regression verifies `[ГОРОД-2]`, its mapping, and `counts.ГОРОД` behavior.
- `loadDocumentPreview()` now revalidates both the analysis generation and selected document after awaiting text analysis, so an obsolete preview cannot overwrite the active document status.

Both regressions were observed failing before the production fixes. Final integrated verification after the fixes: `85 passed in 13.21s`; source E2E smoke, `node --check`, and `compileall` passed.

## Safe formatted DOCX preview and Word round trip

Strict vertical RED→GREEN runs:

- formatted preview RED: `KeyError: 'rich_html'` (`1 failed in 2.57s`) → GREEN: `1 passed in 2.79s` after adding a server-side fixed-tag renderer with escaping, body/table order, nested tables, headings, run emphasis, bounded size/RGB, alignment, breaks/tabs, and separate header/footer sections;
- two-dialog restore RED: API returned an internal `output_path` and never opened a save dialog (`1 failed in 4.87s`) → GREEN: `1 passed in 2.95s` after destination-aware restore and a strict WebView response allowlist;
- UI workflow RED: missing `docxPreviewControls` (`1 failed in 2.32s`) → GREEN: `1 passed in 0.27s` after the default formatted view, text/highlight switch, and explicit Word workflow copy;
- anonymization bridge allowlist RED: `output_path`, `operation_id`, and `document_id` were present (`1 failed in 0.83s`) → GREEN: `1 passed in 0.87s` after returning only fields used by the UI.

The added end-to-end formatting/stamp/unknown-marker regression and save-cancel regression passed on first execution after their underlying vertical slices; this is recorded rather than represented as a separate RED cycle. Targeted integration: `10 passed in 3.26s`. Initial full suite: `91 passed in 10.09s`; `node --check`, `compileall`, and source smoke also passed.

A final UI transition regression then reproduced formatted preview remaining visible after programmatic Clear (`1 failed`). GREEN introduced one shared `leaveDocumentPreview()` transition for Clear, Sample, Paste, Delete, and manual text entry. Final integrated suite: `92 passed in 11.80s`; source E2E smoke, `node --check`, and `compileall` passed.

## Five final DOCX review blockers

Five strict vertical RED→GREEN slices were run:

1. Restore TOCTOU snapshot — the first draft assertion passed immediately because both documents used the same marker position; before any production change it was tightened with distinct `FIRST`/`SECOND` static content. The corrected RED deterministically swapped the external DOCX after stamp verification and restored `SECOND` static content with the first operation's mapping (`1 failed`). GREEN copies every supported restore input through one opened source handle into an app-owned private snapshot, then verifies and processes only that snapshot, with unconditional cleanup (`1 passed`).
2. DOCX sanitize rollback — RED forced `os.replace()` to fail and found `.existing-*.sanitize.tmp` (`1 failed`). GREEN wraps the complete replacement lifecycle in `try/finally`, preserving the prior destination and deleting the plaintext package (`1 passed`).
3. DOCX restore separator collision — RED changed three paragraphs into truncated/crossed pieces when the first contained literal `U+FDD0` (`1 failed`). GREEN restores each paragraph independently and aggregates unknown markers as a sorted deduplicated set while preserving run formatting (`1 passed`).
4. Same-document backend concurrency — RED let the older blocked invocation stale-commit after the newer call (`1 failed`). GREEN adds a thread-safe, reference-counted per-document lock around state read, processing, commit, and old-output cleanup; entries are removed after the final waiter and exceptions release through `finally` (`1 passed`).
5. Drag/drop DOCX preview — RED left the old library selection, empty rich preview, and import-only status (`1 failed`). GREEN explicitly selects the first returned imported id and awaits the generation-guarded preview load without overwriting its status (`1 passed`).

Targeted adversarial verification: `5 passed in 9.39s`.
Final integrated verification: `97 passed in 44.75s`; `node --check` and `compileall` passed. Source E2E returned `ok: true`, preserved the source, restored the DOCX, and reported only the intentional `[ФИО-999]` unknown marker.

## Settings and yellow-review controls

Synthetic RED regressions were added before the implementation. They failed because the
settings had terse labels, secrets were represented by a permanently disabled checkbox,
and the review counter/navigation mixed automatic replacements with actionable yellow
hints.

GREEN created physically new WebView assets `index-v1.8.3.html` and `app-v1.8.5.js`:

- every setting now says what changes and what happens when it is disabled;
- the mandatory secret rule is explanatory text rather than a dead control;
- yellow-review navigation contains only unresolved `.mark-hint` entries, selects the
  first item immediately, and disables action buttons only when no actionable hint exists;
- the counter and status now explain the disabled state instead of showing `0 из N`.

Focused UI verification: `46 passed in 10.52s`; JavaScript syntax passed. Final integrated
verification: `222 passed, 2 warnings in 84.55s`; `compileall`, source E2E,
`release_verify.py`, packaged/installed smoke, and Microsoft Defender scan passed.

## Settings release-review blockers

Independent v24 review found two cross-category leaks. Each was reproduced by a focused
RED regression before the production fix:

- disabling `Уязвимости` left the vulnerability detector off, but the generic task rule
  converted `CVE-2024-12345` into `[ЗАДАЧА-1]-12345`; GREEN excludes the reserved `CVE-`
  namespace from that fallback;
- the network/AD UI group omitted the engine's `DN` category, so a distinguished name was
  still replaced after the group was disabled; GREEN includes `DN` in the same control and
  is verified by extracting the exact UI payload and executing the engine with it.

The focused regressions passed (`2 passed`). The changed HTML uses a physically new
`index-v1.8.4.html` asset. Final source verification: `224 passed, 2 expected duplicate-ZIP
warnings`; `node --check`, `compileall`, source E2E, and `release_verify.py` passed. v25
packaged and installed smoke passed, Defender found no threats, and both EXEs have SHA-256
`022e9e4385ac851929fcc009a17d97d10677a95f957b317cb55d04c3613ed3c7`.

## One checkbox per actual marker class

RED proved that the broad category controls did not express the engine's real marker classes and
allowed lower-priority detectors to relabel values from disabled classes. GREEN replaces the bundles
with one checkbox per 40 normal reversible/fixed classes plus the three paranoid marker classes,
shows the exact marker beside each control, removes the dead `ID` control, and keeps secrets,
custom rules, and yellow-review behavior distinct. Disabled detector matches now reserve their spans
against generic/cross-category fallback; manual FIO/login, dictionary, and paranoid-hint paths obey
the same class switch.

`tests/test_category_controls.py` exercises every class enabled and disabled. The retained
`artifacts/category-controls-proof.json` records 86 physical Office checks (43 classes × DOCX/XLSX):
marker present and original absent when enabled, original present and marker absent when disabled,
including direct inspection of OOXML text payloads. Final source gates: `275 passed`, JavaScript
syntax and `compileall` passed, `release_verify.py` passed. Packaged and installed smoke passed;
Microsoft Defender found no threats. Immutable snapshot `build-release-final-v29` and the installed
tree contain the same 273 files; EXE SHA-256 is
`fabdb0064d1635018fda1b3a3b5e2f610efb179bc838249d93da90ebf20462b8`.
Installed-GUI business-effect check used the bundled synthetic example: toggling Organization
changed the visible marker and replacement count `4 → 3 → 4` immediately.

## Self-explanatory manual-review queue

RED added a UI contract requiring the review block to explain why a candidate is shown, the two
mutually exclusive outcomes, their effect on current settings, progress, accepted-decision state,
and the explicit completion step. GREEN replaces the terse button row with a structured review card,
renames the actions to `Скрыть и запомнить правило` and `Оставить и добавить в исключения`, records
hide and keep decisions consistently, and reports `Осталось N из M · решено K`. Empty, disabled,
completed, text-only, and file-export states now have distinct instructions. A stale yellow-count
banner discovered during packaged GUI testing was corrected so queue completion is reported at once.

Final source gates: `276 passed`, JavaScript syntax and Python `compileall` passed,
`release_verify.py` passed, and all 86 physical DOCX/XLSX category checks passed. Installed-GUI
business-effect proof used only the bundled synthetic example: one yellow candidate changed from
`Осталось 1 из 1 · решено 0` to `Осталось 0 из 1 · решено 1`; the candidate was replaced with a
marker, action buttons became unavailable, all duplicated yellow-status surfaces reported completion,
and the accepted-decision status was shown. Packaged and installed smoke passed; Defender found no
threats. `dist`, installed tree, and immutable `build-release-final-v32` match for all 273 files.
EXE SHA-256: `784fbda6d7dc81aa9a408aae82395b44497ff8b71440539a2bb66e34bdf802c2`.

## Single file-restore workflow

RED extended the UI contract after the installed GUI exposed two file-restore buttons in unrelated
locations (`Импортировать для восстановления…` and `Восстановить исправленный файл…`). GREEN removes
both ambiguous entry points and replaces them with one visible `Восстановление файла` card and one
`Восстановить файл…` action. The card names all three steps: select the originating local record,
select its exported anonymized copy (including a Word-edited copy), then choose the destination for
the new restored file. It identifies the selected record and whether its DPAPI-protected map is ready,
and reports the output path after completion. The separate reverse-text tool is collapsed and explicitly
labelled as text-only; it contains no file-restore action.

Verification: `276 passed`; JavaScript syntax, Python `compileall`, `release_verify.py`, and all 86
physical DOCX/XLSX checks passed. Packaged and installed smoke passed. Installed-GUI inspection showed
one `Восстановить файл…` button, the selected source record, map readiness, and all three steps together.
`dist`, installed tree, and immutable `build-release-final-v33` match for all 273 files. Defender found
no threats. EXE SHA-256: `260e0b01a0d78195232d8f3922d2fede3c76178e2067eeb1439328ef2b30f88b`.

## Office graphics scope shown in the GUI

- **RED:** `test_settings_are_explained_and_do_not_present_a_dead_checkbox` required a visible, non-toggleable DOCX graphics policy and explicit unsupported-object warning; it failed because the GUI contained neither.
- **GREEN:** the settings panel now states that embedded DOCX pictures and static schemes are always removed as `[СХЕМА-N]`, explains whole-image removal versus OCR, and names unsupported SmartArt, charts, OLE, and XLSX graphics with export blocking/manual review.
- **Verification:** targeted GUI contract passed; 12 graphics/drawing document tests passed; full suite 276 passed; category proof 86/86; release verification passed.

## Manual-review DOM integration regression

An independent read-only audit of v32 found that the final review action wrote to `#resultStatus`, but the element was absent from HTML. This could throw a null-reference error after the last decision.

RED added a contract assertion requiring `id="resultStatus"`; the targeted test failed before the fix. GREEN added the live status element to the review card. A static HTML/JS cross-check now reports 74 HTML IDs, 71 JavaScript ID references, and no missing references.

Verification after the fix: 276 pytest tests passed; JavaScript syntax and Python compilation passed; the Office proof remained 86/86; release verification passed; packaged and installed smoke passed. Installed and dist trees match 273/273 files. Defender reported `NO_THREATS` for immutable snapshot `build-release-final-v34`; EXE SHA-256: `b8b4699656d92a0494d9884c9576c4666f3d75908c968483c105072a96ed695e`.

## Stable manual-review navigation

The installed GUI reproduced the defect: `focusMark()` called `scrollIntoView()` for each candidate, so clicking `Следующее` scrolled the entire application page and moved the button away from the pointer. RED added a contract that forbids page-level `scrollIntoView()` in this path, requires scrolling only inside `#richOutput`, and requires the dynamic candidate card to have a fixed height with its own overflow.

GREEN adds `scrollMarkInsidePreview()`, which changes only the text-preview container's `scrollTop`, and gives `.review-candidate` a fixed 86 px viewport. The navigation row therefore keeps the same geometry while the candidate text and reason change.

Verification: 277 pytest tests passed; JavaScript syntax and Python compilation passed; the Office category proof remained 86/86; release verification passed. In the installed GUI, three successive candidates were opened by clicking the same screen point; the page group stayed at `y=-204` and `Следующее` stayed at `(1030, 883, 114, 30)` after every click. `dist`, installed tree, and immutable `build-release-final-v36` match for all 273 files. Defender found no threats. EXE SHA-256: `a7bfd41cc5d3267910b4abbbb6a64e32300b4a344571fb5b22926e502b596b2e`.

## Apply remembered hide decisions to every repetition

The manual `Скрыть и запомнить правило` action previously edited only the selected occurrence in the current rendering. RED added static and JavaScript-runtime regressions requiring the action to save the phrase, enable the `CUSTOM` category, and rerun anonymization of the complete current text/document before reporting success.

GREEN makes the action asynchronous and routes the whole source through the normal engine with the saved literal rule. Exact whole-phrase matches are processed case-insensitively, all repetitions share one reversible marker, stale manual-review candidates disappear, and the same rule applies to later occurrences. The GUI now explicitly explains this scope.

Verification: 278 pytest tests passed; JavaScript syntax and Python compilation passed; release verification passed with 47 replacements and Word COM opening both generated DOCX files; Office category proof passed 86/86. Installed-GUI proof started with two identical yellow candidates: one click produced two `[СКРЫТО-1]` markers and no remaining candidates; adding a third matching occurrence immediately produced a third `[СКРЫТО-1]`. The installed EXE and immutable `build-release-final-v37` EXE have the same SHA-256 `3f7377c5fc0ee52d9e3b8e7cd349250bbea16b2f3c7ae48fedb269c638be238d`. Defender found no threats in the v37 snapshot.

## Validated device identifiers and persistent light/dark theme

A review of `Pioneer113/mcp-152fz-anonymizer` found useful category ideas but its IMEI expression accepts any 15–17 digit sequence. RED therefore required an explicitly labelled IMEI with a valid Luhn checksum, rejected an invalid or unlabelled 15-digit value, required Cisco dotted MAC notation, and required an IPv6 CIDR prefix to be included in the reversible marker.

GREEN adds local dependency-free validation for those forms, an independent IMEI category switch, and physical DOCX/XLSX category proofs. It also adds an accessible light/dark theme button. Theme selection is persisted by the local backend in `ui-settings.json`; first launch follows the Windows/browser preference, while subsequent launches restore the user's explicit choice.

Verification: 284 pytest tests passed; JavaScript syntax passed; release verification passed with Word COM opening anonymized and restored DOCX files; Office category proof passed 88/88. Installed-GUI proof switched dark to light and, after a full process restart, reopened in light mode. Defender found no threats. The installed EXE and immutable `build-release-final-v38` EXE match at SHA-256 `66ec79893a07f2be7f55ebc73bb431f39d1f5d1e44992c0494547e7614250212`.

## Recreate Office file and refresh the visible result

The recreated Office file was written with current settings, but the text/formatted preview stayed on the previous result. This made a remembered rule appear ineffective after `Пересоздать файл с текущими настройками`, even when the generated DOCX had changed.

RED added a JavaScript-runtime regression requiring the file action to refresh the visible anonymized result, plus a service-level DOCX regression that recreates a file with `Яндекс => СКРЫТО`, verifies three repetitions use one marker, and inspects every ZIP member to prove the UTF-8/UTF-16 source value is physically absent. GREEN refreshes the preview only after successful file recreation and retains generation/document guards against stale asynchronous responses.

Verification: 286 pytest tests passed; JavaScript syntax passed; release verification opened anonymized and restored DOCX files through Word COM; Office category proof passed 88/88. Immutable `build-release-final-v39` and the installed EXE match at SHA-256 `b9292e1a6df97372c53a25496daad7ae1e3375d91037b6cd5a7da8918b838c36`; the packaged and installed JavaScript hashes both match the source. The installed application launched successfully, and Microsoft Defender found no threats in the v39 snapshot.

## Compact disabled-state review badge

Enabling `Автоматически скрывать спорное без подтверждения` caused the manual-review progress badge to receive the full explanatory sentence. Because `.review-progress` is intentionally non-wrapping, that min-content width expanded the right-hand column beyond the window and made the GUI appear broken.

RED added a JavaScript-runtime regression requiring a compact progress label while preserving the full explanation in the scrollable candidate area. GREEN keeps `#reviewPos` at `Ручная проверка отключена` and leaves the detailed reason in `#reviewCurrent`; no engine or anonymization behavior changed.

Verification: 287 pytest tests passed; JavaScript syntax passed; Office category proof passed 88/88. Installed v40 GUI proof toggled the checkbox on a real document: processing completed with 31 replacements and zero yellow candidates, the compact badge remained inside the review card, and both application columns fit the window without horizontal overflow. Source, immutable snapshot, and installed JavaScript hashes match at `437935439b8732ab1064396655cce95f28403267912d614fe802280e00e8830c`. Immutable and installed EXE hashes match at `5ec5abaf03ce371bd1d733f8cb118d32dab906a5bd7c713c91f2cedee52275e5`. Defender found no threats in `build-release-final-v40`.

## Two-file anonymized/recovery workflow

The previous export exposed only the anonymized document while restoration still depended on the application's hidden local library. That model was not understandable and did not allow independently managed file pairs.

RED added regressions requiring one export to create `Файл1 — обезличенный.<ext>` plus `Файл1 — информация для восстановления.larecovery`, automatic companion discovery by an internal pair identifier rather than filename alone, rejection of mismatched/tampered companions, restoration after deleting the local library record, renamed companion discovery, and two entries per document in batch ZIP export. GREEN stores the DPAPI-protected restore envelope in the companion, keeps the mapping out of plaintext, validates document/operation identifiers from both artifacts, and separates GUI pair selection/confirmation from the final Restore action.

Verification: 294 pytest tests passed; JavaScript syntax passed; packaged and installed `--pair-smoke` both used a DOCX pair and proved automatic discovery after library deletion, absence of recovery plaintext, and exact restoration. A DOCX integration regression also edits the exported anonymized document, deletes its library record, restores through the companion, and proves that both the user's edit and restored marker survive. The installed GUI visibly shows the three-step pair flow and `Сохранить два файла…`. Office category proof passed 88/88; Word COM release verification passed; Defender found no threats in `build-release-final-v42`. Immutable and installed EXE hashes match at `517bab6675f698e3ef372e7fcb7d7aae48476c4d326cf24b27e70f63afe61e2b`; source, snapshot, and installed HTML/JavaScript hashes also match.

## Aligned text previews with full-width manual review below

The manual-review card previously sat above the anonymized preview inside the right column. This pushed the anonymized text far below the source preview and made the two document views hard to compare.

RED added a DOM-layout regression requiring the source and anonymized previews to remain in the two top-row panes while `Ручная проверка спорных мест` and its warning are a separate direct child below both panes. The targeted test failed before the structural change. GREEN moves the complete review workflow below the two panes and spans it across both columns; no review IDs or JavaScript behavior changed.

Verification: the targeted regression passed, 52 UI/hardening tests passed, and the full suite passed with 295 tests. Chromium geometry at 1600 px showed identical preview tops (`delta: 0`), the review below both previews, and no horizontal overflow. At 760 px the layout stacked source, anonymized result, and review in that order, with no horizontal overflow; the populated queue and compact automatic-review-disabled text both stayed inside the review card.

## Optional DOCX static-graphics redaction

DOCX images and static schemes were previously removed unconditionally even though the surrounding anonymization controls are user-selectable. RED added a GUI regression requiring a real checked checkbox and a document regression requiring a valid embedded PNG to remain byte-identical when graphics redaction is disabled.

GREEN propagates the checkbox through preview, file recreation, API, service, and DOCX processing. Checked keeps the existing reversible `[СХЕМА-N]` removal; unchecked preserves safe PNG/JPEG/GIF/TIFF/BMP/EMF/WMF image parts while package hardening continues to reject unsupported active or linked objects.

Verification: 296 pytest tests passed; JavaScript syntax, Python compilation, release verification, category proof, and end-to-end smoke passed. The installed GUI showed the new checked control and successfully toggled it off. Packaged and installed `--pair-smoke` both passed. Immutable `build-release-final-v44` and the installed tree match for all 273 files with no mismatches; EXE SHA-256 is `2a66302bb063c852cd59abbe7041c90e68d720ff8dac37b0652856b980b0082a`.

## Dictionary-profile JSON export/import round trip

The export button previously serialized only the profile already stored in SQLite, not the rules and whitelist currently visible in the editor. After a valid import, the selector was refreshed but the imported profile was not loaded into the text areas because assigning a `<select>` value does not fire `onchange`. This made a successful import look like nothing happened.

RED added a JavaScript-runtime regression that enters rules and whitelist, exports, clears the editor, imports, and requires the same values to reappear. GREEN explicitly saves the visible settings before export, loads the imported profile into every editor control, reruns the preview, and shows success/error status. API regressions exercise the exact generated JSON file through export → modification → import and prove malformed or structurally invalid JSON reports an error without overwriting the existing profile.

Verification: the new runtime and API round-trip regressions passed; the full 299-test pytest suite, Python compilation, JavaScript syntax, release verification, category proof, and end-to-end smoke passed. Independent review found and blocked stale pair/ZIP export after import; GREEN now marks an existing document dirty, blocks both pair and ZIP exports until settings are applied, and shows that instruction in the import status. The rebuilt v45 application was reinstalled and launched. Source, packaged, and installed JavaScript hashes match at `b244933c1b3ed73943f0bff6ca947904b3f2955417648acac914b4cc5033c39f`; EXE hashes match at `efefba9e02222a46f7c25f91fb182e4ec87ecf7d660bf39cb7455a8cba8b7606`. Installed `--smoke` and Windows Defender scan passed.

## Classification labels are informational, not export blockers

The classifier treated a `Совершенно секретно` label as a `stop` warning and treated `ДСП`/`Конфиденциально` as review warnings. That contradicted the product purpose: classified documents are expected inputs, and their label alone says nothing about whether identifiers, addresses, names, domains, and other sensitive values were successfully anonymized.

RED replaced the old export-blocking assertion with parameterized service regressions for `Совершенно секретно`, `Для служебного пользования`, `ДСП`, and `Конфиденциально`. The focused command failed before the production change. GREEN marks classification findings as informational and excludes only `info` findings from readiness gating; unsupported embedded DOCX objects remain `stop` blockers.

Verification: classification-only TXT and DOCX files become `Готов`, single-pair and ZIP export succeed, and the existing unsupported-object blocker regression still passes. The full suite passed: 313 tests, 2 expected duplicate-ZIP warnings. The rebuilt application was installed. In the installed GUI a DOCX containing `Совершенно секретно`, `ДСП`, and `10.20.30.40` displayed `Гриф ... обнаружен. Это ожидаемо при обезличивании и само по себе не блокирует экспорт`; applying settings produced `Готов`, and `Сохранить два файла…` created both the DOCX and `.larecovery`. ZIP-level verification proved the IP was removed and replaced by `[IP-1]`, while both classification labels remained. Installed EXE SHA-256: `a648117327236ce7dac00f67a64f9df31dc213574d16fd71fb2bf8e41f3b08c0`.

## Cross-platform foundation without changing Windows behavior

RED added regressions for importing the runtime without Win32 modules, Windows/XDG/macOS data directories, injected and fail-closed data protection, an injected legacy `.doc` converter, an injected clipboard reader, platform-scoped GUI dependencies, and a single shared PyInstaller specification. GREEN moved DPAPI, clipboard access, and default data-path selection behind `platform_services`, added storage/service/API injection seams, retained Word COM as the default Windows `.doc` adapter, and made both build wrappers call `LocalAnonymizer.spec`.

The pair smoke check was inconsistent with the already-established portable recovery contract: production and its regressions intentionally use an unencrypted `.larecovery` containing source mappings, while the smoke test still required plaintext absence. The smoke assertion and README now describe the real sensitive-file contract rather than reporting a false failure.

Verification: 351 tests passed with 2 expected duplicate-ZIP warnings; the Windows PyInstaller build completed from `LocalAnonymizer.spec`; packaged `--smoke` and `--pair-smoke` passed; release verification restored DOCX exactly and opened both emitted DOCX files through real Microsoft Word COM. Independent review found and fixed three portability gaps: relative `XDG_DATA_HOME` values are ignored per the XDG contract, falsey injected `.doc` converters are respected instead of falling back to COM, and POSIX application directories/files receive private `0700`/`0600` permissions. Linux and macOS support is not claimed until native secure-storage, GUI, clipboard, packaging, and recovery checks run on those systems.

## Russian/English interface with persistent language choice

RED first covered the missing English assets and backend language setting. Further vertical regressions failed before implementation for persistent English startup, translation of backend document statuses/profile names/review kinds, translation of structured warning kinds, and duplicate numbering in the ordered workflow indicator. GREEN adds separate versioned Russian and English HTML/JavaScript entry assets, stores only `ru`/`en` in `ui-settings.json`, selects the matching page and window title at startup, and translates backend display values only at the English UI boundary while preserving all marker/category/status/profile contract keys.

Verification: 369 pytest tests passed with 3 expected duplicate-ZIP warnings; 98 UI/parity/hardening tests passed; both JavaScript files passed `node --check`; Python compilation passed. Browser checks at 1440×920 verified the English layout and exercised both `English → Русский` and `Русский → English` file-page transitions. The Windows PyInstaller build completed; packaged `--smoke` and `--pair-smoke` passed; release verification restored DOCX and opened anonymized/restored files through Microsoft Word COM. Source and packaged SHA-256 hashes match for all four new versioned UI assets. Windows DOC/DOCX processing code was not changed by the language feature.

A final independent localization review then found runtime-only leaks hidden from the static asset audit: raw backend status/error values and the Russian default profile name could still reach English messages. RED regressions reproduced those paths. GREEN routes document statuses through `documentStatusText`, profile names through `profileDisplayName`, and bridge failures through operation-specific English messages without changing backend contracts. A follow-up fail-closed review also caught the unknown-status fallback and profile save/export/import confirmations; both now avoid raw backend values. Final verification: 373 tests passed with the same 3 expected duplicate-ZIP warnings; JavaScript syntax and Python compilation passed; the Windows build, packaged `--smoke`, packaged `--pair-smoke`, real Word COM release verification, and source/package hashes for all four versioned UI assets passed.

## Packaged abbreviation leak regression

A formatted DOCX preview produced by an older installed build left an uppercase abbreviation with a trailing digit visible next to a detected organization. The current detector already handled the complete synthetic form `QZXB1`, including DOCX runs, but the packaged smoke gate did not exercise that path and therefore could not distinguish the stale executable.

RED added `abbreviation_ok` to the packaged-engine smoke contract; the focused test failed with `KeyError: 'abbreviation_ok'`. GREEN runs an organization-adjacent synthetic trailing-digit abbreviation through the real engine, requires the complete token to map to `СОКРАЩЕНИЯ`, and makes overall smoke success depend on that check. The DOCX regression now covers the same shape split across runs and still requires byte-exact restoration.

A separate test-runner RED exposed that the Windows `pytest.exe` entry point could not import `scripts.release_verify`; adding the repository root to pytest's configured `pythonpath` made the exact command green without changing packaged runtime behavior.

Independent review then found that a stale executable could still return exit code 0 from its own older `--smoke` implementation because it did not know about `abbreviation_ok`. A second RED proved the old installed backup was accepted by its self-test. GREEN adds `scripts/verify_packaged.py` as an external fail-closed validator, makes both `build.bat` and `verify-native.sh` invoke it, and requires the complete smoke, pair-smoke, and platform-smoke schemas. The external verifier now rejects the stale executable with `smoke.engine.abbreviation_ok must be true` and accepts the rebuilt executable.

Verification: the direct full `uv run pytest -q` suite passed with 486 tests and 3 expected duplicate-ZIP warnings; normal and optimized release verification passed; rebuilt dist, portable package, and installed application passed the external packaged verifier, including `abbreviation_ok`, pair restoration, and platform services. The same external verifier rejected the stale executable backup. A synthetic installed-GUI proof showed `QZXB1` replaced by `[СОКРАЩЕНИЯ-1]`. Microsoft Defender found no threats in the prepared portable package. GitHub Release `v0.2.9` remains unpublished pending user confirmation.

## Fail-closed DOCX-image release evidence

An older independent review inspected a pre-fix verifier and correctly found removable `assert` statements and a non-byte-exact comparison. Those defects had already been corrected before its delayed result arrived. Rechecking the current verifier found three remaining evidence gaps: it did not reject original image bytes hidden outside `word/media`, did not pin the reviewed synthetic image, and did not exercise missing or integrity-mutated recovery data inside the release gate.

Three focused RED tests reproduced the gaps: the package-verification helper was absent, a valid PNG with appended bytes was accepted, and the pair fail-closed helper was absent. GREEN adds whole-package original-byte scanning plus visible-marker verification, pins the reviewed synthetic PNG by SHA-256, and uses the public pair API to prove that missing and mutated recovery files raise `MappingError` without creating output. The normal and `python -O` verifier outputs now include `missing_mapping_rejected: true` and `mutated_mapping_rejected: true` only after those probes execute.

Verification: all 6 focused release-verifier tests passed; normal and optimized release verification passed with exact DOCX/image restoration, original graphic removal, and both fail-closed mapping probes; the full suite passed with 489 tests and 3 expected duplicate-ZIP warnings. The pinned PNG was visually rechecked as synthetic-only (`example.test`, private test addresses, fabricated host labels) and contains only `IHDR`, `IDAT`, and `IEND` chunks, with no text or metadata chunk.

## 2026-10-16 — Unicode continuation hardening and packaged proof

**RED:** Extended the complete-token abbreviation regression with a combining mark outside U+0300–U+036F (`U+0483`) and zero-width non-joiner (`U+200C`), including cases where those characters interrupt the three-uppercase run. The regression failed because the regex split both forms. Added smoke-contract tests requiring `abbreviation_unicode_ok`; the source self-test omitted the field and the external packaged validator accepted the stale payload.

**GREEN:** Replaced the bounded abbreviation regex with a Unicode-category scanner. All letter/number characters, every combining-mark category, underscores, internal hyphens, ZWNJ, and ZWJ remain in one token; marks and joiners do not reset the uppercase run. Added source smoke probes for `A\u0483BC` and `AB\u200cC`, and made the external packaged validator require their proof.

**VERIFY:** Focused abbreviation and engine tests passed (`56 passed`), manual probes passed for NFD continuation, post-run combining marks, ZWNJ, `U+0483`, `ÅBC`, `ÅÄÖ`, and `ЄЇІ`, and the full suite passed (`489 passed`, three expected duplicate-ZIP fixture warnings). The previous dist and installed executables were rejected with `smoke.engine.abbreviation_unicode_ok must be true`; a fresh Windows build passed the current external validator for smoke, pair-smoke, and platform-smoke.

## 2026-10-16 — Word TOC domain/page-number boundary

**RED:** A screenshot showed a formatted DOCX table of contents in which Word concatenated domain names and page numbers. A root domain remained fully visible, while subdomains were replaced only through an earlier label and leaked the registered-domain suffix. Synthetic engine and split-run DOCX regressions reproduced both failures (`2 failed`). A release-fixture regression then proved the case was absent from acceptance, and smoke-contract regressions proved packaged verification had no feature gate.

**GREEN:** Added a higher-priority domain match that consumes the complete valid alphabetic-TLD domain only when it is immediately followed by a terminal digit sequence, leaving those digits as the TOC page number. Added `domain_toc_ok` to engine self-test and to the external packaged validator. The synthetic acceptance DOCX now includes the boundary across formatted runs and requires complete domain removal plus a visible domain marker followed by the preserved page number.

**VERIFY:** Focused engine/DOCX/app/package/release tests passed (`11 passed`). The full suite passed (`491 passed`, three expected duplicate-ZIP fixture warnings). Normal and `python -O` release verification passed with byte-exact DOCX restoration and real Word COM opening both outputs. The pre-fix dist executable was rejected with `smoke.engine.domain_toc_ok must be true`; the rebuilt Windows executable passed smoke, pair-smoke, and platform-smoke through the external validator.

## 2026-10-17 — Contextual port category and reliable Windows staging

**RED:** Source, formatted DOCX, parity, UI, engine-smoke, packaged-contract, and release-acceptance regressions failed because contextual port numbers stayed visible and no `ПОРТ` category or `port_ok` gate existed (`9 failed`). A separate security regression showed that a numeric credential such as `user1:1234` could be downgraded to a reversible port when the host heuristic was too broad. Cross-format category proof then exposed two older debts: `СОКРАЩЕНИЯ` had no expected source value, and bare `assert` calls removed all processing under `python -O`. The default PyInstaller work/output paths also failed twice after their exact target directories disappeared during assembly.

**GREEN:** Added the reversible `ПОРТ` category for valid values 1–65535 in explicit labels, ranges, TCP/UDP forms, and IP/domain/bracketed-IPv6/infrastructure endpoints. URL spans keep whole-link priority; numeric credentials keep irreversible-secret priority; bare numbers, times, versions, zero, and values above 65535 remain unchanged. Added `[ПРТ-N]`, independent disable semantics, RU/EN controls and counts, split-run/tab DOCX restoration, acceptance coverage, `port_ok`, and external packaged validation. Category verification now has complete abbreviation/port fixtures and explicit fail-closed checks that execute under optimization. `build.bat` now builds and validates in a staging tree, publishes to `dist` only after success, and validates the published executable again.

**VERIFY:** Focused port/release checks passed (`14 passed`); category-control unit coverage passed (`47 passed`); normal and optimized DOCX/XLSX category proof passed (`92 checks` each); normal and optimized release verification passed with real Word COM and byte-exact restoration. The final full suite passed (`497 passed`, three expected duplicate-ZIP fixture warnings); Python and JavaScript syntax plus `git diff --check` passed. The staged Windows build completed and both its staging EXE and published `dist` EXE passed smoke, pair-smoke, and platform-smoke through the external validator. The still-running pre-update installed EXE was rejected by that validator as stale.

## 2026-10-17 — First-startup formatted source preview

**ROOT CAUSE:** Startup loads the saved profile before the selected library document. Profile loading schedules automatic analysis after 320 ms. The source text arrives first and sets the shared `generation`, but rich DOCX/ODT HTML is still crossing the pywebview bridge. Automatic analysis then increments that same generation, starts a competing formatted-output request against the single preview payload slot, and makes the source loader discard its eventual result. The exact visible state was a left plain-text pane with `Текст загружен · готовится форматированный вид…`, while the right formatted workflow could continue.

**RED:** An executable JavaScript regression held the source rich-HTML request unresolved, triggered the first-startup automatic analysis, and observed one conflicting formatted-output request, an empty source rich host, and the stuck plain-text lifecycle. A second bilingual pending-state regression observed `plainHidden: false`, `formattedHidden: true`, hidden source controls, and no preparation status in both RU and EN bundles.

**GREEN:** Source-preview invalidation now uses a dedicated `previewGeneration`; automatic text analysis cannot cancel it. `loadingPreview` remains active for the whole split source request, so anonymized rich rendering cannot overwrite the source token. DOCX/ODT immediately selects the formatted source host, shows a localized preparation status, disables only unavailable formatted controls, and keeps the optional text-mode button usable. New file-picker/drop invocations still invalidate any older source request.

**VERIFY (focused):** The exact race plus RU/EN pending-state regressions passed (`3 passed`), and the complete UI hardening suite passed (`27 passed`).

## 2026-10-17 — Russian inventory addresses and formatted-preview synchronization

**ADDRESS ROOT CAUSE / RED:** The Russian street-first detector required a comma between the street name and house, accepted only capitalized numeric street names, did not include an administrative-area/city prefix in the replacement span, and recognized arbitrary cities only through a short static list. Synthetic tests matching the document structure failed for a city/street/house without a comma, an ordinal street with a lowercase continuation, an administrative-area prefix, and separate Office fragments for region, federal district, and service-centre locality.

**ADDRESS GREEN:** The detector now accepts bounded whitespace or a comma before the house, ordinal numeric street forms, optional administrative-area and explicitly labelled city prefixes, and complete fragment-scoped inventory geography cells. A split-run DOCX table regression proves package-wide removal and byte-exact restoration. `address_inventory_ok` was added to engine smoke and the external packaged validator so stale executables fail closed.

**SCROLL ROOT CAUSE / RED:** The formatted-preview synchronizer deduplicated block anchors after clamping them to each pane's maximum scroll offset. Different marker wrapping put different numbers of final blocks below that limit, so two structurally identical previews acquired different anchor counts and incorrectly fell back to proportional scrolling. The executable bilingual regression mapped a matching block to `375` instead of `450` before the fix.

**SCROLL GREEN:** Every logical block now retains its positional slot even when several tail blocks clamp to the same maximum offset. Existing proportional fallback remains for genuinely unequal block counts; executable contracts also cover cache invalidation, hidden panes, and mode-position preservation.

**VERIFY:** Focused engine, DOCX, UI, app, and packaged-contract coverage passed (`260 passed`). The complete suite passed (`510 passed`, three expected duplicate-ZIP warnings). Source E2E, normal/optimized category proof (`92 checks` each), normal/optimized release verification, Python compilation, both JavaScript syntax checks, and `git diff --check` passed. On the real saved 44-table DOCX, source inventory cells contained `24` address forms, `63` region forms, `6` federal districts, and `3` service-centre localities; the rebuilt packaged preview contained zero remaining matches in all four groups and showed address/place markers. Runtime CDP verification at logical block `4919` found the same visible block in both panes while their physical `scrollTop` values correctly differed (`78921` versus `83025`). The external packaged validator passed, source/package RU and EN asset hashes matched, byte-exact restoration passed, and Microsoft Defender found no threats in the rebuilt distribution.

## 2026-10-17 — Independent-review blockers: address context, async state, and package provenance

**REVIEW / RED:** Exact-snapshot review rejected the first candidate. Runtime probes reproduced leaks for abbreviated/autonomous/republic-alias administrative forms and a lowercase numeric street continuation. Negative probes showed that standalone `Предметная область`, `Рабочая область`, bare federal-district adjectives, and `КЦ Тестирование` were over-redacted. Executable RU/EN Node regressions also proved three races: selecting document B did not invalidate document A's pending analysis, a settings change during source-preview loading was reset to clean and enabled export, and selecting text mode during rich rendering was overridden at completion. The packaged gate trusted executable booleans without binding the EXE and loose assets to the reviewed source.

**GREEN:** Administrative morphology now covers abbreviated regions, autonomous areas/districts, adjective-first republics, and dash-separated aliases. Numeric street names accept lowercase continuations only behind an explicit street anchor. Complete postal grammar covers leading/trailing index, several explicit geographic components, `пр.`/full street labels, `зд.`/`дом №`, initials, `имени`, and reversed street/house/city/index order. Ambiguous geography cells are detected only as a contiguous inventory row whose fourth cell is a validated postal address, eliminating the standalone false positives. Source loading now invalidates analysis generation, retains settings-generation dirtiness, and preserves the user's pending mode and scroll. Build provenance embeds a deterministic runtime-source digest, Git revision, and worktree-diff digest into the executable; the external manifest additionally pins the EXE and every bundled UI asset.

**VERIFY (focused):** The administrative and six complete-postal address variants, ordinary-fragment negatives, split-run DOCX cases with byte-exact restoration, six bilingual async-state regressions, exact inventory/postal self-tests, provenance generation, manifest tamper checks, JavaScript syntax, and the modified subsystem suites passed. A read-only run against the saved 44-table document found no remaining complete source address in the corresponding anonymized cells and restored the DOCX byte-exactly. Full release/build/installed verification follows after the corrected snapshot is independently reviewed.

## 2026-10-17 — Bounded postal spans and DOCX address cells

**ROOT CAUSE / RED:** A privacy-safe structural scan of the saved DOCX found `128` address cells, but only `82` were replaced as one exact address value; `34` still exposed sensitive source tokens. The component grammar stopped at a locally valid street/house span and could not consume reordered city/region/index components, street-name-before-type forms, trailing building qualifiers, or one non-breaking-space variant. A first whole-record fix removed those leaks, but independent review and synthetic probes rejected its architecture: it could consume surrounding contractual prose, classify project-like `пр.` phrases as addresses, miss a dotted street type joined directly to its name, and leave a lowercase street name open.

**RED:** Synthetic cases covered a complete address embedded between payment prose, no space after a dotted street type, a lowercase street name under strong geographic context, repeatable building qualifiers, and project-like controls. Before the bounded fix, the focused run had `6 failed, 9 passed`; the DOCX integration set additionally exercised split runs, exact surrounding text, table-cell controls, and byte-exact restoration.

**GREEN:** Added a typed component grammar for embedded postal spans: explicit street/house joins, bounded leading or trailing geography, repeatable building parts, Unicode horizontal whitespace, and guarded ambiguous `пр.` forms. Unlabelled house numbers require a strict street name, while labelled houses may retain lowercase names under strong context. The broad line fallback was removed. A separate higher-priority fallback is now restricted to a single DOCX table cell between Office sentinels; it validates street/house structure and typed geography for ambiguous abbreviations, so it can consume uncommon real inventory-cell order without touching ordinary text lines. Explicitly labelled addresses use their own bounded path and preserve surrounding prose.

**VERIFY (source):** Engine, hardening, and DOCX suites passed (`148 passed`). Dedicated DOCX regressions prove exact replacement inside surrounding formatted runs, preservation of project-like table-cell prose, and byte-exact restoration. The privacy-safe saved-document scan reports `128/128` address cells as exact single-marker mappings, `0` leaking cells, `0` tails after a marker, and byte-exact DOCX restoration.

## 2026-10-17 — Complete packaged-runtime manifest

**ROOT CAUSE / RED:** The external manifest pinned the executable and all 52 UI assets, but a packaged tree contained 407 files and had no inventory for the remaining runtime DLLs, archives, libraries, or metadata. A changed runtime file raised no error, and an unmanifested file could be added without invalidating verification. Two focused regressions failed with a missing `files` record and `DID NOT RAISE VerificationError`.

**GREEN:** Manifest schema 2 records the size and SHA-256 of every regular file in the Windows/Linux package tree and the target of every package-internal symlink in a macOS bundle. Validation recomputes the complete inventory and rejects changed, missing, added, or package-root-escaping entries. The explicitly supplied external manifest is excluded only when it is copied inside the installed package, preventing the manifest from being required to hash itself while still rejecting every unrelated extra file.

**VERIFY (focused):** Runtime tamper, unmanifested-addition, and installed-manifest-location checks passed together with the complete packaged-verifier suite (`11 passed`).

## 2026-10-17 — Native CI verification sequencing

**CI ROOT CAUSE:** Run `39001011674` failed in the native build step on both runners. `build.sh` had begun running the full external verifier immediately after PyInstaller, before Linux Secret Service/X11 setup was restored and before the macOS test-keychain item was cleared. Linux `--smoke` exited with code 1; macOS `--pair-smoke` reached the 180-second timeout. The workflow's dedicated native verification steps, which establish those prerequisites, were never reached.

**RED / GREEN:** A focused regression first failed because `build.sh` invoked `verify_packaged.py`. The POSIX build now only produces the provenance-bound executable. `verify-native.sh`, already executed inside the platform-prepared CI environment, runs `--write-manifest`; that single external-verifier invocation performs all smoke checks, writes schema-2 inventory only after they pass, and validates the result. A second RED proved the native archive commands omitted that external manifest; the Linux tarball and macOS staging archive now include it alongside the application. The focused build/verifier suites then passed (`25 passed`).

## 2026-10-17 — Formatted-preview completion scroll alignment

**ROOT CAUSE / RED:** The installed GUI could show different logical tables in the two formatted panes while an anonymized DOCX preview was regenerated. During the asynchronous render, source scrolling was synchronized to the temporary plain-text output by proportional progress. When formatted HTML arrived, that approximate plain-text position was transferred into the formatted pane, losing the source pane's logical-block position. A deterministic bilingual runtime regression reproduced the race with unequal block heights: the old code restored `375` while the matching source block mapped to `450`.

**GREEN:** Formatted-preview completion now samples the currently visible source pane after rendering finishes, switches the anonymized pane to formatted mode, and restores that live logical position directly into the new formatted DOM. Existing block-anchor interpolation continues to handle large replacement, wrapping, table, and visual-height differences during bidirectional scrolling.

**VERIFY:** The new RU/EN race regression passed (`2 passed`), the complete app-hardening suite passed (`39 passed`), both localized JavaScript assets passed `node --check`, and the full source suite passed (`556 passed`). Source e2e, category controls in normal and optimized modes, release verification in normal and optimized modes, and `compileall` also passed.

## 2026-10-18 — Structural scroll anchors and layout-reflow recovery

**ROOT CAUSE / RED:** The asynchronous completion fix covered one race but the scroll algorithm still used ordinal anchors. With blocks removed, the old unequal-count fallback mapped a shared source block to `300` instead of its matching target block at `250`. Multi-column or nested table DOM traversal yielded non-monotonic offsets (`100, 320, 180, 450`), breaking binary search. Cached offsets also remained stale when an image changed block positions without changing the pane's total scroll height. Separate RED regressions observed no structural identifiers in source/anonymized DOCX HTML, the wrong shared-block mapping, unsorted visual anchors, a missing reflow refresh path, and an automatic image-load result that stayed at `250` instead of moving to `350`. An image-only first header also made the same later text header receive `/0/` in the source preview and `/1/` after graphic replacement.

**GREEN:** DOCX rendering now emits matching, non-sensitive structural `data-preview-anchor` paths for body, header/footer, paragraph, table-row, cell, and nested-table blocks; graphics replacement preserves those paths. Header/footer part numbers follow unique OOXML part order rather than the number of already rendered parts, so a graphic-only part cannot shift later shared identities. The bilingual scroll mapper pairs shared identifiers even when counts differ, interpolates between shared physical positions, sorts anchors by rendered vertical position, and keeps proportional progress only when no structural identifiers are shared. It invalidates and re-maps after formatted subtree replacement, image load, font readiness, or window resize while retaining the last genuinely scrolled pane as leader.

**VERIFY:** Stable source/anonymized structural anchors, image-only-header identity, removed-block mapping, nested/multi-column visual ordering, manual reflow refresh, automatic late-image realignment, and the original asynchronous completion race all passed for RU and EN. The complete app-hardening suite passed (`47 passed`), the app integration suite passed (`107 passed`), and the full source suite passed (`566 passed`, three expected duplicate-ZIP fixture warnings). Both JavaScript syntax checks, `git diff --check`, source E2E, normal/optimized category proof (`92 checks` each), normal/optimized release verification with byte-exact restoration and real Word COM, and Python compilation passed.

## 2026-10-18 — Compact manual-review decisions

**RED:** A bilingual DOM regression required the persistent descriptions beside both manual-review decision buttons to be absent, required both explanatory `title` tooltips to remain, and required `hideCandidate` to follow `reviewNext` in the same navigation group. It failed against the prior markup because `hideCandidate` remained in the separate actions column with an adjacent `<small>` description.

**GREEN:** The “Скрыть и запомнить правило” / “Hide and remember rule” action now follows “Следующее” / “Next” in the same wrapping navigation row. The “Оставить и добавить в исключения” / “Keep and add to whitelist” action remains in the decision area. The duplicate always-visible descriptions were removed from both localized pages while the complete hover tooltips and existing element identifiers, handlers, disabled state, keyboard order, and business behavior were preserved.

**VERIFY (source):** The focused bilingual regression passed, the app integration suite passed (`108 passed`), and the full source suite passed (`567 passed`, three expected duplicate-ZIP fixture warnings). Both localized JavaScript assets passed `node --check`; `compileall`, source E2E, normal/optimized category verification, normal/optimized release verification with byte-exact restoration and real Word COM, and `git diff --check` passed.

## 2026-10-18 — Bounded server-inventory names

**ROOT CAUSE / RED:** The generic node detector recognized only known textual prefixes, explicitly listed roles, or role and instance segments separated by another delimiter. Inventory names with an `s`/`v` class letter, four-digit site code, compact alphabetic role plus a two-digit instance, and an optional numeric suffix therefore remained visible. A standalone synthetic regression and a sentinel-separated inventory-table regression each failed. Two additional RED tests proved that the application lacked a complete engine self-test for the new forms and that the external packaged validator accepted a stale executable without that proof.

**GREEN:** Added a bounded case-insensitive standalone rule for the high-confidence `s`/`v` structure, preserving exact source spelling for reversible mappings. A separate context-only path recognizes extended, prefixless, and short forms exclusively in the name column of a structured table whose headers also identify an IP-address column and software or service context, and only when the row contains a valid IP address. The hostname alphabet is explicitly ASCII-scoped so Unicode case-fold characters cannot be absorbed into a partial infrastructure match. Ordinary similar identifiers and non-infrastructure tables remain unchanged. The packaged smoke contract now reports `server_inventory_name_ok`, and the external validator requires it.

**VERIFY (source):** Six engine/DOCX regressions passed, covering case variants, suffixes, short contextual names, Unicode-boundary negatives, misleading prose/tables, category disablement, DOCX package removal, and byte-exact restoration. The engine, DOCX, app, and packaged-verifier suites passed together (`225 passed`); the complete source suite passed (`575 passed`, three expected duplicate-ZIP fixture warnings).
