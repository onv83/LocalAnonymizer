# LocalAnonymizer 0.4.3

### Восстановление DOCX после редактирования

Исправлено: документ, который вы обезличили, отредактировали в Word (текст, таблицы, колонтитулы, стили, списки) и затем восстановили по паре «обезличенный DOCX + `.larecovery`», снова восстанавливается вместо общей ошибки.

Что было не так и что изменено:

- Санитайзер DOCX принимал стандартные структуры Word за «чужой XML» и блокировал восстановление. Теперь корректно обрабатываются поля и закладки в любых колонтитулах (`word/headerN.xml`, `word/footerN.xml`), границы и внутренние отступы ячеек таблиц (`tcMar`, `tcBorders`), повторяющиеся строки заголовков (`tblHeader`), теги элементов управления содержимым, номера страниц (`pgNumType`), уровни структуры (`outlineLvl`), комплексные размеры шрифта (`szCs`), отступы и `keepLines` в стилях, блокировки рисунков (`picLocks`). Поля, закладки и теги при этом остаются инертными: их служебные значения не попадают в результат.
- При совпадении числа абзацев восстановление могло выбрать старый layout-путь и вернуть таблицу, которую вы удалили. Теперь при изменении структуры выбирается семантическое восстановление, а удалённые таблицы и фрагменты не возвращаются.
- Добавленный вами нумерованный список сохраняется; при конфликте идентификаторов нумерации они переназначаются безопасно.
- Для старых пар без сохранённой базовой версии формата существующие стили и списки больше не дублируются (раньше 94 определения превращались в 186, и Word отвергал файл). Для новых пар сохраняется необязательная hash-проверяемая базовая версия только `styles.xml` и `numbering.xml` — без текста документа.
- Безопасные внешние ссылки `https` сохраняются; `file:`, `javascript:`, UNC-пути и прочие внешние отношения, а также небезопасные или повреждённые снимки исходника отклоняются с ошибкой, без создания выходного файла.
- **Новый переключатель «Мягкий режим совместимости»** в блоке восстановления. Когда он включён, неизвестное стандартное форматирование Word вырезается без блокировки восстановления (текст и маркеры сохраняются), а жёстко блокируется только активный контент: OLE, ActiveX, макросы, `altChunk`, внешние связи и небезопасные части пакета. По умолчанию режим выключен, поведение остаётся строгим.

**Что это даёт пользователю:** восстановление реального рабочего документа после правок в Word — с удалёнными таблицами, изменёнными колонтитулами, добавленными списками и изменённым форматированием. Microsoft Word открывает восстановленный файл без ремонта; удалённые фрагменты не возвращаются, а значения удалённых маркеров не угадываются.

### Проверки

- Полный source suite: **1438 passed, 3 warnings** (ожидаемые предупреждения о тестовых ZIP с дубликатами); профильный набор B103 — **49 passed**.
- Восстановление двух реальных пользовательских пар проверено только на read-only копиях: `unknown_markers = 0`, остаточных маркеров и служебных сентинелей нет, висячих style/num-ссылок нет; Microsoft Word `OpenAndRepair=False` открыл файлы без ремонта (1601 и 1569 абзацев).
- Packaged verification `smoke` / `pair-smoke` / `platform-smoke` — зелёная; установленная сборка запущена и проверена.

### Совместимость

Формат `.larecovery` не менялся: пары, созданные прежними версиями, восстанавливаются. `.larecovery` по-прежнему не зашифрован и содержит исходные значения, включая секреты, поэтому его нужно защищать как исходный документ.

### English

### DOCX recovery after editing

Fixed: a document that you anonymized, edited in Word (text, tables, headers/footers, styles, lists) and then restored from the `anonymized DOCX + .larecovery` pair now recovers again instead of failing with a generic error.

- The DOCX sanitizer treated ordinary Word structures as foreign XML and blocked recovery. It now handles fields and bookmarks in every header/footer part, table cell margins and inside borders (`tcMar`, `tcBorders`), repeating table header rows (`tblHeader`), content-control tags, page numbering (`pgNumType`), outline levels (`outlineLvl`), complex-script font sizes (`szCs`), style indentation and `keepLines`, and picture locks (`picLocks`). Fields, bookmarks and tags stay inert: their service values are not carried into the output.
- When paragraph counts happened to match, recovery could take the legacy layout path and bring back a table you had deleted. Structural changes now select semantic recovery, so deleted tables and fragments are not resurrected.
- A list you added keeps its numbering; colliding numbering identifiers are remapped safely.
- For legacy pairs without a stored format baseline, existing styles and lists are no longer duplicated (94 definitions used to become 186, which Word rejected). New pairs store an optional hash-checked baseline of `styles.xml` and `numbering.xml` only, with no document text.
- Safe `https` hyperlinks are preserved; `file:`, `javascript:`, UNC targets and other external relationships, along with unsafe or damaged source snapshots, are rejected with an error and no output file.
- **New “Soft compatibility mode” switch** in the restore panel. When enabled, unknown standard Word formatting is stripped without blocking recovery (text and markers are kept), while active content is still blocked: OLE, ActiveX, macros, `altChunk`, external links and unsafe package parts. The mode is off by default, so strict behavior is unchanged.

**What it gives the user:** recovery of a real working document after edits in Word, including deleted tables, changed headers/footers, added lists and changed formatting. Microsoft Word opens the restored file without repair; deleted fragments do not come back and values of deleted markers are never guessed.

Verification: full source suite **1438 passed, 3 warnings**; B103 profile **49 passed**; two real user pairs restored on read-only copies with `unknown_markers = 0` and no repair (`OpenAndRepair=False`, 1601 and 1569 paragraphs); packaged smoke/pair/platform checks green.
