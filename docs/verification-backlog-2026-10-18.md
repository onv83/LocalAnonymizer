# Единый backlog замечаний — 2026-10-18

> Значения из пользовательских файлов и изображений здесь не приводятся. Проверки используют только синтетические данные, зарезервированные домены и документальные IP-диапазоны.

## Восстановленное окно сообщений

| Порядок | Источник | Privacy-safe класс | Требуемое поведение | Статус и доказательство | Ранее пропущено | Приоритет / зависимость |
|---:|---|---|---|---|---|---|
| 1 | Сообщение «про это тоже говорил»; `image_1ea862.png` | DNS FQDN с подчёркнутой service-меткой | Обезличивать как `УЗЕЛ`; не захватывать email, URL, пути и вложенные идентификаторы; соблюдать отключение категории | **Доказанно закрыто** в `4fdad6ef58802ae46a49f3aa945866e9357004cc`: source/package/installed proofs и CI `39132804985` | Да | P1; повторно прогнать в общей регрессии |
| 2 | Сообщение «не обезличилось»; `image_4e3b9f.png` | Семантические географические значения в табличной инвентаризации | Определять чувствительные столбцы по заголовкам, включая runs/hard breaks; не объединять cells/rows | **Доказанно закрыто** в `4fdad6ef58802ae46a49f3aa945866e9357004cc`: DOCX leakage/restoration, package/installed proofs, CI `39132804985` | Да | P1; повторно прогнать в общей регрессии |
| 3 | Сообщение «тоже ошибка обезличивания»; `image_9f6d4d.png` | Субъект, федеральный округ, филиал/город и полный адрес в 10-колоночной таблице | Обрабатывать все location-bearing columns по заголовкам, независимо от визуального переноса | **Доказанно закрыто** в `4fdad6ef58802ae46a49f3aa945866e9357004cc`: synthetic semantic-column tests, package/installed proofs, CI `39132804985` | Да | P1; повторно прогнать в общей регрессии |
| 4 | Сообщение «тоже ошибка»; `image_3a698f.png` | Географическое прилагательное и контекстный device/inventory identifier | Прилагательное обезличивать как `ГОРОД`; идентификатор — как `УЗЕЛ` только внутри ограниченного semantic block | **Доказанно закрыто** в `4fdad6ef58802ae46a49f3aa945866e9357004cc`: boundary/category/DOCX/package/installed proofs, CI `39132804985` | Да | P1; повторно прогнать в общей регрессии |
| 5 | Сообщение «подобные вещи тоже должны обезличиваться»; `image_511fcb.png` | Повторяющийся компактный device/inventory identifier | Обезличивать все bounded-повторы в semantic guide block; сохранять reversible mapping; не срабатывать вне контекста | **Доказанно закрыто** в `4fdad6ef58802ae46a49f3aa945866e9357004cc`: proof `device_inventory_identifier_ok`, package/installed identity, CI `39132804985` | Да | P1; повторно прогнать в общей регрессии |
| 6 | Сообщение; `image_c44221.png` | Имя сервисной учётной записи в документированном naming-scheme: смешанный регистр, структурные разделители и подчёркивание в назначении | Обезличивать весь bounded token как единый `ЛОГИН`, включая разрыв **внутри токена**; не дробить на `СОКРАЩЕНИЯ`; не захватывать email/URL/path/обычный текст; отключение `ЛОГИН` полностью отключает правило; восстановление byte-exact | **Доказанно закрыто** в `f1e5ee5b6d1ea1cdce124553fd946160adc46896`: все позиции intra-token break, ZIP leakage, category/precedence, byte-exact restoration, source/package/installed proofs и exact-head CI `39139824386` | Да | P0; закрыто, повторно прогнать в общей регрессии |

## Сверка и дедупликация

- Окно содержит ровно шесть пользовательских сообщений: пять предыдущих screenshot-сигналов и текущее сообщение.
- Первые пять сигналов сохранены как отдельные traceable источники, но их закрытые требования не дублируются новыми задачами.
- Новый открытый класс — расширенная структурная форма имени сервисной учётной записи. Это не доказано прежним `service_account_ok`, потому что тот проверяет более узкий синтетический шаблон.
- Ни `4fdad6ef58802ae46a49f3aa945866e9357004cc`, ни `d481419046ff2684eda7cd203a0cfd29ddf37baa` не считаются доказательством полного закрытия B16: второй commit не покрывал разрыв внутри одного токена.

## Обязательные критерии приёмки B16

1. Privacy-safe synthetic RED воспроизводит весь структурный класс без значений с изображения.
2. Весь service-account token получает один маркер `ЛОГИН`; одинаковые повторы используют одно mapping-значение.
3. Более точное правило `ЛОГИН` имеет приоритет над `СОКРАЩЕНИЯ` и общими fallback-правилами.
4. Есть negatives для обычного текста, embedded token, email, URL, filesystem path и более длинного идентификатора.
5. Отключение `ЛОГИН` полностью отключает новое правило; отключение `СОКРАЩЕНИЯ` не ломает его.
6. DOCX runs и hard break **внутри одного service-account token** объединяются только внутри одной semantic region; `U+FDD0` между cells/rows никогда не пересекается; исходный DOCX не меняется, обезличенный ZIP не содержит ни одного исходного фрагмента, восстановление byte-exact.
7. Полный suite, category controls и release gates проходят под обычным Python и `python -O`.
8. Свежий Windows package, установленная копия, независимый commit-bound review и CI подтверждают fix; Release не создаётся.

## B17 — имена узлов в таблице серверных мощностей

- **Источник:** новое сообщение и `image_f6f0fc.png`; реальные значения с изображения не сохраняются.
- **Privacy-safe класс:** значения колонки с наименованиями узлов в семантической таблице, где рядом присутствуют IP-адрес, программное обеспечение и аппаратные характеристики.
- **Корневая причина:** таблица уже распознавалась по заголовкам и валидному IP, но после этого применялся узкий словарь допустимых ролей в имени узла. Структурно корректные значения с другими кодами ролей оставались видимыми.
- **Текущий статус:** ~~выполнено~~ — commit `a808c9b046dac75b6f4cba51b207eafbe2dcc97b`; source/package/install/CI/review gates пройдены, package и install совпадают побайтово.
- **Требование:** после подтверждения семантики таблицы обезличивать всё bounded-значение ячейки колонки узлов как единый `УЗЕЛ`, не полагаясь на словарь ролей.
- **Границы:** не объединять разные cells/rows; runs и внутренние hard breaks разрешены только внутри одной ячейки; необходим валидный IP в той же строке; URL, email, filesystem path, slash-suffix и значения с обычными внутренними пробелами не превращаются в `УЗЕЛ`, dotted hostname в подтверждённой ячейке поддерживается целиком.
- **Приоритет:** точная семантика ячейки `УЗЕЛ` должна выигрывать у broad password/secret и `СОКРАЩЕНИЯ` fallback; при отключённой категории маркер `УЗЕЛ` не создаётся.
- **Контроли:** отключение `УЗЕЛ` оставляет значения без `УЗЕЛ`-маркеров; обычные таблицы с колонкой «Наименование», но без серверной структуры, не затрагиваются.
- **Приёмка:** отсутствие всех synthetic-фрагментов во всём DOCX ZIP, source immutability, byte-exact restoration, полный source/package/install/CI/review gate; `v0.2.9` не создаётся.

## B18 — составные технические идентификаторы как единые сокращения

- **Источник:** текущее сообщение и privacy-safe structural analysis `image_993903.png`, `image_e43aff.png`, `image_ff843e.png`, `image_2d7af8.png`; реальные значения с изображений не сохраняются.
- **Privacy-safe класс:** bounded policy/task identifiers из нескольких дефисных сегментов, смешанного регистра, цифр, точки и внутреннего `_`, включая длинный descriptive suffix.
- **Корневая причина для проверки:** общий detector `СОКРАЩЕНИЯ` ищет uppercase-run внутри отдельных токенов и overlap resolution допускает частичную замену; он не гарантирует один маркер на весь составной identifier.
- **Статус:** ~~выполнено~~ — implementation commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`; numeric dotted-version, hostname-shaped negatives и punctuation boundaries подтверждены source/package/install/review/CI gates. Package и installed tree совпали `407/407`, fail-closed verifier прошёл normal/`python -O`, exact-head CI `39157356254` завершился `success`.
- **Дополнительный RED/GREEN:** synthetic форма с numeric dotted-version после буквенного segment сначала осталась видимой; scanner расширен только на numeric dotted-version в достаточно составном identifier. Алфавитный dotted suffix и короткая numeric dotted hostname-подобная форма остаются negative; terminal `.`/`:` теперь допускаются только как punctuation, а не как начало продолжения; добавлены DOCX hard-break/byte-exact regression и отдельный fail-closed proof `dotted_version_compound_abbreviation_ok`.
- **Требование:** распознавать весь structurally valid identifier единым `СОКРАЩЕНИЯ`, а не отдельные сегменты; не хранить literals и не ограничиваться увиденными примерами.
- **Границы:** не захватывать email, URL, filesystem paths, dotted hostnames, обычную прозу, соседние punctuation/cells/rows; поддержать DOCX runs/hard breaks только внутри одной semantic region.
- **Приёмка:** synthetic RED/GREEN, один marker, category disablement, precedence, punctuation boundaries, ZIP leakage scan, byte-exact restoration, отдельный fail-closed packaged proof и normal/`python -O` verifier.

## B19 — контекстные названия площадок и расширенные адресные формы

- **Источник:** текущее сообщение и privacy-safe structural analysis `image_99b90c.png`, `image_5d080c.png`; реальные адреса и названия с изображений не сохраняются.
- **Privacy-safe класс:** топонимические/региональные прилагательные в колонке названия площадки рядом с колонкой `Адрес`; адреса с типами `ул`, `пер`, `стр`, `д`, `пр-кт` и аналогами, включая parenthetical expansion между типом и названием.
- **Корневая причина для проверки:** существующее address правило ориентируется на прямую последовательность типа улицы и названия и не использует семантику парных колонок; hyphenated type и вставка в скобках разрывают шаблон.
- **Статус:** ~~выполнено~~ — commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`; source/package/install/review gates и exact-head CI `39157356254` пройдены, package и install совпали `407/407`.
- **Требование:** в подтверждённой location table обезличивать название площадки как `АДРЕС` и весь bounded address-cell как один `АДРЕС`; вне таблиц поддержать contextual street-type grammar, включая дефисные сокращения и parenthetical expansion.
- **Границы:** не считать любое прилагательное адресом без cues; не пересекать cells/rows; URL/email/path/account identifiers не захватывать; category disablement обязателен.
- **Приёмка:** synthetic morphologic variants вместо словаря конкретных регионов, RED/GREEN, split-run/hard-break tests, negatives, ZIP leakage scan, restoration и packaged proof.

## B20 — стрелки у навигации словарных настроек

- **Источник:** текущее сообщение и `image_104ff0.png`, `image_71560d.png`.
- **Проблема:** элементы `Профиль словаря`, `Скрывать дополнительно`, `Белый список` выглядят как статические labels и не показывают, что открывают отдельные панели.
- **Статус:** ~~выполнено~~ — commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`; RU/EN contracts, browser layout/accessibility, fresh package/install и exact-head CI `39157356254` подтверждены.
- **Требование:** у каждого пункта справа показывать chevron `›`; у активного пункта сохранять стрелку и явное active-state оформление; английский интерфейс получает тот же affordance и доступное имя.
- **Границы:** стрелка не должна сжимать/обрезать текст, создавать горизонтальный overflow или ломать keyboard navigation/focus-visible на узкой и широкой ширине.
- **Приёмка:** RU/EN static contract, headless layout/accessibility regression и packaged UI proof.

## B21 — обобщённое правило service-account с внутренним `_`

- **Источник:** текущее сообщение и privacy-safe structural analysis `image_22c6ce.png`; реальное значение не сохраняется.
- **Текущий статус:** ~~выполнено~~ — generalized structural rule и semantic precedence подтверждены commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`, fresh package/install и exact-head CI `39157356254`.
- **Требование:** схема `service-prefix + site-code + '-' + mixed-case purpose`, допускающая внутренний `_`, определяется целиком как `ЛОГИН`; одинаковые значения используют один marker.
- **Границы:** bounded matching, category disablement, semantic precedence, DOCX runs/hard breaks внутри одной region; email/URL/path/embedded longer token исключены.
- **Приёмка:** повторная regression/package proof; без example-specific hardcode.

## B22 — мобильная библиотека файлов без обрезанных кнопок

- **Источник:** независимый UI-review после B20.
- **Дефект:** на узком экране четыре колонки `compact-library` оставляли часть кнопок за правой границей.
- **Исправление:** при ширине до 800 px библиотека переходит в одну ограниченную колонку; все элементы получают `min-width:0`, `max-width:100%` и `width:100%`.
- **Проверка:** static contract и реальный браузер при viewport 305 px: `scrollWidth == clientWidth`, все элементы находятся внутри доступной ширины.
- **Статус:** ~~выполнено~~ — narrow-browser proof, fresh package/install и exact-head CI `39157356254` подтверждены для commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`.

## B23 — восстановление одинаковых названий с разной DOCX-разметкой

- **Источник:** adversarial review edited-package restoration.
- **Дефект:** split и unsplit варианты одного названия использовали общий canonical key, поэтому первый hard break мог переноситься во второе значение при восстановлении без byte-exact archive.
- **Исправление:** topology `U+FDD3` включена во внутренний canonical key semantic location-cell; разные разбиения получают разные обратимые маркеры.
- **Проверка:** synthetic DOCX с одинаковым названием в split/unsplit строках восстанавливается без archive с исходной topology каждой строки.
- **Статус:** ~~выполнено~~ — topology-aware restoration, fresh package/install и exact-head CI `39157356254` подтверждены для commit `05b9de0ab4d960ad53ab11a15b2bf7959a62bec4`.

## B24 — содержимое карточки спорного фрагмента не уходит под панель решений

- **Источник:** текущее сообщение и privacy-safe анализ пользовательского изображения; реальные значения из интерфейса не фиксируются.
- **Дефект:** пояснение и служебная строка участвуют в расчёте первой колонки карточки, сжимают проверяемое значение в узкую полосу и визуально уводят его под соседнюю панель.
- **Статус:** ~~выполнено~~ — source/browser regressions в commit `165047b7630eaf827b73717147ca3935e1dbeb8e`; fresh package и безопасная установка подтверждены в `093abfe5b86aade4693f25e0c2ef1ed929b6ca7f`, exact-head CI `39189849080` успешен.
- **Требование:** label и значение остаются в первой строке, пояснение и служебная строка занимают собственные строки на всю ширину; длинные synthetic значения переносятся внутри карточки.
- **Приёмка:** RU/EN static contract и browser geometry regression без пересечений и внутреннего overflow.

## B25 — панель решений не перекрывает инструкции и прогресс

- **Источник:** текущее сообщение и privacy-safe анализ пользовательского изображения.
- **Дефект:** внутренняя карточка действий сжимается по содержимому, а длинные кнопки и соседние инструкции визуально накладываются друг на друга.
- **Статус:** ~~выполнено~~ — source/browser regressions в commit `165047b7630eaf827b73717147ca3935e1dbeb8e`; fresh package и безопасная установка подтверждены в `093abfe5b86aade4693f25e0c2ef1ed929b6ca7f`, exact-head CI `39189849080` успешен.
- **Требование:** панель действий и кнопки ограничены шириной своей grid-области, растягиваются по доступной ширине и безопасно переносят локализованный текст; решение, навигация и итог начинаются ниже самой высокой верхней панели.
- **Приёмка:** synthetic RU/EN browser geometry checks на узкой и широкой колонке, без overlap и горизонтального overflow.

## B26 — адаптивная ручная проверка учитывает ширину рабочей колонки

- **Источник:** текущее сообщение и privacy-safe анализ пользовательского изображения.
- **Дефект:** breakpoint зависит от ширины окна, хотя блок находится в половине двухколоночного экрана; при среднем окне внутренняя сетка остаётся двухколоночной и выходит за границы рабочей колонки.
- **Статус:** ~~выполнено~~ — container-query geometry проверена на 390/700/900 px; fresh package и безопасная установка подтверждены в `093abfe5b86aade4693f25e0c2ef1ed929b6ca7f`, exact-head CI `39189849080` успешен.
- **Требование:** layout переключается по фактической ширине `.workspace-column`: на компактной ширине контекст, действия, решение и итог идут одной колонкой; на достаточной ширине верхние панели могут стоять рядом.
- **Приёмка:** browser regression для synthetic рабочих колонок 390, 700 и 900 px; каждый элемент внутри родителя, компактные панели последовательно расположены, широкие не пересекаются, `scrollWidth == clientWidth`.

## B27 — составное имя с начальной аббревиатурой целиком относится к `СОКРАЩЕНИЯ`

- **Источник:** текущее сообщение и privacy-safe анализ пользовательского изображения; реальные значения документа в repository не фиксируются.
- **Дефект:** в токене вида `ABCD-TitleWord` первая часть содержит явную аббревиатуру, но review-hint на вторую часть блокирует broad abbreviation fallback, поэтому весь токен остаётся видимым.
- **Статус:** ~~выполнено~~ — synthetic Unicode/semantic/whitelist/category/DOCX regressions, fresh package SHA-256 `dd4186b485f47c649a6675e35116c942f806d193bbda1e64689f7fe85303946d`, безопасная установка и exact-head CI `39189849080` подтверждены для commit `093abfe5b86aade4693f25e0c2ef1ed929b6ca7f`.
- **Требование:** единый дефисный токен с 2–8 прописными буквами в префиксе и последующим строго title-cased буквенным компонентом должен относиться к `СОКРАЩЕНИЯ`. Категория имеет приоритет только над вложенным необязательным hint, а подтверждённые структурированные сущности, защищённые границы и отключённая категория сохраняют приоритет.
- **Приёмка:** synthetic regressions для двух-, трёх- и четырёхбуквенных префиксов в обычном и paranoid-режиме, short vowel-only и Unicode combining-mark abbreviation, lowercase/internal-mixed-case/digit-suffixed/uncased-script negatives, проверка границ, URL/email/path/DNS, exact whitelist и category disablement; реальные значения со screenshot отсутствуют в tests/docs/code.

## B28 — техническое составное имя `UPPER_lower-lower` относится к `СОКРАЩЕНИЯ`

- **Источник:** текущее сообщение и privacy-safe анализ второго пользовательского изображения; фактическое значение документа не сохраняется.
- **Дефект:** токен с 2–8-буквенным прописным префиксом, подчёркиванием и двумя строчными компонентами, разделёнными дефисом, остаётся открытым.
- **Статус:** ~~выполнено~~ — generalized synthetic regressions, fail-closed package proof, fresh package/install и exact-head CI `39189849080` подтверждены для commit `093abfe5b86aade4693f25e0c2ef1ed929b6ca7f`.
- **Требование:** целиком классифицировать структурный шаблон `UPPER_lower-lower` как `СОКРАЩЕНИЯ`, не захватывая prose, URL, email, path, DNS/hostname и разорванные соседние токены; whitelist и отключение категории обязательны.
- **Приёмка:** synthetic positive/negative regressions в обычном и paranoid-режиме, category/whitelist controls, fail-closed package proof и отсутствие screenshot literals в repository.

## B29 — граница длины structural prefix и приоритет enclosing semantic detector

- **Источник:** поздний независимый review после B27/B28.
- **Дефект:** generic uppercase fallback мог целиком скрыть structural lookalike с префиксом длиннее 8 `Lu`; exact-whitelisted вложенный abbreviation span мог блокировать enclosing URL/email/path detector.
- **Статус:** ~~выполнено~~ — source/full gates, independent review, fresh Windows package/install и exact-head CI `39191251807` подтверждены для commit `3bbf929ddf7bbfa44566e636d7005946e2838be6`.
- **Требование:** structural shape с 9+ uppercase letters не должен обходить границу 2–8 через fallback; whitelist применяется к самостоятельному токену, но не отменяет более точную enclosing-семантику.
- **Приёмка:** negatives для обеих structural форм с 9-буквенным prefix, whitelist-inside-email/URL/path regressions, расширенный fail-closed smoke proof, full gates, independent review, fresh Windows package/install и exact-head CI.

## B30 — mixed adjacent separator внутри technical compound

- **Источник:** screenshot focus `2026-10-19`; реальный identifier не переносится в repository.
- **Дефект:** compound technical ID с единственной смешанной парой соседних разделителей (`-_` или `_-`) не проходил существующую compound policy, хотя эквивалент с одним разделителем классифицировался как `СОКРАЩЕНИЯ`.
- **Статус:** ~~выполнено~~ — после подтверждения сохранения пользовательской работы закрыт только PID `37236`; safe installer установил 407 byte-identical файлов, installed hash совпал с package, installed smoke прошёл.
- **Требование:** одна mixed adjacent separator pair трактуется как единая граница сегментов только внутри уже валидного compound abbreviation; повторные одинаковые разделители и несколько mixed-пар отклоняются без частичной маскировки.
- **Границы:** exact whitelist и disabled `СОКРАЩЕНИЯ` защищают standalone token в paranoid mode; URL/email/path и более точные semantic entities имеют приоритет; `U+FDD3` допустим только внутри qualifying token, `U+FDD0` непроходим; dotted versions сохраняют numeric-version policy.
- **Проверка:** synthetic normal/paranoid, whitelist, disabled category, precise URL/email/path, malformed separators, DOCX boundaries и fail-closed package proof; focused `31 passed`; full suite `662 passed`; final review `passed=true` (`33 passed`); package verifier normal/optimized прошёл; Defender — `found no threats`; exact-head CI `39196302540` успешно прошёл Linux/macOS.
- **Артефакты:** source commit `98493e7a1c54f6d9a63b46ce09b87a215352b2ad`; Windows EXE SHA-256 `5fb8992a5d0e5ddefc4de16a1ca7e40e0d3baabe1624b39f71c7ba02609e37de`.

## B31 — digit-led inventory compounds и compact mixed-case abbreviation

- **Источник:** screenshot focus `2026-10-19`; реальные identifiers и screenshot metadata не переносятся в repository.
- **Дефект:** связанные inventory/policy identifiers с ведущим числовым сегментом и буквенными `-`/`_`-сегментами не классифицируются целиком как `СОКРАЩЕНИЯ`; отдельно пропускается короткий compact mixed-case acronym-like token. Letter-led structural compound того же списка уже классифицируется, что создаёт непоследовательный результат.
- **Статус:** закрыто 2026-10-19.
- **Требование:** generalized structural policy должна целиком классифицировать digit-led multi-segment inventory identifiers и узко определённые compact mixed-case abbreviations, включая identifier после нейтрального prose prefix; без screenshot literals и без lexical hardcode.
- **Границы:** не расширять правило на обычные числа, естественную речь, даты/версии, URL, email, filesystem path, DNS/hostname или malformed separator sequences; точные semantic detectors сохраняют приоритет; exact whitelist и disabled `СОКРАЩЕНИЯ` защищают standalone qualifying token; `U+FDD3` допустим только внутри одной semantic region, `U+FDD0` непроходим.
- **Приёмка:** synthetic RED/GREEN normal/paranoid regressions для обеих структурных семей, negative boundary corpus, whitelist/disabled controls, enclosing URL/email/path precedence, DOCX boundary coverage, fail-closed package proof, full suite, independent blocker review, fresh Windows package, Defender, exact-head CI и safe install.
- **Проверка:** focused `32 passed`; full suite `665 passed`; category controls `92`; source smoke/release verifier normal/optimized, E2E, compilation, privacy scan и `git diff --check` прошли; independent review `passed=true` после устранения over-broad date/location формы; package verifier normal/optimized прошёл; Defender — `found no threats`; exact-head CI `39200058928` прошёл; installed smoke подтвердил `inventory_style_abbreviation_ok=true`.
- **Артефакты:** source commit `3313d2f5d610a72cd09b49f3c7b49dca7c05e8b2`; Windows EXE SHA-256 `bbb14b687eb1441a35a0d192a5921d452cc3bd88d1a7ed5a2eff17c5379faa7f`; safe install скопировал `407` byte-identical files.

## B32 — симметричные intra-token `U+FDD3` boundaries и semantic precedence

- **Источник:** независимый security review текущей structural-abbreviation реализации.
- **Дефект:** некоторые позиции `U+FDD3` рядом с `-`/`_` приводят к частичной маскировке; точные email/URL/path и специализированные semantic spans не всегда реконструируются до broad abbreviation fallback; mapping/rendering могут учитывать одну physical boundary дважды.
- **Статус:** закрыто 2026-10-19.
- **Требование:** классифицировать и заменять полный логический span независимо от позиции `U+FDD3` внутри одной semantic region; точные semantic detectors всегда имеют приоритет; disabled/whitelist защищают полный structural token; mapping хранит newline-layout ровно один раз; `U+FDD0` остаётся непроходимым.
- **Приёмка:** parameterized RED/GREEN для structural split positions, normal/paranoid/disabled/whitelist; email/URL/Windows path split positions; precise semantic precedence; exact sentinel-count and restoration round-trip; full source/package/CI/install gates и независимый blocker review.
- **Проверено:** `670 passed`; focused `35 passed`; independent exhaustive review passed (`968` + `472` probes, `301` focused tests); package verifier normal/`python -O`; Defender no threats; CI `39204146050` success; safe install copied `407` byte-identical files; installed smoke has `intra_boundary_semantic_precedence_ok=true`.
- **Артефакты:** source commit `502313ebf26abd0eacf8e5e2c7863c25218e1151`; Windows EXE SHA-256 `6f0dae6e29bc0a8841ff400f7e96b6631d68957b65faaaa6dd329084beefe882`.

## B33 — компактная горизонтальная панель ручной проверки

- **Источник:** пользовательское сообщение и приложенный снимок интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Требование:** растянуть карточку «Что проверяется» на всю ширину колонки «Обезличенный текст» и уменьшить её высоту горизонтальной компоновкой; расположить «Предыдущий», «Следующее», «Скрыть и запомнить правило» и «Оставить и добавить в исключения» на одном визуальном уровне с единым стилем; убрать из видимого интерфейса повторяющиеся подсказки о количестве жёлтых элементов и выборе одного из двух решений.
- **Границы:** сохранить RU/EN, доступные скрытые описания действий, keyboard focus, порядок действий и адаптацию по ширине workspace-контейнера; не допускать horizontal overflow, overlap или ухода содержимого под соседнюю панель при `390/700/900 px`.
- **Приёмка:** privacy-safe RED/GREEN contracts и executable browser geometry RU/EN `390/700/900`; полный source suite, JS/compile/diff gates; independent review; свежий Windows package, fail-closed verifier normal/`python -O`, Defender, safe install, installed smoke и installed-artifact geometry; exact-head CI; Release/tag `v0.2.9` не создавать.
- **Проверка:** source commit `f55167ee8ab93eb0cca89f2f0dccafb23f3bd307`; `671 passed`, `tests/test_app.py` — `123 passed`; independent reviews — `passed=true`, без security/logic blockers. Чистый Windows package содержит `407` файлов, прошёл последовательную fail-closed проверку normal/`python -O` и Microsoft Defender (`found no threats`); EXE SHA-256 `7374ab7ccf1674ca208ade6b67a7728aa89374f502fe2265c752fcddeec305b4`.
- **Установка/CI:** safe installer скопировал `407` byte-identical файлов; installed hash совпал, установленный package verifier прошёл normal/`python -O`, installed RU/EN geometry прошла на `390/700/900 px`, нативный GUI запустился. Exact-head CI `39570543689` для `f55167ee8ab93eb0cca89f2f0dccafb23f3bd307` завершился `success`. Release/tag `v0.2.9` не создавался.

## B34 — «Дополнительные режимы» ниже кнопок ручной проверки

- **Источник:** пользовательское сообщение и геометрическая разметка на приложенном снимке интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Требование:** перенести сворачиваемый блок «Дополнительные режимы» / `Additional modes` ниже единой панели из четырёх кнопок ручной проверки.
- **Границы:** сохранить порядок четырёх действий, единый стиль кнопок, полноширинную компактную карточку проверяемого фрагмента, RU/EN parity, доступность `details/summary`, адаптацию `4×1`/`2×2`, отсутствие overlap и horizontal overflow.
- **Приёмка:** RED/GREEN structural contract для обеих локалей; executable geometry RU/EN `390/700/900`; полный source suite и независимый review; свежий Windows package, fail-closed verifier normal/`python -O`, Defender, safe install, installed smoke/geometry и exact-head CI. Release/tag `v0.2.9` не создавать.
- **Проверка:** source commit `95e6500c1f9a2b82e7e45346ae2fc7f73d79584f`; focused `5 passed`, application `124 passed`, full suite `672 passed`; executable RU/EN geometry `390/700/900` и independent review `passed=true`, без security/logic blockers. Clean package содержит `407` файлов, normal/`python -O` verifier и Defender прошли; EXE SHA-256 `bc7b5ca1d8b0a2ce27ce2277ee7ff836ad4f154eb1dd0582371f0636a74edf02`.
- **Установка/CI:** safe install скопировал `407` byte-identical файлов; installed normal/`python -O` verifier, smoke и расширенная installed geometry прошли. Нативный установленный GUI визуально подтвердил расположение «Дополнительных режимов» непосредственно ниже четырёх кнопок. Exact-head CI `39576422687` завершился `success`; Release/tag `v0.2.9` не создавался.

## B35 — пояснение ручной проверки во всплывающей подсказке

- **Источник:** пользовательское сообщение и красная геометрическая аннотация на приложенном снимке интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Требование:** убрать постоянно видимый поясняющий абзац рядом с заголовком ручной проверки и сохранить короткую контекстную справку в компактной всплывающей подсказке.
- **Границы:** синхронные RU/EN тексты; подсказка доступна мышью, с клавиатуры и экранному диктору; её скрытое состояние не занимает место и не перекрывает заголовок, прогресс, карточку кандидата или панель действий; сохранить B33/B34-инварианты и адаптацию `390/700/900 px`.
- **Приёмка:** RED/GREEN structural/accessibility contracts и executable RU/EN geometry; полный source suite, JS/compile/diff/privacy gates, independent review; свежий Windows package, fail-closed verifier normal/`python -O`, Defender, safe install, installed smoke/geometry и exact-head CI. Release/tag `v0.2.9` не создавать.
- **Проверка:** source commit `97560e012402f9fdaf84d756f51e6657c5dcd3b2`; targeted tooltip/geometry contracts и application suite прошли (`125 passed`), полный suite — `673 passed` с тремя ожидаемыми duplicate-ZIP warnings. RU/EN executable geometry `390/700/900`, compileall, Node syntax, source E2E normal/`python -O`, privacy scan и `git diff --check` прошли. Независимый review вернул `passed=true` без security/logic blockers.
- **Установка/CI:** clean Windows package содержит `407` файлов; fail-closed verifier normal/`python -O` и Defender прошли. EXE SHA-256 `be0acb60a296ec85bc8323edb4279eed8dc9e2e384c1b712fa9cef2ac8302049`. После явного разрешения пользователя закрыт только PID `18956`; safe install скопировал byte-identical package, installed verifier и расширенная RU/EN geometry normal/`python -O` прошли, установленный EXE совпадает с package. Нативный установленный GUI показывает компактный значок справки без постоянного абзаца. Exact-head CI `39710309484` завершился `success`; Release/tag `v0.2.9` не создавался.

## B36 — компактная карточка спорного фрагмента без повторного пояснения

- **Источник:** пользовательское сообщение и красная геометрическая аннотация на приложенном снимке интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Требование:** убрать из карточки спорного фрагмента постоянное пояснение о причине неопределённости и передать освободившуюся ширину проверяемому значению и метаданным. Строка с количеством вхождений и названием набора правил должна занимать не более двух строк на показанной desktop-геометрии, чтобы уменьшилась общая высота карточки.
- **Границы:** синхронные RU/EN DOM и CSS; сохранить заголовок, проверяемое значение, метаданные, четыре действия, tooltip B35, доступность и адаптивность без overlap/horizontal overflow на ширинах `390/700/900`; regression использует только синтетические значения.
- **Приёмка:** RED/GREEN structural contract и executable Edge geometry на production-классах для RU/EN; полный source suite, JS/compile/diff/privacy gates, independent review; свежий Windows package, fail-closed verifier normal/`python -O`, Defender, безопасная установка без broad kill, installed smoke/geometry и exact-head CI. Release/tag `v0.2.9` не создавать.
- **Проверка:** source commit `eca4b1fb1a78f2f0a847726ae286f3bd1acf3c28`; targeted production-DOM и extended geometry прошли для RU/EN на `390/700/900`, application suite — `127 passed`, полный suite — `675 passed` с тремя ожидаемыми duplicate-ZIP warnings. Compileall, RU/EN Node syntax, source E2E normal/`python -O`, privacy scan и `git diff --check` прошли. Независимый review вернул `passed=true` без security/logic blockers.
- **Установка/CI:** clean Windows package содержит `407` файлов; fail-closed verifier normal/`python -O` и Defender прошли. EXE SHA-256 `3034f521904db37a553cc6ef7b4ff953d2e067c00aa06ca6d58da54e25da02a2`. После явного подтверждения сохранения закрыт только PID `1032`; safe install скопировал byte-identical package, installed verifier и RU/EN production-DOM geometry normal/`python -O` прошли, установленный EXE и изменённые assets совпадают с package/source. Установленный GUI запущен как PID `3356`. Exact-head CI `39713831063` завершился `success`; Release/tag `v0.2.9` не создавался.

## B37 — единая горизонталь нижних рабочих блоков

- **Источник:** пользовательское сообщение и красная геометрическая аннотация на приложенном снимке интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Требование:** выровнять по одной горизонтали нижние границы двух верхних рабочих панелей и, следовательно, верхние границы следующих за ними блоков настроек и ручной проверки.
- **Границы:** на широком двухколоночном layout допустимое расхождение — не более `1 px`; на узком одноколоночном layout нельзя добавлять искусственную высоту или создавать overlap. Проверить production RU/EN DOM на ширинах `390/700/900`, используя только синтетические значения.
- **Приёмка:** RED/GREEN runtime и browser geometry; полный source suite, package/install verification, Defender, независимый review и exact-head CI. Release/tag `v0.2.9` не создавать.
- **Проверка:** privacy-safe анализ установил расхождение верхних границ нижних блоков ровно на `8 px`: базовый `margin-top` ручной проверки суммировался с `8 px` gap колонки. RED production-DOM Edge regression воспроизвёл это для RU/EN; после `margin:0`, парных нижних alignment-spacer и наблюдения за динамической высотой обеих верхних панелей расхождение стало не более `1 px` на `390/700/900`. Динамическая проверка отдельно заполняет синтетический undo-блок после первого выравнивания и подтверждает повторное выравнивание через `ResizeObserver`.
- **Source/package/install:** source commit `31fee119bf67ddf27f3f94b8fed52eef5a3a78ed`; focused B37 — `5 passed`, application — `128 passed`, полный suite — `676 passed` с тремя ожидаемыми duplicate-ZIP warnings. Compileall, RU/EN Node syntax, source E2E normal/`python -O`, privacy/static scans и `git diff --check` прошли. Финальный независимый review — `passed=true`, без security/logic blockers. Clean Windows package и установленный EXE прошли fail-closed verifier и RU/EN production geometry normal/`python -O`; `407` файлов скопированы byte-identical, SHA-256 обоих EXE `be150d483eee28de952667f7f8ce25b7ba97b85c38a95fbf0acee345ff9081a4`, Defender угроз не обнаружил. Установленный GUI запущен как PID `33424` из точного installed path. Exact-head CI `39915340319` завершился `success` на Linux и macOS; Release/tag `v0.2.9` не создавался.

## B38 — единый режим обработки спорных фрагментов

- **Источник:** пользовательское сообщение и выделение первых двух флажков в блоке «Дополнительные режимы»; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Корневая причина:** два флажка управляют последовательными состояниями одного процесса: первый включает поиск `HINTS`, второй переводит найденные `HINTS` из ручной очереди в автоматическую замену. Независимые checkbox допускают противоречивую комбинацию «не искать, но автоматически скрывать» и визуально выглядят как дубли.
- **Требование:** заменить два видимых флажка одним трёхпозиционным режимом: не искать спорное / показывать для ручной проверки / скрывать автоматически. Runtime по-прежнему передаёт backend совместимые `disabled_categories` и `paranoid`.
- **Совместимость:** старые профили только с `paranoid=true/false` загружаются как автоматический/ручной режим; новые профили сохраняют точный `uncertain_mode`; импорт/экспорт старого JSON version 1 остаётся допустимым. RU/EN синхронны.
- **Приёмка:** RED/GREEN runtime regression для всех трёх состояний и legacy migration; profile round-trip; полный suite, JS/compile/diff/privacy gates; independent review; fresh Windows package, verifier normal/`python -O`, Defender, безопасная установка и push в `main`. Release/tag `v0.2.9` не создавать.
- **Проверка:** RED одновременно воспроизвёл отсутствие единого control, нового profile field и API-совместимости (`3 failed`). GREEN проверяет DOM и runtime RU/EN, все три состояния, legacy `paranoid=true/false`, нормализацию противоречивых/некорректных значений и profile round-trip. Application suite — `131 passed`; полный suite — `680 passed` с тремя ожидаемыми duplicate-ZIP warnings. Compileall, RU/EN Node syntax, source E2E normal/`python -O`, privacy scan и `git diff --check` прошли. Независимый review вернул `passed=true` без security/logic blockers.
- **Source/package/install/CI:** source commit `504e26bdfcd2437316b61e52cd731be312d0f588` отправлен в `main`; exact-head CI `39922997667` завершился `success`. Clean Windows package и установленная копия прошли fail-closed verifier и отдельный RU/EN unified-mode verifier normal/`python -O`; Defender угроз не обнаружил. Safe install скопировал `407` byte-identical файлов; SHA-256 package/installed EXE `2c2096b0bbaf6c6d1ea239d8328b80e293dbefa6c34a0d756894e926e069a25c`. Установленный GUI запущен из точного installed path как PID `3832`. Release/tag `v0.2.9` не создавался.

## B39 — навигация по спорным фрагментам без смены вида

- [x] **Источник:** пользовательское сообщение и снимок экрана; содержимое документа и реальные значения с изображения не сохраняются.
- **Статус:** выполнено.
- **Корневая причина:** общий обработчик `focusMark()` принудительно вызывал `setAnonymizedPreviewMode(false)`, поэтому любая навигация переводила правую панель в «Текст и подсветка». Затем выделение прокручивалось только в текстовом output, а повторяющиеся значения сопоставлялись по порядковому номеру, хотя порядок извлечённого текста и форматированного DOCX с таблицами может различаться.
- **Реализация:** «Следующее» / «Предыдущее» больше не меняют выбранный режим. Для форматированного вида исходное совпадение находится по контексту `sourceOffset`, правое — по тому же `data-preview-anchor`; обе панели центрируются на одном структурном блоке. Текущее точное значение выделяется через CSS Custom Highlight, с блочным fallback для старого движка. Для «Текст и подсветка» сохранены прежнее точное выделение и синхронная прокрутка.
- **Совместимость:** RU/EN runtime синхронны; повторяющиеся значения и различный порядок абзацев/таблиц покрыты; при отсутствии anchor остаётся порядковый fallback; пользовательский форматированный режим сохраняется в обе стороны навигации.
- **Проверка:** focused RED воспроизвёл принудительную смену режима и отсутствие форматированной навигации. GREEN включает постоянный executable Microsoft Edge regression в RU/EN при ширинах `390/700/900`: `Next` и `Previous` сохраняют обе форматированные панели, выбирают один и тот же структурный anchor и точное текущее совпадение при переставленном порядке повторов. Полный suite — `684 passed` с тремя ожидаемыми duplicate-ZIP warnings; compileall, RU/EN Node syntax, `git diff --check` и privacy/security scans прошли. Независимый review: `passed=true`, без security concerns и logic errors; его предложение сохранить Edge regression в tests выполнено.
- **Source/package/install/CI:** source commit `50cec1c21397c23daae3b4767fcb843802d30705` отправлен в `main`; exact-head native CI `39929007579` завершился `success`. Clean Windows package прошёл fail-closed verifier normal/`python -O`; Microsoft Defender угроз не обнаружил. Safe install скопировал `407` byte-identical файлов; установленная копия прошла normal/`python -O` verification с authoritative dist manifest, package/installed SHA-256 совпал: `419fe3734b3c996cd440032a837f7be57d938829d64e6550e7841bf7d18bac0a`. Установленный GUI запущен как PID `5960`. Release/tag `v0.2.9` не создавался.

## B40 — одна строка кнопок форматированного предпросмотра во время подготовки

- [x] **Источник:** пользовательское сообщение и снимки состояний подготовки/готовности; содержимое документа и реальные значения с изображений не сохраняются.
- **Проблема:** пока форматированный вид готовится, текст состояния и кнопки используют float-flow. Часть кнопок остаётся рядом со статусом, а остальные переносятся на следующую строку; после появления более длинного готового статуса раскладка случайно становится ровной.
- **Требование:** статус всегда занимает отдельную верхнюю строку, а пять кнопок навигации/режима — одну общую строку независимо от текста состояния. RU/EN и ширины `390/700/900` не должны получать overlap или горизонтальный overflow.
- **Приёмка:** executable Edge geometry на production DOM для loading/ready и обеих локалей; полный source/package/install/review/CI gate. Release/tag `v0.2.9` не создавать.
- **Закрытие:** status вынесен в отдельную строку, пять кнопок закреплены общей grid-строкой. Executable Edge подтвердил loading/ready для RU/EN × `390/700/900` без overlap/overflow; итоговый B40/B41 source suite — `691 passed`, независимый review — без logic/security findings.

## B41 — единая логика замен и ручной проверки документа

- [x] **Источник:** пользовательское сообщение и снимок противоречия между исходным фрагментом, форматированным обезличенным результатом и карточкой ручной проверки; реальное значение не сохраняется.
- **Подтверждённая корневая причина:** полный структурный DOCX анализ оборачивает документ границами `U+FDD0`, поэтому правило целой адресной записи поглощает всю строку и подавляет вложенную подсказку. Текстовый предпросмотр анализирует ту же строку без структурной обёртки; правило целой записи было ограничено только `U+FDD0`, поэтому создавалась уже неактуальная подсказка внутри значения, которое экспортируемый документ целиком заменял другим правилом.
- **Требование:** начало/конец обычного текста и границы строк должны иметь ту же семантику логической записи, что и безопасные структурные границы документа. Если более приоритетное правило заменяет весь фрагмент, вложенная подсказка не должна попадать в ручную очередь. Нельзя пересекать строки/cells/rows или расширять замену на окружающий повествовательный текст.
- **Приёмка:** privacy-safe synthetic parity test для plain/structured input, negatives для соседнего текста и строк, DOCX result/review consistency, full source/package/install/review/CI gate. Release/tag `v0.2.9` не создавать.
- **Закрытие:** start/end и CR/LF получили семантику безопасных границ логической записи без пересечения строк/cells/rows; более сильная замена целой записи подавляет вложенную устаревшую подсказку. Fail-closed proof `address_review_parity_ok` обязателен для source/package verification normal и `python -O`.

## B42 — выбранное спорное место сразу видно в форматированных панелях

- [x] **Источник:** пользовательское сообщение и снимок интерфейса; содержимое документа и реальные значения с изображения не сохраняются.
- **Проблема:** карточка ручной проверки показывает текущий фрагмент, но соответствующий участок исходного и обезличенного форматированного предпросмотра остаётся ниже видимой области.
- **Требование:** первый автоматический выбор, «Предыдущее», «Следующее» и переход formatted preview из pending в ready прокручивают обе панели к одному logical target. Exact anchor и безопасный missing-anchor fallback обязательны.
- **Матрица:** RU/EN, ширины `390/700/900`, левая/правая панели; выбранный target должен фактически находиться внутри viewport своего scroll container.
- **Ограничение:** исправление привязать к lifecycle рендера/layout без случайного timeout; сохранить B39-подсветку, formatted mode и отсутствие ошибок при недоступном anchor.
- **Корневая причина:** первичный `renderOutput()` обновлял карточку, но не фокусировал форматированные панели; затем асинхронная готовность правой панели заменяла DOM и восстанавливала пропорциональную позицию без повторного перехода к logical target. Отложенный reset исходного preview мог поверх этого вернуть прокрутку назад.
- **Source verification:** Edge regression прошёл для RU/EN × `390/700/900`, обеих панелей, initial/Previous/Next, pending→ready и missing-anchor fallback; полный suite — `693 passed`, E2E normal/optimized и `92` category checks прошли.
- **Закрытие:** independent review — без logic/security findings; source commit `8cee981dbdab4fca0765b37a1d4e6750c0beea2a`, CI `39955595576 success`. Windows package/installed EXE прошли normal/`python -O`, Defender угроз не нашёл; SHA-256 `ebdc8a4dabbe4212b04520ed2353697ddd1735eccee30174f1d3d968d9fbc6a1`. Установленная программа запущена как PID `33680`; release/tag не создавался.

## B43 — intermittent-фокус спорного фрагмента и возврат checkbox

- [x] **Источник:** новое пользовательское сообщение и три снимка интерфейса; содержимое документа и реальные значения с изображений не сохраняются.
- [x] **Исправить реальную видимость:** при выборе слов в разных вертикальных позициях внутри одного форматированного блока обе панели прокручиваются к точному диапазону слова, а не к контейнеру блока.
- [x] **Lifecycle:** initial/Previous/Next, pending→ready, exact anchor и missing-anchor fallback покрыты; stale animation/layout/scroll callbacks не отменяют более новый выбор.
- [x] **Матрица:** executable Edge regression с реальными layout metrics прошёл RU/EN × `390/700/900`, target в начале/середине/конце второго из двух идентичных высоких блоков; проверяется точный range внутри viewport обеих панелей, delayed layout и fallback при отсутствии target/earlier anchor.
- [x] **Вернуть checkbox:** видимый `select#uncertainMode` заменён отдельными флажками ручной проверки и автоматического скрытия; hidden `uncertainMode` сохраняет persisted/profile-семантику `off/review/auto`, обработчики исключают противоречивые состояния.
- [x] **Убрать дубли заголовка:** оба видимых экземпляра «Дополнительные режимы» / `Additional modes` удалены; fieldset имеет локализованное доступное имя.
- [x] **Паритет и совместимость:** RU/EN синхронны; B39–B42 invariants, profile/storage и responsive layout не регрессируют; полный suite — `694 passed`.
- [x] **Проверка и доставка:** полный suite `694 passed`, итоговый независимый review без замечаний, clean Windows build, fail-closed package verification normal/`python -O`, Defender, безопасная установка, проверка установленного EXE и push `378fc294fb26db4f56228ec1b396b0b8e096b999`. CI: macOS success; Linux dependency-install завис до тестов, run отменён. Release/tag не создавался.

## B44 — стабильная высота блока «Что проверяется»

- [x] **Источник:** пользовательское сообщение и три снимка состояний ручной проверки; содержимое документа и реальные значения с изображений не сохраняются.
- [x] **Требование:** высота `.review-candidate` одинакова при режимах `review`, `auto` и `off` и совпадает с высотой активного состояния «Искать спорные места для ручной проверки».
- [x] **Содержание:** длинное объяснение отключённого режима не растягивает карточку; краткий статус остаётся видимым, полное локализованное объяснение сохраняется в tooltip/доступном имени.
- [x] **Матрица:** executable Edge regression прошёл RU/EN × `390/700/900`; для каждого размера высоты `review/auto/off` равны, текст не обрезается, горизонтального overflow нет, кнопки под карточкой остаются на одной позиции.
- [x] **Совместимость:** семантика checkbox/profile `off/review/auto`, очередь, навигация, formatted preview и правила обезличивания сохранены; полный suite — `695 passed`.
- [x] **Проверка и доставка:** независимый review без замечаний; clean Windows package; fail-closed normal/`python -O`; Defender без угроз; безопасная установка после явного подтверждения сохранения; установленный EXE и RU/EN/CSS assets проверены; source commit `f9566aef806e875badc023bb266f4d7fc0b5f78b` pushed; Native Linux/macOS CI `39979070233` success. Release/tag не создавался.

## B45 — русская терминология и наглядные безопасные снимки

- [x] **Источник:** пользователь попросил убрать необязательные англицизмы из описания и журнала изменений, а на главной странице GitHub показать вымышленный пример с текстом, рисунком, адресом и другими распознанными данными.
- [x] **Требование:** русские разделы `README.md` и `CHANGELOG.md` должны использовать естественные русские формулировки; имена файлов, форматов, команд, библиотек и программные идентификаторы сохраняются без механического перевода.
- [x] **Конфиденциальность:** снимки созданы только из специально подготовленного вымышленного DOCX; пользовательские снимки, документы, значения, локальные пути и служебные локальные файлы не использовались и не публикуются.
- [x] **Снимки:** русский и английский интерфейсы показывают исходный рисунок, вымышленное имя, организацию, адрес, почту, телефон и документационный IP-адрес, а справа — соответствующие маркеры обезличивания и удалённый рисунок `[СХЕМА-1]`.
- [x] **Проверка:** оба PNG визуально проверены; в кадре нет локальных путей или реальных пользовательских данных. Подписи README и запись CHANGELOG согласованы с новым заполненным состоянием.
- [x] **Независимый языковой аудит:** проверен полный перечень замечаний к прежней редакции. Оставшиеся общеязыковые англицизмы заменены; точные названия программных сущностей, форматов, команд и режимов сохранены.

## B46 — пропуски учётной записи и различающегося имени в таблицах DOCX

- [x] **Источник:** два пользовательских снимка; их имена и реальные значения не переносятся в репозиторий.
- [x] **Требование:** значение после явной русской или английской подписи учётной записи в соседней ячейке должно заменяться маркером `ЛОГИН`; полное различающееся имя Active Directory должно заменяться одним маркером `DN` без открытых вложенных частей.
- [x] **Причина:** правило учётной записи не допускало служебную границу между ячейками DOCX; у `DN` был более низкий приоритет, чем у вложенного домена, поэтому цельное совпадение отбрасывалось.
- [x] **Проверка исходников:** добавлены синтетические проверки движка, выключения категорий и настоящего DOCX с таблицей, удалением значений из всего пакета и побайтным восстановлением. Различающееся имя проверяется также с пробелами между частями и экранированной запятой; английское слово `Account` без явного разделителя не считается подписью учётной записи.
- [x] **Доставка:** полный набор проверок, свежая сборка, проверка безопасного отказа, проверка Защитником Windows, установка, проверка установленной программы, независимая проверка и отправка в `main`.
- [x] **Версия:** текущие изменения перенесены из безымянного раздела в `0.2.9` с датой `2026-10-25`; ссылка версии подготовлена как разница между `v0.2.8` и `v0.2.9` и до создания тега намеренно недоступна. Отдельное разрешение на выпуск получено и учитывается в B48.

## B47 — выделение и копирование части текста из областей просмотра

- [x] **Источник:** пользователь попросил выделять мышью и копировать произвольную часть текста непосредственно из левой или правой области; приложенный пользовательский снимок не переносится в репозиторий.
- [x] **Требование:** нативное выделение мышью и `Ctrl+C` копируют только выбранный фрагмент в исходной и обезличенной областях, в текстовом и форматированном представлении, в русском и английском интерфейсах.
- [x] **Совместимость:** подсветка и маркеры замен, переходы к найденным местам, прокрутка, текущая позиция просмотра, подготовка форматированного представления и перетаскивание файлов продолжают работать; протягивание через маркер не запускает его действие, а обычный щелчок по маркеру сохранён.
- [x] **Матрица:** исполняемая проверка настоящими событиями мыши и `Ctrl+C` прошла RU/EN × `390/700/900`, текстовые и форматированные структуры, левую и правую области, выделение через несколько элементов и маркер замены.
- [x] **Доставка:** полный набор проверок, свежая Windows-сборка, проверка безопасного отказа обычным Python и `python -O`, Защитник Windows, безопасная установка, проверка установленной программы, независимая проверка и отправка в `main`; выпуск и тег не создавать без отдельного разрешения.

## B48 — единая типографика интерфейсных блоков и выпуск 0.2.9

- [x] **Источник:** пользовательское сообщение и снимок интерфейса от `2026-10-25`; снимок и реальные значения из него не переносятся в репозиторий и выпуск.
- [x] **Проблема:** равнозначные заголовки разделов визуально различались по размеру, насыщенности, межстрочному интервалу и дополнительному межбуквенному интервалу. Особенно заметно было расхождение между заголовками настроек, ручной проверки, восстановления, справочных раскрывающихся блоков и закреплённого состояния.
- [x] **Требование:** введены единые типографические роли для интерфейса: заголовок приложения, заголовок раздела, заголовок панели, основной текст, пояснение и элемент управления. Одинаковые роли имеют одинаковые `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing` и `text-transform` в RU/EN; исходные размеры, начертания и структура форматированного DOCX остались без изменений.
- [x] **Матрица:** исполняемая проверка production HTML/CSS прошла в RU/EN при реальной ширине окна `390`, `700` и `900`; проверены вычисленные стили, отсутствие горизонтального переполнения и сохранение документной типографики.
- [x] **Документация и публикация:** README и CHANGELOG обновлены; публичные снимки содержат только вымышленные данные; change request №1 прошёл проверки и слит в `main`; тег и GitHub Release `v0.2.9` опубликованы с русским описанием, снимками, Windows-пакетом и манифестом.
- [x] **Доставка:** полный набор — `709 passed, 3 warnings`; свежая Windows-сборка прошла безопасный отказ обычным Python и `python -O`; Защитник Windows угроз не обнаружил; установленная программа совпала со сборкой по `408/408` файлам; независимая проверка завершилась без блокеров.

## B49 — состояние публикации 0.2.9 на главной странице GitHub

- [x] **Источник:** пользователь попросил проверить состояние GitHub и продолжить исправления.
- [x] **Проблема:** после публикации выпуска README продолжал предлагать дождаться `v0.2.9` и называл исходный код только подготовленным к выпуску.
- [x] **Исправление:** английская и русская инструкции теперь прямо указывают, что `v0.2.9` опубликован, и содержат ссылки на страницу выпуска и непосредственное скачивание проверенного Windows-архива.
- [x] **Границы:** код программы, пакет, тег и активы выпуска не изменяются; Linux/macOS по-прежнему не объявляются поддерживаемыми выпусками.

## B50 — устранение предупреждений безопасности зависимостей

- [x] **Источник:** после включения уведомлений безопасности GitHub обнаружил восемь предупреждений Dependabot: шесть высокого, одно среднего и одно низкого уровня.
- [x] **Причина:** ограничения проекта удерживали `cryptography` ниже исправленных выпусков, а файл блокировки содержал уязвимую версию `setuptools`.
- [x] **Исправление:** `cryptography` поднят до `50.0.2`, `setuptools` — до `84.2.1`; файл блокировки пересоздан.
- [x] **Проверка:** `uv lock --check`, `709 passed, 3 warnings` и `scripts/release_verify.py` прошли локально; нативные проверки Ubuntu и macOS в запуске `40266489191` завершились успешно.
- [x] **Доставка:** change request №5 слит в `main` коммитом `47048ceefb85dee133676c62123d43762a145ab1`; GitHub API подтвердил закрытие всех восьми предупреждений со статусом `fixed`.

## B51 — обязательная проверка перед слиянием

- [x] **Причина:** защита `main` уже требует change request, но не могла требовать успешную проверку: нативный workflow намеренно запускается только при изменениях кода и не подходит для документационных правок.
- [x] **Решение:** добавить быстрый workflow для каждого change request и отправки в `main`: проверка пробельных ошибок Git, файла блокировки и синтаксиса Python.
- [x] **Проверка:** новый workflow прошёл в change request №7 (запуск `40267093529`) и после слияния в `main` (запуск `40267132217`).
- [x] **Доставка:** change request №7 слит коммитом `511419d34cf022d7f818dd8cd5c720b055080e7b`; проверка `Проверка репозитория` назначена обязательной, строгой и прочитана обратно через GitHub API.

## B52 — лицензия Apache License 2.0

- [x] **Решение владельца:** проект выпускается по разрешительной лицензии Apache License 2.0 с явным предоставлением патентных прав участниками.
- [x] **Оформление:** добавлен полный официальный текст `LICENSE`, лицензия указана в метаданных пакета и в русской и английской частях README.
- [x] **Участие:** README поясняет, что намеренно предложенные изменения принимаются на условиях Apache License 2.0, если явно не указано иное.
- [x] **Проверка:** `uv lock --check`, `compileall`, сборка wheel и проверка метаданных прошли; wheel содержит `License-Expression: Apache-2.0`, `License-File: LICENSE` и сам файл лицензии.
- [x] **Доставка:** change request №9 слит коммитом `0f6ccbd8231374d0cf5e0aec5bf7064ade05e9c0`; обязательная проверка и нативные проверки Linux/macOS прошли, GitHub распознаёт `LICENSE` как Apache License 2.0 (`Apache-2.0`).

## Проверка кода после B53 — исправления и доставка

Исходный снимок аудита: `eb2ec992051db6ad6b8bbd528561a51b5b2529a3`. Пользователь согласовал исправления. Первоначальный полный набор: `710 passed, 3 warnings`; дополнительные синтетические проверки воспроизвели приведённые ниже ошибки.

**Состояние исправлений:** B54–B65 реализованы в исходниках. Итоговый полный набор: `876 passed, 3 warnings`. Независимая повторная проверка дала GO для проверенного объёма; сверен неизменный снимок 112 файлов, SHA-256 манифеста `1fb419b5f88e1a6fc3e8e9728f3abcd6847a121815942aac11d4261f1b47d12b`. Word открыл обезличенный и восстановленный приёмочные документы; проверка восстановления прошла также под `python -O`. Excel подтвердил сохранение текстового типа для строки с `=`, работоспособность обычной формулы и удаление тестового адреса. Фактически установленный `setuptools` обновлён до `84.2.1`, аудит среды известных уязвимостей не нашёл. Доставка исправлений для Windows завершена в `v0.2.10`; приведённые ниже формулировки сохраняют результаты первоначального аудита. Нативная конкурентная проверка B65 остаётся отдельно открытой.

- [x] **B54 / высокий — скрытые данные XLSX.** В выходном пакете со статусом готовности остаются синтетические адреса в названии листа, проверке данных, пользовательском XML и кэше результата формулы. Требуется проверять весь пакет, а не только видимые ячейки.
- [x] **B55 / высокий — скрытые данные ODT.** Синтетические адреса остаются в имени закладки, атрибутах метаданных и настройках; готовность не блокируется.
- [x] **B56 / высокий — необратимое удаление секретов нарушено.** В DOCX и ODT пароль отображается как удалённый, но восстановление неизменённого документа возвращает его из сохранённого полного оригинала. Требуется согласовать сохранение точного оформления с исключением необратимых секретов из архива восстановления.
- [x] **B57 / высокий — секреты в JSON-тексте.** Поле с именем `password` в кавычках пропускается: файл TXT с JSON получает статус «Готов» и экспортируется с исходным секретом без предупреждения.
- [x] **B58 / высокий — текст XLSX становится формулой.** Значение общей строки, начинающееся с `=`, при переписывании становится ячейкой типа formula. Префикс `_xlfn.WEBSERVICE` также проходит проверку опасных формул. Выполнение сетевого запроса в Excel не проверялось; доказано изменение типа и сохранение формулы.
- [x] **B59 / высокий — потеря соседнего файла при восстановлении.** `service.py:395–400`: предсказуемое имя `.NAME.validated.txt` может совпасть с существующим файлом; тот перезаписывается и удаляется. Воспроизведено в отдельной временной папке.
- [x] **B60 / высокий — несовместимая экспортная пара.** `service.py:463–475`: при повторном обезличивании между сериализацией восстановления и экспортом документа создаётся пара разных операций; экспорт сообщает успех, восстановление отклоняет пару.
- [x] **B61 / средний — конкурирующие предпросмотры.** `app.py:905–969`: один общий слот `_ui_preview` позволяет запоздалому запросу аннулировать токен текущего просмотра; воспроизведена ошибка «Предпросмотр устарел».
- [x] **B62 / средний — конкурирующая запись настроек.** `app.py:860–866`: общий временный файл и отсутствие синхронизации приводят к ошибке записи, потере настройки либо некорректному JSON. Воспроизведено параллельными изменениями темы и языка.
- [x] **B63 / средний — граница счётчика маркеров.** После существующего девятизначного номера создаётся десятизначный маркер, который восстановление не распознаёт; исходное значение не восстанавливается.
- [x] **B64 / средний — устаревшая зависимость среды сборки.** В `.venv` обнаружен `setuptools 84.0.0` с `GHSA-xmj3-9gf7-h52w`, хотя `uv.lock` содержит `84.2.1`. Проверка зависимостей файла блокировки для Windows известных уязвимостей не нашла. Это риск среды установки/сборки, не доказанная атака через документ.
- [ ] **B65 / требует нативной проверки — первый ключ Linux/macOS.** На имитации системного хранилища одновременное создание первого ключа делает данные одного экземпляра недоступными следующему. Это подтверждение логики гонки, не проверка реального системного хранилища; развитие Linux/macOS отдельно не согласовано.

**Доставка 2026-10-27:** исправления B54–B64 включены в опубликованный выпуск `v0.2.10` и установленную Windows-копию. Итоговый полный набор — `909 passed, 3 warnings` (ожидаемые предупреждения для отрицательных проверок дублирующихся XML). Независимая проверка исходников и архива пройдена. Сборка и установленная копия прошли обычную проверку и `python -O`; Защитник Windows угроз не обнаружил. Сверены все 413 файлов установленного пакета. Через привычный ярлык отдельно проверены импорт, обезличивание, экспорт пары, редактирование и сохранение в Word, восстановление с сохранением правки, таблицы, объединений, полужирного и курсивного текста; удалённый секрет не вернулся. Исправление логики B65 включено в исходники, но отдельная конкурентная проверка первого ключа в реальных Linux/macOS-хранилищах этим не подтверждается.

## B66 — восстановление после реального редактирования в Word

- [x] **Воспроизведено при проверке готовой Windows-программы:** импорт, обработка и сохранение пары прошли; после открытия, изменения и сохранения обезличенного файла в Microsoft Word восстановление остановлено с `word/settings.xml:foreign-xml`.
- [x] **Исправление в исходниках:** безопасно удаляется только проверенная настройка масштаба Word (целое 10–500 процентов либо точный `bestFit`); неверный контекст, посторонние атрибуты, текст и дочерние элементы по-прежнему блокируют результат. Та же синтетическая пара восстановлена с таблицей, вертикальными объединениями и без удалённого пароля. Интерфейсы RU/EN v1.8.19 явно сообщают об отказе восстановления без внутренних путей; новая обязательная проверка пакета отклоняет старую сборку без доказательства восстановления настроек Word.
- [x] **Проверка и доставка:** полный набор `909 passed, 3 warnings`; новая Windows-сборка `v0.2.10` и отдельно установленная копия прошли пользовательский путь с реальным Word. Выпуск опубликован, установленная программа обновлена, предыдущая копия сохранена для отката.

## B53 — лицензия в нативных пакетах

- [x] **Причина:** одного файла `LICENSE` в репозитории недостаточно для отдельно распространяемого нативного пакета.
- [x] **Решение:** общий PyInstaller spec включает `LICENSE` в нативные пакеты Windows, Linux и macOS.
- [x] **Проверка:** профильный тест прошёл; полный набор — `710 passed, 3 warnings`; полная Windows-сборка прошла, пакет содержит точную копию `LICENSE` по пути `_internal/LICENSE`.
- [x] **Доставка:** обязательная проверка, нативные проверки Ubuntu и macOS прошли; change request №11 слит коммитом `77c60db0ca99449660dfe58e909fb39f2b120018` через защищённый `main`.

## B67 — выпуск v0.2.10

- [x] **Подготовка и публикация:** исходники и архив независимо проверены; [выпуск v0.2.10](https://github.com/onv83/LocalAnonymizer/releases/tag/v0.2.10) опубликован как текущая стабильная версия. Метка указывает на `01d9310ed08066d3a28956a497396a44c0cde606`; обязательная проверка и существующие проверки Ubuntu/macOS прошли. Новые пакеты Linux/macOS не публиковались.
- [x] **Приёмка:** пользовательский путь экспорта и восстановления после редактирования в Word проверен на сборке и установленной копии. Все три опубликованных файла повторно скачаны по публичным ссылкам; байты и SHA-256 совпали с локальными. ZIP содержит 413 проверенных файлов приложения и манифест; лицензия Apache-2.0 совпадает с исходником.
- [x] **Архив:** `LocalAnonymizer-0.2.10-windows-x64.zip`, SHA-256 `de4b29cbed0ce86f9d491e87f24cf27cdb9a29e209d2e744b41a59d9f9189aa1`. Рядом опубликованы `SHA256SUMS.txt` и `LocalAnonymizer.manifest.json`.
- [x] **Сохранность предыдущего выпуска:** метка, идентификаторы, размеры, контрольные суммы и даты изменения файлов `v0.2.9` не изменены.

## B68 — пропуски персоналий и денежных сумм в аналитическом документе

- [ ] **Приоритет:** критический; не закрыто. В предоставленном результате обработки сохраняются имена с фамилиями и фамилия с инициалами, в том числе повторно в перечнях участников и таблицах персоналий.
- [ ] **Суммы:** часть денежных значений заменена, но остаются значения с сокращёнными единицами тысяч и миллионов, в том числе в перечислении затрат и повторных упоминаниях. Реальные значения и исходный документ в репозиторий не переносить.
- [ ] **Проверка:** воспроизвести на полностью вымышленных данных; проверить текст, таблицы, повторы, варианты пробелов и пунктуации, разбиение Word на фрагменты, включение и отключение категорий. Причина и состояние настроек при пользовательской обработке пока не установлены.
- [ ] **Приёмка:** ожидаемые персональные и денежные значения отсутствуют во всём экспортируемом документе; корректность восстановления и сохранность форматирования проверены отдельно. Общие ранее пройденные тесты не закрывают этот дефект.

## Дополнение к B68 — повторная проверка аналитической справки

- [ ] **Критический незакрытый дефект:** в повторно присланном результате остаются имя с фамилией и фамилия с разнесёнными пробелами инициалами; особенно в разделе персоналий и извлечённом содержимом таблиц. Наличие отдельных маркеров ФИО не означает полноты защиты. Реальные имена в репозиторий не переносить.
- [ ] **Приёмка персоналий:** синтетические имена разных языковых традиций, оба порядка имени и фамилии, инициалы с пробелами, отдельные ячейки и фрагменты Word, повторения; проверять весь экспорт, а не только основной текст. Не ограничиваться добавлением конкретных фамилий в словарь.
- [ ] **Дополнительные наблюдения:** повторная сумма после косой черты остаётся открытой; маркеры доменов в переходах между предложениями и организаций вместо обычной лексики требуют проверки исходных границ. По обработанному тексту исходные диапазоны не установлены.
- [ ] **Статус:** исправление персоналий и проверка установленной сборки не выполнены; общий успешный прогон тестов этот дефект не закрывает.

## Дополнение к B68 — второе сообщение: технический отчёт

- [ ] **Источник и разрешение:** новое сообщение пользователя с результатом обработки технического отчёта; явно поручены анализ, внесение в план и начало исправлений по обоим сообщениям. Приватный исходный текст и значения не включаются в репозиторий.
- [ ] **Персоналии:** проверять фамилию с именем, оставшиеся имя и отчество при уже скрытой фамилии, инициалы, латинскую транслитерацию в названиях оконечных устройств; повторения в таблицах. Статус: не начато, ранее не покрыто доказательствами.
- [ ] **Денежный контекст:** скрывать сокращённые денежные величины в перечислениях затрат; не принимать объём памяти, ёмкость носителей и номер поколения оборудования за деньги только из-за слов «сумма» или «объём». Статус: начато исследование, исправление ещё не доказано.

## B70 — неполное скрытие инфраструктурных идентификаторов и контактов

- [ ] **Приоритет:** критический. Источник: второе сообщение пользователя, технический отчёт. Ранее пропущено в приёмке; статус: не начато.
- [ ] **Наблюдение:** остаются полные и короткие имена узлов, имена репозиториев/томов/ресурсов, служебные учётные записи, цифровые и смешанные серийные номера после S/N и слов «серийный номер»; телефон с пробелом после плюса и добавочным; часть городов, улица и дом после маркера города.
- [ ] **Требование:** контекстное распознавание по заголовкам таблиц и вводным словам; целостные идентификаторы вместо скрытия отдельного суффикса как задачи. Учитывать уже замаскированный домен и разрывы фрагментов Word, не выдавая остаток имени за полностью обезличенный узел.
- [ ] **Границы:** сохранять общие названия продуктов, стандартные термины и обычные слова, если их категория не выбрана; не распространять заголовок столбца на последующий раздел. Проверять отключение каждой категории.
- [ ] **Приёмка:** синтетические текстовые и DOCX-примеры, таблицы с изолированными ячейками, повторы и восстановление. Источник ошибки в распознавании, настройках или предварительно обработанном документе установить отдельно.

## B71 — ложная классификация технических значений и удаление обычного текста

- [ ] **Приоритет:** высокий; для необратимого удаления — критический. Источник: второе сообщение пользователя. Статус: начато исследование; ранее не покрыто доказательствами.
- [ ] **Наблюдение:** в оглавлении названия стандартных административных групп заканчиваются сообщением об удалённом пароле, тогда как в основном тексте названия сохранены. В описании аппаратных отказов присутствуют сообщения об удалённых учётных данных. Без оригинала точный удалённый диапазон неизвестен.
- [ ] **Требование:** проверять склеивание номера страницы и заголовка; не удалять стандартную техническую фразу как пароль без достаточных признаков. Настоящие пароли, токены и учётные данные должны по-прежнему необратимо удаляться, включая проверку восстановления.
- [ ] **Категории:** различать версии микрокода и IP/телефоны, поколения носителей и RAID и ключи задач, скорость порта и номер порта, аппаратную платформу и логин. Не исправлять конфликт простым отключением защитного распознавателя.
- [ ] **Приёмка:** парные положительные/отрицательные синтетические проверки, контекст таблицы и обычного текста, границы диапазона и правила приоритетов; никаких настоящих секретов в тестах.

## B69 — избыточные замены обычной лексики и технических сокращений

- [ ] **Приоритет:** высокий; не закрыто. В предоставленном результате обычные слова и словосочетания заменяются маркерами организаций, а многочисленные технические сокращения скрываются с потерей читаемости.
- [ ] **Дополнение по техническому отчёту:** маркер производителя появляется вместо предлога и обозначения программного обеспечения, а также в контекстах обычных существительных. В словах имеются внутренние пропуски. Проверить исходный документ, пользовательский словарь, выделение псевдонимов и границы слова; наличие подчёркиваний в результате само по себе не доказывает, что их создала текущая версия.
- [ ] **Проверка:** на вымышленных примерах отделить ложное распознавание организаций от сознательно включённого скрытия сокращений; проверить настройки и контекстные границы. Не считать все замены сокращений ошибкой без проверки выбранных категорий.
- [x] **Первый проверенный шаг B69:** воспроизведено ложное распознавание заголовка «Производитель ПО» с распространением на обычные слова; заголовочные значения исключены до создания производных замен. Проверены сохранность текста и заголовка в DOCX и побайтовое восстановление. Остальные виды избыточных замен остаются открытыми.
- [ ] **Приёмка:** общеупотребительная лексика не распознаётся как организация; технические названия и сокращения обрабатываются согласно явно выбранным категориям без ослабления защиты персоналий и сумм.

### Первый этап реализации B68–B71

- [x] Телефон: пробел, табуляция, неразрывный и узкий неразрывный пробел после плюса; отрицательные примеры и отключение категории. DOCX: разорванные фрагменты, таблица, неизменность исходника и побайтовое восстановление. Добавочный номер пока отдельно не исправлен.
- [x] Суммы: полное распознавание проверенных цифровых сумм с масштабом, записанным словом; контекст расходов без валюты; исключены проверенные ёмкости, количества, даты и версии после коммерческих слов. Перечисления составляющих затрат и полнота обработки пользовательского документа пока не подтверждены.
- [x] Проверка текущего кода: `tests/test_b69_vendor_heading.py`, `tests/test_b70_phone_spacing.py`, `tests/test_b68_money_context.py`, `tests/test_engine.py` — 128 passed. `git diff --check` без ошибок.
- [x] Суммы через косую черту без пробелов: воспроизведён пропуск второго значения с валютой и исправлена левая граница правила. Проверены разорванные фрагменты и таблица DOCX, отключение категории, неизменность исходника и побайтовое восстановление. Целевые денежные проверки: 29 passed; совместно с основными проверками движка до добавления двух DOCX/настроечных проверок: 243 passed. Это не закрывает перечни без повторения валюты.
- [x] Узкое исправление оглавления: отдельные строки `Domain/Enterprise/Schema Admins` с номером страницы больше не удаляются как пароль. Проверены точки-лидеры, таблица и разорванные фрагменты DOCX, точное восстановление; явно помеченные пароли (включая перенос строки/границу ячейки после подписи) по-прежнему удаляются. Это не закрывает остальные ложные секреты и внутрисловные повреждения.
- [x] Частичное исправление персоналий: инициалы распознаются без обязательного полного ФИО рядом; поддержаны дополнительные горизонтальные пробелы, обратный порядок фамилия/имя и расширенный общий словарь имён. Разные имена/инициалы при одной фамилии не объединяются; исключены проверенные обычные фразы и склеивание несвязанных ячеек. Проверены DOCX с разорванными фрагментами и таблицей, сохранение исходника, точное восстановление и отключение категории. Общая целевая проверка текущих изменений: 326 passed. Реальные полные имена пользователя в тесты не перенесены. Полнота по произвольным именам и пользовательским документам не доказана; B68 остаётся открытой.
- [x] Полный прогон после первого этапа: 1019 passed, 3 warnings; предупреждения относятся к намеренным дублям ZIP-записей. Это не доказывает полноту распознавания.
- [ ] Оставшиеся подзадачи, новая сборка, установка и публикация: не завершены. Нельзя считать текущую установленную программу исправленной по всем сообщениям.

### B68 — повторное сообщение после полного прогона

- [ ] Пользователь вновь показал открытые персоналии в хронологии и карте участников. Проверка отдельных строк непосредственно текущим движком подтвердила пропуски фамилий без типичных окончаний, включая короткие фамилии и фамилии на «-бо»/«-оль». Реальные полные имена в репозиторий не переносились.
- [ ] Часть других показанных персоналий текущий движок уже скрывает в отдельных строках. Это не доказывает обработку исходного DOCX; версия установленной программы и структура исходного документа должны проверяться отдельно.
- [ ] Требуется общий механизм распознавания нетипичных фамилий с отрицательными проверками обычной лексики, обоими порядками, таблицами и точным восстановлением. Не ограничиваться добавлением фамилий из пользовательского документа.

## B72 — большой офлайн-словарь имён и контекстные фамилии

- [ ] **Общее требование пользователя:** очень большой общий словарь имён разных традиций России, склонение имён, ё/е; известное имя рядом с заглавным словом трактовать как имя+фамилию в обоих порядках, включая короткие/несклоняемые фамилии. B68 и приёмка на пользовательском документе остаются открытыми.
- [x] **Ресурс:** из generic names.jsonl проекта datacoon/russiannames (Ivan Begtin, BSD-3-Clause, закреплённый commit `e4e7e687b9d53db9bca815c26c2a13f8bc66c4b0`) отфильтрованы 10 283 написания / 10 275 нормализованных ключей; исходных записей 32 134. В пакете нет реальных полных ФИО, идентификаторов, частот или пользовательских данных. UTF-8 names.txt — 142 779 байт; рядом лицензия, атрибуция, manifest и воспроизводимый конвертер с проверкой SHA-256.
- [x] **Склонение:** офлайн-парадигмы по лексическому полу, -а/-я/-ия/-ья, мужские согласные/-й/-ий/-ь, женское -ь, исключения Лев/Павел; всего 48 191 точный ключ имя/форма. Несклоняемые классы сохраняются. Это не универсальный морфоанализатор: иностранные исключения, ударение, редкие формы и часть языков РФ не покрыты. При коллизиях формы не объединяются с угаданным именем (например Романа/Роман, Игор/Игорь); все проверенные формы при этом скрываются.
- [x] **Правила:** добавлена ограниченная пара с точным словарным якорем и заглавной фамилией; без перехода через пунктуацию, строки и границы ячеек/абзацев. Учитываются отрицательные примеры организаций, продуктов, названий; имя+отчество не создаёт ложный якорь фамилии. Два известных имени не трактуются новой эвристикой как имя+фамилия. Старые суффиксные правила не расширены до любых двух заглавных слов.
- [x] **Проверка:** строгие RED/GREEN для нового словаря, нетипичных фамилий, склонений, разделения идентичностей и границ. `tests/test_b72_given_name_dictionary.py tests/test_b68_person_names.py`: **115 passed**. Проверены оба порядка, категория ФИО выключена, ё/е, UTF-8/число/хеш словаря, синтетические DOCX с разорванными runs и таблицами, сохранность исходника и побайтовое восстановление.
- [x] **Замороженный ресурс:** PyInstaller smoke-exe реально собран и запущен из временного каталога вне репозитория: `B72 frozen resource + offline engine OK: 10275 bases, 48191 forms`, exit 0. Использована та же рекурсивная схема assets, что в LocalAnonymizer.spec; тест проверяет spec и Hatch package path. Первый smoke-build не нашёл относительный assets при spec во временном каталоге; повтор с абсолютным путём успешен. Полный wheel не собирался (hatchling отсутствует, установки запрещены).
- [x] **Повторная независимая проверка после прерывания:** прочитан журнал предыдущего исполнителя и фактический diff; реализация сохранена без перезаписи B68–B71. Повторный целевой прогон B72, B68 person/money, B69, B70, B71 и test_engine: **259 passed in 36.52s**; `git diff --check` чистый. Дополнительно проверены полное совпадение ключей genders.json со словарём, допустимые значения пола, число форм и безопасная канонизация Давиду/Роман/Романа. Повторная офлайн-конверсия закреплённого исходника дала побайтово идентичные names.txt, genders.json и manifest.json; LICENSE.txt побайтово совпадает с лицензией закреплённого upstream commit. Smoke-exe повторно запущен: exit 0, 10275 bases / 48191 forms.
- [ ] **Полный прогон B72 не подтверждён:** сохранённый b72-test-results.log не содержит итоговой строки; повторный полный pytest остановлен тайм-аутом инструмента через 420 секунд без результата. Не подменять его предыдущим полным прогоном B68–B71 или целевыми 259 проверками.
- [ ] **Остаточные риски:** шумные исходные написания; не все редкие имена, региональные буквы и составные имена; омонимия имён и обычных слов; нетипичная фамилия, совпадающая со словарным именем; неоднозначные формы не всегда получают один маркер. Установленная программа и выпуск не изменены, commit/push/install не выполнялись.

## B73 — города и регионы России со склонением

- [x] **Интеграция в исходниках, 2026-10-29:** `engine.py` использует точные физические spans `find_locations` вместо `CITIES`/suffix-wildcard и для распознавания, и для review hints. Канонические ID используются для исключений; различные исходные написания получают отдельные обратимые маркеры. Категория ГОРОД (включая paranoid), приоритет АДРЕС, составные/склонённые города и регионы, отрицательные «Томский модуль»/обычные слова проверены. Сохранена прежняя поддержка Берлина отдельными конечными формами, вне российского snapshot.
- [x] **Источник и пределы:** 1117 городов и 85 регионов из snapshot 2021 года, pinned upstream `ae661bffe572880472249097c9b29c42b09650ea`, CC BY-SA 4.0; лицензия/NOTICE в assets. Это не текущий исчерпывающий административный список и не универсальная морфология. Омонимы требуют контекста; границы ячеек/абзацев не склеиваются.
- [x] **Интеграционные проверки:** синтетический DOCX с разорванными форматированными runs и таблицей, сохранность исходника, побайтовое восстановление; тесты production engine без подмены. Совместный целевой прогон B68–B74 + test_engine: **349 passed in 75.44s**. Первичный RED выявлял пропуски; отдельно воспроизведена регрессия Берлине→СКРЫТО и исправлена без ослабления старого теста.
- [x] **Замороженный ресурс:** отдельный PyInstaller smoke реально собран и запущен вне репозитория, exit 0: `B72/B73/B74 frozen offline engine OK: names, 1202 geography records, Berlin, passport, surname-city disambiguation, exact restoration` (пересборка и запуск после исправления Иванова). Проверены offline-загрузка assets/NOTICE и production engine, отключение ГОРОД и отрицательный пример; рекурсивный assets соответствует LocalAnonymizer.spec. Hatch wheel package path проверен тестом; **wheel не собран**, hatchling отсутствует, установка зависимостей запрещена.
- [x] **Полный прогон, 2026-10-29:** первый завершился **3 failed, 1159 passed, 3 warnings in 767.46s** (exit 1). Все три сбоя: `test_engine_hardening::test_initials_disambiguate_people_but_bare_surname_remains_hint`, `::test_initials_remain_hint_when_multiple_anchors_are_compatible`, `test_parity::test_people_with_same_surname_do_not_collide_or_claim_ambiguous_alias`. Причина: Иванова ошибочно распознавался как форма города Иваново вместо неоднозначного известного персонального алиаса. Исправлена фильтрация географии при известных фамильных якорях; явный локальный географический контекст сохраняет город. Исходные проверки не ослаблены; добавлены положительные контексты `г.`, `города`, `из`. Фокусный прогон: **107 passed in 18.98s**. Повторный полный прогон завершён: **1170 passed, 3 warnings in 782.25s (0:13:02)**, exit 0; лог `geography-passport-full-final.log`. Три предупреждения относятся к намеренным дублированным ZIP entries в защитных XLSX/ODT/DOCX тестах. Ошибок не осталось. Это приёмка исходников/регрессий, не установленного релиза.
- [ ] **Приёмка:** установленная программа и релиз не менялись. Проверка пользовательского документа/установленной копии остаётся открытой.

## B75 — macOS, нативный bridge и выпуск 0.2.11 (2026-10-29)

- [x] Пользователь явно разрешил интеграцию macOS и публикацию исходников/сборок; прежнее исключение macOS из объёма более не действует. Старый v0.2.10 не перезаписывается.
- [x] Архив 0.2.10-arm64 изучен без запуска его бинарников; перенесены нативное копирование, Cmd+Enter и переключение языка. Старые движок/ресурсы не заменяют B68–B74.
- [x] Отвергнуто ослабление CSP через unsafe-eval. Добавлен совместимый bridge на замыканиях и нативных ответах, с отдельными регрессионными тестами. Ошибки восстановления RU/EN сохраняют безопасное сообщение.
- [x] Windows source GUI smoke подтвердил strict CSP bridge, native clipboard, restore и language API. Это не подтверждает macOS.
- [x] **Обновление по опубликованному выпуску v0.2.11:** отчёт выпуска фиксирует Windows 1177 passed и успешные проверки EXE; [нативный ARM64 CI](https://github.com/onv83/LocalAnonymizer/actions/runs/40908065255) — 1161 passed, 16 skipped и packaged smoke. Документационная перепаковка и повторные Windows smoke/readback проверены отдельно в B76; эти результаты не закрывают ручную приёмку Mac.
- [ ] Ручная приёмка на пользовательском Mac, Developer ID/notarization и Intel Mac не подтверждены. B65 остаётся открытым для нативной конкурентной проверки keyring.

## B74 — сообщение о пропусках паспортов

- [x] **Исходники, 2026-10-29:** production engine вызывает `register_passport_rules(add)` вместо старого number-only правила. Сам passport_rules.py при интеграции не менялся. Из тестовой fixture убрана exec-подмена движка: все 34 проверки теперь проходят через реальную регистрацию.
- [x] **RED/GREEN:** до регистрации production-прогон показал **11 failed / 23 passed** по паспортам (совместно с Берлином 12 failed / 23 passed); после регистрации входят в успешные **349 passed** целевого прогона. Проверены повторные/неразрывные пробелы, №, отдельно подписанные серия/номер, issuer/date/subdivision, DOCX split runs/table, выключение категории, отрицательные паспорта оборудования/числа/структурные границы и точное восстановление включая исходные пробелы и DOCX bytes.
- [ ] **Не закрыта пользовательская приёмка:** исходный пользовательский документ и установленная программа не проверялись; реальные паспортные данные в репозиторий не переносились. Метаданные распознаются только в подписанном ограниченном паспортном контексте (400 символов), не во всех произвольных макетах. Установка/публикация не выполнялись.

## B76 — документация в дистрибутивах v0.2.11 (2026-10-30)

- [x] По явному разрешению пользователя заменены ZIP текущего v0.2.11: Windows README/CHANGELOG актуализированы; русская `README-macOS.md` добавлена в корень Mac ZIP и рядом с `.app`. Есть установка без Python, ARM64/preliminary, безопасное открытие конкретного приложения через Gatekeeper и чек-лист ручной приёмки.
- [x] Исправлен нижний раздел README: убраны дублирующие `uv run --no-project` команды; пути сборок сверены с build.bat/build.sh, Python 3.11 — с pyproject.toml; DPAPI-only формулировка обобщена до защищённой локальной карты, WebView2 не выдан за Mac backend. Уточнён реально разрешённый исходниками PNG/JPEG data-URI предпросмотр, вместо неверного утверждения, что изображения вообще не показываются.
- [x] Все 424 остальных Windows ZIP entries и все 689 исходных Mac entries побайтно сохранены. Mac: сохранены 54 symlinks, режимы/ZIP metadata и содержимое `.app`, включая имеющиеся данные подписи. Проверены CRC, отсутствие дубликатов и небезопасных путей, разрешение цепочек symlinks без выхода из `.app`.
- [x] Сверены все записи существующих manifests: 423 Windows / 577 Mac, хеши EXE и Mac executable. Манифесты побайтно прежние: изменённые инструкции вне инвентаря приложения. SHA256SUMS.txt пересчитан для новых ZIP и согласован со всеми четырьмя assets.
- [x] Windows EXE из отдельной распаковки прошёл `--smoke`, `--pair-smoke`, `--platform-smoke`: engine invariants, точное восстановление пары, защищённое хранилище и clipboard. Установленная пользовательская копия не заменялась. Mac executable на Windows не запускался и не пересобирался.
- [x] Все пять assets опубликованы и заново скачаны с GitHub; readback побайтно совпал с проверенными локальными файлами, инструкции и SHA-256 проверены повторно. Первый download прерван тайм-аутом 180 секунд; повторный полный download успешен. Метки Git и идентичность assets/описание v0.2.10 сверены до/после — без изменений.
- [x] Обновлено и прочитано обратно описание [релиза](https://github.com/onv83/LocalAnonymizer/releases/tag/v0.2.11). [Публичный отчёт с SHA-256](release-0.2.11-documentation-repack.md).
- [ ] Ручная приёмка Mac (Gatekeeper, Cmd+Enter, RU/EN, реальный DOCX/Word, clipboard/dialogs), Intel, Developer ID/notarization и нативная конкурентная проверка B65 остаются открытыми. Новый полный pytest не запускался для документационных изменений; старый CI не выдаётся за новый.
