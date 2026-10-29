"""Russian internal-passport fields, registered through the engine callback.

Retains disabled-category blockers, whitelists and exact reversible mappings.
Issue metadata extends the legacy number-only category, but only after a local
passport heading, never across blank paragraphs or separate DOCX tables.
"""
import re


def register_passport_rules(add):
    horizontal = r"[^\S\r\n]*"

    def in_passport_context(match):
        prefix = match.string[max(0, match.start() - 400):match.start()]
        headings = list(re.finditer(r"\bпаспорт(?:а)?\b", prefix, re.I))
        if not headings:
            return False
        context = prefix[headings[-1].end():]
        if not re.match(r"(?:[^\S\r\n]+РФ\b)?[\s:;№,\ufdd0\ufdd2\ufdd3]*(?:[0-9]|серия\b|кем\b|выдан\b|дата\b|код\b|$)", context, re.I):
            return False
        return not re.search(r"\ufdd1|\r?\n[^\S\r\n]*\r?\n|\b(?:договор|заказ|сч[её]т|издели[ея])\b", context, re.I)

    label_gap = r"[^\S\r\n]*(?::[^\S\r\n]*)?(?:\ufdd0[^\S\r\n]*)?"
    metadata = (
        (r"(?:кем\s+выдан|выдан|орган\s+выдачи)", r"[^\s\d:;\ufdd0][^;\r\n\ufdd0]{1,179}?", r"(?=[^\S\r\n]*(?:[;\r\n\ufdd0]|$|(?:дата\s+выдачи|код\s+подразделения)\b))"),
        (r"дата\s+выдачи", r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", r"(?![\w.])"),
        (r"код\s+подразделения", r"[0-9]{3}[^\S\r\n]*[-–][^\S\r\n]*[0-9]{3}", r"(?![\w-])"),
    )
    for label, field, end in metadata:
        add(
            rf"\b{label}{label_gap}({field}){end}",
            "ПАСПОРТ", 94, group=1, allow_boundary_context=True,
            validate=in_passport_context,
            canonical=lambda match: match.group(1), case_sensitive_canonical=True,
        )
    series = rf"[0-9]{{2}}{horizontal}[0-9]{{2}}"
    number = r"[0-9]{6}"
    value = rf"{series}{horizontal}(?:№{horizontal})?{number}"
    field_separator = r"[\s:;№,\ufdd0\ufdd2\ufdd3]*"
    passport = r"\bпаспорт(?:а)?\b"
    series_context = rf"(?:\bсерия{horizontal}паспорта\b|{passport}{field_separator}серия\b)"
    number_context = (
        rf"(?:\bномер{horizontal}паспорта\b|{passport}{field_separator}"
        rf"(?:серия{field_separator}{series}{field_separator})?номер\b)"
    )
    for context, digits in ((series_context, series), (number_context, number)):
        add(
            rf"{context}{field_separator}({digits})(?!\w)",
            "ПАСПОРТ", 94, group=1, allow_boundary_context=True,
            canonical=lambda match: match.group(1), case_sensitive_canonical=True,
        )
    add(
        rf"\bпаспорт{horizontal}:{horizontal}\ufdd0{horizontal}({value})(?!\w)",
        "ПАСПОРТ", 94, group=1, allow_boundary_context=True,
        canonical=lambda match: match.group(1), case_sensitive_canonical=True,
    )
    add(
        rf"\b(?:паспорт(?:{horizontal}РФ)?|серия){horizontal}[:№]?{horizontal}({value})(?!\w)",
        "ПАСПОРТ", 94, group=1,
        canonical=lambda match: match.group(1), case_sensitive_canonical=True,
    )
