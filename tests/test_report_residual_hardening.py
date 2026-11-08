from local_anonymizer.engine import Anonymizer


def test_gpo_inventory_masks_complete_name_cells_without_hiding_indices():
    source = (
        "Приложение А Групповые политики"
        "\ufdd0\ufdd1\ufdd0№\ufdd0Наименование"
        "\ufdd0\ufdd2\ufdd01\ufdd0QZ_Internal_Local_Admin"
        "\ufdd0\ufdd2\ufdd02\ufdd0QZ Custom Policy 7"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "QZ_Internal_Local_Admin" not in result.text
    assert "QZ Custom Policy 7" not in result.text
    assert result.text.count("[СТРУКТУРА-AD-") == 2
    assert "1\ufdd0[СТРУКТУРА-AD-" in result.text
    assert "2\ufdd0[СТРУКТУРА-AD-" in result.text


def test_system_inventory_masks_complete_system_cells():
    source = (
        "Интеграционные системы"
        "\ufdd0\ufdd1\ufdd0№\ufdd0Система\ufdd0Тип"
        "\ufdd0\ufdd2\ufdd01\ufdd0QZ Internal Suite\ufdd0Информационная система"
        "\ufdd0\ufdd2\ufdd02\ufdd0QZ Monitoring Hub\ufdd0Мониторинг"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "QZ Internal Suite" not in result.text
    assert "QZ Monitoring Hub" not in result.text
    assert result.text.count("[СИСТЕМА-") == 2
    assert "Информационная система" in result.text
    assert "Мониторинг" in result.text


def test_structured_identifier_does_not_split_a_fqdn():
    source = "Сервер srv-db-01.alfa.local (10.15.24.18)"

    result = Anonymizer().anonymize(source)

    assert "srv-db-01" not in result.text
    assert "alfa.local" not in result.text
    assert "[ДОМЕН-" in result.text


def test_current_use_product_systems_are_masked_but_future_requirements_stay():
    source = (
        "В инфраструктуре используется централизованная система мониторинга Qzmonitor. "
        "Используется Qzvirtual. Почтового сервера Qzmail. В состав входит Qzidentity. "
        "Qzidentity использует встроенный каталог. Система Qzmaster. "
        "Интеграционной Платформы 2.0 с qzauth."
    )

    result = Anonymizer().anonymize(source)

    for value in ("Qzmonitor", "Qzvirtual", "Qzmail", "Qzidentity", "Qzmaster", "qzauth"):
        assert value not in result.text
    assert sum(marker.startswith("[СИСТЕМА-") for marker in result.mapping) == 6
    future = Anonymizer().anonymize("Должна обеспечивать интеграцию с Qzmaster")
    assert "Qzmaster" in future.text


def test_linux_os_inventory_and_structured_identifier_variants_are_masked():
    os_source = "\ufdd0\ufdd1\ufdd0[УЗЕЛ-1]\ufdd0Alt Linux (64-bit)\ufdd0[IP-1]\ufdd0[УЗЕЛ-2]\ufdd0Astra Linux 1.7.5\ufdd0[IP-2]"
    os_result = Anonymizer().anonymize(os_source)
    assert "Alt Linux (64-bit)" not in os_result.text
    assert "Astra Linux 1.7.5" not in os_result.text
    assert os_result.text.count("[ПРОГРАММА-") == 2

    id_source = "Пример: сервер QZ_v10_RF, 1900-qz01-2 и qz30-всr01"
    id_result = Anonymizer().anonymize(id_source)
    for value in ("QZ_v10_RF", "1900-qz01-2", "qz30-всr01"):
        assert value not in id_result.text
    assert id_result.text.count("[УЗЕЛ-") == 3


def test_internal_group_name_and_domain_shorthand_are_masked():
    source = "Самые большие группы это \"QzGroup_Servers\". В доменах qz и rx используется сервер"

    result = Anonymizer().anonymize(source)

    assert "QzGroup_Servers" not in result.text
    assert "qz и rx" not in result.text
    assert result.text.count("[СТРУКТУРА-AD-") == 1
    assert result.text.count("[ДОМЕН-") == 1


def test_schema_marker_prefix_and_inline_host_ip_os_shapes_are_masked():
    source = (
        "[СОКРАЩЕНИЯ-15] Schema\ufdd0(99) - Windows Server 2022"
        "\ufdd3[УЗЕЛ-13];\"[IP-108]\";\"Windows Server 2022 Standard\""
    )

    result = Anonymizer().anonymize(source)

    assert "(99) - Windows Server 2022" not in result.text
    assert "Windows Server 2022 Standard" not in result.text
    assert result.text.count("[ПРОГРАММА-") == 2


def test_privileged_directory_names_membership_and_admincount_are_masked():
    source = (
        "Domain Admins 17 участников. Enterprise Admins и Schema Admins. "
        "Участник – administrator. AdminCount=1 - 64 пользователя. qdomain admins"
    )

    result = Anonymizer().anonymize(source)

    for value in ("Domain Admins", "Enterprise Admins", "Schema Admins", "qdomain admins", "administrator", "AdminCount=1", "17", "64"):
        assert value not in result.text
    assert result.text.count("[СТРУКТУРА-AD-") == 5
    assert result.text.count("[МЕТРИКА-") == 2
    assert result.text.count("[ЛОГИН-") == 1


def test_capacity_thousands_with_infrastructure_context_are_masked():
    source = "сервер – 8,6 тыс.; АРМ – 16,4 тыс.; пользователи – 19 тыс.; устройств - 54 тыс."

    result = Anonymizer().anonymize(source)

    for value in ("8,6 тыс.", "16,4 тыс.", "19 тыс.", "54 тыс."):
        assert value not in result.text
    assert result.text.count("[МЕТРИКА-") == 4
    unrelated = Anonymizer().anonymize("Сервер установлен. В документе 14 тыс. слов")
    assert "14 тыс." in unrelated.text
    assert "[МЕТРИКА-" not in unrelated.text
    marked = Anonymizer().anonymize("сервер – 8,6 тыс.; [СОКРАЩЕНИЯ-28] – 16,4 тыс.")
    assert "8,6 тыс." not in marked.text
    assert "16,4 тыс." not in marked.text
    assert marked.text.count("[МЕТРИКА-") == 2


def test_ad_schema_and_functional_levels_are_program_metadata():
    source = "AD Schema\ufdd0(99) - Windows Server 2022\ufdd0Domain mode\ufdd02012 R2. лес – Windows Server 2012 R2"

    result = Anonymizer().anonymize(source)

    assert "(99) - Windows Server 2022" not in result.text
    assert "2012 R2" not in result.text
    assert result.text.count("[ПРОГРАММА-") == 3


def test_literal_secret_marker_is_not_reparsed_but_labelled_secret_still_wins():
    source = "Domain [SECRET-4]; password=[PERSON-1]"

    result = Anonymizer().anonymize(source)

    assert "[SECRET-4]" in result.text
    assert "[SECRET-[SECRET-" not in result.text
    assert "password=[PERSON-1]" not in result.text
    assert "[PERSON-1]" in result.mapping.values()
    with_boundary = Anonymizer().anonymize("Domain [SECRET-4]\ufdd3Для")
    assert "[SECRET-4]" in with_boundary.text
    assert "[SECRET-[SECRET-" not in with_boundary.text
    assert "1]\nДля" not in with_boundary.mapping.values()


def test_extended_security_and_backup_metric_forms_are_masked():
    source = (
        "Защита от брутфорса - 45 минут. "
        "Установлено количество неправильных попыток ввода 7. "
        "Максимальный жизнь билета 12 часов. "
        "Максимальное обновление - 14 дней. "
        "Обновление пароля - автоматически в 120 дней. "
        "Смена пароля не чаще чем один раз в день. "
        "Сроком хранения 11 дней. "
        "Security в два раза больше."
    )

    result = Anonymizer().anonymize(source)

    for value in (
        "45 минут", "ввода 7", "12 часов", "14 дней", "120 дней",
        "один раз в день", "11 дней", "в два раза больше",
    ):
        assert value not in result.text
    assert result.text.count("[МЕТРИКА-") == 8


def test_document_export_and_order_metadata_are_masked():
    source = "Exported on 2030-01-02 03:04:05. Введено Приказом от 01.02.2030 № 123"

    result = Anonymizer().anonymize(source)

    assert "2030-01-02 03:04:05" not in result.text
    assert "01.02.2030 № 123" not in result.text
    assert result.text.count("[ДОКУМЕНТ-") == 2


def test_structured_naming_example_identifiers_are_masked():
    source = "Пример: рабочая станция Q7000-XY0001234 и принтер Q7000XY0000002"

    result = Anonymizer().anonymize(source)

    assert "Q7000-XY0001234" not in result.text
    assert "Q7000XY0000002" not in result.text
    assert result.text.count("[УЗЕЛ-") == 2


def test_current_software_products_and_versions_are_masked():
    source = "Используется Qzbackup 9.4. Почтовый сервер Qzmail, версии 13"

    result = Anonymizer().anonymize(source)

    assert "9.4" not in result.text
    assert "версии 13" not in result.text
    assert result.text.count("[ПРОГРАММА-") == 2
    assert "Qzbackup" not in result.text
    assert "Qzmail" not in result.text


def test_security_and_capacity_metrics_use_labelled_values_only():
    values = (
        "14 символов", "45 минут", "15 минут", "512000 байт",
        "45 дней", "30 тыс.", "200-3000 Мб/с",
    )
    source = (
        "Установлена минимальная длина пароля 14 символов. "
        "Длительность блокировки учетной записи 45 минут. "
        "Установлено максимальное отклонение 15 минут. "
        "Журнал Application установлен 512000 байт. "
        "Срок хранения 45 дней. "
        "Общее количество активных пользовательских аккаунтов примерно 30 тыс. "
        "Скорость филиала 200-3000 Мб/с."
    )

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in values)
    assert result.text.count("[МЕТРИКА-") == len(values)
    disabled = Anonymizer(disabled_categories={"МЕТРИКА"}).anonymize(source)
    assert all(value in disabled.text for value in values)
    assert "[МЕТРИКА-" not in disabled.text
    ordinary = Anonymizer().anonymize("В документе 14 символов и 45 минут")
    assert "[МЕТРИКА-" not in ordinary.text


def test_server_inventory_masks_complete_os_cells_only_in_table_context():
    source = (
        "Серверы\ufdd0\ufdd1\ufdd0[УЗЕЛ-1]\ufdd0[IP-1]\ufdd0Windows Server 2022 Standard"
        "\ufdd0\ufdd2\ufdd0[УЗЕЛ-2]\ufdd0[IP-2]\ufdd0Windows Server 2012 R2 Standard"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "Windows Server 2022 Standard" not in result.text
    assert "Windows Server 2012 R2 Standard" not in result.text
    assert result.text.count("[ПРОГРАММА-") == 2
    ordinary = Anonymizer().anonymize("Windows Server 2022 Standard")
    assert "Windows Server 2022 Standard" in ordinary.text


def test_single_unconfirmed_system_row_is_not_guessed():
    source = (
        "\ufdd0\ufdd1\ufdd01\ufdd0Ordinary Internal Suite\ufdd0Информационная система"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "Ordinary Internal Suite" in result.text
    assert "[СИСТЕМА-" not in result.text


def test_numbered_non_gpo_table_does_not_become_directory_inventory():
    source = (
        "Приложение Б Список документов"
        "\ufdd0\ufdd1\ufdd0№\ufdd0Наименование"
        "\ufdd0\ufdd2\ufdd01\ufdd0Ordinary Policy Notes"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "Ordinary Policy Notes" in result.text
    assert "[СТРУКТУРА-AD-" not in result.text
