from pathlib import Path

from local_anonymizer.engine import Anonymizer


def test_acceptance_sample_redacts_required_values_and_preserves_non_sensitive_numerics():
    text = Path("acceptance_sample.txt").read_text(encoding="utf-8")
    result = Anonymizer().anonymize(text)
    output = result.text

    expected_markers = [
        "[ФИО-1]", "[ОРГАНИЗАЦИЯ-1]", "[ПОЧТА-1]", "[ТЕЛЕФОН-1]",
        "[ТЕЛЕФОН-2]", "[АККАУНТ-1]", "[ДОМЕН-1]", "[IP-1]", "[IP-2]",
        "[MAC-1]", "[ССЫЛКА-1]", "[СЗИ-1]", "[СЗИ-2]", "[ЗАДАЧА-1]",
        "[уязвимость]", "[ИНН-1]", "[КПП-1]", "[СНИЛС-1]", "[СЧЁТ-1]",
        "[КАРТА-1]", "[КАДАСТР-1]", "[ГОСНОМЕР-1]", "[ТАБЕЛЬНЫЙ-1]",
        "[ДОГОВОР-1]", "[СУММА-1]", "[СУММА-2]", "[СТАВКА-1]",
        "[ДАТА-РОЖДЕНИЯ-1]", "[ФИО-2]", "[ФИО-3]", "[ПОРТ-1]",
    ]
    for marker in expected_markers:
        assert marker in output, marker
    assert output.count("[ФИО-1]") == 1
    assert result.mapping["[ФИО-3]"] == "Иванов"
    assert output.count("[ОРГАНИЗАЦИЯ-1]") >= 2
    assert "1.7.5.16" in output
    assert "порт [ПОРТ-1]" in output
    assert result.mapping["[ПОРТ-1]"] == "8080"
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }
    assert {"SLA", "НДС"} <= abbreviation_values
    for secret in ("Qwerty123!", "str0ngggg", "Str0ngpassw"):
        assert secret not in output
    assert output.count("(удалено") >= 3
    assert sum(1 for part in result.parts if part.get("secret")) >= 3
    assert all(secret not in str(result.mapping) for secret in ("Qwerty123!", "str0ngggg", "Str0ngpassw"))


def test_device_and_network_identifiers_use_validated_local_rules():
    source = (
        "IMEI: 123456789012347; ошибочный IMEI: 123456789012345; "
        "MAC Cisco: a1b2.c3d4.e5f6; сеть: 2001:db8::/32"
    )

    result = Anonymizer().anonymize(source)

    assert "123456789012347" not in result.text
    assert result.mapping["[IMEI-1]"] == "123456789012347"
    assert "123456789012345" in result.text
    assert "a1b2.c3d4.e5f6" not in result.text
    assert result.mapping["[MAC-1]"] == "a1b2.c3d4.e5f6"
    assert "2001:db8::/32" not in result.text
    assert result.mapping["[IP-1]"] == "2001:db8::/32"


def test_domains_glued_to_toc_page_numbers_are_redacted_as_complete_domains():
    source = "\n".join((
        "2.2 Общие данные по домену qzxsafe.test11",
        "2.3 Общие данные по домену go.qzxsafe.test14",
        "2.4 Общие данные по домену rf.qzxsafe.test19",
    ))

    result = Anonymizer().anonymize(source)

    assert result.text.splitlines() == [
        "2.2 Общие данные по домену [ДОМЕН-1]11",
        "2.3 Общие данные по домену [ДОМЕН-2]14",
        "2.4 Общие данные по домену [ДОМЕН-3]19",
    ]
    assert result.mapping == {
        "[ДОМЕН-1]": "qzxsafe.test",
        "[ДОМЕН-2]": "go.qzxsafe.test",
        "[ДОМЕН-3]": "rf.qzxsafe.test",
    }


def test_contextual_network_ports_are_reversible_and_bounded():
    source = (
        "порт 8080; Port: 8443; TCP-порт 5432; диапазон портов 8000-8002; сервис 53/udp; "
        "192.0.2.10:22; node.qzxsafe.test:636; srv-db-01:3306; "
        "[2001:db8::1]:9443. "
        "Без контекста: 8081, 12:30, версия 1.8.18, порт 0, port 65536."
    )

    result = Anonymizer().anonymize(source)

    assert set(value for marker, value in result.mapping.items() if marker.startswith("[ПОРТ-")) == {
        "8080", "8443", "5432", "8000", "8002", "53", "22", "636", "3306", "9443",
    }
    assert result.counts["ПОРТ"] == 10
    for leaked in (
        "порт 8080", "Port: 8443", "порт 5432", "портов 8000-8002", "53/udp",
        "192.0.2.10:22", "node.qzxsafe.test:636", "srv-db-01:3306", "]:9443",
    ):
        assert leaked not in result.text
    for public in ("8081", "12:30", "1.8.18", "порт 0", "port 65536"):
        assert public in result.text


def test_port_priority_disabled_category_and_compact_marker_are_explicit():
    source = "https://qzxsafe.test:9443/path порт 8080, 198.51.100.4:8080"

    result = Anonymizer().anonymize(source)
    assert result.mapping["[ССЫЛКА-1]"] == "https://qzxsafe.test:9443/path"
    assert "9443" not in result.text
    assert result.text.count("[ПОРТ-1]") == 2
    assert result.mapping["[ПОРТ-1]"] == "8080"

    disabled = Anonymizer(disabled_categories={"ПОРТ"}).anonymize(source)
    assert "порт 8080" in disabled.text
    assert ":8080" in disabled.text
    assert "[ПОРТ-" not in disabled.text
    assert "[ССЫЛКА-1]" in disabled.text
    assert "[IP-1]:8080" in disabled.text

    compact = Anonymizer(compact_markers=True).anonymize("порт 8080")
    assert compact.text == "порт [ПРТ-1]"
    assert compact.mapping == {"[ПРТ-1]": "8080"}


def test_numeric_credentials_are_not_downgraded_to_network_ports():
    source = "login user1:1234; endpoint srv-db-01:3306"

    result = Anonymizer().anonymize(source)

    assert "user1:1234" not in result.text
    assert "user1:1234" not in repr(result.mapping)
    assert "(удалено: учётные данные)" in result.text
    assert result.mapping["[ПОРТ-1]"] == "3306"


def test_unlabelled_fifteen_digit_number_is_not_assumed_to_be_imei():
    source = "Номер записи 123456789012347"

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert not result.mapping


def test_labelled_russian_street_address_redacts_street_house_city_and_index():
    source = (
        "Работы должны быть выполнены по адресу "
        "Профсоюзная ул., 125А, Москва, 17630."
    )

    result = Anonymizer().anonymize(source)

    assert result.text == "Работы должны быть выполнены по адресу [АДРЕС-1], [ИНДЕКС-1]."
    assert result.mapping == {
        "[АДРЕС-1]": "Профсоюзная ул., 125А, Москва",
        "[ИНДЕКС-1]": "17630",
    }
    assert result.counts["АДРЕС"] == 1
    assert result.counts["ИНДЕКС"] == 1
    for leaked in ("Профсоюзная", "125А", "Москва", "17630"):
        assert leaked not in result.text


def test_explicit_postal_index_is_redacted_but_unlabelled_numbers_are_not():
    source = "Почтовый индекс: 630099. Номер заявки 17630. Сборка 123456."

    result = Anonymizer().anonymize(source)

    assert result.text == (
        "Почтовый индекс: [ИНДЕКС-1]. Номер заявки 17630. Сборка 123456."
    )
    assert result.mapping == {"[ИНДЕКС-1]": "630099"}


def test_postal_index_category_can_be_disabled_inside_a_labelled_address():
    source = "Работы по адресу Профсоюзная ул., 125А, Москва, 17630."

    result = Anonymizer(disabled_categories={"ИНДЕКС"}).anonymize(source)

    assert result.text == "Работы по адресу [АДРЕС-1], 17630."
    assert "[ИНДЕКС-" not in result.text


def test_email_address_wording_is_not_mistaken_for_a_postal_address():
    source = "Ответ направить по адресу электронной почты user@example.test."

    result = Anonymizer().anonymize(source)

    assert "по адресу электронной почты" in result.text
    assert "[АДРЕС-" not in result.text


def test_compact_markers_reduce_placeholder_width_without_changing_restore_mapping():
    source = "Иванов Иван Иванович работает в ООО «Ромашка»."

    result = Anonymizer(compact_markers=True).anonymize(source)

    assert "[Ф-1]" in result.text
    assert "[ОРГ-1]" in result.text
    assert "[ФИО-1]" not in result.text
    assert "[ОРГАНИЗАЦИЯ-1]" not in result.text
    assert result.mapping["[Ф-1]"] == "Иванов Иван Иванович"
    assert result.mapping["[ОРГ-1]"] == "ООО «Ромашка»"


def test_canonical_aliases_reuse_markers_and_unknown_candidates_are_reported():
    result = Anonymizer().anonymize("ООО «Ромашка». Ромашка. Инженер отдела ИБ Кудряшов.")
    assert result.text.count("[ОРГАНИЗАЦИЯ-1]") == 2
    assert "Кудряшов" in result.candidates


def test_inflected_surname_is_not_merged_with_full_name_without_strong_identity_evidence():
    result = Anonymizer().anonymize(
        "Опарин Алексей Викторович подписал акт. Ответ от Опарина получен."
    )

    assert result.text == "[ФИО-1] подписал акт. Ответ от [ФИО-2] получен."
    assert result.mapping == {
        "[ФИО-1]": "Опарин Алексей Викторович",
        "[ФИО-2]": "Опарина",
    }


def test_enterprise_infrastructure_values_from_real_report_are_anonymized():
    sep = "\ufdd0"
    source = sep.join([
        "NetBIOS-имя", "OVBPORT",
        "Источник времени для леса известен — 172.17.4.100.",
        "Площадки ЦА", "Волгоград", "Астрахань",
        "Локальный DNS-сервер", "adc4", "adc8", "ad-dns-06", "ad-dns-10",
        "Полное имя", "adc8.ovbport.net",
        "Платформа виртуализации", "zVirt",
        "Производитель (дистрибутив)", "Orion Soft",
        "Примечание", "В процессе перехода с ESXi на zVirt",
        "Имя объекта", "ovbport-ADC8-CA",
        "DN", "CN=ovbport-ADC8-CA,CN=AIA,CN=Public Key Services,CN=Services,CN=Configuration,DC=ovbport,DC=net",
        "Имя ЦС", "vog-DC001-CA", "Имя ЦС", "asf-ast-DC1-CA",
        "Имена серверов / IP-адреса", "oco-srkv/172.17.60.113\nCyberBackUp/172.17.60.120\nCyber2Data/172.17.60.125",
        "Имя", "SamAccountName", "Burganov", "Burganov", "cherevach", "cherevach",
        "Администратор", "Администратор",
    ])

    result = Anonymizer().anonymize(source)

    leaked = [
        "OVBPORT", "172.17.4.100", "Волгоград", "Астрахань",
        "adc4", "adc8", "ad-dns-06", "ad-dns-10", "ovbport.net", "zVirt", "Orion Soft",
        "ovbport-ADC8-CA", "DC=ovbport", "vog-DC001-CA", "asf-ast-DC1-CA",
        "oco-srkv", "CyberBackUp", "Cyber2Data", "Burganov", "cherevach",
        "Администратор",
    ]
    assert all(value.casefold() not in result.text.casefold() for value in leaked)
    assert result.text.count(sep) == source.count(sep)
    assert result.counts["IP"] == 4
    assert result.counts["ГОРОД"] == 2
    assert result.counts["ЛОГИН"] >= 6


def test_contextual_value_and_abbreviation_preserve_office_fragment_boundary():
    source = "NetBIOS-имя\ufdd0OVBPORT"

    result = Anonymizer().anonymize(source)

    assert result.text == "[СОКРАЩЕНИЯ-1]\ufdd0[УЗЕЛ-1]"
    assert result.mapping["[СОКРАЩЕНИЯ-1]"] == "NetBIOS-имя"
    assert result.mapping["[УЗЕЛ-1]"] == "OVBPORT"
    assert result.text.count("\ufdd0") == 1


def test_explicit_server_labels_anonymize_single_label_hostnames():
    cases = [
        ("Сервер: OVBPORT", "OVBPORT"),
        ("Имя узла: APPNODE", "APPNODE"),
        ("Хост\ufdd0DBSERVER", "DBSERVER"),
    ]

    for source, hostname in cases:
        result = Anonymizer().anonymize(source)

        assert hostname not in result.text
        assert result.text.endswith("[УЗЕЛ-1]")
        assert result.mapping == {"[УЗЕЛ-1]": hostname}


def test_lowercase_hyphenated_directory_controller_name_is_a_node_not_a_secret():
    source = "qzlab-dc01"

    result = Anonymizer().anonymize(source)

    assert result.text == "[УЗЕЛ-1]"
    assert result.mapping == {"[УЗЕЛ-1]": source}
    assert "удалено" not in result.text.casefold()


def test_underscored_dns_fqdn_is_a_node_without_matching_embedded_identifiers():
    value = "_locator.synthetic.example"
    source = (
        f"{value} "
        f"admin@{value} "
        f"https://{value}/path "
        f"C:\\inventory\\{value} "
        f"parent.{value}"
    )

    result = Anonymizer().anonymize(source)

    assert result.text.startswith("[УЗЕЛ-1] ")
    assert result.mapping["[УЗЕЛ-1]"] == value
    assert result.text.count("[УЗЕЛ-") == 1
    assert result.text.count("[ПОЧТА-") == 1
    assert result.text.count("[ССЫЛКА-") == 1
    assert result.text.count("[ПУТЬ-") == 1
    node_values = [
        original
        for marker, original in result.mapping.items()
        if marker.startswith("[УЗЕЛ-")
    ]
    assert node_values == [value]


def test_underscored_dns_fqdn_respects_disabled_node_category():
    value = "_locator.synthetic.example"

    result = Anonymizer(disabled_categories={"УЗЕЛ"}).anonymize(value)

    assert result.text == value
    assert result.mapping == {}


def test_explicit_server_labels_accept_hostname_immediately_after_colon():
    cases = [
        ("Сервер:XQNODE", "XQNODE"),
        ("Имя узла:YQNODE", "YQNODE"),
        ("Хост:ZQNODE", "ZQNODE"),
    ]

    for source, hostname in cases:
        result = Anonymizer().anonymize(source)

        assert hostname not in result.text
        assert result.text.endswith("[УЗЕЛ-1]")
        assert result.mapping == {"[УЗЕЛ-1]": hostname}


def test_explicit_server_labels_accept_unicode_whitespace_after_colon():
    for separator in ("\u00a0", "\u2009"):
        source = f"Сервер:{separator}UNICODEHOST"

        result = Anonymizer().anonymize(source)

        assert result.text == f"Сервер:{separator}[УЗЕЛ-1]"
        assert result.mapping == {"[УЗЕЛ-1]": "UNICODEHOST"}


def test_abbreviation_replaces_complete_unicode_token_after_server_label():
    anonymizer = Anonymizer()
    for suffix in ("é", "\u0301"):
        source = f"Сервер:NODEABC{suffix};"
        result = anonymizer.anonymize(source)

        assert result.text == "Сервер:[СОКРАЩЕНИЯ-1];"
        assert result.mapping == {"[СОКРАЩЕНИЯ-1]": f"NODEABC{suffix}"}

    mixed_script = "Сервер:NODEABCЖ;"
    result = anonymizer.anonymize(mixed_script)
    assert result.text == "Сервер:[СОКРАЩЕНИЯ-1];"
    assert result.mapping == {"[СОКРАЩЕНИЯ-1]": "NODEABCЖ"}


def test_server_label_case_variants_receive_distinct_reversible_markers():
    source = "Сервер:NodeABC; Хост:NODEABC"

    result = Anonymizer().anonymize(source)

    assert result.text == "Сервер:[УЗЕЛ-1]; Хост:[УЗЕЛ-2]"
    assert result.mapping == {"[УЗЕЛ-1]": "NodeABC", "[УЗЕЛ-2]": "NODEABC"}
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_explicit_server_label_replaces_entire_valid_long_hostname():
    hostname = "NODE" + "A" * 35
    source = f"Сервер:{hostname}"

    result = Anonymizer().anonymize(source)

    assert hostname not in result.text
    assert result.text == "Сервер:[УЗЕЛ-1]"
    assert result.mapping == {"[УЗЕЛ-1]": hostname}
    assert result.text.replace("[УЗЕЛ-1]", result.mapping["[УЗЕЛ-1]"]) == source


def test_explicit_server_label_never_partially_replaces_long_identifier():
    hostname = "NODE" + "B" * 76
    source = f"Хост: {hostname};"

    result = Anonymizer().anonymize(source)

    assert result.text == "Хост: [УЗЕЛ-1];"
    assert result.mapping == {"[УЗЕЛ-1]": hostname}


def test_server_label_rule_does_not_treat_prose_as_a_hostname_field():
    source = "Сервер работает стабильно, а хост указан в приложении."

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_server_names_with_site_and_role_segments_are_anonymized():
    server_names = [
        "vog-dc-0001",
        "asf-dns-0001",
        "ovb-dhcp-0001",
        "stw-fs-0001",
        "mrv-web-0001",
        "ovb-RDP-0001",
        "tjm-app-0001",
        "pee-db-0001",
    ]
    source = "Справочник серверов: " + ", ".join(server_names)

    result = Anonymizer().anonymize(source)

    assert all(name.casefold() not in result.text.casefold() for name in server_names)
    assert result.text.count("[УЗЕЛ-") == len(server_names)


def test_server_names_from_naming_standard_examples_are_anonymized():
    server_names = [
        "vog-dcv-0001",
        "ovb-hv-0001",
        "pee-pk-0001",
        "gdx-nb-0001",
        "kej-mon-0001",
        "uud-bak-0001",
        "vog-print-0001",
        "tof-scud-0001",
        "ovb-studio-0001",
        "vog-dbv-0001",
        "vog-pk-0001",
        "vog-nb-0001",
        "vog-mfu-0001",
    ]
    source = "\n".join(server_names)

    result = Anonymizer().anonymize(source)

    assert all(name not in result.text for name in server_names)
    assert result.text.count("[УЗЕЛ-") == len(server_names)
    assert set(result.mapping.values()) == set(server_names)


def test_organization_with_nested_russian_quotes_is_anonymized():
    organization = "АО «Международный аэропорт „Саранск“»"

    result = Anonymizer().anonymize(organization)

    assert organization not in result.text
    assert result.text == "[ОРГАНИЗАЦИЯ-1]"
    assert result.mapping == {"[ОРГАНИЗАЦИЯ-1]": organization}


def test_server_name_rule_does_not_capture_generic_hyphenated_identifiers():
    source = "Документ abc-report-0001 и задача proj-task-0002 остаются текстом."

    result = Anonymizer().anonymize(source)

    assert "abc-report-0001" in result.text
    assert "proj-task-0002" in result.text


def test_contextual_host_inventory_redacts_short_hostnames_without_digits():
    sep = "\ufdd0"
    source = sep.join([
        "Имя хоста", "IP-адрес", "vCPU", "RAM",
        "lab-nas", "[IP-74]", "32", "128",
        "vm-pc", "[IP-75]", "16", "32",
        "Повторное упоминание узла lab-nas в примечании",
    ])

    result = Anonymizer().anonymize(source)

    assert "lab-nas" not in result.text
    assert "vm-pc" not in result.text
    assert result.text.count("[УЗЕЛ-") == 3
    assert result.text.count("[УЗЕЛ-1]") == 2
    assert result.text.count(sep) == source.count(sep)


def test_netbios_table_row_redacts_every_site_value():
    sep = "\ufdd0"
    source = sep.join([
        "Параметр", "Площадка 1", "Площадка 2", "Площадка 3",
        "NetBIOS", "ALPHAHQ", "BETA-LAB", "GAMMA_AST",
        "ОС контроллеров", "Windows Server", "Windows Server", "Windows Server",
    ])

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in ("ALPHAHQ", "BETA-LAB", "GAMMA_AST"))
    assert result.text.count("[УЗЕЛ-") == 3
    assert result.text.count(sep) == source.count(sep)


def test_ad_ou_inventory_redacts_complete_client_specific_paths():
    sep = "\ufdd0"
    values = [
        "Computers_ACME/Production/Site-A",
        "Servers/Legacy-RDP",
        "Computers/ACME-Finance",
    ]
    source = sep.join([
        "OU или контейнер AD", "Компьютерных УЗ", "Включено", "Отключено",
        values[0], "21", "21", "0",
        values[1], "12", "11", "1",
        values[2], "5", "5", "0",
        f"Описание структуры {values[1]}",
    ])

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in values)
    assert result.text.count("[СТРУКТУРА-AD-") == 4
    assert "Servers/Legacy-RDP" not in result.text
    assert result.text.count(sep) == source.count(sep)


def test_ad_ou_inventory_redacts_standalone_root_container_names():
    sep = "\ufdd0"
    values = ["Domain Controllers", "NAS_VOG", "Computers_VOG"]
    source = sep.join([
        "OU или контейнер AD", "Компьютерных УЗ", "Включено", "Отключено",
        "Computers_VOG/Production/OMO", "2", "2", "0",
        values[0], "2", "2", "0",
        values[1], "2", "2", "0",
        "Computers_ADM/Igor_Test", "1", "1", "0",
        values[2], "1", "1", "0",
        "Computers_VOG/BMO", "1", "1", "0",
    ])

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in values)
    assert result.text.count("[СТРУКТУРА-AD-") == 6
    assert all(metric in result.text for metric in ("2", "1", "0"))
    assert result.text.count(sep) == source.count(sep)


def test_software_inventory_redacts_each_product_name_but_preserves_metrics():
    sep = "\ufdd0"
    products = ["Example Secure Client", "Northwind Banking Plug-in", "Contoso Remote Token"]
    source = sep.join([
        "Инвентаризация программного обеспечения", "Наименование ПО", "Установок", "Доля",
        products[0], "10", "1,6%",
        products[1], "4", "0,6%",
        products[2], "3", "0,5%",
        f"Примечание: модуль {products[0]} требует настройки",
    ])

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in products)
    assert result.text.count("[ПРОГРАММА-") == 4
    assert products[0] not in result.text
    assert all(metric in result.text for metric in ("10", "1,6%", "4", "0,6%", "3", "0,5%"))


def test_windows_to_alse_software_table_redacts_both_product_columns():
    sep = "\ufdd0"
    row_boundary = "\ufdd0\ufdd2\ufdd0"
    windows_products = [
        "Microsoft Office",
        "Яндекс Браузер",
        "Агент администрирования Kaspersky Security Center",
        "7-Zip",
        "DameWare Mini Remote Control",
    ]
    linux_products = [
        "LibreOffice, пакет libreoffice",
        "Mozilla Firefox ESR, пакет firefox-esr",
        "Kaspersky Security Center Network Agent for Linux",
        "7-Zip, пакет 7zip",
        "Remmina и TigerVNC",
    ]
    statuses = [
        "Да — Astra",
        "Совместимость подтверждена внутренним тестированием",
        "Нет в перечне Astra; дистрибутив производителя",
        "Доступен в штатном репозитории",
        "Ручная установка по инструкции поставщика",
    ]
    table = row_boundary.join([
        sep.join([
            "Исходное Windows-ПО",
            "Вариант для ALSE / Linux",
            "Статус аналогов и наличие в репозитории Astra",
        ]),
        *[sep.join(row) for row in zip(windows_products, linux_products, statuses)],
    ])
    boundary = "\ufdd0\ufdd1\ufdd0"
    source = boundary + table + boundary

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in windows_products + linux_products)
    assert all(status in result.text for status in statuses)
    assert len([value for value in result.mapping.values() if value in windows_products + linux_products]) == 10
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_windows_to_alse_software_cell_redacts_nonsecret_remainder_around_secret():
    sep = "\ufdd0"
    row_boundary = "\ufdd0\ufdd2\ufdd0"
    boundary = "\ufdd0\ufdd1\ufdd0"
    software = "SecureSuite TOPSECRET Management Agent"
    table = row_boundary.join([
        sep.join([
            "Исходное Windows-ПО",
            "Вариант для ALSE / Linux",
            "Статус аналогов и наличие в репозитории Astra",
        ]),
        sep.join([software, "Safe Alternative", "Любой статус"]),
    ])

    result = Anonymizer(user_dictionary={"TOPSECRET": "SECRET"}).anonymize(
        boundary + table + boundary
    )

    assert "TOPSECRET" not in result.text
    assert "SecureSuite" not in result.text
    assert "Management Agent" not in result.text
    assert "Safe Alternative" not in result.text
    assert "(удалено)" in result.text
    assert all("TOPSECRET" not in value for value in result.mapping.values())


def test_windows_to_alse_software_cell_redacts_short_and_numeric_secret_remainders():
    sep = "\ufdd0"
    row_boundary = "\ufdd0\ufdd2\ufdd0"
    boundary = "\ufdd0\ufdd1\ufdd0"
    table = row_boundary.join([
        sep.join([
            "Исходное Windows-ПО",
            "Вариант для ALSE / Linux",
            "Статус аналогов и наличие в репозитории Astra",
        ]),
        sep.join(["A TOPSECRET B", "TOPSECRET 2025", "Любой статус"]),
    ])

    result = Anonymizer(user_dictionary={"TOPSECRET": "SECRET"}).anonymize(
        boundary + table + boundary
    )

    assert "TOPSECRET" not in result.text
    assert "2025" not in result.text
    assert {"A", "B", "2025"}.issubset(set(result.mapping.values()))
    assert all("TOPSECRET" not in value for value in result.mapping.values())


def test_windows_to_alse_table_skips_structural_rows_inside_recognized_table():
    sep = "\ufdd0"
    row_boundary = "\ufdd0\ufdd2\ufdd0"
    boundary = "\ufdd0\ufdd1\ufdd0"
    headings = [
        "Исходное Windows-ПО",
        "Вариант для ALSE / Linux",
        "Статус аналогов и наличие в репозитории Astra",
    ]
    structural_rows = [
        headings,
        ["Итого программ: 12", "", ""],
        ["  ВСЕГО: 12  ", "", ""],
        ["Примечание к таблице", "Ответственный отдел", ""],
        ["Комментарии: варианты согласованы", "", ""],
        ["Раздел 1. Офисные приложения", "", ""],
    ]
    table = row_boundary.join([
        sep.join(headings),
        sep.join(["Microsoft Office", "LibreOffice", "Подтверждено"]),
        *[sep.join(row) for row in structural_rows],
    ])

    result = Anonymizer().anonymize(boundary + table + boundary)

    assert "Microsoft Office" not in result.text
    assert "LibreOffice" not in result.text
    software_values = {
        original
        for token, original in result.mapping.items()
        if token.startswith("[ПРОГРАММА-")
    }
    assert software_values == {"Microsoft Office", "LibreOffice"}


def test_windows_to_alse_table_does_not_reclassify_unrelated_status_like_triples():
    sep = "\ufdd0"
    row_boundary = "\ufdd0\ufdd2\ufdd0"
    software_table = row_boundary.join([
        sep.join([
            "Исходное Windows-ПО",
            "Вариант для ALSE / Linux",
            "Статус аналогов и наличие в репозитории Astra",
        ]),
        sep.join(["Microsoft Office", "LibreOffice, пакет libreoffice", "Да — Astra"]),
    ])
    unrelated_table = sep.join([
        "Раздел согласования",
        "Ответственный отдел",
        "Да, согласовано",
    ])
    boundary = "\ufdd0\ufdd1\ufdd0"
    source = boundary + software_table + boundary + unrelated_table + boundary

    result = Anonymizer().anonymize(source)

    assert "Microsoft Office" not in result.text
    assert "LibreOffice, пакет libreoffice" not in result.text
    assert "Раздел согласования" in result.text
    assert "Ответственный отдел" in result.text


def test_contextual_software_alias_respects_disabled_category():
    sep = "\ufdd0"
    source = sep.join([
        "Инвентаризация программного обеспечения", "Установок", "Доля",
        "Example Secure Client", "10", "1,6%",
        "Повтор Example Secure Client",
    ])

    result = Anonymizer(disabled_categories={"ПРОГРАММА"}).anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_disabled_vulnerability_category_leaves_cve_unchanged():
    source = "Уязвимость CVE-2024-12345."

    result = Anonymizer(disabled_categories={"уязвимость"}).anonymize(source)

    assert result.text == source
    assert result.mapping == {}
    assert result.candidates == []
    assert result.hint_count == 0


def test_contextual_software_alias_uses_one_compact_reversible_marker():
    sep = "\ufdd0"
    source = sep.join([
        "Инвентаризация программного обеспечения", "Установок", "Доля",
        "Example Secure Client", "10", "1,6%",
        "Повтор Example Secure Client",
    ])

    result = Anonymizer(compact_markers=True).anonymize(source)

    assert result.text.count("[ПО-1]") == 2
    assert result.mapping == {"[ПО-1]": "Example Secure Client"}
    assert result.text.replace("[ПО-1]", result.mapping["[ПО-1]"]) == source


def test_script_and_deployment_example_cells_are_redacted_as_complete_lists():
    sep = "\ufdd0"
    script_list = "CleanupJob; MapDisk; DisableLegacyName; LinkPolicy"
    deployment_list = "Suite 8.4; New_setup_suite; deploy_office2024"
    source = sep.join([
        "Тип", "Примеры", "Оценка",
        "Скрипты", script_list, "Проверить воспроизводимость",
        "Развертывание ПО", deployment_list, "Согласовать установку",
    ])

    result = Anonymizer().anonymize(source)

    assert script_list not in result.text
    assert deployment_list not in result.text
    assert "[СКРИПТЫ-1]" in result.text
    assert "[ПРОГРАММА-1]" in result.text


def test_deployment_cell_with_russian_yo_redacts_real_software_list():
    sep = "\ufdd0"
    deployment_list = (
        "1C 8.3.27.1859; New_setup_1C; Setup_1C_*; TessaDesk; "
        "Установка LanDocs; deploy_office2016; Kaspersky_AK*"
    )
    source = sep.join([
        "Развёртывание ПО",
        deployment_list,
        "Установка возможна при наличии поддерживаемых Linux-пакетов",
    ])

    result = Anonymizer().anonymize(source)

    assert deployment_list not in result.text
    assert "TessaDesk" not in result.text
    assert "LanDocs" not in result.text
    assert "Kaspersky_AK" not in result.text
    assert "[ПРОГРАММА-1]" in result.text
    assert result.mapping["[ПРОГРАММА-1]"] == deployment_list


def test_disk_labels_and_windows_paths_are_redacted_reversibly():
    source = r"Сценарий обрабатывает only disk k; резервная папка C:\Clients\Acme\Archive и том DATA01. Метка DATA01 повторяется."

    result = Anonymizer().anonymize(source)

    for leaked in (" k", r"C:\Clients\Acme\Archive", "DATA01"):
        assert leaked not in result.text
    assert "[ДИСК-" in result.text
    assert "[ПУТЬ-" in result.text
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_privileged_group_member_login_with_initial_is_redacted():
    source = "Состав Enterprise Admins по площадкам: Administrator, Example_A, service_admin. Учетная запись Example_A активна."

    result = Anonymizer().anonymize(source)

    assert "Example_A" not in result.text
    assert "[ЛОГИН-" in result.text


def test_labelled_login_in_adjacent_docx_table_cell_is_redacted():
    account = "synthetic_demo_user"
    source = f"Учётная запись\ufdd0{account}"

    result = Anonymizer().anonymize(source)

    assert result.text == "Учётная запись\ufdd0[ЛОГИН-1]"
    assert result.mapping == {"[ЛОГИН-1]": account}
    assert result.counts == {"ЛОГИН": 1}
    disabled = Anonymizer(disabled_categories={"ЛОГИН"}).anonymize(source)
    assert disabled.text == source
    assert disabled.mapping == {}


def test_english_account_label_in_adjacent_docx_table_cell_is_redacted():
    account = "synthetic_demo_user"
    source = f"Account\ufdd0{account}"

    result = Anonymizer().anonymize(source)

    assert result.text == "Account\ufdd0[ЛОГИН-1]"
    assert result.mapping == {"[ЛОГИН-1]": account}


def test_english_account_requires_an_explicit_label_separator():
    ordinary = "Account manager handles billing"
    labelled = "Account: synthetic_demo_user"

    assert Anonymizer().anonymize(ordinary).text == ordinary
    result = Anonymizer().anonymize(labelled)
    assert result.text == "Account: [ЛОГИН-1]"
    assert result.mapping == {"[ЛОГИН-1]": "synthetic_demo_user"}


def test_distinguished_name_wins_over_nested_domain_and_abbreviations():
    distinguished_name = "CN=alpha.example,CN=System,DC=rf,DC=alpha,DC=example"

    result = Anonymizer().anonymize(distinguished_name)

    assert result.text == "[DN-1]"
    assert result.mapping == {"[DN-1]": distinguished_name}
    assert result.counts == {"DN": 1}
    disabled = Anonymizer(disabled_categories={"DN"}).anonymize(distinguished_name)
    assert disabled.text == distinguished_name
    assert disabled.mapping == {}


def test_distinguished_name_accepts_spaces_between_rdns():
    distinguished_name = "CN=Alpha User, OU=Users, DC=alpha, DC=example"

    result = Anonymizer().anonymize(distinguished_name)

    assert result.text == "[DN-1]"
    assert result.mapping == {"[DN-1]": distinguished_name}


def test_distinguished_name_accepts_escaped_commas_inside_rdn_values():
    distinguished_name = r"CN=Doe\, John, OU=Users, DC=alpha, DC=example"

    result = Anonymizer().anonymize(distinguished_name)

    assert result.text == "[DN-1]"
    assert result.mapping == {"[DN-1]": distinguished_name}


def test_service_account_with_site_code_is_one_bounded_login_marker():
    account = "SvcQAZ-BackupTask"
    source = f"Учётная запись: {account}. Повтор: {account}."

    result = Anonymizer().anonymize(source)

    assert result.text == "Учётная запись: [ЛОГИН-1]. Повтор: [ЛОГИН-1]."
    assert result.mapping == {"[ЛОГИН-1]": account}
    assert result.counts["ЛОГИН"] == 2
    assert Anonymizer(disabled_categories={"ЛОГИН"}).anonymize(account).text == account


def test_service_account_assignment_with_internal_underscore_is_one_login_marker():
    account = "SvcQXZ-DB_Backup"
    source = f"Пример: {account}. Повтор: {account}."

    result = Anonymizer().anonymize(source)

    assert result.text == "Пример: [ЛОГИН-1]. Повтор: [ЛОГИН-1]."
    assert result.mapping == {"[ЛОГИН-1]": account}
    assert result.counts["ЛОГИН"] == 2
    disabled = Anonymizer(disabled_categories={"ЛОГИН"}).anonymize(account)
    assert disabled.text == account
    assert disabled.mapping == {}


def test_service_account_hard_break_is_supported_at_every_internal_character_boundary():
    account = "SvcQXZ-DB_Backup"
    intra = "\ufdd3"

    for split_at in range(1, len(account)):
        physical = account[:split_at] + intra + account[split_at:]
        result = Anonymizer().anonymize(physical)

        assert result.text == "[ЛОГИН-1]" + intra
        assert result.mapping == {
            "[ЛОГИН-1]": account[:split_at] + "\n" + account[split_at:]
        }
        assert result.counts == {"ЛОГИН": 1}
        disabled = Anonymizer(disabled_categories={"ЛОГИН"}).anonymize(physical)
        assert disabled.text == physical
        assert disabled.mapping == {}


def test_service_account_detection_never_crosses_docx_cell_boundary():
    source = "SvcQXZ-DB_\ufdd0Backup"
    result = Anonymizer(disabled_categories={"СОКРАЩЕНИЯ"}).anonymize(source)

    assert "[ЛОГИН-" not in result.text
    assert result.mapping == {}


def test_service_account_rule_does_not_capture_embedded_or_malformed_tokens():
    source = (
        "xSvcQAZ-BackupTask SvcQAZ-BackupTask9 "
        "SvcQaZ-BackupTask SvcQAZ-backuptask "
        "user@SvcQAZ-BackupTask.example.test /SvcQAZ-BackupTask/log "
        "xSvcQXZ-DB_Backup SvcQXZ-DB_Backup.example.test "
        "user@SvcQXZ-DB_Backup.example.test /SvcQXZ-DB_Backup/log"
    )

    result = Anonymizer(disabled_categories={"ДОМЕН", "ССЫЛКА", "ПОЧТА", "ПУТЬ"}).anonymize(source)

    assert "[ЛОГИН-" not in result.text


def test_virtual_machine_inventory_names_with_compact_role_and_digits_are_anonymized():
    vm_names = [
        "qzx-monitor0101",
        "qzx-repo0101",
        "qzx-print0101",
        "qzx-fs0101",
        "qzx-journal0101",
    ]
    source = "\n".join(vm_names)

    result = Anonymizer().anonymize(source)

    assert all(name not in result.text for name in vm_names)
    assert result.text.count("[УЗЕЛ-") == len(vm_names)
    assert set(result.mapping.values()) == set(vm_names)
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_server_inventory_names_with_site_number_and_compact_role_are_anonymized():
    server_names = [
        "s1234-qzx01",
        "V2345-QZX02-1",
        "s3456-lab03",
        "v4567-dev04-12",
    ]
    source = "\n".join(server_names)

    result = Anonymizer().anonymize(source)

    assert all(name not in result.text for name in server_names)
    assert result.text.splitlines() == [f"[УЗЕЛ-{index}]" for index in range(1, 5)]
    assert set(result.mapping.values()) == set(server_names)
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_server_inventory_table_context_redacts_structured_and_short_name_cells():
    table = "\ufdd0\ufdd1\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    cell = "\ufdd0"
    rows = [
        cell.join(("Наименование", "IP адрес", "Программное обеспечение", "ИТ-сервис")),
        cell.join(("q1234-qz01", "192.0.2.11", "Sample Linux", "Тестовый сервис")),
        cell.join(("1234-lb02-2", "192.0.2.12", "Sample Linux", "Тестовый сервис")),
        cell.join(("zx23", "192.0.2.13", "Sample Linux", "Тестовый сервис")),
        cell.join(("q1234-qzİ01", "192.0.2.14", "Sample Linux", "Тестовый сервис")),
    ]
    source = table + row.join(rows) + table

    result = Anonymizer().anonymize(source)

    server_names = {"q1234-qz01", "1234-lb02-2", "zx23"}
    assert all(name not in result.text for name in server_names)
    assert result.text.count("[УЗЕЛ-") == len(server_names)
    assert server_names <= set(result.mapping.values())
    assert "q1234-qzİ01" in result.text
    for separator in ("\ufdd0", "\ufdd1", "\ufdd2"):
        assert result.text.count(separator) == source.count(separator)


def test_server_inventory_pattern_does_not_capture_unrelated_codes():
    source = (
        "Документ a1234-qzx01; план 1234-lb02-2; код zx23; "
        "версия s1234-qzx1; пакет v1234-report01; "
        "unicode s1234-qzİ01 s1234-qzı01 s1234-qzſ01 s1234-qzK01."
    )

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_server_inventory_table_requires_semantic_supporting_columns():
    table = "\ufdd0\ufdd1\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    cell = "\ufdd0"
    source = table + row.join((
        cell.join(("Наименование", "IP адрес", "Стоимость", "Статус")),
        cell.join(("q1234-qz01", "192.0.2.21", "100", "готово")),
        cell.join(("zx23", "192.0.2.22", "200", "готово")),
    )) + table

    result = Anonymizer().anonymize(source)

    assert "q1234-qz01" in result.text
    assert "zx23" in result.text
    assert "[УЗЕЛ-" not in result.text


def test_semantic_server_node_beats_broad_secret_and_respects_disable():
    table = "\ufdd0\ufdd1\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    cell = "\ufdd0"
    node_name = "admin-pass01"
    source = table + row.join((
        cell.join(("Наименование", "IP адрес", "Программное обеспечение", "CPU")),
        cell.join((node_name, "192.0.2.81", "Synthetic Linux", "32")),
    )) + table

    enabled = Anonymizer().anonymize(source)
    disabled = Anonymizer(disabled_categories={"УЗЕЛ"}).anonymize(source)

    assert node_name not in enabled.text
    assert "(удалено" not in enabled.text
    assert node_name in set(enabled.mapping.values())
    assert any(marker.startswith("[УЗЕЛ-") for marker in enabled.mapping)
    assert "(удалено" in disabled.text
    assert not any(marker.startswith("[УЗЕЛ-") for marker in disabled.mapping)


def test_semantic_server_node_cell_is_whole_value_bounded():
    table = "\ufdd0\ufdd1\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    cell = "\ufdd0"
    dotted_node = "edge-04.lab.example.test"
    rejected = (
        "https://edge-04.lab.example.test/status",
        "ops@edge-04.lab.example.test",
        r"C:\edge-04.lab.example.test\config",
        "prefix edge-04.lab.example.test suffix",
        "edge-04.lab.example.test/child",
    )
    header = cell.join(("Наименование", "IP адрес", "Программное обеспечение", "CPU"))

    def inventory(value, ip):
        data = cell.join((value, ip, "Synthetic Linux", "32"))
        return table + row.join((header, data)) + table

    result = Anonymizer().anonymize(inventory(dotted_node, "192.0.2.91"))
    node_values = {
        value
        for marker, value in result.mapping.items()
        if marker.startswith("[УЗЕЛ-")
    }

    assert node_values == {dotted_node}
    assert result.text.count("[УЗЕЛ-") == 1
    for index, value in enumerate(rejected):
        rejected_result = Anonymizer().anonymize(
            inventory(value, f"192.0.2.{92 + index}")
        )
        assert not any(
            marker.startswith("[УЗЕЛ-") for marker in rejected_result.mapping
        )


def test_server_inventory_names_respect_disabled_and_compact_node_category():
    source = "s1234-qzx01"

    disabled = Anonymizer(disabled_categories={"УЗЕЛ"}).anonymize(source)
    compact = Anonymizer(compact_markers=True).anonymize(source)

    assert disabled.text == source
    assert disabled.mapping == {}
    assert compact.text == "[УЗЛ-1]"
    assert compact.mapping == {"[УЗЛ-1]": source}


def test_compact_vm_case_variants_receive_distinct_reversible_markers():
    source = "qzx-monitor0101 QZX-MONITOR0101"

    result = Anonymizer().anonymize(source)

    assert result.text == "[УЗЕЛ-1] [УЗЕЛ-2]"
    assert result.mapping == {
        "[УЗЕЛ-1]": "qzx-monitor0101",
        "[УЗЕЛ-2]": "QZX-MONITOR0101",
    }
    restored = result.text
    for marker, value in result.mapping.items():
        restored = restored.replace(marker, value)
    assert restored == source


def test_compact_vm_rule_does_not_capture_generic_document_names():
    source = "Файлы qzx-report0101 и qzx-contract0101 остаются без изменений."

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_paranoid_job_title_does_not_leave_a_word_suffix():
    source = "Начальник отдела безопасности работает."

    result = Anonymizer(paranoid=True).anonymize(source)

    assert result.text == "[ДОЛЖНОСТЬ-1] работает."
    assert result.mapping == {"[ДОЛЖНОСТЬ-1]": "Начальник отдела безопасности"}


def test_user_dictionary_whitelist_and_paranoid_candidates():
    normal = Anonymizer(user_dictionary={"Вымпел": "СИСТЕМА"}, whitelist={"Казань"})
    result = normal.anonymize("Вымпел расположен в Казани")
    assert "[СИСТЕМА-1]" in result.text
    assert "Казани" in result.text
    paranoid = Anonymizer(paranoid=True).anonymize("офис в Берлине")
    assert "[ГОРОД-1]" in paranoid.text


def test_validated_identifiers_reject_bad_checksums():
    result = Anonymizer().anonymize("ИНН 7707083893, ИНН 7707083894; карта 4111 1111 1111 1111, карта 4111 1111 1111 1112")
    assert "[ИНН-1]" in result.text and "7707083894" in result.text
    assert "[КАРТА-1]" in result.text and "4111 1111 1111 1112" in result.text


def test_literal_markers_do_not_collide_and_reprocessing_is_idempotent():
    source = "Литерал [ФИО-1], Иванов Сергей Петрович"
    first = Anonymizer().anonymize(source)
    assert "[ФИО-1]" in first.text and "[ФИО-2]" in first.text
    assert first.mapping == {"[ФИО-2]": "Иванов Сергей Петрович"}
    second = Anonymizer().anonymize(first.text)
    assert second.text == first.text and second.mapping == {}
    restored = first.text.replace("[ФИО-2]", first.mapping["[ФИО-2]"])
    assert restored == source


def test_compound_policy_identifiers_are_replaced_as_one_abbreviation():
    values = (
        "QA-IT-RefreshCache",
        "34ZX-NW-DeviceLock_All",
        "QA-IT-info_previous_events",
        "51LM-NW-Policy07",
        "QA-IT-CM_5.0.8692_ClientInstall",
        "QA-IT-Core.5.8.2-Deploy",
    )
    source = " ".join(values)

    result = Anonymizer().anonymize(source)

    assert result.text == " ".join(
        f"[СОКРАЩЕНИЯ-{index}]" for index in range(1, len(values) + 1)
    )
    assert result.mapping == {
        f"[СОКРАЩЕНИЯ-{index}]": value
        for index, value in enumerate(values, start=1)
    }
    disabled = Anonymizer(disabled_categories={"СОКРАЩЕНИЯ"}).anonymize(source)
    assert disabled.text == source
    assert disabled.mapping == {}


def test_hyphenated_token_with_uppercase_prefix_outranks_nested_review_hint():
    for value in (
        "ЖФКТ-Навигация",
        "ИТ-Навигация",
        "АЭ-Навигация",
        "АЭК-Навигация",
        "ЖФ-На\u0483вигация",
        "IT-Cafe\u0301",
        "ИТ-Иванов",
    ):
        source = f"Объект {value} используется."

        for paranoid in (False, True):
            result = Anonymizer(paranoid=paranoid).anonymize(source)
            assert result.text == "Объект [СОКРАЩЕНИЯ-1] используется."
            assert result.mapping == {"[СОКРАЩЕНИЯ-1]": value}
            assert not result.candidates

        for paranoid in (False, True):
            disabled = Anonymizer(
                paranoid=paranoid,
                disabled_categories={"СОКРАЩЕНИЯ"},
            ).anonymize(source)
            assert disabled.text == source
            assert disabled.mapping == {}
            assert not disabled.candidates

        for paranoid in (False, True):
            whitelisted = Anonymizer(
                paranoid=paranoid,
                whitelist={value},
            ).anonymize(source)
            assert whitelisted.text == source
            assert whitelisted.mapping == {}
            assert not whitelisted.candidates

    excluded = (
        "ИТ-навигация ИТ-НаВигация ИТ-Навигация2 中文-Навигация "
        "user@ИТ-Навигация.example.test https://example.test/ИТ-Навигация "
        "C:\\Temp\\ИТ-Навигация"
    )
    unchanged = Anonymizer().anonymize(excluded)
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-")
        for marker in unchanged.mapping
    )

    for overlong in ("ABCDEFGHI-Title", "ABCDEFGHI_delta-node"):
        overlong_result = Anonymizer().anonymize(overlong)
        assert overlong not in overlong_result.mapping.values()


def test_exact_whitelist_does_not_block_enclosing_precise_structure():
    whitelisted = "IT-Cafe"
    for source in (
        f"user@{whitelisted}.example.test",
        f"https://example.test/{whitelisted}",
        f"C:\\Temp\\{whitelisted}",
    ):
        for paranoid in (False, True):
            result = Anonymizer(
                paranoid=paranoid,
                whitelist={whitelisted},
            ).anonymize(source)
            assert source in result.mapping.values()
            assert not any(
                marker.startswith("[СОКРАЩЕНИЯ-")
                for marker in result.mapping
            )


def test_split_structural_abbreviations_join_only_inside_one_cell():
    for physical, logical in (
        ("IT-Na\ufdd3vigation", "IT-Na\nvigation"),
        ("QWER_delta\ufdd3-node", "QWER_delta\n-node"),
        ("QA-IT-Portal-\ufdd3_ActiveX", "QA-IT-Portal-\n_ActiveX"),
    ):
        result = Anonymizer().anonymize(physical)
        assert result.text == "[СОКРАЩЕНИЯ-1]\ufdd3"
        assert result.mapping == {"[СОКРАЩЕНИЯ-1]": logical}

        disabled = Anonymizer(
            paranoid=True,
            disabled_categories={"СОКРАЩЕНИЯ"},
        ).anonymize(physical)
        assert disabled.text == physical
        assert disabled.mapping == {}
        assert not disabled.candidates

        whitelisted = Anonymizer(
            paranoid=True,
            whitelist={logical.replace("\n", "")},
        ).anonymize(physical)
        assert whitelisted.text == physical
        assert whitelisted.mapping == {}
        assert not whitelisted.candidates

    for separated in (
        "IT-Na\ufdd0vigation",
        "QWER_delta\ufdd0-node",
        "QA-IT-Portal-\ufdd0_ActiveX",
    ):
        result = Anonymizer().anonymize(separated)
        assert separated not in result.mapping.values()
        assert "\ufdd0" in result.text

    protected_structures = (
        "user@\ufdd3QWER_delta-node.example.test",
        "https://example.test/\ufdd3QWER_delta-node",
        "C:\ufdd3\\Temp\\QWER_delta-node",
    )
    for source in protected_structures:
        result = Anonymizer().anonymize(source)
        assert not any(
            marker.startswith("[СОКРАЩЕНИЯ-")
            for marker in result.mapping
        )


def test_structural_abbreviations_support_every_intra_token_boundary():
    for value in ("IT-Navigation", "QWER_delta-node"):
        for split_at in range(1, len(value)):
            physical = value[:split_at] + "\ufdd3" + value[split_at:]
            expected_mapping = physical.replace("\ufdd3", "\n")

            for paranoid in (False, True):
                result = Anonymizer(paranoid=paranoid).anonymize(physical)
                assert result.text == "[СОКРАЩЕНИЯ-1]\ufdd3"
                assert result.mapping == {
                    "[СОКРАЩЕНИЯ-1]": expected_mapping,
                }

                disabled = Anonymizer(
                    paranoid=paranoid,
                    disabled_categories={"СОКРАЩЕНИЯ"},
                ).anonymize(physical)
                assert disabled.text == physical
                assert disabled.mapping == {}
                assert disabled.candidates == []

                whitelisted = Anonymizer(
                    paranoid=paranoid,
                    whitelist={value},
                ).anonymize(physical)
                assert whitelisted.text == physical
                assert whitelisted.mapping == {}
                assert whitelisted.candidates == []

            hard_boundary = value[:split_at] + "\ufdd0" + value[split_at:]
            separated = Anonymizer(paranoid=True).anonymize(hard_boundary)
            assert expected_mapping not in separated.mapping.values()
            assert "\ufdd0" in separated.text


def test_precise_semantic_hint_outranks_split_abbreviation_fallback():
    physical = "IT-Диа\ufdd3гноз"
    for disabled_categories in (set(), {"СОКРАЩЕНИЯ"}):
        ordinary = Anonymizer(
            disabled_categories=disabled_categories,
        ).anonymize(physical)
        assert ordinary.text == physical.replace("\ufdd3", "\n")
        assert ordinary.mapping == {}
        assert ordinary.candidates == ["Диа\nгноз"]

        paranoid = Anonymizer(
            paranoid=True,
            disabled_categories=disabled_categories,
        ).anonymize(physical)
        assert paranoid.text == "IT-[СПЕЦКАТЕГОРИЯ-1]\ufdd3"
        assert paranoid.mapping == {
            "[СПЕЦКАТЕГОРИЯ-1]": "Диа\nгноз",
        }
        assert paranoid.candidates == []

    word = "Диагноз"
    for split_at in range(1, len(word)):
        whitelisted_physical = (
            "IT-" + word[:split_at] + "\ufdd3" + word[split_at:]
        )
        for paranoid in (False, True):
            whitelisted = Anonymizer(
                paranoid=paranoid,
                whitelist=[word],
            ).anonymize(whitelisted_physical)
            assert whitelisted.text == whitelisted_physical
            assert whitelisted.mapping == {}
            assert whitelisted.candidates == []


def test_precise_structures_support_every_intra_token_boundary():
    values = (
        ("user@QWER_delta-node.example.test", "ПОЧТА"),
        ("https://example.test/QWER_delta-node", "ССЫЛКА"),
        ("C:\\Temp\\QWER_delta-node", "ПУТЬ"),
    )
    for value, category in values:
        for split_at in range(1, len(value)):
            physical = value[:split_at] + "\ufdd3" + value[split_at:]
            result = Anonymizer(paranoid=True).anonymize(physical)
            assert result.text == f"[{category}-1]\ufdd3"
            assert result.mapping == {
                f"[{category}-1]": physical.replace("\ufdd3", "\n"),
            }
            assert result.text.count("\ufdd3") == physical.count("\ufdd3")
            assert not any(
                marker.startswith("[СОКРАЩЕНИЯ-")
                for marker in result.mapping
            )

            for paranoid in (False, True):
                whitelisted = Anonymizer(
                    paranoid=paranoid,
                    whitelist=[value],
                ).anonymize(physical)
                assert whitelisted.text == physical
                assert whitelisted.mapping == {}
                assert whitelisted.candidates == []

            hard_boundary = value[:split_at] + "\ufdd0" + value[split_at:]
            separated = Anonymizer(paranoid=True).anonymize(hard_boundary)
            assert value not in separated.mapping.values()
            assert "\ufdd0" in separated.text


def test_precise_semantic_hint_outranks_hyphenated_abbreviation_fallback():
    source = "Объект IT-Диагноз используется."
    for disabled_categories in (set(), {"СОКРАЩЕНИЯ"}):
        ordinary = Anonymizer(
            disabled_categories=disabled_categories,
        ).anonymize(source)
        assert ordinary.text == source
        assert ordinary.mapping == {}
        assert ordinary.candidates == ["Диагноз"]

        paranoid = Anonymizer(
            paranoid=True,
            disabled_categories=disabled_categories,
        ).anonymize(source)
        assert paranoid.text == "Объект IT-[СПЕЦКАТЕГОРИЯ-1] используется."
        assert paranoid.mapping == {"[СПЕЦКАТЕГОРИЯ-1]": "Диагноз"}
        assert not paranoid.candidates


def test_uppercase_prefix_with_lowercase_underscore_hyphen_tail_is_abbreviation():
    for value in (
        "QWER_delta-node",
        "IT_alpha-beta",
        "Q\u0307A_cafe\u0301-node",
    ):
        source = f"Компонент {value} включён."

        for paranoid in (False, True):
            result = Anonymizer(paranoid=paranoid).anonymize(source)
            assert result.text == "Компонент [СОКРАЩЕНИЯ-1] включён."
            assert result.mapping == {"[СОКРАЩЕНИЯ-1]": value}
            assert not result.candidates

        for paranoid in (False, True):
            disabled = Anonymizer(
                paranoid=paranoid,
                disabled_categories={"СОКРАЩЕНИЯ"},
            ).anonymize(source)
            assert disabled.text == source
            assert disabled.mapping == {}
            assert not disabled.candidates

            whitelisted = Anonymizer(
                paranoid=paranoid,
                whitelist={value},
            ).anonymize(source)
            assert whitelisted.text == source
            assert whitelisted.mapping == {}
            assert not whitelisted.candidates

    excluded = "alpha_delta-node"
    unchanged = Anonymizer().anonymize(excluded)
    assert unchanged.text == excluded
    assert unchanged.mapping == {}

    protected_values = (
        "user@QWER_delta-node.example.test",
        "https://example.test/QWER_delta-node",
        "C:\\Temp\\QWER_delta-node",
    )
    protected = Anonymizer().anonymize(" ".join(protected_values))
    assert set(protected.mapping.values()) == set(protected_values)
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-")
        for marker in protected.mapping
    )

    semantic_source = "Компонент IT_alpha-диагноз включён."
    semantic = Anonymizer(
        paranoid=True,
        disabled_categories={"СОКРАЩЕНИЯ"},
    ).anonymize(semantic_source)
    assert semantic.mapping == {"[СПЕЦКАТЕГОРИЯ-1]": "диагноз"}
    assert semantic.text == "Компонент IT_alpha-[СПЕЦКАТЕГОРИЯ-1] включён."


def test_compound_abbreviation_accepts_one_mixed_adjacent_separator_pair():
    values = (
        "QA-IT-Portal-_ActiveX",
        "QA_IT_Portal_-ActiveX",
        "QA-IT-Portal-_v1.2.3",
        "QA_IT_Portal_-v1.2.3",
    )

    for value in values:
        for paranoid in (False, True):
            result = Anonymizer(paranoid=paranoid).anonymize(value)
            assert result.text == "[СОКРАЩЕНИЯ-1]"
            assert result.mapping == {"[СОКРАЩЕНИЯ-1]": value}

        for anonymizer in (
            Anonymizer(paranoid=True, whitelist={value}),
            Anonymizer(
                paranoid=True,
                disabled_categories={"СОКРАЩЕНИЯ"},
            ),
        ):
            protected = anonymizer.anonymize(value)
            assert protected.text == value
            assert protected.mapping == {}
            assert protected.candidates == []

    for paranoid in (False, True):
        split = Anonymizer(paranoid=paranoid).anonymize("QA--IT-Portal-_ActiveX")
        assert split.text == "QA--IT-Portal-_ActiveX"
        assert split.mapping == {}
        assert split.candidates == []

        rejected = Anonymizer(paranoid=paranoid).anonymize("QA__IT_Portal")
        assert rejected.text == "QA__IT_Portal"
        assert rejected.mapping == {}
        assert rejected.candidates == []

        multiple_mixed = Anonymizer(paranoid=paranoid).anonymize(
            "QA-_IT-Portal_-ActiveX"
        )
        assert multiple_mixed.text == "QA-_IT-Portal_-ActiveX"
        assert multiple_mixed.mapping == {}
        assert multiple_mixed.candidates == []

        fragmented_reverse = Anonymizer(paranoid=paranoid).anonymize(
            "QA_IT_\ufdd3-Portal"
        )
        assert fragmented_reverse.text == "[СОКРАЩЕНИЯ-1]\ufdd3"
        assert fragmented_reverse.mapping == {
            "[СОКРАЩЕНИЯ-1]": "QA_IT_\n-Portal"
        }

    compound = values[0]
    precise_values = (
        f"user@{compound}.example.test",
        f"https://example.test/{compound}",
        f"C:\\Temp\\{compound}",
    )
    precise = Anonymizer().anonymize(" ".join(precise_values))
    assert set(precise.mapping.values()) == set(precise_values)
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-")
        for marker in precise.mapping
    )


def test_digit_led_inventory_compounds_are_abbreviations():
    values = (
        "8300-QA-ClientInstall",
        "8300-QA-DeviceLock",
        "8300-QA-DefaultPolicy",
        "8300-QA-ScreenSaver_and_Wallpaper",
    )
    source = " ".join(values)

    for paranoid in (False, True):
        result = Anonymizer(paranoid=paranoid).anonymize(source)
        assert set(result.mapping.values()) == set(values)
        assert result.text.count("[СОКРАЩЕНИЯ-") == len(values)
        assert not result.candidates

    prefixed = Anonymizer().anonymize("Copy of 5500-ZX-Proxy_Spark")
    assert prefixed.text == "Copy of [СОКРАЩЕНИЯ-1]"
    assert prefixed.mapping == {
        "[СОКРАЩЕНИЯ-1]": "5500-ZX-Proxy_Spark",
    }

    fragmented = Anonymizer().anonymize("8300-QA-\ufdd3ClientInstall")
    assert fragmented.text == "[СОКРАЩЕНИЯ-1]\ufdd3"
    assert fragmented.mapping == {
        "[СОКРАЩЕНИЯ-1]": "8300-QA-\nClientInstall",
    }
    hard_boundary = Anonymizer().anonymize("8300-QA-\ufdd0ClientInstall")
    assert "8300-QA-\nClientInstall" not in hard_boundary.mapping.values()

    value = values[0]
    for anonymizer in (
        Anonymizer(paranoid=True, whitelist={value}),
        Anonymizer(paranoid=True, disabled_categories={"СОКРАЩЕНИЯ"}),
    ):
        protected = anonymizer.anonymize(value)
        assert protected.text == value
        assert protected.mapping == {}
        assert protected.candidates == []

    precise_values = (
        f"user@{value}.example.test",
        f"https://example.test/{value}",
        f"C:\\Temp\\{value}",
    )
    precise = Anonymizer().anonymize(" ".join(precise_values))
    assert set(precise.mapping.values()) == set(precise_values)
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-") for marker in precise.mapping
    )

    for rejected in (
        "8-QA-ClientInstall",
        "8300-qA-ClientInstall",
        "8300-QA-Client",
        "2026-US-October-Report",
        "20-US-New-York",
        "8300--QA-ClientInstall",
        "8300-QA__ClientInstall",
    ):
        result = Anonymizer(paranoid=True).anonymize(rejected)
        assert result.text == rejected
        assert result.mapping == {}
        assert result.candidates == []


def test_compact_mixed_case_acronym_like_token_is_abbreviation():
    value = "MixPC"
    for paranoid in (False, True):
        result = Anonymizer(paranoid=paranoid).anonymize(value)
        assert result.text == "[СОКРАЩЕНИЯ-1]"
        assert result.mapping == {"[СОКРАЩЕНИЯ-1]": value}
        assert not result.candidates

    for anonymizer in (
        Anonymizer(paranoid=True, whitelist={value}),
        Anonymizer(paranoid=True, disabled_categories={"СОКРАЩЕНИЯ"}),
    ):
        protected = anonymizer.anonymize(value)
        assert protected.text == value
        assert protected.mapping == {}
        assert protected.candidates == []

    fragmented = Anonymizer().anonymize("Mix\ufdd3PC")
    assert fragmented.text == "[СОКРАЩЕНИЯ-1]\ufdd3"
    assert fragmented.mapping == {"[СОКРАЩЕНИЯ-1]": "Mix\nPC"}
    hard_boundary = Anonymizer().anonymize("Mix\ufdd0PC")
    assert "Mix\nPC" not in hard_boundary.mapping.values()

    precise_values = (
        f"user@{value}.example.test",
        f"https://example.test/{value}",
        f"C:\\Temp\\{value}",
    )
    precise = Anonymizer().anonymize(" ".join(precise_values))
    assert set(precise.mapping.values()) == set(precise_values)
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-") for marker in precise.mapping
    )

    for rejected in ("Mixed", "TitleX", "ABc", "mixPC"):
        result = Anonymizer().anonymize(rejected)
        assert rejected not in {
            original
            for marker, original in result.mapping.items()
            if marker.startswith("[СОКРАЩЕНИЯ-")
        }


def test_compound_policy_identifier_rule_is_bounded_and_avoids_paths_urls_and_email():
    value = "QA-IT-RefreshCache"
    source = (
        f"x{value} {value}9 user@{value}.example.test "
        f"https://example.test/{value} C:\\Temp\\{value} single-Part "
        "IF-then-ELSE DO_not_DO QA-is-IT-policy "
        "QA-is-\ufdd3IT-policy QA-IT-host.example "
        "EU-UK-market IF-THEN-else AB-CD-example"
        " QA-IT-Core.alpha-Deploy QA-IT-host.12.34 "
        "QA-IT-host.12.34-Deploy QA-IT-file.12.34-Report"
    )

    result = Anonymizer().anonymize(source)

    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-") and original == value
        for marker, original in result.mapping.items()
    )
    assert "IF-then-ELSE" in result.text
    assert "DO_not_DO" in result.text
    assert "QA-is-IT-policy" in result.text
    assert "QA-is-\ufdd3IT-policy" in result.text
    assert "EU-UK-market" in result.text
    assert "IF-THEN-else" in result.text
    assert "AB-CD-example" in result.text
    assert "QA-IT-Core.alpha-Deploy" in result.text
    assert "QA-IT-host.12.34" in result.text
    assert "QA-IT-host.12.34-Deploy" in result.text
    assert "QA-IT-file.12.34-Report" in result.text
    assert not any(
        marker.startswith("[СОКРАЩЕНИЯ-")
        and original in {
            "QA-IT-host",
            "QA-IT-host.example",
            "QA-IT-host.12.34-Deploy",
            "QA-IT-file.12.34-Report",
        }
        for marker, original in result.mapping.items()
    )


def test_dotted_version_compound_allows_terminal_sentence_punctuation():
    value = "QA-IT-Core.5.8.2-Deploy"
    for punctuation in (".", ":", ",", ";", ")", "!"):
        result = Anonymizer().anonymize(value + punctuation)
        assert result.text == f"[СОКРАЩЕНИЯ-1]{punctuation}"
        assert result.mapping == {"[СОКРАЩЕНИЯ-1]": value}


def test_repeated_short_compound_policy_names_in_one_table_column_are_abbreviations():
    cell = "\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    table = "\ufdd0\ufdd1\ufdd0"
    values = ("QA-IT-Certs", "QA-IT-Screen", "QA-IT-Prestage")
    source = table + row.join(
        cell.join((str(index), value))
        for index, value in enumerate(values, start=1)
    ) + table

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == set(values)
    assert result.text.count("[СОКРАЩЕНИЯ-") == len(values)
    disabled = Anonymizer(disabled_categories={"СОКРАЩЕНИЯ"}).anonymize(source)
    assert all(value in disabled.text for value in values)


def test_contextual_location_table_redacts_site_name_and_hyphenated_avenue_address():
    cell = "\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    table = "\ufdd0\ufdd1\ufdd0"
    headers = (
        "Название", "Оператор A скорость", "Оператор B скорость",
        "Часовой пояс", "Адрес",
    )
    first = (
        "Макетинский", "30", "10", "+3",
        "пр-кт (проспект) Проверочный, д. 37, г. Тестоградск, 344002",
    )
    second = (
        "Контрольская площадка", "40", "8", "+5",
        "ул. Лабораторная, д. 8, г. Образцовск, 614000",
    )
    account_row = (
        "SvcQWE-DB_Backup", "50", "12", "+7",
        "ул. Синтетическая, д. 4, г. Примерск, 630000",
    )
    source = table + row.join((
        cell.join(headers), cell.join(first), cell.join(second), cell.join(account_row),
    )) + table

    result = Anonymizer().anonymize(source)

    address_values = {
        original for marker, original in result.mapping.items()
        if marker.startswith("[АДРЕС-")
    }
    assert address_values == {
        first[0], first[4], second[0], second[4], account_row[4],
    }
    assert all(value not in result.text for value in address_values)
    assert any(
        marker.startswith("[ЛОГИН-") and original == account_row[0]
        for marker, original in result.mapping.items()
    )
    disabled = Anonymizer(disabled_categories={"АДРЕС"}).anonymize(source)
    assert all(value in disabled.text for value in address_values)


def test_hyphenated_avenue_with_optional_parenthetical_expansion_is_one_address():
    values = (
        "пр-кт Проверочный, д. 37, г. Тестоградск, 344002",
        "пр-кт (проспект) Лабораторный, д. 8, г. Образцовск, 614000",
    )

    for value in values:
        result = Anonymizer().anonymize(value)
        assert result.text == "[АДРЕС-1]"
        assert result.mapping == {"[АДРЕС-1]": value}


def test_contextual_location_table_requires_address_semantics_and_does_not_cross_cells():
    cell = "\ufdd0"
    row = "\ufdd0\ufdd2\ufdd0"
    table = "\ufdd0\ufdd1\ufdd0"
    ordinary = table + row.join((
        cell.join(("Название", "Описание")),
        cell.join(("Макетинский", "Демонстрационный профиль")),
    )) + table
    malformed_address = table + row.join((
        cell.join(("Название", "Адрес")),
        cell.join(("Контрольский", "https://example.test/path")),
    )) + table
    commercial = table + row.join((
        cell.join(("Название", "Канал продаж", "Адрес")),
        cell.join((
            "Стандартный Тариф", "Онлайн",
            "ул. Проверочная, д. 8, г. Образцовск, 614000",
        )),
    )) + table

    result = Anonymizer().anonymize(ordinary + malformed_address + commercial)

    assert "Макетинский" in result.text
    assert "Контрольский" in result.text
    assert "Стандартный Тариф" in result.text
    assert not any(
        original in {"Макетинский", "Контрольский"}
        for original in result.mapping.values()
    )
