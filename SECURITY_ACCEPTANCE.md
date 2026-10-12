# Security and detector acceptance additions

These requirements are release gates for the local anonymizer.

## Fail-closed DOCX handling
- Inspect the whole OOXML ZIP, not only `python-docx` surfaces. Remove comments, core/custom properties, tracked deletions, external relationships/templates/images, and unsupported hidden text where safe.
- Process visible body, nested tables, headers and footers. If footnotes/endnotes/text boxes/diagram text/embedded objects/alt-text or another unsupported text-bearing part is detected, do not show an unconditional success status: mark the document `Требуется ручная проверка` and list the unsupported parts without exposing their text in logs.
- Canary tests must unzip output and assert sensitive canaries are absent from every ZIP entry that is expected to be sanitized.

## Storage and restoration binding
- DPAPI envelope must include schema version, `document_id`, anonymization-operation ID, marker manifest and integrity checks. Restoration with another document's mapping or a corrupted/truncated blob must fail closed before producing output.
- Existing literal marker-looking text must not collide with generated markers. Preserve it through roundtrip using an escaped/reserved manifest strategy.
- SQLite/logs/WAL/temp files must not contain plaintext mappings or document text. Logs contain IDs/counts/error types only.
- Deletion may remove only canonical app-owned paths beneath the application data root; never delete the user's imported source. Defend against `..`, absolute-path substitution, symlinks/junctions.
- File publication is atomic; status must never say ready without a valid output.
- Mapping CSV export must neutralize spreadsheet formula injection for values beginning with `=`, `+`, `-`, or `@`, and require an explicit warning/confirmation in the UI.

## DOC conversion
- Word COM: disable macros, alerts and link updates; open read-only; never overwrite input; always close document and quit Word on errors. Treat `.doc` as untrusted.

## Detector architecture
- Do not mutate text detector-by-detector. Collect candidates on original offsets, globally resolve overlaps deterministically, then replace right-to-left.
- Priority: protected markers/allowlist; secrets; checksum-validated identifiers; URL/email/network/contact compounds; finance; organizations; people; weak contextual IDs.
- Credential URI beats URL; URL beats nested domain/IP/port; email beats nested username/domain; organization beats a person name inside its legal name; full FIO beats component names; validated identifiers beat generic numbers.
- Canonical aliases are scoped per document. Different categories never merge. A bare surname reuses a person only when exactly one compatible full-name anchor exists. Organization aliases derive from a strong legal-name/context anchor.
- Assignment of marker indexes is deterministic by first accepted occurrence.
- Explicit non-redaction classifiers cover software versions, SLA/availability percentages, VAT/НДС rates, ports, dates and common technical/model numbers.
- Reprocessing an already anonymized document is idempotent.

## P0 tests
1. Split-run replacement preserves unrelated run formatting.
2. Reverse split-run markers in body, nested tables, headers and footers; unknown markers remain and are reported; removed secrets never return.
3. Wrong/corrupted mapping fails closed and publishes no output.
4. Literal marker collision roundtrips correctly.
5. Plaintext canaries absent from DB, WAL/journal, logs and app temp files except intentionally stored original/restored copies.
6. Atomic-write failure does not corrupt previous output or create false ready state.
7. Safe deletion cannot escape app root or delete imported source.
8. No external relationships remain in emitted DOCX; runtime code performs no network calls.
9. `.doc` conversion disables macros/link updates and always closes Word.
10. Output opens with both `python-docx` and Word COM; input is byte-for-byte unchanged.

README must state: copied originals remain sensitive; DPAPI does not protect against compromise of the current Windows user/admin; secure deletion on SSD is not guaranteed; final human review is mandatory.
