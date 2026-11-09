# ТЗ и приёмочный документ LocalAnonymizer

**Дата аудита:** 2026-11-08  
**Статус:** на утверждение перед разработкой  
**Связанный единый backlog:** `docs/verification-backlog-2026-10-18.md`, B101  
**Базовый release:** `v0.4.0` (`1214a7a`)  
**Текущий WIP:** сохранён отдельно и не считается принятым.

## 1. Полнота аудита

Аналитик восстановил и прочитал **884 уникальных пользовательских сообщения** сессии `20260910_232105_2eccb3`, включая исходное ТЗ и повторные сообщения об остатках. Очередь Hermes проверена: `delivery_obligations` и `pending_messages` пусты. Репозиторий, B01–B100, tests, changelog, README и текущее дерево исследованы.

Дополнительно выполнен differential audit `0.3.0 → 0.3.1 → 0.4.0 → current`:

- plain FQDN, reverse-DNS, IPv4, CIDR и hostname после явных labels маскируются во всех версиях;
- синтетические inventory-table hostname gaps воспроизводятся и в 0.3.x, то есть это не доказанная новая регрессия 0.4.0;
- дифференциальное отличие current от 0.3.x/0.4.0 (review B2, намеренное): прежние inventory-строки «host-токен + mount-path (`/…`) + ≥3 чисто числовых ячеек» без IPv4/CIDR/существующего `[IP-N]` в той же строке больше не принимаются — утверждённый A5 требует row-local IP evidence, прежнее поведение маскировало значения без сетевого доказательства и было небезопасным; это не потеря detections, а задокументированное ужесточение, и восстановление старого поведения не выполняется;
- на четырёх доступных forensic DOCX 0.4.0 маскирует больше значений, а не меньше;
- точный файл нового screenshot среди доступных документов не найден, поэтому полный список регрессий нельзя объявлять доказанным без differential gate на общем corpus.

Реальные значения пользователя не переносятся в репозиторий, tests, docs или release notes. В документе используются только классы и синтетические примеры.

## 2. Инвентарь уже закрытых требований

Следующие группы имеют реализацию и evidence в 0.4.0, но остаются в обязательном regression suite:

- **ФИО:** полные/краткие формы, initials, оба порядка, aliases, падежи, role-labelled surnames, split DOCX runs/cells; русскоязычные татарские/славянские/тюркские и Kazakh/Ukrainian extended-Cyrillic ресурсы.
- **Контакты/география:** почта, телефоны, Telegram, адресные последовательности с ограниченными границами, регионы/города/индексы.
- **Организации/системы/ПО:** ОПФ и aliases, продуктовые системы и версии, contextual login/account detection, сокращения, NetBIOS/диски/AD.
- **Секреты:** обратимые `[SECRET-N]`, восстановление через пару «документ + `.larecovery`», обязательная автоматическая категория, актуальные RU/EN подсказки в текущем source fix.
- **Реквизиты/финансы:** ИНН/КПП/ОГРН/СНИЛС/счета/карты/паспорт/VIN/кадастр/госномер/табельный/договор/документ/задача/суммы/ставки с контекстными исключениями.
- **DOCX/ODT/XLSX и восстановление:** package preservation, formatting, tables, merged cells, split runs, Word edits, portable pair, unknown markers, metadata, graphics controls.
- **Пользовательские правила:** таблицы «Скрывать дополнительно»/«Белый список», add/edit/delete, source-selection actions, category picker, повторы, profiles, formatted-preview persistence.
- **UI/performance:** RU/EN, category controls, formatted/plain modes, scroll synchronization, async race guards, clipboard, layout, ускорение DOCX hot paths.
- **Публикация:** Windows package/install, native Linux/macOS CI, GitHub Release и внутренний Bitbucket с `main`/tag/public access.

Эти пункты не переоткрываются без нового failing evidence, но обязаны сохраниться при сетевых изменениях.

## 3. Открытые требования B101 — сетевой инвентарь

| ID | Требование | Текущее доказанное состояние | Приоритет |
|---|---|---|---|
| A1 | Территориальные FQDN 3+ меток, включая numeric first label → `[ДОМЕН-N]` | Plain source GREEN; полный DOCX/package gate не выполнен | P0 |
| A2 | CIDR целиком `IPv4/prefix` → `[IP-N]` | Plain source GREEN; смежный marker case A7 отдельно FAIL | P0 |
| A3 | Reverse-DNS `*.in-addr.arpa` любой разумной глубины → `[ДОМЕН-N]` | Plain source GREEN; полный gate не выполнен | P0 |
| A4 | Обычный IPv4, включая первый октет `0` → `[IP-N]` | Plain source GREEN; полный gate не выполнен | P0 |
| A5 | Inventory hostnames: compact letters+digits, multi-segment alnum/hyphen, mixed case → `[УЗЕЛ-N]` с row-local evidence | Есть неутверждённый WIP и focused GREEN; не принято | P0 |
| A6 | Серверные списки вне таблиц после ограниченного заголовка/structural context → целый `[УЗЕЛ-N]`, без `ЗАДАЧА`-фрагментации | **FAIL воспроизведён аналитиком** | P0 |
| A7 | CIDR/prefix, примыкающий к существующему маркеру, не остаётся открытым суффиксом | **FAIL воспроизведён аналитиком** | P0 |
| A8 | Прежние MAC/ports/URLs/IMEI/DN/AD/disk/path сохраняются | Regression gate обязателен | P0 |
| A9 | Дифференциальная совместимость 0.3.0/0.3.1/0.4.0/current на общем synthetic corpus | Gate сформирован, полный corpus не прогнан | P0 |

### Универсальный механизм A5

Hostname не определяется списком конкретных строк. Кандидат должен:

- состоять из ASCII letters/digits/internal hyphens;
- начинаться с буквы, содержать минимум одну букву и одну цифру;
- иметь разумную ограниченную длину;
- захватываться целиком с явной правой границей;
- не быть IPv4, версией, датой, обычным числом, marker или свободной прозой.

Для inventory row требуется сочетание:

1. явное host-column/structural evidence **или** grammar плюс OS/numeric evidence;
2. row-local IPv4/CIDR **или** существующий `[IP-N]`;
3. изоляция текущей строки и ячейки, без переноса контекста в следующий раздел.

Специализированная категория `УЗЕЛ` имеет приоритет над `ЗАДАЧА`/`СОКРАЩЕНИЯ`, поэтому mixed-case structured hostname не разбивается на префикс и суффикс.

### Универсальный механизм A6

Для списков вне таблиц нужен отдельный bounded block parser:

- старт: явный `Сервер`/`Hostname`/`Имя узла` или эквивалентная structural heading;
- допустимы marker-only строки между заголовком и хостами;
- хост принимается по общей grammar A5 с полным захватом;
- стоп: следующий section heading, нехостовый содержательный абзац, table/document boundary;
- обычная фраза «Сервер работает штатно» не открывает список;
- негативы на обычную прозу, отключённую категорию и соседние разделы обязательны.

### Универсальный механизм A7

Суффикс `/8…/32` после уже существующего маркера обрабатывается только при доказанном subnet/IP context:

- не оставлять открытый `/NN` рядом с masked subnet/site/IP label;
- не захватывать обычные дроби, пути, даты, версии или произвольный `[CATEGORY-N]/NN`;
- сохранить обратимость и idempotence второго прохода;
- определить итоговую категорию так, чтобы не создавать фиктивный IP из несетевого текста.

## 4. Требования к regression fixtures

Каждый пункт A1–A7 получает:

1. synthetic plain-text positive;
2. negative ordinary prose;
3. category-disabled behavior без relabel;
4. exact right boundary и отсутствие partial mask;
5. repeated identical value marker reuse;
6. distinct values без случайного identity merge;
7. DOCX split runs, split cells, tables/lists;
8. существующие `[IP-N]`/другие markers;
9. second-pass idempotence;
10. source preservation и восстановление по поддерживаемой паре;
11. physical OOXML residue check;
12. differential run на 0.3.x/current там, где менялось прежнее поведение.

Два реальных литерала, попавшие в текущий uncommitted `tests/test_network_inventory_hardening.py`, **заменить синтетическими аналогами до любого commit**. WIP не считается закрытым или принятым.

## 5. Другие открытые/отложенные пункты

- **B88 formatted preview:** реализация и browser/package evidence существуют (`039beeb`, fallback/race tests). Не считать «не начато»; обновить документационный статус после очередной актуальной проверки.
- **B65 native keyring race:** остаётся отдельным platform-specific исследованием, не входит в network patch.
- **macOS:** native CI зелёный, но physical Mac/Gatekeeper/реальные документы остаются preliminary acceptance.
- **ПЛ3 Linux/Astra desktop port и `.doc` вне Windows:** отложено пользователем ранее; не включать молча в network release.
- **Полный покнопочный GUI audit:** E2E покрытие существует; отдельную исчерпывающую control-by-control матрицу вести независимо, не блокируя доказанные network fixes без нового GUI defect.

## 6. ТЖД — приёмочная матрица

**Релиз запрещён, пока все обязательные строки не PASS. Один FAIL или NOT RUN = NO-GO.**

| # | Проверка | PASS-критерий | Сейчас |
|---|---|---|---|
| T1 | A1–A4 plain network classes | Все synthetic positives/negatives зелёные | частично, focused GREEN |
| T2 | A5 inventory hostnames | Все grammar forms + row IP/marker evidence, без `ЗАДАЧА` fragmentation | WIP GREEN, не принято |
| T3 | A6 внетаабличные списки | Целый hostname, ограниченный block, negatives | **FAIL** |
| T4 | A7 marker-adjacent CIDR | Нет открытого prefix, нет false positives на путях/дробях | **FAIL** |
| T5 | Synthetic privacy | Ноль реальных литералов в diff/tests/docs/history | **FAIL: 2 значения заменить** |
| T6 | DOCX boundaries | Split runs/cells/lists, row isolation, source preserved | частично |
| T7 | Восстановление | Поддерживаемая пара восстанавливает исходный текст/структуру; byte-exact там, где контракт это требует | частично |
| T8 | Idempotence | Повторный проход не создаёт новых/вложенных маркеров | не завершено |
| T9 | Category controls | Каждая новая категория работает enabled/disabled без relabel | не завершено |
| T10 | Differential 0.3.x/current | Нет необоснованных потерь прежних detections; все изменения объяснены | не завершено |
| T11 | Полный serial suite | 0 failed; прежние 1341 + новые tests | NOT RUN |
| T12 | Реальные forensic DOCX | Все доступные документы: 0 контролируемых остатков A1–A7, restore проверен | NOT RUN |
| T13 | Независимый exact-snapshot review | GO без blockers, manifest/hash воспроизведён | NOT RUN |
| T14 | Build/install | Clean commit build, normal/`python -O`, Defender, byte-identical safe install, installed smoke | NOT RUN |
| T15 | Публикация | GitHub + Bitbucket один snapshot, tag/changelog/README/assets/readback/CI, Bitbucket default `main` | ЗАПРЕЩЕНО до T1–T14 |

## 7. Обязательный конвейер

1. **Инвентарь:** каждое пользовательское сообщение и очередь → единый backlog; дубли группируются с сохранением источников.
2. **Утверждение:** пользователь подтверждает scope и порядок B101.
3. **Передача:** полное ТЗ и матрица передаются GLM-5.3 одним заданием.
4. **RED:** каждый пробел получает падающий synthetic regression.
5. **Универсальная реализация:** semantic anchor + stop boundary + полный захват; point-hardcode запрещён.
6. **Boundary gates:** negatives, category disable, marker reuse, row/cell isolation, idempotence.
7. **DOCX/restore:** split runs, source preservation, восстановление и physical OOXML checks.
8. **Differential:** сравнение с 0.3.x/current и проверка отсутствия регрессий.
9. **Полный suite:** один serial прогон текущего snapshot.
10. **Forensic acceptance:** все доступные реальные документы и повторная обработка.
11. **Независимая приёмка:** read-only exact-snapshot review по manifest.
12. **Build/install:** fresh clean commit, packaged normal/optimized, Defender, safe install.
13. **Публикация:** только после 100% PASS, один snapshot в GitHub и Bitbucket, readback.
14. **Новые замечания:** возврат к пункту 1, без молчаливого release одного исправления из десяти.

## 8. Порядок на утверждение

1. P0: A6/A7 как подтверждённые FAIL, затем A1–A5 и synthetic privacy.
2. P0: DOCX/idempotence/category/differential и все forensic документы.
3. P0: full suite, independent review, build/install.
4. P1: README/CHANGELOG/release notes и SECRET hints, B88 documentation status.
5. P1: публикация исправленного выпуска в GitHub и Bitbucket.
6. Отдельно, не в network patch: B65, physical Mac, ПЛ3, расширенный GUI audit.
