# Changelog

All notable changes to LocalAnonymizer are documented here.

The project follows [Semantic Versioning](https://semver.org/). GitHub Releases contain the verified Windows packages and matching checksums.

## [Unreleased]

### English

No unreleased changes yet.

### Русский

Новых неопубликованных изменений пока нет.

## [0.2.1] — 2026-10-14

### English

#### Fixed

- DOCX cells and paragraphs containing manual line breaks now anonymize every server name and enabled IP address instead of joining adjacent lines during detection.
- Word hard breaks, tabs, run formatting, and the existing DOC/DOCX formatting-preserving pipeline remain intact.

### Русский

#### Исправлено

- В ячейках и абзацах DOCX с ручными переносами строк теперь обезличиваются все имена серверов и включённые IP-адреса: соседние строки больше не склеиваются при распознавании.
- Ручные переносы Word, табуляция, форматирование фрагментов и существующий конвейер сохранения оформления DOC/DOCX остаются неизменными.

## [0.2.0] — 2026-10-14

### English

#### Added

- Local ODT anonymization, recovery, and sanitized formatted previews.
- English interface with persistent Russian/English language selection.
- Bidirectional synchronized scrolling between source and anonymized document previews, mapped by logical document blocks.
- Cross-platform foundations for Linux and macOS: native data directories, keyring-backed AES-GCM storage, clipboard adapters, shared PyInstaller configuration, and native verification scripts.
- English and Russian interface screenshots in the repository documentation.

#### Changed

- Windows remains the reference and fully verified platform for DOC/DOCX fidelity; Linux and macOS packages are not yet published as supported releases.
- Identity matching is more conservative: uncertain surname variants remain separate unless stronger evidence links them to the same person.
- Source and anonymized previews now remain vertically aligned across plain/formatted modes, collapsed sections, resizing, responsive layouts, and fullscreen transitions.

#### Security

- Non-Windows protected storage fails closed when a suitable system keyring is unavailable; plaintext fallback is not permitted.
- ODT/DOCX formatted previews use sanitized, bounded local content and do not expose raw document XML, scripts, event handlers, or external URLs.
- Platform smoke tests verify secure storage and clipboard backend availability without reading or modifying the user's clipboard.

### Русский

#### Добавлено

- Локальное обезличивание и восстановление ODT, а также безопасный форматированный предпросмотр.
- Английский интерфейс с сохранением выбора русского или английского языка.
- Двунаправленная синхронная прокрутка исходного и обезличенного документов по логическим блокам.
- Кроссплатформенная основа для Linux и macOS: системные каталоги данных, AES-GCM с ключом в системном keyring, адаптеры буфера обмена, общая конфигурация PyInstaller и нативные проверочные скрипты.
- Скриншоты русского и английского интерфейсов в документации репозитория.

#### Изменено

- Windows остаётся основной полностью проверенной платформой для точного сохранения DOC/DOCX; готовые поддерживаемые сборки Linux и macOS пока не публикуются.
- Сопоставление ФИО стало консервативнее: сомнительные варианты фамилий остаются раздельными без достаточно сильных признаков одной личности.
- Исходный и обезличенный предпросмотры всегда начинаются на одном уровне при переключении обычного и форматированного режима, сворачивании секций, изменении размера окна, адаптивной компоновке и полноэкранном просмотре.

#### Безопасность

- На системах вне Windows защищённое хранилище прекращает работу при отсутствии подходящего системного keyring; открытый fallback запрещён.
- Форматированный предпросмотр ODT/DOCX использует очищенное локальное содержимое с ограниченным размером и не передаёт сырой XML, скрипты, обработчики событий или внешние URL.
- Платформенная smoke-проверка подтверждает наличие защищённого хранилища и буфера обмена, не читая и не изменяя пользовательский clipboard.

## [0.1.0] — 2026-10-12

### English

- First verified Windows x64 release.
- Fully local reversible anonymization with encrypted mappings and portable recovery files.
- DOCX formatting preservation, Microsoft Word COM conversion for legacy DOC, XLSX and text-format processing.
- Conservative handling of uncertain surname variants.

### Русский

- Первый проверенный выпуск для Windows x64.
- Полностью локальное обратимое обезличивание с зашифрованными картами и переносимыми файлами восстановления.
- Сохранение форматирования DOCX, преобразование старых DOC через Microsoft Word COM, обработка XLSX и текстовых форматов.
- Консервативная обработка неопределённых вариантов фамилий.

[Unreleased]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/onv83/LocalAnonymizer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/onv83/LocalAnonymizer/releases/tag/v0.1.0
