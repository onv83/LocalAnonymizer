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
