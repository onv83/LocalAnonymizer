"""B101 network inventory regressions (A1-A7).

Every network value in this module is synthetic: RFC 5737 documentation
addresses, ``*.example`` domains, TEST-NET derived reverse zones and
invented hostnames.  Real user network identifiers must never appear here.
"""

import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document

from local_anonymizer.documents import DocxProcessor
from local_anonymizer.engine import Anonymizer

TABLE = "\ufdd0\ufdd1\ufdd0"
ROW = "\ufdd0\ufdd2\ufdd0"
CELL = "\ufdd0"

# Synthetic documentation-only fixtures (A1-A4).
FQDN_NUMERIC_FIRST = "2.host.region.example"
FQDN_TERRITORIAL = "host.city.example"
REVERSE_ZONE_DEEP = "4.2.0.192.in-addr.arpa"
REVERSE_ZONE_SHALLOW = "100.51.198.in-addr.arpa"
IPV4_LEADING_ZERO = "0.198.51.100"
CIDR_DOCUMENTATION = "203.0.113.0/24"
INVENTORY_IP = "192.0.2.10"
EXISTING_IP_MARKER = "[IP-7]"

# Synthetic inventory hostnames (A5/A6 grammar forms).
HOST_COMPACT = "qxr77"
HOST_MULTI_SEGMENT = "qx61-virt02"
HOST_MIXED_CASE = "QX-AB01-5"


def inventory(host: str, ip: str = INVENTORY_IP) -> str:
    header = CELL.join(("Сервер", "IP", "ОС", "CPU", "RAM", "Disk"))
    data = CELL.join((host, ip, "Synthetic OS (64-bit)", "32", "64", "144"))
    return TABLE + ROW.join((header, data)) + TABLE


def server_list(*hosts: str, heading: str = "Серверы региона:") -> str:
    return "\n".join((heading, *hosts))


# ---------------------------------------------------------------------------
# A1-A4: plain network classes.
# ---------------------------------------------------------------------------


def test_plain_network_names_cidr_and_reverse_dns_are_fully_masked():
    values = (
        FQDN_NUMERIC_FIRST,
        FQDN_TERRITORIAL,
        REVERSE_ZONE_DEEP,
        REVERSE_ZONE_SHALLOW,
        IPV4_LEADING_ZERO,
        CIDR_DOCUMENTATION,
    )
    result = Anonymizer().anonymize("\n".join(values))
    for value in values:
        assert value not in result.text
    assert result.text.count("[ДОМЕН-") == 4
    assert result.text.count("[IP-") == 2
    assert "/24" not in result.text
    assert set(result.mapping.values()) == set(values)


def test_plain_network_values_have_exact_right_boundaries():
    source = (
        f"Регион обслуживает узел {FQDN_NUMERIC_FIRST}.\n"
        f"Доступен шлюз {INVENTORY_IP}.\n"
        f"Выделена подсеть {CIDR_DOCUMENTATION}.\n"
        f"Описана зона {REVERSE_ZONE_DEEP}.\n"
        f"Адрес {IPV4_LEADING_ZERO} зарезервирован.\n"
    )
    result = Anonymizer().anonymize(source)
    assert "[ДОМЕН-1]." in result.text
    assert "[IP-1]." in result.text
    assert re.search(r"\[IP-\d+\]\.", result.text)
    assert "[ДОМЕН-2]." in result.text
    # No partial mask: nothing between the marker and the sentence dot.
    assert not re.search(r"\[ДОМЕН-\d+\][\w/]", result.text)
    assert not re.search(r"\[IP-\d+\][\w/]", result.text)


def test_plain_network_ordinary_prose_is_untouched():
    source = (
        "Сервер работает штатно, замечаний нет.\n"
        "Результат деления: 1/2 от планового объёма.\n"
        "Обновление от 13.10.2026 выполнено.\n"
        "Версия платформы 2.4.1 поддерживается.\n"
        "Путь к отчёту: /24/data/report.txt.\n"
    )
    result = Anonymizer().anonymize(source)
    assert result.text == source
    assert not result.mapping


def test_network_category_disable_keeps_values_without_relabel():
    values = "\n".join(
        (FQDN_NUMERIC_FIRST, REVERSE_ZONE_SHALLOW, IPV4_LEADING_ZERO, CIDR_DOCUMENTATION)
    )
    ip_disabled = Anonymizer(disabled_categories=["IP"]).anonymize(values)
    assert IPV4_LEADING_ZERO in ip_disabled.text
    assert CIDR_DOCUMENTATION in ip_disabled.text
    assert "[IP-" not in ip_disabled.text
    # No relabel into any other category.
    assert "[МЕТРИКА-" not in ip_disabled.text
    assert "[ДОКУМЕНТ-" not in ip_disabled.text
    assert "[СОКРАЩЕНИЯ-" not in ip_disabled.text
    assert ip_disabled.text.count("[ДОМЕН-") == 2

    domain_disabled = Anonymizer(disabled_categories=["ДОМЕН"]).anonymize(values)
    assert FQDN_NUMERIC_FIRST in domain_disabled.text
    assert REVERSE_ZONE_SHALLOW in domain_disabled.text
    assert "[ДОМЕН-" not in domain_disabled.text
    assert domain_disabled.text.count("[IP-") == 2


# ---------------------------------------------------------------------------
# A5: inventory hostnames inside tables.
# ---------------------------------------------------------------------------


def test_inventory_hostnames_use_row_local_ip_and_numeric_evidence():
    # Generic all-caps header/OS cells keep their pre-existing СОКРАЩЕНИЯ
    # handling; these assertions stay focused on the hostname cell itself.
    for host in (HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE):
        result = Anonymizer().anonymize(inventory(host))
        assert host not in result.text
        assert host.split("-")[0] not in result.text
        assert "[УЗЕЛ-" in result.text
        assert "[ЗАДАЧА-" not in result.text
        # Exact right boundary: the complete cell value is replaced.
        assert re.search(r"\[УЗЕЛ-\d+\]", result.text)


def test_inventory_hostnames_use_existing_ip_markers_without_task_fragmentation():
    for host in (HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE):
        result = Anonymizer().anonymize(inventory(host, EXISTING_IP_MARKER))
        assert host not in result.text
        assert "[УЗЕЛ-" in result.text
        assert "[ЗАДАЧА-" not in result.text
        assert EXISTING_IP_MARKER in result.text


def test_inventory_hostname_right_boundary_and_no_partial_mask():
    # An over-long inventory-shaped cell value is left completely intact:
    # the grammar must never mask only a prefix of the token.
    overlong = "qx61-virt02" + "x" * 50
    result = Anonymizer().anonymize(inventory(overlong))
    assert overlong in result.text
    assert "[УЗЕЛ-" not in result.text

    # A punctuation-terminated host is captured whole, without the punctuation.
    row = TABLE + ROW.join(
        (
            CELL.join(("Сервер", "IP", "ОС", "CPU", "RAM", "Disk")),
            CELL.join((HOST_MULTI_SEGMENT + ",", INVENTORY_IP, "Synthetic OS (64-bit)", "32", "64", "144")),
        )
    ) + TABLE
    punctuated = Anonymizer().anonymize(row)
    assert HOST_MULTI_SEGMENT not in punctuated.text
    assert re.search(r"\[УЗЕЛ-\d+\],", punctuated.text)


def test_inventory_hostname_reuses_marker_and_keeps_case_identity():
    rows = TABLE + ROW.join(
        (
            CELL.join(("Сервер", "IP", "ОС", "CPU", "RAM", "Disk")),
            CELL.join((HOST_MULTI_SEGMENT, INVENTORY_IP, "Synthetic OS (64-bit)", "32", "64", "144")),
            CELL.join((HOST_MULTI_SEGMENT, "198.51.100.7", "Synthetic OS (64-bit)", "32", "64", "144")),
            CELL.join((HOST_MULTI_SEGMENT.upper(), "203.0.113.9", "Synthetic OS (64-bit)", "32", "64", "144")),
        )
    ) + TABLE
    result = Anonymizer().anonymize(rows)
    assert HOST_MULTI_SEGMENT not in result.text
    assert HOST_MULTI_SEGMENT.upper() not in result.text
    node_markers = set(re.findall(r"\[УЗЕЛ-\d+\]", result.text))
    # Two distinct source spellings keep distinct markers; the repeated
    # byte-identical value reuses one marker for both rows.
    assert len(node_markers) == 2
    assert len([value for value in result.mapping.values() if value == HOST_MULTI_SEGMENT]) == 1


def test_inventory_hostname_category_disable_without_relabel():
    result = Anonymizer(disabled_categories=["УЗЕЛ"]).anonymize(inventory(HOST_MULTI_SEGMENT))
    assert HOST_MULTI_SEGMENT in result.text
    assert "[УЗЕЛ-" not in result.text
    assert "[ЗАДАЧА-" not in result.text
    # The host token itself is not relabeled by the abbreviation fallback.
    assert HOST_MULTI_SEGMENT.split("-")[0] in result.text


def test_inventory_hostname_row_context_does_not_leak_across_sections():
    # A host-shaped value in an unrelated later table without row IP
    # evidence must stay intact.
    source = inventory(HOST_MULTI_SEGMENT) + "\n" + TABLE + ROW.join(
        (
            CELL.join(("Участник", "Роль")),
            CELL.join((HOST_COMPACT, "Наблюдатель")),
        )
    ) + TABLE
    result = Anonymizer().anonymize(source)
    assert HOST_MULTI_SEGMENT not in result.text
    # qxr77 is a participant name here, not a host: no row IP evidence.
    assert HOST_COMPACT in result.text


# ---------------------------------------------------------------------------
# A6: server lists outside tables (bounded block parser).
# ---------------------------------------------------------------------------


def test_server_list_outside_table_masks_whole_hostnames():
    source = server_list(HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE)
    result = Anonymizer().anonymize(source)
    for host in (HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE):
        assert host not in result.text
    assert result.text.count("[УЗЕЛ-") == 3
    assert "[ЗАДАЧА-" not in result.text
    assert "[СОКРАЩЕНИЯ-" not in result.text
    assert set(result.mapping.values()) == {HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE}


def test_server_list_accepts_heading_numbering_and_list_prefixes():
    for heading in (
        "Серверы:",
        # Exact approved singular heading «Сервер» (review B1 preserves it).
        "Сервер:",
        "Сервер",
        # Noun-phrase heading without a trailing colon stays valid.
        "Серверы региона",
        "3.2.1 Перечень серверов",
        "Список серверов объекта:",
        "Hostname",
        "Имя узла:",
        "2.4 Состав серверов:",
        "Хосты площадки:",
    ):
        result = Anonymizer().anonymize(server_list(HOST_MULTI_SEGMENT, heading=heading))
        assert HOST_MULTI_SEGMENT not in result.text, heading
        assert "[УЗЕЛ-" in result.text, heading


def test_server_list_allows_marker_only_and_record_lines_between_hosts():
    source = "\n".join(
        (
            "Серверы региона:",
            EXISTING_IP_MARKER,
            "[СОКРАЩЕНИЯ-2] [СИСТЕМА-1] (64-bit)",
            "32",
            "64",
            "144",
            HOST_COMPACT,
            INVENTORY_IP,
            "Synthetic OS (64-bit)",
            "32",
            "64",
            "144",
            HOST_MULTI_SEGMENT,
        )
    )
    result = Anonymizer().anonymize(source)
    assert HOST_COMPACT not in result.text
    assert HOST_MULTI_SEGMENT not in result.text
    assert result.text.count("[УЗЕЛ-") == 2
    assert EXISTING_IP_MARKER in result.text


def test_server_list_stops_at_substantive_prose():
    source = "\n".join(
        (
            "Серверы региона:",
            HOST_MULTI_SEGMENT,
            "Сервер работает штатно, замечаний нет.",
            "abc12",
            "def34",
        )
    )
    result = Anonymizer().anonymize(source)
    assert HOST_MULTI_SEGMENT not in result.text
    assert "abc12" in result.text
    assert "def34" in result.text
    assert result.text.count("[УЗЕЛ-") == 1


def test_server_list_stops_at_next_section_heading():
    source = "\n".join(
        (
            "Серверы региона:",
            HOST_MULTI_SEGMENT,
            "3. Маршрутизация сети",
            "abc12",
        )
    )
    result = Anonymizer().anonymize(source)
    assert HOST_MULTI_SEGMENT not in result.text
    assert "abc12" in result.text

    # A new server-list heading re-opens the block after the stop.
    reopened = "\n".join(
        (
            "Серверы региона:",
            HOST_MULTI_SEGMENT,
            "3. Маршрутизация сети",
            "abc12",
            "Серверы второго контура:",
            HOST_COMPACT,
        )
    )
    result = Anonymizer().anonymize(reopened)
    assert HOST_MULTI_SEGMENT not in result.text
    assert "abc12" in result.text
    assert HOST_COMPACT not in result.text


def test_ordinary_prose_does_not_open_a_server_list():
    source = "\n".join(
        (
            "Сервер работает штатно, замечаний нет.",
            "abc12",
            "def34",
        )
    )
    result = Anonymizer().anonymize(source)
    assert result.text == source


def test_generic_list_headings_do_not_open_a_server_list():
    # Review B1: a generic перечень/список/состав heading without explicit
    # server/host/VM semantics must not open the A6 gate, so host-shaped
    # Latin tokens in the following lines stay untouched.
    for heading in (
        "Перечень оборудования",
        "Список оборудования",
        "Состав работ",
        "Перечень работ",
        "2.3 Состав оборудования",
    ):
        source = "\n".join((heading, "abc12", "def34"))
        result = Anonymizer().anonymize(source)
        assert result.text == source, heading
        assert not result.mapping, heading


def test_plural_prose_is_rejected_as_a_server_list_heading():
    # Review B1: plural prose such as «Серверы работают штатно» is a
    # sentence, not a structural heading; host-shaped Latin tokens after
    # it must stay untouched.
    source = "\n".join(("Серверы работают штатно", "abc12", "def34"))
    result = Anonymizer().anonymize(source)
    assert result.text == source
    assert not result.mapping


def test_server_list_isolated_from_adjacent_sections():
    source = "\n".join(
        (
            "Приложение А.",
            "Лист согласования:",
            "abc12",
            "def34",
        )
    )
    result = Anonymizer().anonymize(source)
    assert result.text == source


def test_server_list_category_disable_without_relabel():
    source = server_list(HOST_MIXED_CASE, HOST_MULTI_SEGMENT)
    result = Anonymizer(disabled_categories=["УЗЕЛ"]).anonymize(source)
    assert HOST_MIXED_CASE in result.text
    assert HOST_MULTI_SEGMENT in result.text
    assert "[УЗЕЛ-" not in result.text
    assert "[ЗАДАЧА-" not in result.text
    assert "[СОКРАЩЕНИЯ-" not in result.text


def test_server_list_marker_reuse_and_case_identity():
    source = server_list(HOST_MULTI_SEGMENT, HOST_MULTI_SEGMENT, HOST_MULTI_SEGMENT.upper())
    result = Anonymizer().anonymize(source)
    assert result.text.count("[УЗЕЛ-") == 3
    markers = set(re.findall(r"\[УЗЕЛ-\d+\]", result.text))
    assert len(markers) == 2
    assert sorted(result.mapping.values()) == sorted(
        [HOST_MULTI_SEGMENT, HOST_MULTI_SEGMENT.upper()]
    )


def test_server_list_full_boundary_and_no_partial_mask():
    source = "\n".join(
        (
            "Серверы региона:",
            "- " + HOST_MULTI_SEGMENT,
            "1. " + HOST_COMPACT,
            HOST_MULTI_SEGMENT + ",",
        )
    )
    result = Anonymizer().anonymize(source)
    assert HOST_MULTI_SEGMENT not in result.text
    assert HOST_COMPACT not in result.text
    assert re.search(r"- \[УЗЕЛ-\d+\]", result.text)
    assert re.search(r"1\. \[УЗЕЛ-\d+\]", result.text)
    assert re.search(r"\[УЗЕЛ-\d+\],", result.text)


def test_server_list_second_pass_idempotence():
    source = server_list(HOST_COMPACT, HOST_MULTI_SEGMENT, HOST_MIXED_CASE)
    first = Anonymizer().anonymize(source)
    second = Anonymizer().anonymize(first.text)
    assert second.text == first.text
    assert not second.mapping
    assert not re.search(r"\[[^\]]*\[", second.text)


# ---------------------------------------------------------------------------
# A7: subnet prefix adjacent to an existing marker.
# ---------------------------------------------------------------------------


def test_marker_adjacent_prefix_after_ip_marker_is_masked():
    source = f"Подсеть {EXISTING_IP_MARKER}/19 используется для управления."
    result = Anonymizer().anonymize(source)
    assert "/19" not in result.text
    assert EXISTING_IP_MARKER in result.text
    assert result.text.count("[IP-") >= 2
    assert "/19" in result.mapping.values()


def test_marker_adjacent_prefix_after_domain_marker_is_masked():
    source = "Диапазон [ДОМЕН-2]/24 выделен для стенда."
    result = Anonymizer().anonymize(source)
    assert "/24" not in result.text
    assert "[ДОМЕН-2]" in result.text
    assert result.text.count("[ДОМЕН-") >= 2
    assert "/24" in result.mapping.values()


def test_marker_adjacent_prefix_after_site_label_marker_is_masked():
    source = "Список подсетей сайта [ПРОГРАММА-3]/24 передан заказчику."
    result = Anonymizer().anonymize(source)
    assert "/24" not in result.text
    assert "[ПРОГРАММА-3]" in result.text
    assert result.text.count("[ПРОГРАММА-") >= 2
    assert "/24" in result.mapping.values()


def test_marker_adjacent_prefix_negatives_stay_untouched():
    source = "\n".join(
        (
            "Результат деления: 1/2 от объёма.",
            "Путь опубликован: [ССЫЛКА-1]/24 не является префиксом.",
            "Ответственный: [ФИО-2]/24 вне контекста.",
            "Версия стенда [ПРОГРАММА-4]/24 указана отдельно.",
            "Дефекты [ЗАДАЧА-1]/1524/1533 закрыты.",
            "Протокол от [ДОКУМЕНТ-5]/2026 подписан.",
            "Порт [ПОРТ-9]/10051 открыт.",
        )
    )
    result = Anonymizer().anonymize(source)
    assert result.text == source


def test_marker_adjacent_prefix_reversibility_and_idempotence():
    source = f"Подсеть {EXISTING_IP_MARKER}/19 используется.\nСайт [ДОМЕН-2]/24 выделен."
    first = Anonymizer().anonymize(source)
    restored = first.text
    for marker, value in first.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source
    second = Anonymizer().anonymize(first.text)
    assert second.text == first.text
    assert not second.mapping


def test_marker_adjacent_prefix_category_disable_keeps_suffix_without_relabel():
    source = f"Подсеть {EXISTING_IP_MARKER}/19 используется."
    result = Anonymizer(disabled_categories=["IP"]).anonymize(source)
    assert f"{EXISTING_IP_MARKER}/19" in result.text
    assert "[МЕТРИКА-" not in result.text
    assert "[ДОКУМЕНТ-" not in result.text


def test_marker_adjacent_prefix_whitelist_keeps_suffix_without_relabel():
    # Review B3: a whitelisted prefix value is honoured by A7 and stays
    # untouched, without a relabel into any other category.
    source = f"Подсеть {EXISTING_IP_MARKER}/19 используется для управления."
    result = Anonymizer(whitelist=["/19"]).anonymize(source)
    assert result.text == source
    assert not result.mapping
    assert "/19" not in result.mapping.values()
    assert "[МЕТРИКА-" not in result.text
    assert "[ДОКУМЕНТ-" not in result.text
    assert "[ЗАДАЧА-" not in result.text


def test_marker_adjacent_prefix_only_valid_prefix_lengths():
    for prefix in ("/0", "/7", "/33", "/64"):
        source = f"Подсеть {EXISTING_IP_MARKER}{prefix} описана."
        result = Anonymizer().anonymize(source)
        assert prefix in result.text
    for prefix in ("/8", "/16", "/24", "/32"):
        source = f"Подсеть {EXISTING_IP_MARKER}{prefix} описана."
        result = Anonymizer().anonymize(source)
        assert prefix not in result.text


# ---------------------------------------------------------------------------
# DOCX: split runs, split cells, lists, restore and package residue.
# ---------------------------------------------------------------------------


def test_docx_split_run_network_inventory_roundtrip(tmp_path: Path):
    source = tmp_path / "source.docx"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    document = Document()
    paragraph = document.add_paragraph()
    for value in (FQDN_NUMERIC_FIRST, REVERSE_ZONE_DEEP, CIDR_DOCUMENTATION):
        for character in value:
            paragraph.add_run(character)
        paragraph.add_run("\n")
    table = document.add_table(rows=2, cols=6)
    for index, heading in enumerate(("Сервер", "IP", "ОС", "CPU", "RAM", "Disk")):
        table.rows[0].cells[index].text = heading
    values = (HOST_MULTI_SEGMENT, INVENTORY_IP, "Synthetic OS (64-bit)", "32", "64", "144")
    for index, value in enumerate(values):
        cell = table.rows[1].cells[index]
        cell.text = ""
        for character in value:
            cell.paragraphs[0].add_run(character)
    document.save(source)
    source_bytes = source.read_bytes()

    result = DocxProcessor().anonymize(source, anonymized)
    output = Document(anonymized)
    text = "\n".join(paragraph.text for paragraph in output.paragraphs)
    text += "\n" + "\n".join(cell.text for row in output.tables[0].rows for cell in row.cells)
    for value in (FQDN_NUMERIC_FIRST, REVERSE_ZONE_DEEP, CIDR_DOCUMENTATION, HOST_MULTI_SEGMENT):
        assert value not in text
    assert "[ДОМЕН-" in text
    assert "[IP-" in text
    assert "[УЗЕЛ-" in text
    assert source.read_bytes() == source_bytes

    DocxProcessor().restore(anonymized, restored, result.mapping)
    restored_document = Document(restored)
    assert [paragraph.text for paragraph in restored_document.paragraphs] == [
        paragraph.text for paragraph in document.paragraphs
    ]
    assert [
        [cell.text for cell in row.cells]
        for table in restored_document.tables
        for row in table.rows
    ] == [
        [cell.text for cell in row.cells]
        for table in document.tables
        for row in table.rows
    ]


def test_docx_server_list_roundtrip_with_split_runs(tmp_path: Path):
    source = tmp_path / "list-source.docx"
    anonymized = tmp_path / "list-anonymized.docx"
    restored = tmp_path / "list-restored.docx"
    document = Document()
    document.add_paragraph("Серверы регионального контура:")
    split_paragraph = document.add_paragraph()
    for fragment in ("qx", "61-virt", "01"):
        split_paragraph.add_run(fragment)
    document.add_paragraph(HOST_COMPACT)
    document.add_paragraph(HOST_MIXED_CASE)
    document.add_paragraph("Сервер работает штатно, замечаний нет.")
    document.add_paragraph("abc12")
    document.save(source)
    source_bytes = source.read_bytes()

    result = DocxProcessor().anonymize(source, anonymized)
    output = Document(anonymized)
    paragraphs = [paragraph.text for paragraph in output.paragraphs]
    for host in (HOST_MULTI_SEGMENT, HOST_COMPACT, HOST_MIXED_CASE):
        assert host not in paragraphs
    # Prose and the adjacent-section token stay intact.
    assert "Сервер работает штатно, замечаний нет." in paragraphs
    assert "abc12" in paragraphs
    # Whole-hostname markers, no ЗАДАЧА fragmentation.
    assert "[ЗАДАЧА-" not in "\n".join(paragraphs)
    assert len([p for p in paragraphs if re.fullmatch(r"\[УЗЕЛ-\d+\]", p)]) == 3
    assert source.read_bytes() == source_bytes

    DocxProcessor().restore(anonymized, restored, result.mapping)
    restored_document = Document(restored)
    assert [paragraph.text for paragraph in restored_document.paragraphs] == [
        paragraph.text for paragraph in document.paragraphs
    ]


def test_docx_output_package_has_no_source_network_residue(tmp_path: Path):
    source = tmp_path / "residue-source.docx"
    anonymized = tmp_path / "residue-anonymized.docx"
    document = Document()
    document.add_paragraph(f"Узел {FQDN_NUMERIC_FIRST} и подсеть {CIDR_DOCUMENTATION} описаны.")
    document.add_paragraph(f"Зона {REVERSE_ZONE_DEEP} и адрес {IPV4_LEADING_ZERO} учтены.")
    table = document.add_table(rows=2, cols=6)
    for index, heading in enumerate(("Сервер", "IP", "ОС", "CPU", "RAM", "Disk")):
        table.rows[0].cells[index].text = heading
    values = (HOST_MULTI_SEGMENT, INVENTORY_IP, "Synthetic OS (64-bit)", "32", "64", "144")
    for index, value in enumerate(values):
        table.rows[1].cells[index].text = value
    document.add_paragraph("Серверы региона:")
    document.add_paragraph(HOST_COMPACT)
    document.add_paragraph(HOST_MIXED_CASE)
    document.save(source)

    DocxProcessor().anonymize(source, anonymized)
    forbidden = (
        FQDN_NUMERIC_FIRST,
        REVERSE_ZONE_DEEP,
        CIDR_DOCUMENTATION,
        IPV4_LEADING_ZERO,
        HOST_MULTI_SEGMENT,
        HOST_COMPACT,
        HOST_MIXED_CASE,
    )
    with ZipFile(anonymized) as package:
        for name in package.namelist():
            if name.endswith(".xml"):
                content = package.read(name).decode("utf-8", "replace")
                for value in forbidden:
                    assert value not in content, (name, value)
    visible = "\n".join(paragraph.text for paragraph in Document(anonymized).paragraphs)
    for value in forbidden:
        assert value not in visible


def test_docx_second_pass_does_not_create_nested_markers(tmp_path: Path):
    source = tmp_path / "idempotence-source.docx"
    first_output = tmp_path / "idempotence-first.docx"
    second_output = tmp_path / "idempotence-second.docx"
    document = Document()
    document.add_paragraph(f"Узел {FQDN_NUMERIC_FIRST} и подсеть {CIDR_DOCUMENTATION} описаны.")
    document.add_paragraph("Серверы региона:")
    document.add_paragraph(HOST_COMPACT)
    document.add_paragraph(HOST_MULTI_SEGMENT)
    document.save(source)

    first = DocxProcessor().anonymize(source, first_output)
    first_markers = set(re.findall(r"\[[А-ЯA-ZЁа-яё][^\]]*-\d+\]", _visible_text(first_output)))
    second = DocxProcessor().anonymize(first_output, second_output)
    second_markers = set(re.findall(r"\[[А-ЯA-ZЁа-яё][^\]]*-\d+\]", _visible_text(second_output)))
    assert first_markers
    assert second_markers == first_markers
    assert not second.mapping
    assert not re.search(r"\[[^\]]*\[", _visible_text(second_output))


def _visible_text(path: Path) -> str:
    return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
