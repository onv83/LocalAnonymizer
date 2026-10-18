from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable


# One reversible-marker contract shared by every format processor.
# Profile validation permits digits, underscores and hyphens in labels.
LABEL_PATTERN = r"[А-ЯA-ZЁа-яё][А-ЯA-ZЁа-яё0-9_-]{0,63}"
MARKER_PATTERN = rf"\[{LABEL_PATTERN}-\d{{1,9}}\]"
MARKER_RE = re.compile(MARKER_PATTERN)
# Protect marker-shaped literals even when the numeric suffix is deliberately
# too large to be a valid restorable marker. Valid marker parsing remains
# bounded by MARKER_PATTERN, so protection never implies integer conversion.
LITERAL_MARKER_RE = re.compile(rf"\[{LABEL_PATTERN}-\d+\]|\[уязвимость\]")

COMPACT_MARKER_LABELS = {
    "ФИО": "Ф",
    "ОРГАНИЗАЦИЯ": "ОРГ",
    "ПОЧТА": "ПЧ",
    "ТЕЛЕФОН": "ТЕЛ",
    "АККАУНТ": "АКК",
    "ЛОГИН": "ЛОГ",
    "ДОМЕН": "ДОМ",
    "ПОРТ": "ПРТ",
    "УЗЕЛ": "УЗЛ",
    "СТРУКТУРА-AD": "AD",
    "ДИСК": "ДСК",
    "ПУТЬ": "ПУТЬ",
    "ПРОГРАММА": "ПО",
    "СКРИПТЫ": "СКРП",
    "ССЫЛКА": "URL",
    "СИСТЕМА": "СИС",
    "ПРОИЗВОДИТЕЛЬ": "ПРЗ",
    "ДОЛЖНОСТЬ": "ДОЛЖ",
    "ГОРОД": "ГОР",
    "АДРЕС": "АДР",
    "ИНДЕКС": "ИНД",
    "СПЕЦКАТЕГОРИЯ": "СПЕЦ",
    "СКРЫТО": "СКР",
    "ДАТА-РОЖДЕНИЯ": "ДР",
    "ТАБЕЛЬНЫЙ": "ТАБ",
    "ГОСНОМЕР": "ГРЗ",
    "ДОГОВОР": "ДОГ",
    "ДОКУМЕНТ": "ДОК",
    "СУММА": "СУМ",
    "СОКРАЩЕНИЯ": "СОКР",
    "СТАВКА": "СТВ",
}


def normalize_label(label: str) -> str:
    normalized = label.strip().upper()
    if not re.fullmatch(LABEL_PATTERN, normalized):
        raise ValueError("Некорректная метка правила")
    return normalized


def _is_abbreviation_word_char(char: str) -> bool:
    category = unicodedata.category(char)
    return char == "_" or category.startswith(("L", "N"))


def _is_abbreviation_continuation(char: str) -> bool:
    category = unicodedata.category(char)
    return _is_abbreviation_word_char(char) or category.startswith("M") or char in {"\u200c", "\u200d"}


def _iter_abbreviation_tokens(value: str) -> Iterable[tuple[int, int]]:
    index = 0
    while index < len(value):
        if not _is_abbreviation_continuation(value[index]):
            index += 1
            continue
        start = index
        index += 1
        while index < len(value):
            char = value[index]
            if _is_abbreviation_continuation(char):
                index += 1
                continue
            if char == "-" and index + 1 < len(value) and _is_abbreviation_continuation(value[index + 1]):
                index += 1
                continue
            break
        yield start, index


def _is_short_abbreviation(value: str) -> bool:
    normalized = unicodedata.normalize("NFC", value)
    uppercase_letters = 0
    for char in normalized:
        category = unicodedata.category(char)
        if category == "Lu":
            uppercase_letters += 1
        elif category.startswith("M") or char in {"\u200c", "\u200d"}:
            continue
        else:
            return False
    return uppercase_letters == 2


@dataclass(frozen=True)
class Detection:
    start: int
    end: int
    category: str
    priority: int
    value: str
    canonical: str | None = None
    irreversible: bool = False
    fixed: str | None = None
    scope_start: int | None = None
    scope_end: int | None = None
    case_sensitive_canonical: bool = False


@dataclass(frozen=True)
class Hint:
    start: int
    end: int
    value: str
    kind: str


@dataclass
class AnonymizationResult:
    text: str
    mapping: dict[str, str]
    candidates: list[str] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    parts: list[dict] = field(default_factory=list)
    legend: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0
    legend_total: int = 0
    hint_count: int = 0


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def valid_luhn(value: str) -> bool:
    ds = [int(x) for x in _digits(value)]
    if not 13 <= len(ds) <= 19:
        return False
    return sum((n * 2 - 9 if n > 4 else n * 2) if (len(ds) - i) % 2 == 0 else n for i, n in enumerate(ds)) % 10 == 0


def valid_inn(value: str) -> bool:
    d = [int(x) for x in _digits(value)]
    if len(d) == 10:
        return sum(a * b for a, b in zip(d[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8])) % 11 % 10 == d[9]
    if len(d) == 12:
        c1 = sum(a * b for a, b in zip(d[:10], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])) % 11 % 10
        c2 = sum(a * b for a, b in zip(d[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])) % 11 % 10
        return c1 == d[10] and c2 == d[11]
    return False


def valid_ogrn(value: str) -> bool:
    s = _digits(value)
    return (len(s) == 13 and int(s[:-1]) % 11 % 10 == int(s[-1])) or (len(s) == 15 and int(s[:-1]) % 13 % 10 == int(s[-1]))


def valid_snils(value: str) -> bool:
    s = _digits(value)
    if len(s) != 11:
        return False
    if int(s[:9]) <= 1001998:
        return True
    total = sum(int(s[i]) * (9 - i) for i in range(9))
    check = total if total < 100 else (0 if total in (100, 101) else total % 101)
    return (0 if check == 100 else check) == int(s[9:])


NAMES = set("""александр алексей анатолий андрей антон артем артём артур борис вадим валентин валерий василий виктор виталий владимир владислав вячеслав геннадий георгий глеб григорий даниил денис дмитрий евгений егор иван игорь илья кирилл константин леонид максим михаил никита николай олег павел петр пётр роман руслан сергей станислав степан тимофей тимур федор фёдор юрий ярослав анна анастасия алина валентина валерия вера вероника виктория галина дарья екатерина елена ирина ксения любовь людмила маргарита марина мария надежда наталья оксана ольга полина светлана софия татьяна юлия яна""".split())
LAT_NAMES = set("alexander alexey andrey anton artem boris dmitry evgeny ivan igor ilya kirill maxim mikhail nikita nikolay oleg pavel peter petr roman ruslan sergey sergei timur yuri anna anastasia alina daria darya elena irina maria natalia olga polina svetlana tatiana yulia".split())
CITIES = "Москва Санкт-Петербург Новосибирск Екатеринбург Казань Самара Омск Уфа Красноярск Воронеж Пермь Волгоград Астрахань Краснодар Саратов Тюмень Иркутск Хабаровск Ярославль Владивосток Томск Оренбург Кемерово Рязань Тула Сочи Берлин".split()
COMMON_SURNAMES = set("Иванов Смирнов Кузнецов Попов Васильев Петров Соколов Михайлов Новиков Фёдоров Морозов Волков Алексеев Лебедев Семёнов Егоров Павлов Козлов Степанов Николаев Орлов Андреев Макаров Никитин Захаров Зайцев Соловьёв Борисов Романов Кудряшов Медведев Сидоров".lower().replace("ё", "е").split())
STOP_PROPER = set("договор приложение заказчик исполнитель подрядчик система программа продукт документ данные информация доступ проект отдел управление департамент служба компания организация общество банк начальник директор руководитель специалист инженер менеджер".split())

def _stem_surname(value: str) -> str:
    x = value.casefold().replace("ё", "е")
    adjective = re.fullmatch(r"(.+(?:ск|цк))(?:ий|ая|ую|ой|ого|ому|им|ом|ие|их|ими)", x)
    if adjective:
        return adjective.group(1) + "ий"
    nominal = re.fullmatch(r"(.+(?:ов|ев|ин|ын))(?:а|у|ым|ом|е|ой|ою|ы|ами|ах)", x)
    return nominal.group(1) if nominal else x


def _name_stem(value: str) -> str:
    x = value.casefold().replace("ё", "е")
    x = re.sub(r"(?:ием|ьей|ьею|ою|ею|ем|ой|ей|им|ым)$", "", x)
    return re.sub(r"[аеиоуыюяйь]{1,2}$", "", x)


def _canonical_name_component(value: str) -> str:
    x = value.casefold().replace("ё", "е")
    for name in NAMES:
        base = name.replace("ё", "е")
        if base.endswith(("ей", "ий")):
            root = base[:-2]
            forms = {base} | {root + ending for ending in ("ея", "ею", "еем", "ее", "ия", "ию", "ием", "ии")}
        elif base.endswith("й"):
            root = base[:-1]
            forms = {base} | {root + ending for ending in ("я", "ю", "ем", "е")}
        elif base.endswith("а"):
            root = base[:-1]
            forms = {base} | {root + ending for ending in ("ы", "е", "у", "ой", "ою")}
        elif base.endswith("я"):
            root = base[:-1]
            forms = {base} | {root + ending for ending in ("и", "е", "ю", "ей", "ею")}
        else:
            forms = {base} | {base + ending for ending in ("а", "у", "ом", "е")}
        if x in forms:
            return base
    return _name_stem(x)


def _name_like(value: str) -> bool:
    stem = _name_stem(value)
    return any(stem == _name_stem(name) for name in NAMES)


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False) if "/" in value else ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _valid_port(value: str) -> bool:
    return value.isdigit() and 1 <= int(value) <= 65535


def _infrastructure_host(value: str) -> bool:
    host = value.casefold()
    return (
        host == "localhost"
        or bool(re.search(r"[-_\d]", host))
        or bool(re.match(r"(?:srv|host|vm|node|dc|db|app|web|mail|proxy|fw|gw|dns|vpn|nas)", host))
    )


def _strong_infrastructure_host(value: str) -> bool:
    host = value.casefold()
    return (
        host == "localhost"
        or bool(re.match(r"(?:srv|host|vm|node|dc|db|app|web|mail|proxy|fw|gw|dns|vpn|nas)(?:[-_]|\d)", host))
        or (host.count("-") >= 2 and bool(re.search(r"\d", host)))
    )


class Anonymizer:
    """Deterministic, offline detector that resolves every match on source offsets."""

    def __init__(self, *, user_dictionary: dict[str, str] | None = None,
                 whitelist: Iterable[str] | None = None, paranoid: bool = False,
                 disabled_categories: Iterable[str] | None = None,
                 compact_markers: bool = False):
        self.user_dictionary = {
            phrase: normalize_label(label)
            for phrase, label in (user_dictionary or {}).items()
        }
        self.whitelist = {x.casefold() for x in (whitelist or ())}
        self.paranoid = paranoid
        self.disabled_categories = set(disabled_categories or ())
        self.compact_markers = bool(compact_markers)

    @staticmethod
    def _canon(value: str) -> str:
        return value.strip(" «»\"'.,:;()[]`").casefold().replace("ё", "е")

    @staticmethod
    def _org_key(value: str) -> str:
        x = re.sub(r"[«»\"„”()]", "", value).strip().casefold().replace("ё", "е")
        if " " not in x:
            x = re.sub(r"[аяоеиыуюь]$", "", x)
        return x

    def anonymize(self, source: str) -> AnonymizationResult:
        found: list[Detection] = []
        abbreviation_candidates: list[Detection] = []
        aliases: list[tuple[str, str, str]] = []
        exact_aliases: list[tuple[str, str, str, bool]] = []
        disabled_spans: list[tuple[int, int]] = []

        def add(pattern: str, category: str, priority: int, *, flags: int = re.I,
                group: int = 0, validate: Callable[[re.Match], bool] | None = None,
                canonical: Callable[[re.Match], str] | None = None,
                irreversible: bool = False, fixed: str | None = None,
                allow_boundary_context: bool = False,
                case_sensitive_canonical: bool = False) -> list[re.Match]:
            matches = list(re.finditer(pattern, source, flags))
            if category in self.disabled_categories and category != "SECRET":
                for m in matches:
                    value = m.group(group)
                    if value.casefold() in self.whitelist or (validate and not validate(m)):
                        continue
                    disabled_spans.append(m.span(group))
                return matches
            for m in matches:
                value = m.group(group)
                if (category != "SECRET" and value.casefold() in self.whitelist) or (validate and not validate(m)):
                    continue
                found.append(Detection(
                    *m.span(group), category, priority, value,
                    canonical(m) if canonical else None, irreversible, fixed,
                    *(m.span(group) if allow_boundary_context else m.span()),
                    case_sensitive_canonical=case_sensitive_canonical,
                ))
            return matches

        def remember_exact(matches: Iterable[re.Match], category: str, *, group: int = 1,
                           minimum_length: int = 2, case_sensitive: bool = True) -> None:
            if category in self.disabled_categories:
                return
            for match in matches:
                raw = match.group(group)
                if len(raw) >= minimum_length:
                    exact_aliases.append((
                        raw,
                        raw if case_sensitive else self._canon(raw),
                        category,
                        case_sensitive,
                    ))

        literal_markers = list(LITERAL_MARKER_RE.finditer(source))
        protected = [m.span() for m in literal_markers]
        for m in re.finditer(r"(?i)\b(?:верси[яи]|version|build|сборк[а-яё]*)\s+(?:платформы\s+)?(\d+(?:\.\d+){1,4})", source):
            protected.append(m.span(1))

        # Secrets are irreversible and intentionally absent from mapping/legend.
        add(r"-----BEGIN [A-Z ]{1,48}-----.*?-----END [A-Z ]{1,48}-----", "SECRET", 110,
            flags=re.I | re.S, irreversible=True, fixed="(удалено: ключ/сертификат)")
        secret_word = r"(?:парол(?:ь|я|ю|ем|и)|password|passwd|pwd|passphrase|секрет(?:ная фраза)?|secret|token|токен|api[ _-]?key|apikey|access[ _-]?key|private[ _-]?key|client[ _-]?secret|ключ доступа)"
        quoted_or_token = r'(?:"[^"\r\n\ufdd0]+"|\'[^\'\r\n\ufdd0]+\'|«[^»\r\n\ufdd0]+»|[^\s,;"\'«»\ufdd0]+)'
        add(rf"\b{secret_word}\s*[:=—-]\s*({quoted_or_token})", "SECRET", 109, group=1, irreversible=True, fixed="(удалено)")
        add(rf"\b[A-Za-z_][A-Za-z0-9_]*(?:PASS|PASSWD|PASSWORD|PWD|PSWD|PSW|SECRET|TOKEN|APIKEY|API_KEY|ACCESSKEY|ACCESS_KEY|PRIVATE_KEY|CRED|CREDS|AUTH)[A-Za-z0-9_]*\s*[:=]\s*({quoted_or_token})", "SECRET", 109, group=1,
            validate=lambda m: not (re.search(r"TOKENS\s*[:=]", m.group(0), re.I) and m.group(1).rstrip(";,)").isdigit()), irreversible=True, fixed="(удалено)")
        add(r"\b(?:парол[а-яё]*|password|пасс[а-яё]*|pwd|секретн[а-яё]+\s+фраз[а-яё]+|кодов[а-яё]+\s+слов[а-яё]*)\s+(?:(?:от|для|к|на)\s+)?(?:[а-яё]+\s+){0,3}((?=[^\s]*[\d!@#$%^&*_+])[A-Za-zА-Яа-яЁё0-9!@#$%^&*_+.\-]{4,})", "SECRET", 108, group=1, irreversible=True, fixed="(удалено)")
        add(r"(?<![\w./@-])[a-z][a-z0-9_-]{2,20}:[A-Za-z0-9!@#$%^&*_+.\-]{4,40}(?![\w/@])", "SECRET", 107,
            validate=lambda m: bool(
                re.search(r"[A-Za-z]", m.group())
                and re.search(r"\d|[!@#$%^&*_+]|(?=.*[a-z])(?=.*[A-Z])", m.group().split(":", 1)[1])
                and not (
                    _strong_infrastructure_host(m.group().split(":", 1)[0])
                    and _valid_port(m.group().split(":", 1)[1])
                )
            ), irreversible=True, fixed="(удалено: учётные данные)")
        add(r"\b(?:Bearer|Basic)\s+([A-Za-z0-9+/=_.~-]{8,})", "SECRET", 106, group=1,
            validate=lambda m: bool(re.search(r"[\d=.]", m.group(1)) or (len(m.group(1)) >= 12 and re.search(r"[a-z]", m.group(1)) and re.search(r"[A-Z]", m.group(1)))), irreversible=True, fixed="(удалено)")
        add(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]{4,})?", "SECRET", 106, irreversible=True, fixed="(удалено: токен)")
        add(r"\b(?:ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{15,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|rk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ya29\.[A-Za-z0-9_-]{20,})\b", "SECRET", 106, irreversible=True, fixed="(удалено: токен)")
        add(r"(?<![\wА-Яа-яЁё@#.-])(?:qwerty|password|passw0rd|passwd|admin|root|toor|asdf|zxcv|letmein|welcome|monkey|dragon|master|secret|секрет|парол[ья])[A-Za-z0-9!@#$%^&*_+.-]*", "SECRET", 105,
            validate=lambda m: len(m.group()) >= 6 and bool(re.search(r"\d", m.group())), irreversible=True, fixed="(удалено: похоже на пароль)")
        add(r"\b[0-9a-fA-F]{32,64}\b", "SECRET", 102,
            validate=lambda m: bool(re.search(r"[a-fA-F]", m.group()) and re.search(r"\d", m.group()) and not re.search(r"(?:commit|sha|hash|хеш|хэш|md5|checksum)\s*[:=]?\s*$", source[max(0, m.start()-25):m.start()], re.I)), irreversible=True, fixed="(удалено: похоже на ключ)")
        add(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])", "SECRET", 101,
            validate=lambda m: bool(re.search(r"[a-z]", m.group()) and re.search(r"[A-Z]", m.group()) and re.search(r"\d", m.group())), irreversible=True, fixed="(удалено: похоже на ключ)")

        # Strong validated requisites.
        add(r"\bИНН(?:/КПП)?\s*(\d(?:\s?\d){9,11})\b", "ИНН", 95, group=1,
            validate=lambda m: valid_inn(m.group(1)), canonical=lambda m: _digits(m.group(1)))
        add(r"\bОГРН(?:ИП)?\s*(\d{13}|\d{15})\b", "ОГРН", 95, group=1, validate=lambda m: valid_ogrn(m.group(1)))
        add(r"\bСНИЛС\s*(\d{3}[- ]?\d{3}[- ]?\d{3}[ -]?\d{2}|\d{11})", "СНИЛС", 95, group=1,
            validate=lambda m: valid_snils(m.group(1)), canonical=lambda m: _digits(m.group(1)))
        add(r"\b(?:IMEI|идентификатор\s+устройства)\s*(?:№|N|1|2)?\s*[:=]?\s*(\d(?:[ -]?\d){14})\b", "IMEI", 95, group=1,
            validate=lambda m: valid_luhn(m.group(1)), canonical=lambda m: _digits(m.group(1)))
        add(r"\b(?:карта|card)\s*(\d(?:[ -]?\d){12,18})", "КАРТА", 95, group=1,
            validate=lambda m: valid_luhn(m.group(1)), canonical=lambda m: _digits(m.group(1)))
        add(r"(?:\bКПП\s*|(?<=/))(\d{9})\b", "КПП", 94, group=1)
        add(r"\b(?:сч[её]т|р/с)\s*(\d{20})\b", "СЧЁТ", 94, group=1)
        add(r"\bБИК\s*[:№]?\s*(04\d{7})\b", "БИК", 94, group=1)
        add(r"\b(?:паспорт|серия)\D{0,15}(\d{2}\s?\d{2}\s?\d{6})\b", "ПАСПОРТ", 94, group=1, canonical=lambda m: _digits(m.group(1)))
        add(r"\b(?:VIN|кузов|шасси)\s*[:№]?\s*([A-HJ-NPR-Z0-9]{17})\b", "VIN", 94, group=1,
            validate=lambda m: bool(re.search(r"\d", m.group(1)) and re.search(r"[A-Z]", m.group(1))))
        add(r"\bкадастров(?:ый|ого)\s+(?:номер[а]?\s*)?(\d{2}:\d{1,2}:\d{6,7}:\d{1,5})", "КАДАСТР", 93, group=1)
        add(r"\b(?:машина|госномер)\s*([АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\s?\d{2,3})\b", "ГОСНОМЕР", 93, group=1)
        add(r"\bтабельн[а-яё]*\s*(?:номер|№)?\s*[:—-]?\s*(\d{3,10})\b", "ТАБЕЛЬНЫЙ", 93, group=1)
        add(r"\b(?:договор|контракт|соглашени[а-яё]*|спецификаци[а-яё]*|заказ|сч[её]т)[а-яё]*\s+№\s*([\w/.-]{2,30})", "ДОГОВОР", 92, group=1)
        add(r"\b(?:приказ|распоряжени[а-яё]*|протокол|письм[ао]|служебн[а-яё]*\s+запис[а-яё]*|исх|вх)[а-яё.]*\s*№\s*([\w/.-]{2,25})", "ДОКУМЕНТ", 92, group=1)
        add(r"\b(?:дата\s+рождения|д\.\s?р\.|родил(?:ся|ась))\D{0,12}(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", "ДАТА-РОЖДЕНИЯ", 92, group=1)

        # Postal addresses need an explicit address/street anchor.  This keeps
        # ordinary five- and six-digit task/build numbers out of the detector.
        street_type = r"(?i:ул(?:ица)?\.?|просп(?:ект|\.)|пр-т|пр\.?|шоссе|пер(?:еулок)?\.?|наб(?:ережная)?\.?|б-р|бульвар|проезд|аллея|алл\.)"
        named_street = r"[А-ЯЁ][А-Яа-яЁё0-9'’.-]*(?:[ \t]+[А-ЯЁа-яё0-9'’.-]+){0,3}"
        numeric_street = r"\d+(?:-?(?:го|я|й|е|ый))?(?:[ \t]+лет)?[ \t]+[А-ЯЁа-яё][А-Яа-яЁё'’.-]*(?:[ \t]+[А-ЯЁа-яё'’.-]+){0,2}"
        street_name = rf"(?:{numeric_street}|{named_street})"
        house_designator = r"(?i:д(?:ом)?|зд(?:ание)?|вл(?:адение)?|стр(?:оение)?|корп(?:ус)?)"
        house = rf"(?:{house_designator}\.?[ \t]*(?:№[ \t]*)?)?\d+[ \t]*[А-ЯЁа-яё]?(?:[/-](?:\d+[А-ЯЁа-яё]?|[А-ЯЁа-яё]))?"
        city_name = r"[А-ЯЁ][А-Яа-яЁё-]*(?:[ \t]+[А-ЯЁа-яЁё-]+){0,2}"
        title_place = r"[А-ЯЁ][А-Яа-яЁё-]*(?:[ \t]+[А-ЯЁ][А-Яа-яЁё-]+){0,2}"
        region_suffix = r"(?i:автономная[ \t]+область|автономный[ \t]+округ|область|обл\.?|край|республика)"
        republic_prefix = rf"(?i:республик[а-яё]*)[ \t]+{title_place}(?:[ \t]*\({title_place}\))?"
        suffix_region = rf"{title_place}[ \t]+{region_suffix}(?:[ \t]*[—-][ \t]*{title_place})?"
        administrative_area = rf"(?:{republic_prefix}|{suffix_region})"
        city = rf"(?:г\.?[ \t]*)?{city_name}"
        explicit_city = rf"г(?:ород)?\.?[ \t]*{city_name}"
        street_house_separator = r"(?:[ \t]*,[ \t]*|[ \t]+)"
        address_value = rf"{street_name}[ \t]+{street_type}[ \t]*,[ \t]*{house}(?:[ \t]*,[ \t]*{city})?"
        extended_street_name = (
            rf"(?:{numeric_street}|(?:(?i:имени|им\.)[ \t]+)?"
            rf"[А-ЯЁ][А-Яа-яЁё0-9'’.-]*(?:[ \t]+[А-ЯЁа-яё0-9'’.-]+){{0,5}})"
        )
        district_component = rf"{title_place}[ \t]+(?i:район|р-н\.?)"
        geography_component = rf"(?:{administrative_area}|{explicit_city}|{district_component}|{title_place})"
        geography_prefix = rf"(?:\d{{5,6}}[ \t]*,[ \t]*)?(?:{geography_component}[ \t]*,[ \t]*){{0,4}}"
        complete_postal_address = (
            rf"{geography_prefix}{street_type}[ \t]+{extended_street_name}"
            rf"{street_house_separator}{house}"
            rf"(?:[ \t]*,[ \t]*{explicit_city})?"
            rf"(?:[ \t]*,[ \t]*\d{{5,6}})?"
        )

        # Parse complete postal spans from typed components instead of consuming
        # an entire line or table cell. This keeps surrounding prose visible while
        # supporting reordered geography and repeatable building qualifiers.
        address_hws = r"[ \t\u00a0]"
        address_comma = rf"{address_hws}*,{address_hws}*"
        address_join = rf"(?:{address_comma}|{address_hws}+)"
        strong_street_type = (
            r"(?i:ул(?:ица)?\.?|просп(?:ект|\.)|пр-т|шоссе|"
            r"пер(?:еулок)?\.?|наб(?:ережная)?\.?|б-р|бульвар|проезд|"
            r"аллея|алл\.)"
        )
        ambiguous_street_type = r"(?i:пр\.?)"
        bounded_street_type = rf"(?:{strong_street_type}|{ambiguous_street_type})"
        bounded_street_word = r"[А-ЯЁа-яё0-9][А-Яа-яЁё0-9'’.-]*"
        bounded_street_name = (
            rf"(?:{numeric_street}|(?:(?i:имени|им\.){address_hws}+)?"
            rf"{bounded_street_word}(?:{address_hws}+{bounded_street_word}){{0,5}})"
        )
        strict_street_name = (
            rf"(?:{numeric_street}|[А-ЯЁ][А-Яа-яЁё0-9'’.-]*"
            rf"(?:{address_hws}+[А-ЯЁ][А-Яа-яЁё0-9'’.-]*){{0,3}})"
        )
        type_name_join = rf"(?:{address_hws}+|(?<=\.))"
        bounded_street_core = (
            rf"(?:{bounded_street_type}{type_name_join}{bounded_street_name}|"
            rf"{strict_street_name}{address_hws}+{bounded_street_type})"
        )
        strict_street_core = (
            rf"(?:{strong_street_type}{type_name_join}{strict_street_name}|"
            rf"{strict_street_name}{address_hws}+{strong_street_type})"
        )
        house_no = (
            rf"\d{{1,5}}"
            rf"(?:{address_hws}*[А-ЯЁа-яё](?![А-ЯЁа-яё]))?"
            rf"(?:[/-](?:\d{{1,5}}[А-ЯЁа-яё]?|[А-ЯЁа-яё]))?"
        )
        primary_house_designator = r"(?i:д(?:ом)?|зд(?:ание)?|вл(?:адение)?)"
        labelled_house = (
            rf"{primary_house_designator}\.?{address_hws}*"
            rf"(?:№{address_hws}*)?{house_no}"
        )
        street_house = (
            rf"(?:{bounded_street_core}{address_join}{labelled_house}|"
            rf"{strict_street_core}{address_comma}{house_no}|"
            rf"{strict_street_core}{address_hws}+{house_no})"
        )
        building_designator = (
            r"(?i:корп(?:ус)?|к|стр(?:оение)?|лит(?:ера)?|"
            r"пом(?:ещение)?|оф(?:ис)?|уч(?:асток)?|кв(?:артира)?)"
        )
        building_value = (
            rf"(?:№{address_hws}*)?(?:\d{{1,5}}(?:[/-]\d{{1,5}})?"
            rf"[А-ЯЁа-яё]?|[А-ЯЁа-яё])"
        )
        building_part = (
            rf"{building_designator}\.?{address_hws}*"
            rf"(?:,{address_hws}*)?{building_value}"
        )
        building_tail_separator = rf"(?:{address_comma}|{address_hws}+)"
        building_tail = rf"(?:{building_tail_separator}{building_part}){{0,8}}"

        bounded_title_place = (
            rf"[А-ЯЁ][А-Яа-яЁё-]*(?:{address_hws}+[А-ЯЁ][А-Яа-яЁё-]+){{0,2}}"
        )
        bounded_city_name = (
            rf"[А-ЯЁ][А-Яа-яЁё-]*(?:{address_hws}+[А-ЯЁа-яЁё-]+){{0,2}}"
        )
        bounded_explicit_city = (
            rf"г(?:ород)?\.?{address_hws}*{bounded_city_name}"
        )
        bounded_region_suffix = (
            rf"(?i:автономная{address_hws}+область|"
            rf"автономный{address_hws}+округ|область|обл\.?|край|республика)"
        )
        bounded_republic_prefix = (
            rf"(?i:республик[а-яё]*){address_hws}+{bounded_title_place}"
            rf"(?:{address_hws}*\({bounded_title_place}\))?"
        )
        bounded_suffix_region = (
            rf"{bounded_title_place}{address_hws}+{bounded_region_suffix}"
            rf"(?:{address_hws}*[—-]{address_hws}*{bounded_title_place})?"
        )
        bounded_region = rf"(?:{bounded_republic_prefix}|{bounded_suffix_region})"
        bounded_district = (
            rf"{bounded_title_place}{address_hws}+(?i:район|р-н\.?)"
        )
        bounded_country = r"(?i:Россия|Российская Федерация|РФ)"
        bounded_region_city = (
            rf"{bounded_region}(?:{address_comma}|{address_hws}+)"
            rf"{bounded_explicit_city}"
        )
        bounded_geo_unit = (
            rf"(?:{bounded_region_city}|{bounded_region}|"
            rf"{bounded_explicit_city}|{bounded_district})"
        )
        bounded_country_or_typed_title = (
            rf"(?:{bounded_country}|{bounded_title_place}"
            rf"(?={address_comma}{bounded_region}{address_comma}))"
        )
        leading_geography = (
            rf"(?:\d{{5,6}}{address_comma})?"
            rf"(?:{bounded_country_or_typed_title}{address_comma})?"
            rf"(?:{bounded_geo_unit}{address_comma}){{0,6}}"
        )
        leading_address = rf"{leading_geography}{street_house}{building_tail}"
        trailing_address = (
            rf"{street_house}{building_tail}"
            rf"(?:{address_join}{bounded_explicit_city})?"
            rf"(?:{address_comma}{bounded_region}){{0,2}}"
            rf"(?:{address_comma}{bounded_country})?"
            rf"(?:{address_comma}\d{{5,6}})?"
        )
        bounded_full_address = rf"(?:{trailing_address}|{leading_address})"
        ambiguous_street_token = re.compile(
            r"(?i)(?<![А-Яа-яЁё])пр\.(?![А-Яа-яЁё])"
        )
        typed_geography_evidence = re.compile(
            rf"(?:\d{{5,6}}|{bounded_country}|{bounded_region}|{bounded_explicit_city})"
        )
        labelled_house_evidence = re.compile(
            rf"(?<![А-Яа-яЁё]){primary_house_designator}\.?{address_hws}*"
            rf"(?:№{address_hws}*)?\d"
        )
        secondary_building_evidence = re.compile(
            rf"(?<![А-Яа-яЁё]){building_designator}\.?{address_hws}*"
            rf"(?:№{address_hws}*)?(?:\d|[А-ЯЁа-яё](?![А-ЯЁа-яё]))"
        )

        def is_bounded_address(match: re.Match) -> bool:
            value = match.group(1)
            if not ambiguous_street_token.search(value):
                return True
            if typed_geography_evidence.search(value):
                return True
            if (
                labelled_house_evidence.search(value)
                and secondary_building_evidence.search(value)
            ):
                return True
            prefix = source[max(0, match.start(1) - 500):match.start(1)]
            if re.search(r"(?i)\bадрес(?:у|а|е)?\s*[:—-]?\s*$", prefix):
                return True
            list_context = re.search(
                r"(?i)\b(?:по\s+)?адресам\s*[:—-]?"
                r"[^\r\n\ufdd0\ufdd3;!?…]{0,450}$",
                prefix,
            )
            if list_context is None:
                return False
            return re.search(
                rf"\d{{1,5}}(?:[А-ЯЁа-яё]|[/-](?:\d{{1,5}}[А-ЯЁа-яё]?|[А-ЯЁа-яё]))?"
                rf"\.(?={address_hws}+[А-ЯЁ0-9])",
                list_context.group() + value[:1],
            ) is None

        add(
            rf"(?<![А-Яа-яЁё0-9])({bounded_full_address})(?![А-Яа-яЁё0-9])",
            "АДРЕС", 99, group=1, flags=0,
            validate=is_bounded_address,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
        )
        labelled_bounded_address = (
            rf"{street_house}{building_tail}"
            rf"(?:{address_comma}{city_name})?"
        )
        add(
            rf"\b(?:по{address_hws}+)?адрес(?:у|а|е)?{address_hws}*"
            rf"[:—-]?{address_hws}*({labelled_bounded_address})",
            "АДРЕС", 100, group=1, flags=0,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
        )
        contextual_untyped_address = (
            rf"{strict_street_name}{address_comma}{labelled_house}{building_tail}"
        )
        add(
            rf"\b(?:по{address_hws}+)?адрес(?:у|а|е)?{address_hws}*"
            rf"[:—-]?{address_hws}*({contextual_untyped_address})",
            "АДРЕС", 100, group=1, flags=0,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
        )

        # A postal address in a dedicated DOCX table cell is one record even
        # when its components are reordered or contain uncommon building
        # qualifiers. This fallback never applies to ordinary text lines.
        record_street_start = re.compile(
            rf"(?<![А-Яа-яЁё]){street_type}(?:{address_hws}+|(?<=\.))"
            rf"(?:(?i:имени|им\.){address_hws}+)?"
            rf"(?:\d+|[А-ЯЁа-яё](?:\.|[А-Яа-яЁё0-9'’.-]*))",
        )
        record_street_end = re.compile(
            rf"(?:\d+|[А-ЯЁ][А-Яа-яЁё0-9'’.-]*)"
            rf"(?:[ \t]+[А-ЯЁа-яё0-9'’.-]+){{0,2}}[ \t]+{street_type}"
            rf"(?![А-Яа-яЁё])",
        )
        record_house = re.compile(
            r"(?i)(?:^|[ \t,])(?:д(?:ом)?|зд(?:ание)?|вл(?:адение)?|"
            r"стр(?:оение)?|корп(?:ус)?|лит(?:ера)?|пом(?:ещение)?|"
            r"оф(?:ис)?|уч(?:асток)?|кв(?:артира)?)\.?[ \t]*(?:№[ \t]*)?"
            r"\d+[ \t]*[А-ЯЁа-яё]?(?:[/-]\d+[А-ЯЁа-яё]?)?",
        )
        record_unlabelled_house = re.compile(
            r"(?:^|[ \t,])\d{1,5}[ \t]*[А-ЯЁа-яё]?(?:[/-]\d+[А-ЯЁа-яё]?)?"
            r"(?=$|[ \t,])",
        )
        record_allowed = re.compile(
            r"[-–—А-Яа-яЁёA-Za-z0-9_\s.,№'’\"«»()/\\]+",
        )
        record_context_words = {
            "г", "город", "россия", "рф", "республика", "республики",
            "область", "обл", "край", "автономная", "автономный", "округ",
            "район", "р", "н", "д", "дом", "зд", "здание", "вл",
            "владение", "стр", "строение", "корп", "корпус", "к", "лит",
            "литера", "пом", "помещение", "оф", "офис", "уч", "участок",
            "кв", "квартира", "п", "пос", "поселок", "посёлок", "с", "село",
            "дер", "деревня", "мкр", "микрорайон", "тер", "территория",
        }

        def is_address_only_context(value: str) -> bool:
            if re.search(r"[:;!?]", value):
                return False
            for match in re.finditer(r"[А-Яа-яЁё]+", value):
                word = match.group()
                numeric_qualifier = re.match(
                    r"\.?[ \t]*(?:№[ \t]*)?\d",
                    value[match.end():],
                )
                if (
                    len(word) > 1
                    and word[0].islower()
                    and word.casefold() not in record_context_words
                    and numeric_qualifier is None
                ):
                    return False
            return True

        def is_complete_address_record(match: re.Match) -> bool:
            value = re.sub(r"\s+", " ", match.group(1).replace("\ufdd3", " ")).strip()
            if not 6 <= len(value) <= 400 or not record_allowed.fullmatch(value):
                return False
            if (
                ambiguous_street_token.search(value)
                and not typed_geography_evidence.search(value)
            ):
                return False
            anchor = record_street_start.search(value) or record_street_end.search(value)
            if anchor is None or not is_address_only_context(value[:anchor.start()]):
                return False
            tail = value[anchor.end():]
            house_match = record_house.search(tail) or record_unlabelled_house.search(tail)
            if house_match is None:
                return False
            return is_address_only_context(tail[house_match.end():])

        add(
            r"(?<=\ufdd0)([^\r\n\ufdd0\ufdd3]{5,400})(?=\ufdd0)",
            "АДРЕС", 101, group=1, flags=0,
            validate=is_complete_address_record,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
            allow_boundary_context=True,
        )

        add(
            rf"\b(?:по[ \t]+)?адрес(?:у|а|е)?[ \t]*[:—-]?[ \t]*({address_value})",
            "АДРЕС", 96, group=1,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
        )
        add(
            rf"\b(?:по[ \t]+)?адрес(?:у|а|е)?[ \t]*[:—-]?[ \t]*{address_value}[ \t]*,[ \t]*(\d{{5,6}})(?!\d)",
            "ИНДЕКС", 97, group=1,
        )
        add(
            r"\b(?:почтов(?:ый|ого)[ \t]+)?индекс[ \t]*[:№—-]?[ \t]*(\d{5,6})(?!\d)",
            "ИНДЕКС", 95, group=1,
        )
        # Region, district and service-centre cells are ambiguous by themselves.
        # Redact them only as one contiguous inventory row ending in a validated
        # postal address; this preserves ordinary cells such as "Рабочая область".
        federal_district = (
            r"(?:(?:Центральный|Северо-Западный|Южный|Северо-Кавказский|"
            r"Приволжский|Уральский|Сибирский|Дальневосточный)"
            r"(?:[ \t]+федеральный[ \t]+округ)?|[А-ЯЁ]{2,5})"
        )
        cell_separator = r"[ \t]*\ufdd0[ \t]*"
        inventory_row = (
            rf"(?:(?<=\ufdd0)|^)({administrative_area}){cell_separator}"
            rf"({federal_district}){cell_separator}(?:КЦ[ \t]+)?({title_place})"
            rf"{cell_separator}({complete_postal_address})(?=$|\ufdd0)"
        )
        add(
            inventory_row, "ГОРОД", 64, group=1, flags=0,
            canonical=lambda m: "region:" + self._canon(m.group(1)),
            allow_boundary_context=True,
        )
        add(
            inventory_row, "ГОРОД", 64, group=2, flags=0,
            canonical=lambda m: "district:" + self._canon(m.group(2)),
            allow_boundary_context=True,
        )
        add(
            inventory_row, "ГОРОД", 64, group=3, flags=0,
            canonical=lambda m: self._canon(m.group(3)),
            allow_boundary_context=True,
        )

        english_street = (
            r"\d+[A-Za-z]?(?:[ \t]+[A-Z][A-Za-z'’.-]*){1,5}[ \t]+"
            r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Way)"
            r"(?:[ \t]+(?:N|S|E|W|NE|NW|SE|SW))?"
        )
        english_city = r"[A-Z][A-Za-z'’.-]*(?:[ \t]+[A-Z][A-Za-z'’.-]*){0,3}"
        english_region = r"[A-Z]{2}"
        english_postal = r"\d{5,6}(?:-\d{4})?"
        english_postal_separator = r"(?:[ \t]*,[ \t]*|[ \t]+)"
        english_address = rf"{english_street}[ \t]*,[ \t]*{english_city}(?:[ \t]*,[ \t]*{english_region})?"
        english_label_separator = r"[ \t]*:[ \t\ufdd3]*"
        add(
            rf"\bAddress{english_label_separator}({english_address})(?=(?:{english_postal_separator}{english_postal})?(?:$|[\r\n\ufdd0\ufdd3]))",
            "АДРЕС", 96, group=1, flags=re.I,
            canonical=lambda m: re.sub(r"\s+", " ", m.group(1).casefold()),
            allow_boundary_context=True,
        )
        add(
            rf"\bAddress{english_label_separator}{english_address}{english_postal_separator}({english_postal})(?=$|[\r\n\ufdd0\ufdd3])",
            "ИНДЕКС", 97, group=1, flags=re.I,
            allow_boundary_context=True,
        )

        # Network and contacts.
        url_matches = add(r"(?:@url:\s*)?`?(?:https?|ftp|sftp|ssh|rdp|smb|ldaps?)://[^\s`<>\"'«»()\ufdd0]+`?", "ССЫЛКА", 90)
        add(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "ПОЧТА", 89, canonical=lambda m: m.group().casefold())
        add(r"[a-z0-9._-]{2,}\s*(?:[([]\s*(?:at|собака|эт)\s*[)\]]|\s(?:at|собака)\s)\s*[a-z0-9а-яё._-]{2,}(?:\s*(?:\.|точка|dot)\s*[a-zа-яё]{2,})+", "ПОЧТА", 88, canonical=lambda m: re.sub(r"\s+", "", m.group().casefold()))
        add(r"(?<![\w:])(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}(?![\w:])", "MAC", 89,
            canonical=lambda m: m.group().casefold().replace("-", ":"))
        add(r"(?<![\w.])(?:[0-9A-F]{4}\.){2}[0-9A-F]{4}(?![\w.])", "MAC", 89,
            canonical=lambda m: ":".join(re.findall(r"[0-9a-f]{2}", m.group().casefold())))
        # A sentence-final dot is punctuation, not part of the IPv4 address.
        add(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?!\w|\.\d)", "IP", 88,
            validate=lambda m: _valid_ip(m.group()) and not any(m.start() >= a and m.end() <= b for a, b in protected), canonical=lambda m: m.group().casefold())
        add(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:/\d{1,3})?(?![\w:])", "IP", 88,
            validate=lambda m: _valid_ip(m.group()), canonical=lambda m: m.group().casefold())
        phone_pat = r"(?<![\d\w+])(?:\+\d{1,3}|8)(?:[\s()-]*\d){7,14}(?!\d)"
        add(phone_pat, "ТЕЛЕФОН", 87, validate=lambda m: 8 <= len(_digits(m.group())) <= 15,
            canonical=lambda m: ("7" + _digits(m.group())[1:]) if len(_digits(m.group())) == 11 and _digits(m.group())[0] in "78" else _digits(m.group()))
        domain_pattern = r"(?:[A-Za-zА-Яа-яЁё0-9](?:[A-Za-zА-Яа-яЁё0-9-]{0,61}[A-Za-zА-Яа-яЁё0-9])?\.){1,6}(?:[A-Za-zА-Яа-яЁёрф]{2,}|local)"

        # Port numbers are sensitive only in explicit network contexts. Keep
        # bare numerics, times, versions and invalid IANA-range values intact.
        # URLs remain one complete marker; IP/domain/host and port digits can be
        # independently restored.
        def port_outside_url(match: re.Match, group: int) -> bool:
            start, end = match.span(group)
            return not any(start >= url.start() and end <= url.end() for url in url_matches)

        port_label = r"(?:порт(?:а|у|ом|е|ы|ов)?|ports?)"
        port_gap = r"[ \t\r\n\ufdd0\ufdd3]{0,12}"
        add(
            rf"(?<![\w-])(?:(?:tcp|udp)[ \t]*[-/][ \t]*)?{port_label}"
            rf"{port_gap}(?:№|no\.?|number)?{port_gap}[:=]?{port_gap}(\d{{1,5}})(?!\d)",
            "ПОРТ", 89, group=1,
            validate=lambda m: _valid_port(m.group(1)) and port_outside_url(m, 1),
            canonical=lambda m: m.group(1),
            allow_boundary_context=True,
        )
        add(
            rf"(?<![\w-]){port_label}{port_gap}(?:№|no\.?|number)?{port_gap}[:=]?{port_gap}"
            rf"(\d{{1,5}}){port_gap}[-–—]{port_gap}(\d{{1,5}})(?!\d)",
            "ПОРТ", 89, group=2,
            validate=lambda m: (
                _valid_port(m.group(1))
                and _valid_port(m.group(2))
                and int(m.group(1)) <= int(m.group(2))
                and port_outside_url(m, 2)
            ),
            canonical=lambda m: m.group(2),
            allow_boundary_context=True,
        )
        add(
            r"(?<!\d)(\d{1,5})[ \t]*/[ \t]*(?:tcp|udp)\b",
            "ПОРТ", 89, group=1,
            validate=lambda m: _valid_port(m.group(1)) and port_outside_url(m, 1),
            canonical=lambda m: m.group(1),
        )
        add(
            r"\b(?:tcp|udp)[ \t]*(?:[/=:]|[ \t])[ \t]*(\d{1,5})(?!\d)",
            "ПОРТ", 89, group=1,
            validate=lambda m: _valid_port(m.group(1)) and port_outside_url(m, 1),
            canonical=lambda m: m.group(1),
        )
        add(
            r"(?<![\w.])((?:\d{1,3}\.){3}\d{1,3}):(\d{1,5})(?!\d)",
            "ПОРТ", 89, group=2,
            validate=lambda m: (
                _valid_ip(m.group(1))
                and _valid_port(m.group(2))
                and port_outside_url(m, 2)
            ),
            canonical=lambda m: m.group(2),
        )
        add(
            r"\[([0-9a-f:]+)\]:(\d{1,5})(?!\d)",
            "ПОРТ", 89, group=2,
            validate=lambda m: (
                _valid_ip(m.group(1))
                and _valid_port(m.group(2))
                and port_outside_url(m, 2)
            ),
            canonical=lambda m: m.group(2),
        )
        add(
            rf"(?<![\w.-])({domain_pattern}):(\d{{1,5}})(?!\d)",
            "ПОРТ", 89, group=2,
            validate=lambda m: _valid_port(m.group(2)) and port_outside_url(m, 2),
            canonical=lambda m: m.group(2),
        )

        def infrastructure_endpoint(match: re.Match) -> bool:
            return (
                _valid_port(match.group(2))
                and _infrastructure_host(match.group(1))
                and port_outside_url(match, 2)
            )

        add(
            r"(?<![\w.-])([A-Za-z][A-Za-z0-9_-]{2,63}):(\d{1,5})(?!\d)",
            "ПОРТ", 89, group=2,
            validate=infrastructure_endpoint,
            canonical=lambda m: m.group(2),
        )
        # Word TOCs can concatenate a domain and its page number (example.test11).
        # Match the complete domain before the digits so a shorter prefix such as
        # "go.example" cannot win and leak the registered-domain suffix.
        add(rf"(?<![\wА-Яа-яЁё@.:/-])({domain_pattern})(?=\d+(?![\w-]))", "ДОМЕН", 90,
            group=1, validate=lambda m: m.group(1).casefold() not in self.whitelist,
            canonical=lambda m: m.group(1).casefold())
        add(rf"(?<![\wА-Яа-яЁё@.:/-]){domain_pattern}(?![\w-])", "ДОМЕН", 89,
            validate=lambda m: m.group().casefold() not in self.whitelist, canonical=lambda m: m.group().casefold())
        # DNS service/subtree owners (for example an underscored locator FQDN)
        # identify infrastructure nodes.  Keep this below URL, email and path
        # priorities, and reject embedded account/path/dotted-identifier spans.
        underscored_dns_fqdn = (
            r"(?:_[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"[A-Za-z]{2,63}"
        )
        add(
            rf"(?<![\w@/\\.-]){underscored_dns_fqdn}(?![\w-])",
            "УЗЕЛ", 88,
            canonical=lambda m: m.group().casefold(),
        )
        add(r"(?<![\w.@:-])(?:srv|host|vm|node|dc|db|app|web|mail|proxy|fw|gw|kvm|esx|hv|pc|dns|vpn|nas|k8s|adc)[a-z0-9]*(?:[-_][a-z0-9]+)+(?![\w-])", "УЗЕЛ", 81,
            validate=lambda m: bool(re.search(r"\d", m.group())), canonical=lambda m: m.group().casefold())
        # Inventory names often begin with a site code and carry the server
        # role in a later segment (for example site-dns-0001).
        add(r"(?<![\w.@:-])[a-z0-9]{2,15}[-_](?:dc|dcv|dns|dhcp|fs|web|rdp|app|db|dbv|hv|pk|nb|mon|bak|print|scud|studio|mfu)[-_]\d{1,8}(?![\w-])", "УЗЕЛ", 83,
            canonical=lambda m: m.group().casefold())
        # VM inventories also use a site prefix plus a compact role-and-number
        # suffix, without a delimiter before the numeric instance identifier.
        add(r"(?<![\w.@:-])[a-z0-9]{2,15}[-_](?:monitor|repo|print|fs|journal)\d{1,8}(?![\w-])", "УЗЕЛ", 83,
            canonical=lambda m: m.group(), case_sensitive_canonical=True)
        # Physical/virtual server inventories use an S/V prefix, a four-digit
        # site code, and a compact alphabetic role plus a two-digit instance.
        add(r"(?<![\w.@:-])(?a:[sv]\d{4}-[a-z]{2,4}\d{2}(?:-\d{1,2})?)(?![\w-])", "УЗЕЛ", 84,
            canonical=lambda m: m.group(), case_sensitive_canonical=True)
        add(r"(?<![\w.@:-])(?:adc\d+|ad-dns-\d+)(?![\w-])", "УЗЕЛ", 84,
            canonical=lambda m: m.group().casefold())

        # Infrastructure inventory fields can be split between adjacent DOCX
        # table cells.  U+FDD0 is the internal, immutable cell/paragraph
        # boundary; only the captured value is replaced.
        boundary = r"[ \t\r\n\ufdd0]{1,12}"
        add(rf"\bNetBIOS[- ]имя{boundary}([A-Za-z][A-Za-z0-9_-]{{2,31}})", "УЗЕЛ", 87,
            group=1, canonical=lambda m: m.group(1).casefold(), allow_boundary_context=True)
        server_label_separator = r"(?:[^\S\r\n]*:[\s\ufdd0]{0,12}|[^\S\r\n]*\ufdd0[\s\ufdd0]{0,11})"

        def server_identifier_has_right_boundary(match: re.Match) -> bool:
            end = match.end(1)
            if end >= len(source):
                return True
            following = source[end]
            return following not in "_-" and unicodedata.category(following)[0] not in {"L", "M", "N"}

        add(
            rf"\b(?:Сервер|Имя\s+узла|Хост){server_label_separator}([A-Za-z][A-Za-z0-9_-]{{2,254}})(?![A-Za-z0-9_-])",
            "УЗЕЛ", 87, group=1, flags=re.I,
            validate=server_identifier_has_right_boundary,
            canonical=lambda m: m.group(1), allow_boundary_context=True,
            case_sensitive_canonical=True,
        )
        platform_matches = add(
            rf"\bплатформа\s+виртуализации{boundary}([A-Za-z][A-Za-z0-9 ._-]{{1,40}}?)(?=\ufdd0|\r?$)",
            "СИСТЕМА", 84, group=1, flags=re.I | re.M, canonical=lambda m: self._canon(m.group(1)),
            allow_boundary_context=True,
        )
        aliases.extend((m.group(1), self._canon(m.group(1)), "СИСТЕМА") for m in platform_matches)
        vendor_matches = add(
            rf"\bпроизводитель(?:\s*\([^\r\n\ufdd0)]{{1,40}}\))?{boundary}([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9 ._-]{{1,50}}?)(?=\ufdd0|\r?$)",
            "ПРОИЗВОДИТЕЛЬ", 83, group=1, flags=re.I | re.M, canonical=lambda m: self._canon(m.group(1)),
            allow_boundary_context=True,
        )
        aliases.extend((m.group(1), self._canon(m.group(1)), "ПРОИЗВОДИТЕЛЬ") for m in vendor_matches)
        add(r"(?<![\w-])(?:[A-Za-z0-9]+-){1,5}(?:DC\d*|ADC\d*|CA)(?:-[A-Za-z0-9]+)*(?![\w-])",
            "УЗЕЛ", 86, canonical=lambda m: m.group().casefold())
        add(r"(?<!\w)(?:(?:CN|OU|DC)=[^,\r\n\ufdd0]{1,80})(?:,(?:CN|OU|DC)=[^,\r\n\ufdd0]{1,80})+(?!\w)",
            "DN", 87, canonical=lambda m: re.sub(r"\s+", "", m.group().casefold()))
        add(r"(?<![\w-])([A-Za-z][A-Za-z0-9-]{2,31})(?=/(?:\d{1,3}\.){3}\d{1,3}(?!\d))",
            "УЗЕЛ", 85, group=1, canonical=lambda m: m.group(1).casefold())
        add(r"(?<!\w)@[A-Za-z][A-Za-z0-9_]{3,31}\b", "АККАУНТ", 80, canonical=lambda m: m.group().casefold())

        # Contextual infrastructure tables.  DOCX paragraphs/cells are joined
        # with U+FDD0, so these rules replace only a cell value and never the
        # immutable fragment boundary used to reconstruct the package.
        host_inventory_matches = add(
            r"(?<![\w.-])([A-Za-z][A-Za-z0-9_-]{2,63})(?=\ufdd0(?:\[IP-\d+\]|(?:\d{1,3}\.){3}\d{1,3})\ufdd0\d+\ufdd0\d+)",
            "УЗЕЛ", 88, group=1, flags=re.I,
            canonical=lambda m: m.group(1), allow_boundary_context=True,
            case_sensitive_canonical=True,
        )
        remember_exact(host_inventory_matches, "УЗЕЛ")

        if "УЗЕЛ" not in self.disabled_categories:
            fragments = list(re.finditer(r"[^\ufdd0]+", source))
            for index, fragment in enumerate(fragments):
                if not re.fullmatch(r"\s*NetBIOS(?:[- ]имя)?\s*", fragment.group(), re.I):
                    continue
                for value_fragment in fragments[index + 1:index + 9]:
                    raw = value_fragment.group()
                    value = raw.strip()
                    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,31}", value):
                        break
                    left = value_fragment.start() + len(raw) - len(raw.lstrip())
                    right = value_fragment.end() - (len(raw) - len(raw.rstrip()))
                    found.append(Detection(
                        left, right, "УЗЕЛ", 88, value, value,
                        scope_start=left, scope_end=right,
                        case_sensitive_canonical=True,
                    ))
                    exact_aliases.append((value, value, "УЗЕЛ", True))

        if re.search(r"\bOU\s+или\s+контейнер\s+AD\b", source, re.I):
            ou_matches = add(
                r"(?<=\ufdd0)([^\r\n\ufdd0]{1,180})(?=\ufdd0\d+\ufdd0\d+\ufdd0\d+(?:\ufdd0|$))",
                "СТРУКТУРА-AD", 91, group=1, flags=re.I,
                validate=lambda m: (
                    "/" in m.group(1)
                    or "_" in m.group(1)
                    or m.group(1).strip().casefold() == "domain controllers"
                ),
                canonical=lambda m: m.group(1), allow_boundary_context=True,
                case_sensitive_canonical=True,
            )
            remember_exact(ou_matches, "СТРУКТУРА-AD")

        # DOCX supplies protected table, row, cell, and intra-cell boundaries.
        # Parse the actual three-column table structure instead of guessing from
        # status wording or from a document-global paragraph stream.
        table_boundary = "\ufdd0\ufdd1\ufdd0"
        row_boundary = "\ufdd0\ufdd2\ufdd0"
        intra_cell_boundary = "\ufdd3"

        def split_spans(value: str, delimiter: str) -> list[tuple[int, int, str]]:
            spans: list[tuple[int, int, str]] = []
            start = 0
            while True:
                end = value.find(delimiter, start)
                if end < 0:
                    spans.append((start, len(value), value[start:]))
                    return spans
                spans.append((start, end, value[start:end]))
                start = end + len(delimiter)

        # A domain-controller inventory identifies its administrative-region
        # column by the table header.  Treat every non-empty data cell in that
        # column as one geography value, including abbreviated forms such as
        # "Респ.", instead of guessing from a short list of region spellings.
        if "ГОРОД" not in self.disabled_categories and table_boundary in source:
            block_start = 0
            for block in source.split(table_boundary):
                current_start = block_start
                block_start += len(block) + len(table_boundary)
                rows = split_spans(block, row_boundary)
                header = None
                for index, (_, _, row_text) in enumerate(rows):
                    cells = split_spans(row_text, "\ufdd0")
                    headings = [
                        re.sub(r"\s+", " ", cell[2].replace(intra_cell_boundary, " ")).strip()
                        for cell in cells
                    ]
                    subject_index = next((
                        position for position, heading in enumerate(headings)
                        if re.fullmatch(r"Субъект\s+Российской\s+Федерации", heading, re.I)
                    ), None)
                    has_domain_inventory_shape = (
                        any(re.fullmatch(r"Федеральный\s+округ", heading, re.I) for heading in headings)
                        and any(re.fullmatch(r"Имя\s+сервера", heading, re.I) for heading in headings)
                    )
                    if subject_index is not None and has_domain_inventory_shape:
                        header = (index, len(cells), subject_index)
                        break
                if header is None:
                    continue
                header_row, column_count, subject_index = header
                for row_offset, _, row_text in rows[header_row + 1:]:
                    cells = split_spans(row_text, "\ufdd0")
                    if len(cells) != column_count:
                        continue
                    cell_start, _cell_end, raw = cells[subject_index]
                    meaningful = [
                        position for position, char in enumerate(raw)
                        if char != intra_cell_boundary and not char.isspace()
                    ]
                    if not meaningful:
                        continue
                    local_start, local_end = meaningful[0], meaningful[-1] + 1
                    physical_value = raw[local_start:local_end]
                    logical_value = re.sub(
                        r"[\s\ufdd3]+", " ", physical_value
                    ).strip()
                    if logical_value.startswith("[") or not re.search(r"[А-Яа-яЁё]", logical_value):
                        continue
                    left = current_start + row_offset + cell_start + local_start
                    right = current_start + row_offset + cell_start + local_end
                    mapping_value = physical_value.replace(intra_cell_boundary, "\n")
                    found.append(Detection(
                        left, right, "ГОРОД", 94, mapping_value, self._canon(logical_value),
                        scope_start=left, scope_end=right,
                    ))
                    if intra_cell_boundary not in physical_value:
                        exact_aliases.append((physical_value, self._canon(logical_value), "ГОРОД", False))

        if "УЗЕЛ" not in self.disabled_categories and table_boundary in source:
            contextual_server_name = re.compile(
                r"(?a:(?:"
                r"[a-z]?\d{4}-[a-z]{2,4}\d{2}(?:-\d{1,2})?"
                r"|[a-z]{2}\d{2}"
                r"|[a-z][a-z0-9]{1,14}-(?:dc|srv|vm|host|node|app|db|web)\d{1,3}"
                r"))",
                re.I,
            )
            block_start = 0
            for block in source.split(table_boundary):
                current_start = block_start
                block_start += len(block) + len(table_boundary)
                rows = split_spans(block, row_boundary)
                header = None
                for index, (_, _, row_text) in enumerate(rows):
                    cells = split_spans(row_text, "\ufdd0")
                    headings = [
                        re.sub(r"\s+", " ", cell[2].replace(intra_cell_boundary, " ")).strip()
                        for cell in cells
                    ]
                    name_index = next((
                        position for position, heading in enumerate(headings)
                        if re.fullmatch(
                            r"(?:наименование|имя\s+(?:сервера|узла|хоста)|сервер)",
                            heading,
                            re.I,
                        )
                    ), None)
                    ip_index = next((
                        position for position, heading in enumerate(headings)
                        if re.fullmatch(r"IP[\s-]*адрес", heading, re.I)
                    ), None)
                    supporting_columns = any(
                        re.search(
                            r"(?:программ\w*\s+обеспечен\w*|software|ИТ[\s-]*сервис)",
                            heading,
                            re.I,
                        )
                        for heading in headings
                    )
                    if (
                        name_index is not None
                        and ip_index is not None
                        and name_index != ip_index
                        and supporting_columns
                    ):
                        header = (index, len(cells), name_index, ip_index)
                        break
                if header is None:
                    continue
                header_row, column_count, name_index, ip_index = header
                for row_offset, _, row_text in rows[header_row + 1:]:
                    cells = split_spans(row_text, "\ufdd0")
                    if len(cells) != column_count:
                        continue
                    ip_value = re.sub(
                        r"\s+", "", cells[ip_index][2].replace(intra_cell_boundary, "")
                    )
                    if not (_valid_ip(ip_value) or re.fullmatch(r"\[IP-\d+\]", ip_value)):
                        continue
                    cell_start, _cell_end, raw = cells[name_index]
                    meaningful = [
                        position for position, char in enumerate(raw)
                        if char != intra_cell_boundary and not char.isspace()
                    ]
                    if not meaningful:
                        continue
                    local_start, local_end = meaningful[0], meaningful[-1] + 1
                    value = raw[local_start:local_end]
                    logical_value = re.sub(r"[\s\ufdd3]+", "", value)
                    if not contextual_server_name.fullmatch(logical_value):
                        continue
                    left = current_start + row_offset + cell_start + local_start
                    right = current_start + row_offset + cell_start + local_end
                    mapping_value = value.replace(intra_cell_boundary, "\n")
                    found.append(Detection(
                        left, right, "УЗЕЛ", 88, mapping_value, logical_value,
                        scope_start=left, scope_end=right,
                        case_sensitive_canonical=True,
                    ))
                    if intra_cell_boundary not in value:
                        exact_aliases.append((value, value, "УЗЕЛ", True))

        if "ПРОГРАММА" not in self.disabled_categories and table_boundary in source:
            block_start = 0
            for block in source.split(table_boundary):
                current_start = block_start
                block_start += len(block) + len(table_boundary)
                rows = split_spans(block, row_boundary)
                header_row = None
                for index, (_, _, row_text) in enumerate(rows):
                    cells = split_spans(row_text, "\ufdd0")
                    headings = [
                        re.sub(r"\s+", " ", cell[2].replace(intra_cell_boundary, " ")).strip()
                        for cell in cells
                    ]
                    if (
                        len(headings) == 3
                        and re.fullmatch(r"Исходное\s+Windows[-‐‑–— ]ПО", headings[0], re.I)
                        and re.fullmatch(r"Вариант\s+для\s+ALSE\s*/\s*Linux", headings[1], re.I)
                        and re.fullmatch(r"Статус\s+аналогов.*", headings[2], re.I)
                    ):
                        header_row = index
                        break
                if header_row is None:
                    continue
                for row_offset, _, row_text in rows[header_row + 1:]:
                    cells = split_spans(row_text, "\ufdd0")
                    # A merged or malformed row is skipped rather than allowing
                    # column positions to drift into another row.
                    if len(cells) != 3:
                        continue
                    row_values = [
                        re.sub(r"\s+", " ", cell[2].replace(intra_cell_boundary, " ")).strip()
                        for cell in cells
                    ]
                    repeated_header = (
                        re.fullmatch(r"Исходное\s+Windows[-‐‑–— ]ПО", row_values[0], re.I)
                        and re.fullmatch(r"Вариант\s+для\s+ALSE\s*/\s*Linux", row_values[1], re.I)
                        and re.fullmatch(r"Статус\s+аналогов.*", row_values[2], re.I)
                    )
                    structural_label = any(
                        re.match(
                            r"^(?:итого|всего|примечани[ея]|комментари[йи]|раздел)\b",
                            value,
                            re.I,
                        )
                        for value in row_values[:2]
                    )
                    if repeated_header or structural_label:
                        continue
                    for cell_start, _cell_end, raw in cells[:2]:
                        meaningful = [
                            index for index, char in enumerate(raw)
                            if char != intra_cell_boundary and not char.isspace()
                        ]
                        if not meaningful:
                            continue
                        local_start, local_end = meaningful[0], meaningful[-1] + 1
                        value = raw[local_start:local_end].replace(intra_cell_boundary, "\n")
                        if (
                            len(value) < 2
                            or value.startswith("[")
                            or not re.search(r"[A-Za-zА-Яа-яЁё]", value)
                        ):
                            continue
                        left = current_start + row_offset + cell_start + local_start
                        right = current_start + row_offset + cell_start + local_end
                        found.append(Detection(
                            left, right, "ПРОГРАММА", 93, value, value,
                            scope_start=left, scope_end=right,
                            case_sensitive_canonical=True,
                        ))
                        exact_aliases.append((value, value, "ПРОГРАММА", True))

        if re.search(r"(?:программ\w*\s+обеспечен\w*|(?:^|[^\w])ПО(?:[^\w]|$)|software)", source, re.I):
            software_matches = add(
                r"(?<=\ufdd0)([^\r\n\ufdd0]{2,160})(?=\ufdd0\d+\ufdd0\d{1,3}(?:[.,]\d+)?\s*%)",
                "ПРОГРАММА", 91, group=1, flags=re.I,
                validate=lambda m: bool(re.search(r"[A-Za-zА-Яа-яЁё]", m.group(1)))
                and m.group(1).strip().casefold() not in {"итого", "всего"},
                canonical=lambda m: m.group(1), allow_boundary_context=True,
                case_sensitive_canonical=True,
            )
            remember_exact(software_matches, "ПРОГРАММА")
        software_label_matches = add(
            r"(?im)(?:^|(?<=[\ufdd0\ufdd3]))Software[ \t]*:[ \t\ufdd3]*([^\r\n\ufdd0\ufdd3]{2,160}?)(?=[ \t]*(?:$|[\ufdd0\ufdd3]))",
            "ПРОГРАММА", 91, group=1,
            validate=lambda m: bool(re.search(r"[A-Za-z]", m.group(1))),
            canonical=lambda m: m.group(1), case_sensitive_canonical=True,
            allow_boundary_context=True,
        )
        remember_exact(software_label_matches, "ПРОГРАММА")

        script_matches = add(
            rf"\bСкрипты{boundary}([^\r\n\ufdd0]{{2,500}})(?=\ufdd0)",
            "СКРИПТЫ", 91, group=1, flags=re.I,
            canonical=lambda m: m.group(1), allow_boundary_context=True,
            case_sensitive_canonical=True,
        )
        remember_exact(script_matches, "СКРИПТЫ")
        deployment_matches = add(
            rf"\bРазв[её]ртывание\s+ПО{boundary}([^\r\n\ufdd0]{{2,500}})(?=\ufdd0)",
            "ПРОГРАММА", 91, group=1, flags=re.I,
            canonical=lambda m: m.group(1), allow_boundary_context=True,
            case_sensitive_canonical=True,
        )
        remember_exact(deployment_matches, "ПРОГРАММА")

        # Explicit storage identifiers and local/UNC paths can expose a
        # customer's naming conventions even when no hostname is present.
        add(
            r"(?<![\w])(?:[A-Za-z]:\\|\\\\[^\s\\/:*?\"<>|\r\n\ufdd0]+\\)(?:[^\s\\/:*?\"<>|\r\n\ufdd0]+\\)*[^\s\\/:*?\"<>|\r\n\ufdd0.,;:!?]+",
            "ПУТЬ", 92, canonical=lambda m: m.group(),
            case_sensitive_canonical=True,
        )
        disk_matches = add(
            r"\b(?:disk|диск|том(?!\s+числе\b)|volume)\s+([A-Za-zА-Яа-яЁё0-9](?:[A-Za-zА-Яа-яЁё0-9_.-]{0,29}[A-Za-zА-Яа-яЁё0-9])?)(?![\w-])",
            "ДИСК", 86, group=1, flags=re.I,
            canonical=lambda m: m.group(1), case_sensitive_canonical=True,
        )
        remember_exact(disk_matches, "ДИСК", minimum_length=3)

        # Security/product/task identifiers.
        add(r"\b(?:CVE-\d{4}-\d{4,7}|БДУ[:\s]*\d{4}-\d{5})\b", "уязвимость", 86, irreversible=True, fixed="[уязвимость]")
        add(r"\b(?!CVE-|ОКПД2?-|ГОСТ-|RFC-)[A-ZА-ЯЁ][A-ZА-ЯЁ0-9]{1,9}-\d{1,6}\b", "ЗАДАЧА", 79, flags=0)
        add(r"\b(?:Secret\s?Net(?:\s?Studio)?|Dallas\s?Lock|ViPNet|Випнет|КриптоПро|Kaspersky|Касперск[а-яё]+|Dr\.?\s?Web|UserGate|MaxPatrol)(?:\s+(?:Client|Server|Studio|Enterprise|Endpoint|Security|Center|VPN|CSP))*(?:\s+v?\d[\w.-]*)?\b", "СЗИ", 78)

        # Finance requires currency or explicit commercial context.
        fnum = r"(?:\d{1,3}(?:[ \u00A0.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        fcur = r"(?:руб(?:л[а-яё]+)?\.?|р\.|₽|RUB|долл(?:ар[а-яё]*)?\.?|\$|USD|евро|€|EUR|у\.\s?е\.)"
        add(rf"(?<![\d.,№/-]){fnum}(?:\s*(?:тыс|млн|млрд|трлн)\.?)?(?:\s*\([^()\n]{{0,70}}\))?\s*{fcur}(?:\s*\d{{1,2}}\s*коп[а-яё]*\.?)?", "СУММА", 77, canonical=lambda m: "fin:" + _digits(m.group()))
        add(rf"(?:₽|\$|€|USD|EUR|RUB)\s*{fnum}(?:\s*(?:тыс|млн|млрд)\.?)?", "СУММА", 77, canonical=lambda m: "fin:" + _digits(m.group()))
        add(rf"(?<![\d.,-]){fnum}\s*т\.\s?р\.?(?![а-яёA-Za-z])", "СУММА", 77, canonical=lambda m: "fin:" + _digits(m.group()))
        fword = r"(?:один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|сто|двести|триста|четыреста|тысяч[а-яё]*|миллион[а-яё]*|миллиард[а-яё]*|млн|млрд)"
        add(rf"\b{fword}(?:[ \t-]+{fword}){{0,7}}\s+рубл[а-яё]*", "СУММА", 76, canonical=lambda m: "finw:" + re.sub(r"\s+", " ", m.group().casefold()))
        def is_commercial_amount(match: re.Match) -> bool:
            trailing = source[match.end(1):match.end(1) + 64]
            return not re.match(
                r"[ \t]*(?:\([^()\r\n]{1,50}\)[ \t]*)?"
                r"(?:(?:рабочих?|календарных?|банковских?)[ \t]+)*"
                r"(?:дн(?:я|ей)|час(?:а|ов))\b",
                trailing, re.I,
            )

        add(
            rf"\b(?:стоимост[а-яё]*|цен[а-яё]*|бюджет[а-яё]*|сумм[а-яё]*|НМЦК|смет[а-яё]*|затрат[а-яё]*|аванс[а-яё]*|оплат[а-яё]*|выручк[а-яё]*|марж[а-яё]*|прибыл[а-яё]*|тариф[а-яё]*|итого)\D{{0,30}}({fnum}(?:\s*(?:тыс|млн|млрд)\.?)?)",
            "СУММА", 75, group=1, validate=is_commercial_amount,
            canonical=lambda m: "fin:" + _digits(m.group(1)),
        )
        add(r"\b(?:скидк[а-яё]*|марж[а-яё]*|наценк[а-яё]*|рентабельн[а-яё]*|комисси[а-яё]*|ставк[а-яё]*|аванс[а-яё]*)\D{0,20}(\d{1,2}(?:[.,]\d{1,2})?\s*%)", "СТАВКА", 75, group=1,
            validate=lambda m: "ндс" not in m.group().casefold(), canonical=lambda m: re.sub(r"\s", "", m.group(1)))

        # Organizations and systems; anchors feed a second derived pass.
        def harvest(pattern: str, category: str, priority: int, group: int = 1,
                    flags: int = re.I, replace_group: bool = False):
            for m in re.finditer(pattern, source, flags):
                name = m.group(group).strip()
                if name.casefold() in self.whitelist:
                    continue
                if category in self.disabled_categories:
                    disabled_spans.append(m.span(group) if replace_group else m.span())
                    continue
                key = self._org_key(name)
                span = m.span(group) if replace_group else m.span()
                value = name if replace_group else m.group()
                found.append(Detection(*span, category, priority, value, key,
                                       scope_start=m.start(), scope_end=m.end()))
                aliases.append((name, key, category))

        opf = r"(?:ООО|АО|ПАО|ЗАО|ОАО|НАО|АНО|НКО|ФГУП|ГУП|МУП|ФГБУ|ФГАУ|ФГКУ|ГБУ|ГКУ|ИП|КФХ|СПК|ТСЖ|КБ|НПО|НПП|УК|ГК)"
        # Russian legal names may use nested low/high quotes inside the outer
        # guillemets: АО «Международный аэропорт „Саранск“».
        harvest(rf"\b{opf}\s*«([^«»\n\ufdd0]{{2,80}})»", "ОРГАНИЗАЦИЯ", 73)
        harvest(rf"\b{opf}\s*[\"„]([^«»\"„”\n\ufdd0]{{2,60}})[\"”]", "ОРГАНИЗАЦИЯ", 72)
        harvest(r"\b(?:публичн[а-яё]+\s+акционерн[а-яё]+\s+обществ[а-яё]+|акционерн[а-яё]+\s+обществ[а-яё]+|обществ[а-яё]+\s+с\s+ограниченн[а-яё]+\s+ответственность[а-яё]*|индивидуальн[а-яё]+\s+предпринимател[а-яё]+)\s*[«\"„]([^«»\"„”\n\ufdd0]{2,60})[»\"”]", "ОРГАНИЗАЦИЯ", 72)
        harvest(rf"(?<![\w-])((?:[«\"„][^«»\"„”\n\ufdd0]{{2,60}}[»\"”])|(?:[А-ЯЁ][А-Яа-яЁё0-9&-]{{2,}}(?:[ \t]+[А-ЯЁ][А-Яа-яЁё0-9&-]+){{0,2}}))[ \t]*,?[ \t]+{opf}\b", "ОРГАНИЗАЦИЯ", 71)
        harvest(rf"\b([А-ЯЁ][А-Яа-яЁё0-9&-]+(?:\s+[А-ЯЁа-яё][А-Яа-яЁё0-9&-]+){{0,3}})\s*\(\s*{opf}\s*\)", "ОРГАНИЗАЦИЯ", 71)
        harvest(r"(?<![\w-])([A-Z][\w&.-]{2,}(?:\s+[A-Z][\w&.-]+){0,2})\s*,?\s+(?:LLC|Ltd\.?|Inc\.?|Corp\.?|GmbH|JSC|PJSC|AG|S\.A\.|B\.V\.)\b", "ОРГАНИЗАЦИЯ", 71, flags=0)
        role = r"(?:заказчик[а-яё]*|клиент[а-яё]*|партн[её]р[а-яё]*|контор[а-яё]*|фирм[а-яё]*|подрядчик[а-яё]*|поставщик[а-яё]*|компани[а-яё]+|организаци[а-яё]+)"
        harvest(rf"\b{role}\s*[—:–-]?\s*[«\"]([^«»\"\n\ufdd0]{{2,60}})[»\"]", "ОРГАНИЗАЦИЯ", 70, replace_group=True)
        harvest(rf"\b{role}[ \t]*[—:–-][ \t]*([A-Za-zА-Яа-яЁё0-9][^\n\ufdd0,.;:!?«»\"]{{1,48}})", "ОРГАНИЗАЦИЯ", 69, replace_group=True)
        harvest(r"\b(?:называ[её]тся|именуе[а-яё]*|назван(?:а|о|ы)?|зов[её]тся)\s+(?:просто\s+|теперь\s+|официально\s+)?([A-Za-zА-Яа-яЁё0-9][\wА-Яа-яЁё&.-]*(?:\s+(?:и|and)\s+[а-яёa-z]{3,}){0,2})", "ОРГАНИЗАЦИЯ", 69, replace_group=True)
        harvest(r"\b(?:АС|ИС|АИС|ГИС|ЕГИС|СЭД|СМЭВ|АСУ|ПК|ПО|систем[а-яё]+|подсистем[а-яё]+|платформ[а-яё]+|модул[а-яё]+|сервис[а-яё]*|комплекс[а-яё]*)\s+[«\"]([^«»\"\n\ufdd0]{2,60})[»\"]", "СИСТЕМА", 73, replace_group=True)

        # People anchors and direct forms.
        surnames: list[tuple[str, str]] = []

        def full_person_key(match: re.Match, surname_group: int) -> str:
            surname_span = match.span(surname_group)
            components: list[str] = []
            for token in re.finditer(r"[A-Za-zА-Яа-яЁё-]+", match.group()):
                absolute_span = (match.start() + token.start(), match.start() + token.end())
                if absolute_span != surname_span:
                    components.append(_canonical_name_component(token.group()))
            return "фио-полное:" + ":".join((_stem_surname(match.group(surname_group)), *components))

        def person(pattern: str, priority: int, surname_group: int, flags: int = 0,
                   validate: Callable[[re.Match], bool] | None = None,
                   full_key: bool = False):
            for m in re.finditer(pattern, source, flags):
                if validate and not validate(m):
                    continue
                if "ФИО" in self.disabled_categories:
                    disabled_spans.append(m.span())
                    continue
                surname = m.group(surname_group)
                key = full_person_key(m, surname_group) if full_key else ("фио:" + _stem_surname(surname))
                found.append(Detection(*m.span(), "ФИО", priority, m.group(), key))
                surnames.append((surname, key))

        patr = r"(?:[её]вич(?:а|у|ем|е)?|ович(?:а|у|ем|е)?|ич(?:а|у|ем|е)?|[её]вн(?:а|ы|е|у|ой)|овн(?:а|ы|е|у|ой)|ичн(?:а|ы|е|у|ой)|оглы|кызы)"
        person(rf"\b([А-ЯЁ][а-яё-]+)\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+{patr}\b", 68, 1, full_key=True)
        person(rf"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+{patr}\s+([А-ЯЁ][а-яё-]+)\b", 68, 1, full_key=True)
        person(r"\b([А-ЯЁ][а-яё-]{2,})\s+[А-ЯЁ]\s?\.\s?[А-ЯЁ]\s?\.", 67, 1)
        person(r"\b[А-ЯЁ]\s?\.\s?[А-ЯЁ]\s?\.\s?([А-ЯЁ][а-яё-]{2,})\b", 67, 1)
        latin_pair = r"(?<![\w.-])([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})(?![\w-])"
        def valid_labelled_contact(match: re.Match) -> bool:
            parts = match.group(1).split()
            if not 2 <= len(parts) <= 4:
                return False
            for part in parts:
                initial = part.endswith(".")
                core = part[:-1] if initial else part
                pieces = re.split(r"[-'’]", core)
                if (
                    not core
                    or not core[0].isupper()
                    or any(not piece or not piece.isalpha() for piece in pieces)
                    or (initial and len(core) != 1)
                    or (not initial and len(core) < 2)
                ):
                    return False
            return True

        add(
            r"(?im)(?:^|(?<=[\ufdd0\ufdd3]))Contact[ \t]*:[ \t\ufdd3]*([^\r\n\ufdd0\ufdd3]{2,80}?)(?=[ \t]*(?:$|[\ufdd0\ufdd3]))",
            "ФИО", 69, group=1,
            validate=valid_labelled_contact,
            canonical=lambda m: "contact:" + self._canon(m.group(1)),
            allow_boundary_context=True,
        )
        person(latin_pair, 66, 2, validate=lambda m: m.group(1).lower() in LAT_NAMES and m.group(2).lower() not in LAT_NAMES, full_key=True)
        person(latin_pair, 66, 1, validate=lambda m: m.group(2).lower() in LAT_NAMES and m.group(1).lower() not in LAT_NAMES, full_key=True)
        person(r"\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,}(?:ов|ев|ёв|ин|ын|енко|ко|ук|юк|чук|швили|дзе|ян|ский|цкий)(?:а|у|ым|ом|е|ой)?)\b", 65, 2, validate=lambda m: _name_like(m.group(1)), full_key=True)
        person(r"\b([А-ЯЁ][а-яё]{2,})\s+([а-яё]+(?:ов|ев|ёв|ин|ын|енко|ко|ук|юк|чук|швили|дзе|ян|ский|цкий)(?:а|у|ым|ом|е|ой)?)\b", 65, 2, validate=lambda m: _name_like(m.group(1)), full_key=True)
        full_by_surname: dict[str, set[str]] = {}
        for raw, key in surnames:
            if key.startswith("фио-полное:"):
                full_by_surname.setdefault(_stem_surname(raw), set()).add(key)
        resolved_people: list[Detection] = []
        for item in found:
            if item.category != "ФИО" or not item.canonical or not item.canonical.startswith("фио:"):
                resolved_people.append(item)
                continue
            stem = item.canonical.removeprefix("фио:")
            initials = {letter.casefold().replace("ё", "е") for letter in re.findall(r"([А-ЯЁ])\s?\.", item.value)}
            compatible = [
                key for key in full_by_surname.get(stem, ())
                if initials.issubset({part[0] for part in key.removeprefix("фио-полное:").split(":") if part})
            ]
            if len(compatible) == 1:
                resolved_people.append(Detection(
                    item.start, item.end, item.category, item.priority, item.value,
                    compatible[0], item.irreversible, item.fixed,
                    item.scope_start, item.scope_end,
                ))
        found = resolved_people
        surnames = [(raw, key) for raw, key in surnames if key.startswith("фио-полное:")]
        role_name = r"(?:ответственн[а-яё]+|исполнител[а-яё]+|контакт[а-яё]*|менеджер[а-яё]*|куратор[а-яё]*|представител[а-яё]+|коллег[а-яё]+|сотрудник[а-яё]*|инженер[а-яё]*|администратор[а-яё]*|директор[а-яё]*|руководител[а-яё]+|начальник[а-яё]*|специалист[а-яё]*|звонить|писать)"
        for m in re.finditer(rf"\b{role_name}\s*[—:-]?\s+((?-i:[А-ЯЁ][а-яё]{{2,}}))\b", source, re.I):
            name = m.group(1)
            if _name_like(name) or re.search(r"(?:ов|ев|ин|ский|цкий)(?:а|у|ым|ом|е|ой)?$", name.casefold()):
                if "ФИО" in self.disabled_categories:
                    disabled_spans.append(m.span(1))
                else:
                    key = "фио-имя:" + _name_stem(name)
                    found.append(Detection(*m.span(1), "ФИО", 64, name, key,
                                           scope_start=m.start(), scope_end=m.end()))

        # Login/account names are reversible, unlike passwords.
        add(
            r"(?<![\w@./\\-])(Svc[A-Z]{2,8}-(?=[A-Za-z]{4,30}(?![\w@/\\-]|\.[A-Za-z0-9]))"
            r"(?=[A-Za-z]*[A-Z])(?=[A-Za-z]*[a-z])[A-Za-z]{4,30})(?![\w@/\\-]|\.[A-Za-z0-9])",
            "ЛОГИН", 86, group=1, flags=0,
            canonical=lambda m: m.group(1), case_sensitive_canonical=True,
        )
        add(r"\b[A-Za-z][\w.-]{1,20}\\[A-Za-z][\w.-]{1,30}\b", "ЛОГИН", 63, canonical=lambda m: m.group().casefold())
        add(r"\b(?:уч[её]тн[а-яё]+\s+запис[а-яё]+|логин[а-яё]*|login|username|уч[её]тк[а-яё]+)\s*[:=—-]?\s*([A-Za-z][\w.@-]{2,30})", "ЛОГИН", 63, group=1, canonical=lambda m: m.group(1).casefold())
        if re.search(r"\b(?:Enterprise|Schema)\s+Admins\b", source, re.I):
            privileged_login_matches = add(
                r"(?<![\w.-])([A-ZА-ЯЁ][a-zа-яё]{2,30}_[A-ZА-ЯЁ])(?![\w.-])",
                "ЛОГИН", 85, group=1, flags=0,
                canonical=lambda m: m.group(1), case_sensitive_canonical=True,
            )
            remember_exact(privileged_login_matches, "ЛОГИН")
        if re.search(r"\bSamAccountName\b", source, re.I):
            repeated_account = re.compile(
                r"(?<![\w.-])([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9._-]{2,30})(\ufdd0)\1(?![\w.-])",
                re.I,
            )
            for match in repeated_account.finditer(source):
                raw = match.group(1)
                canonical = raw.casefold()
                first = match.span(1)
                second = (match.start(1) + len(raw) + 1, match.start(1) + len(raw) + 1 + len(raw))
                if "ЛОГИН" in self.disabled_categories:
                    disabled_spans.extend((first, second))
                else:
                    found.append(Detection(*first, "ЛОГИН", 85, raw, canonical,
                                           scope_start=first[0], scope_end=first[1]))
                    found.append(Detection(*second, "ЛОГИН", 85, source[slice(*second)], canonical,
                                           scope_start=second[0], scope_end=second[1]))

        city_pattern = "|".join(re.escape(c[:-1] if c.endswith(("а", "ь", "й")) else c) + r"[а-яё]{0,3}" for c in CITIES)
        whitelist_stems = {_name_stem(value) for value in self.whitelist}
        add(rf"(?<![А-Яа-яЁё-])(?:{city_pattern})(?![А-Яа-яЁё-])", "ГОРОД", 62,
            validate=lambda m: _name_stem(m.group()) not in whitelist_stems,
            canonical=lambda m: _name_stem(m.group()))

        if "СОКРАЩЕНИЯ" not in self.disabled_categories:
            abbreviation_tokens = list(_iter_abbreviation_tokens(source))
            for start, end in abbreviation_tokens:
                value = source[start:end]
                normalized = unicodedata.normalize("NFC", value)
                if _is_short_abbreviation(value):
                    abbreviation_candidates.append(Detection(
                        start, end, "СОКРАЩЕНИЯ", 45, value, value,
                        case_sensitive_canonical=True,
                    ))
                    continue
                uppercase_run = 0
                for char in normalized:
                    category = unicodedata.category(char)
                    if category == "Lu":
                        uppercase_run += 1
                        if uppercase_run >= 3:
                            break
                    elif category.startswith("M") or char in {"\u200c", "\u200d"}:
                        continue
                    else:
                        uppercase_run = 0
                if uppercase_run < 3:
                    continue
                abbreviation_candidates.append(Detection(
                    start, end, "СОКРАЩЕНИЯ", 45, value, value,
                    case_sensitive_canonical=True,
                ))

        for value, category in sorted(self.user_dictionary.items(), key=lambda x: len(x[0]), reverse=True):
            if not value:
                continue
            secret_label = category.upper() in {"SECRET", "СЕКРЕТ", "ПАРОЛЬ", "TOKEN", "ТОКЕН", "КЛЮЧ"}
            enabled = secret_label or (
                "CUSTOM" not in self.disabled_categories
                and category not in self.disabled_categories
                and value.casefold() not in self.whitelist
            )
            if enabled:
                pattern = re.escape(value) if secret_label else rf"(?<!\w){re.escape(value)}(?!\w)"
                for m in re.finditer(pattern, source, re.I):
                    found.append(Detection(*m.span(), "SECRET" if secret_label else category, 100,
                                           m.group(), value.casefold(), secret_label,
                                           "(удалено)" if secret_label else None))
            elif not secret_label:
                pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
                disabled_spans.extend(m.span() for m in re.finditer(pattern, source, re.I))

        # U+FDD0 is an internal Office fragment boundary, never detector data.
        # Only explicitly allowlisted table-field detectors narrow their scope
        # to a captured value on one side of the boundary.
        found = [
            item for item in found
            if "\ufdd0" not in source[
                item.scope_start if item.scope_start is not None else item.start:
                item.scope_end if item.scope_end is not None else item.end
            ]
        ]

        # First overlap resolution, then stable derived aliases from surviving anchors.
        accepted: list[Detection] = []
        occupied = [*protected, *disabled_spans]
        for item in sorted(found, key=lambda x: (-x.priority, -(x.end-x.start), x.start, x.category)):
            blockers = [(x.start, x.end) for x in accepted] if item.irreversible else occupied
            overlaps = sorted(
                (max(item.start, start), min(item.end, end))
                for start, end in blockers
                if item.start < end and item.end > start
            )
            if overlaps:
                # A structured software cell may contain a higher-priority
                # irreversible secret or another validated entity. Preserve that
                # detector, but still redact every visible remainder of the cell.
                if item.category == "ПРОГРАММА" and item.priority == 93:
                    cursor = item.start
                    uncovered: list[tuple[int, int]] = []
                    for start, end in overlaps:
                        if start > cursor:
                            uncovered.append((cursor, start))
                        cursor = max(cursor, end)
                    if cursor < item.end:
                        uncovered.append((cursor, item.end))
                    for start, end in uncovered:
                        while start < end and (
                            source[start].isspace() or source[start] == "\ufdd3"
                        ):
                            start += 1
                        while end > start and (
                            source[end - 1].isspace() or source[end - 1] == "\ufdd3"
                        ):
                            end -= 1
                        raw = source[start:end]
                        value = raw.replace("\ufdd3", "\n")
                        if not value:
                            continue
                        fragment = Detection(
                            start, end, item.category, item.priority, value, value,
                            scope_start=start, scope_end=end,
                            case_sensitive_canonical=True,
                        )
                        accepted.append(fragment)
                        occupied.append((start, end))
                continue
            accepted.append(item)
            occupied.append((item.start, item.end))
        surviving_keys = {(x.category, x.canonical) for x in accepted}
        for raw, key, category in aliases:
            if (category, key) not in surviving_keys:
                continue
            clean = re.sub(r"[«»\"„”]", "", raw).strip()
            if not clean:
                continue
            if " " in clean or re.search(r"[A-Za-z]", clean):
                pattern = re.escape(clean)
            else:
                base = re.sub(r"[аяоеиыуюь]$", "", clean)
                pattern = re.escape(base) + r"[а-яё]{0,3}"
            for m in re.finditer(rf"(?<![\w-]){pattern}(?![\w-])", source, re.I):
                if not any(m.start() < e and m.end() > s for s, e in occupied):
                    accepted.append(Detection(*m.span(), category, 50, m.group(), key)); occupied.append(m.span())
        surname_keys: dict[str, set[str]] = {}
        for raw, key in surnames:
            surname_keys.setdefault(_stem_surname(raw), set()).add(key)
        for raw, key in surnames:
            if ("ФИО", key) not in surviving_keys:
                continue
            stem = _stem_surname(raw)
            if len(stem) < 3 or len(surname_keys.get(stem, ())) != 1:
                continue
            for m in re.finditer(r"(?<![\w-])[А-Яа-яЁё][А-Яа-яЁё-]{2,}(?![\w-])", source):
                if _stem_surname(m.group()) != stem:
                    continue
                if not any(m.start() < e and m.end() > s for s, e in occupied):
                    # A matching surname stem is enough to detect the value, but
                    # not enough to prove that it names the same person as the
                    # full-name anchor. Keep a separate reversible identity key.
                    surname_key = "фио-фамилия:" + self._canon(m.group())
                    accepted.append(Detection(*m.span(), "ФИО", 49, m.group(), surname_key))
                    occupied.append(m.span())
        seen_exact_aliases: set[tuple[str, str, str, bool]] = set()
        for raw, key, category, case_sensitive in exact_aliases:
            alias = (raw, key, category, case_sensitive)
            if alias in seen_exact_aliases or (category, key) not in surviving_keys:
                continue
            seen_exact_aliases.add(alias)
            flags = 0 if case_sensitive else re.I
            for match in re.finditer(rf"(?<![\w-]){re.escape(raw)}(?![\w-])", source, flags):
                if any(match.start() < end and match.end() > start for start, end in occupied):
                    continue
                accepted.append(Detection(
                    *match.span(), category, 48, match.group(), key,
                    case_sensitive_canonical=case_sensitive,
                ))
                occupied.append(match.span())

        # Hints fill only unoccupied spans.
        hints: list[Hint] = []
        hint_categories = {
            "должность": "ДОЛЖНОСТЬ", "город": "ГОРОД", "спецкатегория ПДн": "СПЕЦКАТЕГОРИЯ",
            "возможная фамилия": "ФИО", "возможное ФИО": "ФИО", "возможное имя заказчика": "ОРГАНИЗАЦИЯ",
            "возможное имя собственное": "СКРЫТО",
        }
        def hint(pattern: str, kind: str, flags: int = re.I, group: int = 0,
                 validate: Callable[[re.Match], bool] | None = None):
            if "HINTS" in self.disabled_categories or hint_categories.get(kind, "СКРЫТО") in self.disabled_categories:
                return
            for m in re.finditer(pattern, source, flags):
                if validate and not validate(m):
                    continue
                span = m.span(group)
                if any(span[0] < e and span[1] > s for s, e in occupied):
                    continue
                value = m.group(group)
                if value.casefold() in self.whitelist:
                    continue
                hints.append(Hint(*span, value, kind)); occupied.append(span)
        hint(r"\b(?:начальник[а-яё]*|заместител[а-яё]+|руководител[а-яё]+|директор[а-яё]*|куратор[а-яё]*|главн[а-яё]+\s+(?:инженер|бухгалтер|специалист)|ведущ[а-яё]+\s+(?:инженер|специалист)|администратор[а-яё]*|архитектор[а-яё]*)\s+(?:(?:отдел[а-яё]*|управлени[а-яё]+|департамент[а-яё]*|служб[а-яё]+|направлени[а-яё]+|групп[а-яё]+|центр[а-яё]*)(?:\s+(?!(?:[а-яё]+(?:ет|ют|ит|ят|ут|л|ла|ли))\b)[а-яё]+){0,2}|по\s+[а-яё]+(?:\s+[а-яё]+){0,2})\b", "должность")
        hint(rf"(?<![А-Яа-яЁё-])(?:{city_pattern})(?![А-Яа-яЁё-])", "город")
        hint(r"\b(?:диагноз[а-яё]*|инвалидн[а-яё]+|судимост[а-яё]+|вероисповедан[а-яё]+|национальност[а-яё]+|беременн[а-яё]+|болезн[а-яё]+)\b", "спецкатегория ПДн")
        hint(r"\b[А-ЯЁ][а-яё-]{3,}\b", "возможная фамилия", flags=0,
             validate=lambda m: _stem_surname(m.group()) in {_stem_surname(x) for x in COMMON_SURNAMES})
        # Capitalized-only proper nouns in the middle of a sentence.
        lower_stems = {_name_stem(m.group()) for m in re.finditer(r"\b[а-яё][а-яё-]{3,}\b", source)}
        hint(r"\b[А-ЯЁ][а-яё-]{3,}\b", "возможное имя собственное", flags=0,
             validate=lambda m: _name_stem(m.group()) not in lower_stems and m.group().casefold() not in STOP_PROPER and m.start() > 0 and source[m.start()-1] not in ".!?\n")

        if self.paranoid:
            for h in hints:
                label = hint_categories.get(h.kind, "СКРЫТО")
                accepted.append(Detection(h.start, h.end, label, 10, h.value, self._canon(h.value)))
            hints = []

        # Abbreviations are the broad fail-closed fallback. Apply them only
        # after validated entities, exact aliases and semantic review spans, so
        # an uppercase run cannot split a known structured or contextual value.
        for item in abbreviation_candidates:
            if any(item.start < end and item.end > start for start, end in occupied):
                continue
            accepted.append(item)
            occupied.append((item.start, item.end))
        accepted.sort(key=lambda x: (x.start, x.end))

        warnings = self._warnings(source)
        counts: dict[str, int] = {}
        counters: dict[str, int] = {}
        mapping: dict[str, str] = {}
        by_key: dict[tuple[str, str], str] = {}
        for m in literal_markers:
            parsed = re.fullmatch(r"\[([А-ЯA-ZЁа-яё][А-ЯA-ZЁа-яё0-9_-]{0,63})-(\d{1,9})\]", m.group())
            if parsed:
                suffix = parsed.group(2)
                if len(suffix) <= 9:
                    counters[parsed.group(1)] = max(counters.get(parsed.group(1), 0), int(suffix))

        merged: list[tuple[int, int, Detection | Hint]] = [(x.start, x.end, x) for x in accepted] + [(x.start, x.end, x) for x in hints]
        merged.sort(key=lambda x: (x[0], x[1]))
        parts: list[dict] = []
        legend: list[dict] = []
        cursor = 0
        for start, end, item in merged:
            if start > cursor:
                parts.append({"t": "text", "s": source[cursor:start]})
            if isinstance(item, Hint):
                parts.append({"t": "hint", "s": item.value, "orig": item.value, "kind": item.kind, "s0": start, "s1": end})
            else:
                if item.fixed or item.irreversible:
                    replacement = item.fixed or "(удалено)"
                else:
                    key_value = item.value if item.case_sensitive_canonical else item.canonical or item.value
                    key = (
                        item.category,
                        key_value if item.case_sensitive_canonical else self._canon(key_value),
                    )
                    replacement = by_key.get(key, "")
                    if not replacement:
                        marker_label = (
                            COMPACT_MARKER_LABELS.get(item.category, item.category)
                            if self.compact_markers
                            else item.category
                        )
                        counters[marker_label] = counters.get(marker_label, 0) + 1
                        replacement = f"[{marker_label}-{counters[marker_label]}]"
                        by_key[key] = replacement
                        mapping[replacement] = item.value
                        legend.append({"ph": replacement, "orig": item.value, "cat": item.category})
                counts[item.category] = counts.get(item.category, 0) + 1
                # U+FDD3 is a protected intra-cell paragraph/run boundary used
                # by the DOCX transformer. Keep every occurrence so replacing a
                # complete multi-paragraph cell cannot change the XML group count.
                protected_boundaries = source[start:end].count("\ufdd3") * "\ufdd3"
                rendered_replacement = replacement + protected_boundaries
                parts.append({"t": "ph", "s": rendered_replacement, "orig": "" if item.irreversible else item.value, "cat": item.category,
                              "secret": item.irreversible or item.category == "SECRET", "s0": start, "s1": end})
            cursor = end
        if cursor < len(source):
            parts.append({"t": "text", "s": source[cursor:]})
        output = "".join(part["s"] for part in parts)
        return AnonymizationResult(output, mapping, list(dict.fromkeys(h.value for h in hints)), warnings,
                                   parts, legend, counts, len(accepted), len(legend), len(hints))

    @staticmethod
    def _warnings(source: str) -> list[dict[str, str]]:
        specs = [
            ("ГОСТАЙНА", "info", r"совершенно\s+секретно|особой\s+важности|государственн[а-яё]+\s+тайн|гостайн|(?<![а-яё])секретно(?![а-яё])", "Обнаружен гриф секретности. Это ожидаемый сценарий обезличивания и не блокирует экспорт; проверьте обезличенный результат."),
            ("ДСП", "info", r"для\s+служебного\s+пользования|(?<![а-яё])ДСП(?![а-яё])|коммерческ[а-яё]+\s+тайн|конфиденциальн", "Обнаружен гриф ДСП или признак конфиденциальности. Это ожидаемый сценарий обезличивания и не блокирует экспорт; проверьте обезличенный результат."),
            ("КИИ", "warn", r"критическ[а-яё]+\s+информационн[а-яё]+\s+инфраструктур|(?<![а-яё])КИИ(?![а-яё])", "Упоминается КИИ: перепроверьте объекты и идентификаторы систем."),
            ("ЗАКУПКИ", "warn", r"ОКПД\s?2|КТРУ", "Есть ОКПД2/КТРУ: проверьте связку кода, описания, объёма и заказчика."),
            ("МАССИВ-ПДН", "warn", r"массив[а-яё]*\s+(?:персональн[а-яё]+\s+данн[а-яё]+|ПДн)|реестр[а-яё]*\s+(?:сотрудник|клиент|пациент)[а-яё]*", "Есть признак массива персональных данных; ручная проверка обязательна."),
        ]
        return [{"kind": kind, "level": level, "message": message} for kind, level, pattern, message in specs if re.search(pattern, source, re.I)]


def warnings_require_review(warnings: list[str | dict[str, str]]) -> bool:
    """Informational findings remain visible but do not hold or block export."""
    return any(
        not isinstance(warning, dict) or warning.get("level") != "info"
        for warning in warnings
    )
