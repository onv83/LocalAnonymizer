# Changelog

All notable changes to LocalAnonymizer are documented here.

The project follows [Semantic Versioning](https://semver.org/). GitHub Releases contain the verified Windows packages and matching checksums.

## [Unreleased]

### English

#### Changed

- Added a separate reversible `ПОРТ` / Port category for valid 1–65535 values in explicit `port` labels, ranges, TCP/UDP forms, and IP/domain/IPv6/infrastructure endpoints. Bare numbers, times, versions, invalid values, and numeric credentials stay out of the detector; URLs keep precedence as one link marker. The category includes a UI switch, counts, compact `[ПРТ-N]` markers, DOCX split-run/tab support, byte-exact restoration, release acceptance, and an external packaged-build gate.
- Release verification now embeds a digest-pinned synthetic test diagram in its DOCX fixture, proves across every ZIP member that anonymization removes the original image bytes and inserts visible `[СХЕМА-1]`, rejects missing or integrity-mutated recovery mappings without creating output, and proves byte-exact document restoration plus exact image-byte restoration after editing. The public README screenshots now use this synthetic document.
- Added the independent `СОКРАЩЕНИЯ` / Abbreviations category: every standalone token containing at least three consecutive uppercase Unicode letters is replaced with a reversible `[СОКРАЩЕНИЯ-N]` marker. A token made of exactly two uppercase letters is also replaced when the same NFC-normalized token occurs at least six times across the document's logical text; Unicode combining marks and join controls remain token continuations rather than extra letters. Five or fewer occurrences, mixed-case forms, and longer identifiers do not activate the frequency rule. The category has a separate UI switch, counts, compact markers, DOCX support across runs, tables, and tabs, and an external packaged-build proof.
- Added native Linux/macOS CI builds and packaged smoke gates, including Linux desktop-session tests and an isolated macOS Keychain probe; PyInstaller now collects the runtime-loaded secure-storage backends on those platforms. Windows remains the primary supported platform, and the Word COM path is unchanged.
- Packaged builds now include the runtime `python-docx` templates required for DOCX creation and export.
- Moved the compact manual-review workspace below the two preview panes, kept the apply controls visible, and placed optional review modes in a collapsed disclosure.
- Removed duplicate always-visible descriptions beside the two manual-review decision buttons while keeping their hover tooltips, and placed `Hide and remember rule` directly after `Next`.
- The anonymized-preview toolbar now appears as soon as formatted rendering starts, shows a clear preparation message, and keeps unavailable formatted-only controls disabled until the view is ready.
- Rewrote the built-in usage guide to match the current interface: the Open button, automatic preview, side-by-side document panes, manual review below the previews, fixed apply control, and the current export and restoration buttons.
- Removed the visible drag-and-drop hint while retaining window-level file drop, and used the reclaimed space to enlarge both document previews.
- Collapsed the empty undo-restoration row below the anonymized preview, reducing the blank gap before the statistics from 36 to 8 pixels while keeping real undo actions visible.
- Removed the redundant visible source-editor label and the static local-storage notice from both interface languages while retaining an accessible label for the editor.
- All collapsible section headers now show a right-pointing arrow when closed and a downward arrow when open.
- Compacted the desktop header controls into one row, kept the complete explanation on a slim second line, and enlarged the document preview panes in low-height windows.
- Increased the preferred desktop window width from 1440 to 1600 pixels so long preview-status text and the two document panes have more horizontal space, while clamping the launch size and position to the primary monitor's working area on constrained displays.

#### Fixed

- Contextual Russian address lists now redact every complete entry without absorbing the surrounding sentence. The bounded grammar accepts `аллея`, numeric ordinals ending in `-ый`, slash-letter house suffixes, and space-separated building qualifiers; an explicitly labelled singular address may omit the street type when its name is title-cased and followed by a labelled house. Ambiguous `пр.` remains restricted to direct address or bounded address-list context, ordinary project prose stays visible, DOCX runs are sanitized with byte-exact restoration, and packaged verification requires a dedicated current-build proof.
- Server-inventory names that use an `s`/`v` class prefix, four-digit site code, hyphenated compact role and two-digit instance are now redacted as `УЗЕЛ` case-insensitively, including optional numeric suffixes. In inventory tables with name, IP-address and software/service columns, the name column also accepts the same bounded structure with another or omitted one-letter prefix and a short two-letter/two-digit form. Ordinary identifiers outside that table context remain untouched, and packaged verification now requires a dedicated proof from the current executable.
- Fixed formatted-preview desynchronization after large text replacements, removed diagrams, nested or multi-column tables, and delayed image layout. DOCX previews now carry matching structural block identifiers; scroll mapping continuously pairs shared identifiers, sorts anchors by their visual position, and re-aligns after formatted DOM or image layout changes. When the anonymized preview finishes asynchronously, it restores directly from the currently visible source pane instead of inheriting proportional progress from the temporary plain-text pane.
- On first startup with an existing DOCX/ODT document, automatic profile analysis no longer cancels the source document's formatted-preview load and leaves the left pane stuck as plain text. The formatted source pane is now selected immediately with a localized preparation status, while conflicting formatted-output work waits for the source preview to finish.
- Russian postal and inventory-style addresses now redact the complete value: leading or trailing postal index, administrative hierarchy, explicitly labelled city/district, street, building, and house. A typed component grammar consumes only the complete embedded address span, while a dedicated DOCX table-cell fallback handles uncommon component order and building qualifiers without extending to ordinary text lines. The detector supports street names before their type, no space after a dotted type, lowercase names in strongly typed postal context, non-breaking spaces, and repeatable block, structure, letter, premises, or office parts. The grammar covers `пр.` and full street labels, `зд.`/`дом №`, initials and `имени` in street names, lowercase numeric-street continuations, republic/abbreviated-region/autonomous forms, and dash-separated aliases. Narrative text around an embedded address remains visible, and project-like phrases are not treated as addresses. Separate region, federal-district, and service-centre cells are redacted only as a complete inventory row ending in a validated address, so ordinary phrases such as subject/work areas and isolated directional adjectives remain visible.
- The source and anonymized formatted previews now keep one logical document position when replacements change wrapping near the scrollable tail. Logical block anchors retain their one-to-one indexes even when several final blocks clamp to the same maximum scroll offset, instead of incorrectly falling back to unrelated proportional positions.
- Selecting another document now invalidates every in-flight text analysis. Settings changed while a source preview is loading remain dirty and keep export blocked, and choosing the text view during formatted rendering preserves that mode and its scroll position when rich HTML arrives.
- Packaged verification is now bound to an external manifest containing the executable hash, the size and SHA-256 of every bundled runtime file, all bundled UI-asset hashes, the Git revision, the worktree-diff hash, and a deterministic runtime-source snapshot embedded into the executable. A stale, added, missing, or mixed executable/runtime/asset/source combination fails closed even if its internal smoke booleans report success.
- The Windows build wrapper now assembles and externally verifies the PyInstaller tree in dedicated staging paths, publishes to `dist` only after that proof succeeds, and verifies the published executable again; intermittent deletion or locking of the default PyInstaller target can no longer produce a partial successful build.
- Linux/macOS builds now defer executable smoke checks and manifest creation to the platform-aware verification step, after Linux Secret Service/X11 setup or macOS test-keychain cleanup. This prevents the build phase from failing before the required native services are available, and both native archives now include the verified external manifest alongside the application.
- Domains immediately followed by a Word table-of-contents page number are now redacted as the complete domain while preserving the page number; subdomains can no longer be partially replaced while leaking the registered-domain suffix. DOCX, release-acceptance, engine-smoke, and external packaged-build gates cover this case.
- Packaged build verification now runs an external fail-closed check for an organization-adjacent, trailing-digit abbreviation such as `QZXB1`; an outdated executable that self-reports success but omits this proof is rejected by the Windows and native release gates.
- Abbreviation token scanning now treats every Unicode combining-mark category plus zero-width non-joiner/joiner as token continuations, so canonically equivalent or format-joined forms cannot expose a token fragment; packaged smoke requires the corresponding `abbreviation_unicode_ok` proof.
- Clearing a loaded formatted document now hides both formatted-preview hosts before restoring the empty text panes, preventing the anonymized preview from remaining as a second blank panel.
- Postal addresses written after an explicit address label now redact the street, building, city, and trailing five- or six-digit postal index without treating unrelated numbers as postal codes.
- Russian street-first and street-suffix forms such as `ул. Энтузиастов, д.5, к.6` and `Профсоюзная улица, 125А` are now redacted without hiding generic mentions of streets or avenues.
- Document headings, the phrase `в том числе`, contract defect wording, and payment deadlines in working days no longer seed false organization, disk, person, or money replacements across a document.
- English `Contact:`, `Address:`, and `Software:` fields now redact labelled names, postal addresses and software values in plain text and DOCX while preserving formatting and exact restoration.

### Русский

#### Изменено

- Добавлена отдельная обратимая категория `ПОРТ` для допустимых значений 1–65535 после явной подписи «порт»/`port`, в диапазонах, обозначениях TCP/UDP и конечных точках IP/домен/IPv6/инфраструктурный узел. Голые числа, время, версии, недопустимые значения и цифровые учётные данные не считаются портами; ссылка сохраняет приоритет и заменяется одним маркером. Для категории добавлены переключатель, счётчики, компактный маркер `[ПРТ-N]`, DOCX с разрывами runs и табуляцией, побайтное восстановление, приёмочная проверка и внешний барьер готовой сборки.
- В проверочный DOCX для релиза добавлен синтетический тестовый рисунок с закреплённым хешем: проверка просматривает все элементы ZIP, доказывает удаление исходных байтов рисунка с видимой заменой на `[СХЕМА-1]`, безопасно отклоняет отсутствующую или изменённую информацию для восстановления без создания выходного файла, а также проверяет побайтное восстановление неизменённого документа и точное восстановление байтов рисунка после редактирования. Публичные скриншоты README обновлены на этом синтетическом документе.
- Добавлена самостоятельная категория `СОКРАЩЕНИЯ`: каждый отдельный токен, содержащий не менее трёх подряд заглавных Unicode-букв, заменяется обратимым маркером `[СОКРАЩЕНИЯ-N]`. Токен ровно из двух заглавных букв также заменяется, если тот же NFC-нормализованный токен встречается в логическом тексте документа не менее шести раз; комбинируемые Unicode-символы и управляющие символы соединения остаются продолжением токена, а не дополнительными буквами. Пять и менее вхождений, формы в другом регистре и более длинные идентификаторы частотное правило не включают. Для категории предусмотрены отдельный переключатель, счётчик, компактные маркеры, поддержка DOCX с разрывами runs, таблицами и табуляцией и внешняя проверка готовой сборки.
- Добавлены нативные CI-сборки Linux/macOS и проверки упакованных приложений, включая Linux-тесты в графической сессии и изолированную проверку macOS Keychain; PyInstaller теперь включает динамически загружаемые модули защищённого хранилища для этих платформ. Windows остаётся основной поддерживаемой платформой, Word COM-конвейер не изменён.
- В готовые сборки включены служебные шаблоны `python-docx`, необходимые во время создания и экспорта DOCX.
- Компактный блок ручной проверки перенесён под две панели предпросмотра, панель применения остаётся видимой, а дополнительные режимы проверки находятся в сворачиваемом блоке.
- У двух кнопок решения в блоке ручной проверки удалены дублирующие постоянные пояснения, но сохранены всплывающие подсказки; кнопка «Скрыть и запомнить правило» размещена сразу после кнопки «Следующее».
- Панель обезличенного предпросмотра теперь появляется сразу после начала подготовки форматированного вида, показывает понятный статус и временно блокирует недоступные команды до готовности документа.
- Встроенная инструкция переписана под текущий интерфейс: кнопка «Открыть», автоматический предпросмотр, две панели документа, ручная проверка под ними, закреплённая кнопка применения и актуальные команды экспорта и восстановления.
- Видимая подсказка перетаскивания удалена, но загрузка файла перетаскиванием в окно сохранена; освобождённое место отдано обеим областям предпросмотра документа.
- Пустая строка отмены восстановления под обезличенным текстом теперь схлопывается: зазор перед счётчиками уменьшен с 36 до 8 пикселей, а реальные кнопки отмены по-прежнему отображаются.
- Из обеих локализаций удалены избыточная видимая подпись исходного редактора и статическое уведомление о локальном хранении; доступная подпись поля сохранена для вспомогательных технологий.
- Во всех заголовках сворачиваемых разделов теперь показывается стрелка вправо в закрытом состоянии и вниз в открытом.
- Элементы управления верхней панели собраны в одну строку, полное пояснение сохранено отдельной компактной строкой, а области предпросмотра документов в невысоких окнах увеличены.
- Предпочтительная начальная ширина окна увеличена с 1440 до 1600 пикселей, чтобы длинный статус предпросмотра и две панели документов получали больше места по горизонтали; на ограниченных дисплеях размер и положение запуска ограничиваются рабочей областью основного монитора.

#### Исправлено

- В контекстных списках русских адресов теперь целиком обезличивается каждый элемент без захвата окружающего предложения. Ограниченная грамматика поддерживает `аллею`, числовые порядковые названия на `-ый`, буквенную часть дома после косой черты и реквизиты строения без запятой; после явной подписи одиночный адрес может не содержать тип улицы, если название написано с заглавных букв и за ним следует обозначение дома. Неоднозначное `пр.` по-прежнему допускается только после прямой подписи адреса или внутри ограниченного списка адресов, обычный проектный текст сохраняется, DOCX очищается через разрывы runs с побайтным восстановлением, а внешняя проверка сборки требует отдельное доказательство актуального EXE.
- Имена серверов в инвентаризационных списках с префиксом класса `s`/`v`, четырёхзначным кодом площадки, компактной ролью после дефиса и двузначным номером теперь регистронезависимо заменяются маркером `УЗЕЛ`, включая варианты с дополнительным числовым суффиксом. В таблице с колонками наименования, IP-адреса и ПО/ИТ-сервиса колонка наименования также поддерживает такой ограниченный формат с другим или отсутствующим однобуквенным префиксом и короткую форму «две буквы + две цифры». Похожие обычные идентификаторы вне такого табличного контекста не затрагиваются, а внешняя проверка сборки требует отдельное доказательство от актуального EXE.
- Исправлена рассинхронизация форматированных панелей после крупных замен текста, удаления схем, вложенных или многоколоночных таблиц и позднего изменения размеров изображений. В DOCX-предпросмотр добавлены одинаковые структурные идентификаторы блоков; при прокрутке непрерывно сопоставляются общие идентификаторы, якоря сортируются по фактической позиции на экране, а после замены форматированного DOM или загрузки изображения панели выравниваются заново. Когда правый форматированный предпросмотр готов асинхронно, его позиция восстанавливается напрямую по текущему логическому блоку левой панели, а не по приблизительной доле прокрутки временного текстового вида.
- При первом запуске с уже добавленным DOCX/ODT автоматический анализ профиля больше не отменяет загрузку форматированного исходного документа и не оставляет левую панель в виде обычного текста. Форматированная левая панель выбирается сразу и показывает статус подготовки, а конфликтующая подготовка правого форматированного вида ждёт завершения исходного предпросмотра.
- Русские почтовые адреса и адреса в инвентаризационных таблицах теперь обезличиваются целиком: начальный или конечный индекс, административная иерархия, явно указанные город/район, улица, здание и дом. Типизированная грамматика заменяет только полный встроенный адрес, а отдельный резервный путь для адресной ячейки DOCX обрабатывает необычный порядок компонентов и реквизитов здания, не распространяясь на обычные строки текста. Поддержаны название перед типом улицы, отсутствие пробела после сокращения с точкой, строчное название при сильном почтовом контексте, неразрывные пробелы и повторяющиеся реквизиты корпуса, строения, литеры, помещения или офиса. Грамматика также покрывает `пр.` и полные подписи улиц, `зд.`/`дом №`, инициалы и слово «имени» в названиях, строчные продолжения числовых улиц, формы республики/сокращённой области/автономной области или округа и псевдонимы после тире. Обычный текст до или после адреса сохраняется, а похожие на адрес формулировки о проектах не заменяются. Отдельные ячейки региона, федерального округа и города сервисного центра заменяются только в полной строке инвентаризации, завершающейся проверенным адресом, поэтому обычные «предметная/рабочая область» и одиночные направления не затрагиваются.
- Исходный и обезличенный форматированные предпросмотры теперь сохраняют одну логическую позицию документа, даже если замены изменили переносы строк в нижней части. Индексы логических блоков больше не теряются, когда несколько последних блоков упираются в одинаковую максимальную позицию прокрутки, поэтому синхронизация не переключается ошибочно на несвязанные пропорциональные позиции.
- Выбор другого документа теперь отменяет все незавершённые результаты анализа предыдущего. Изменение настроек во время загрузки исходного предпросмотра сохраняет признак необходимости повторной обработки и блокирует экспорт, а выбранный пользователем текстовый режим и его позиция не сбрасываются после прихода форматированного HTML.
- Внешняя проверка сборки теперь привязана к манифесту с хешем EXE, размером и SHA-256 каждого файла упакованной среды выполнения, хешами всех UI-ресурсов, Git-ревизией, хешем изменений рабочей копии и детерминированным снимком runtime-исходников, встроенным в EXE. Устаревшее, добавленное, пропавшее или смешанное сочетание EXE/runtime/UI/исходников отклоняется, даже если внутренние smoke-флаги сообщают об успехе.
- Windows-оболочка сборки теперь собирает и проверяет внешний контракт PyInstaller в отдельных staging-каталогах, публикует результат в `dist` только после успешной проверки и повторно проверяет уже опубликованный EXE; исчезновение или блокировка стандартного каталога PyInstaller больше не может выдать частичную сборку за успешную.
- Сборка Linux/macOS теперь откладывает smoke-проверки исполняемого файла и создание манифеста до platform-aware этапа проверки — после настройки Linux Secret Service/X11 или очистки тестовой связки ключей macOS. Этап сборки больше не завершается ошибкой до появления обязательных нативных сервисов, а оба нативных архива теперь содержат проверенный внешний манифест рядом с приложением.
- Домены, к которым Word в оглавлении присоединил номер страницы без разделителя, теперь заменяются целиком с сохранением номера страницы; для поддоменов больше не остаётся открытым суффикс основного домена. Случай проверяется на уровне DOCX, приёмочного документа, engine smoke и внешней проверки готовой сборки.
- Проверка готовой сборки теперь выполняет внешний fail-closed контроль сокращения с завершающей цифрой рядом с организацией, например `QZXB1`; устаревший EXE, который сообщает об успехе, но не выдаёт это доказательство, отклоняется Windows- и нативными выпускными барьерами.
- При поиске сокращений продолжением токена теперь считаются все категории комбинируемых Unicode-символов, а также zero-width non-joiner/joiner: канонически эквивалентная или соединённая служебным символом форма больше не оставляет открытый фрагмент; packaged smoke требует отдельное доказательство `abbreviation_unicode_ok`.
- После очистки загруженного форматированного документа обе области форматированного предпросмотра теперь скрываются до возврата пустых текстовых панелей; лишняя пустая панель справа больше не остаётся.
- В адресах после явного указания «адрес» теперь обезличиваются улица, дом, город и завершающий пяти- или шестизначный почтовый индекс; посторонние числа индексами не считаются.
- Теперь обезличиваются русские адреса с типом улицы до или после названия, например `ул. Энтузиастов, д.5, к.6` и `Профсоюзная улица, 125А`; обычные упоминания улиц и проспектов не затрагиваются.
- Заголовки документов, оборот `в том числе`, формулировки о недостатках по договору и сроки оплаты в рабочих днях больше не создают ложные замены организаций, дисков, ФИО и денежных сумм по всему документу.
- В английских полях `Contact:`, `Address:` и `Software:` теперь обезличиваются подписанные имена, почтовые адреса и названия программ в обычном тексте и DOCX с сохранением форматирования и точным восстановлением.

## [0.2.8] — 2026-10-15

### English

#### Fixed

- Removed the obsolete design selector before the first frame renders and made preference migration non-blocking.
- Restyled the manual-review candidate and decision cards for consistent dark-theme contrast and removed the unnecessary inner scrollbar.

### Русский

#### Исправлено

- Устаревший переключатель дизайна удалён до отрисовки первого кадра; перенос настройки больше не может остановить запуск интерфейса.
- Карточки кандидата и решений ручной проверки приведены к цветам тёмной темы, лишняя внутренняя прокрутка удалена.

## [0.2.7] — 2026-10-15

### English

#### Fixed

- Recognized Windows-to-ALSE/Linux compatibility tables no longer classify repeated headers, totals, notes, comments, or explicit section-label rows as software.
- Added a regression covering structural rows inside a valid compatibility table without weakening arbitrary or empty status support.
- Removed the obsolete new/legacy design selector; the current interface is now used consistently in Russian and English.

### Русский

#### Исправлено

- В распознанных таблицах совместимости Windows → ALSE/Linux повторные заголовки, итоги, примечания, комментарии и явно обозначенные строки разделов больше не классифицируются как программы.
- Добавлена регрессионная проверка структурных строк внутри корректной таблицы без ограничения произвольных и пустых статусов.
- Удалён устаревший переключатель нового и старого дизайна; актуальный интерфейс теперь всегда используется на русском и английском языках.

## [0.2.6] — 2026-10-15

### English

#### Fixed

- Structured software cells now anonymize every non-empty remainder around a higher-priority secret, including one-character and numeric-only fragments.
- Added regressions preventing values such as `A TOPSECRET B` and `TOPSECRET 2025` from being disclosed partially.

### Русский

#### Исправлено

- В структурированных ячейках ПО теперь обезличивается каждый непустой остаток вокруг секрета с более высоким приоритетом, включая однобуквенные и полностью числовые фрагменты.
- Добавлены регрессионные проверки, исключающие частичное раскрытие значений вида `A TOPSECRET B` и `TOPSECRET 2025`.

## [0.2.5] — 2026-10-15

### English

#### Fixed

- Higher-priority secrets inside structured software cells remain irreversible, while every remaining visible part of the software name is also anonymized as `ПРОГРАММА`.
- Added a regression preventing overlap resolution from exposing the non-secret remainder of a software value.

### Русский

#### Исправлено

- В структурированных ячейках ПО секреты с более высоким приоритетом остаются необратимыми, а все остальные видимые части наименования также обезличиваются как `ПРОГРАММА`.
- Добавлен регрессионный тест, исключающий раскрытие незасекречённого остатка значения ПО при пересечении сущностей.

## [0.2.4] — 2026-10-15

### English

#### Fixed

- Both software columns in Windows-to-ALSE/Linux compatibility tables are now anonymized as complete reversible `ПРОГРАММА` values.
- Linux alternatives such as package descriptions and multi-product cells no longer remain visible, while compatibility status text and DOCX formatting are preserved.

### Русский

#### Исправлено

- Оба столбца с программами в таблицах соответствия Windows и ALSE/Linux теперь полностью и обратимо обезличиваются как значения `ПРОГРАММА`.
- Linux-аналоги, включая описания пакетов и ячейки с несколькими продуктами, больше не остаются открытыми; статус совместимости и форматирование DOCX сохраняются.

## [0.2.3] — 2026-10-14

### English

#### Fixed

- Standalone Active Directory container names in OU inventory tables are now anonymized, including root entries such as `Domain Controllers` and underscore-based internal names.
- Full OU paths, standalone containers, table metrics, reversible restoration, and DOCX formatting remain preserved.

### Русский

#### Исправлено

- Теперь обезличиваются отдельные названия контейнеров Active Directory в таблицах инвентаризации OU, включая корневые записи вроде `Domain Controllers` и внутренние имена с подчёркиванием.
- Полные пути OU, отдельные контейнеры, числовые показатели таблиц, обратное восстановление и форматирование DOCX сохранены.

## [0.2.2] — 2026-10-14

### English

#### Fixed

- Software deployment lists introduced by the correctly spelled Russian heading `Развёртывание ПО` are now anonymized as complete reversible values.
- Identifiers such as setup package names, internal product names, deployment scripts, and product-specific variants no longer remain visible in that table row.

### Русский

#### Исправлено

- Списки программ в строках с нормативным написанием `Развёртывание ПО` теперь полностью и обратимо обезличиваются.
- Имена установочных пакетов, внутренних продуктов, сценариев развёртывания и специализированных вариантов ПО больше не остаются открытыми в этой строке таблицы.

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

[Unreleased]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.8...HEAD
[0.2.8]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/onv83/LocalAnonymizer/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/onv83/LocalAnonymizer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/onv83/LocalAnonymizer/releases/tag/v0.1.0
