import re

from local_anonymizer.engine import Anonymizer


def test_product_versions_are_complete_including_chains_and_marker_products():
    source = (
        "Тестовая версия Qzdesk 6.0.2 + Qzware версия 6.7.0. "
        "Цепочка Qzpost 3.3.0→3.4.0→4.1.0; "
        "[СОКРАЩЕНИЯ-5] Pro 2.4.0→3.1.0; [СОКРАЩЕНИЯ-6] 1.7.9uu1. "
        "Цепочка без имени 5.2.0→5.3.0; Шаблон адаптирован под 5.4.0"
    )

    result = Anonymizer().anonymize(source)

    for value in (
        "Qzdesk 6.0.2", "Qzware версия 6.7.0", "3.3.0", "3.4.0", "4.1.0",
        "2.4.0", "3.1.0", "1.7.9uu1", "5.2.0", "5.3.0", "5.4.0",
    ):
        assert value not in result.text
    assert re.search(r"\[ПРОГРАММА-\d+\]\.\d", result.text) is None


def test_export_timestamp_with_already_masked_label_is_document_metadata():
    source = "[СКРЫТО-1] on 2030-01-02 03:04:05"

    result = Anonymizer().anonymize(source)

    assert "2030-01-02 03:04:05" not in result.text
    assert result.text.count("[ДОКУМЕНТ-") == 1


def test_vm_inventory_masks_host_capacity_partition_and_ipv4_prefix():
    source = (
        "Компоненты\ufdd0\ufdd1\ufdd0№\ufdd0Компонент\ufdd0Hostname\ufdd0CPU\ufdd0RAM\ufdd0Disk\ufdd0Разметка\ufdd0IP\ufdd0Маска"
        "\ufdd0\ufdd2\ufdd01\ufdd0Основной сервер\ufdd0qzz-dhcpv-0001\ufdd04\ufdd08\ufdd0100"
        "\ufdd0/boot 1 [СОКРАЩЕНИЯ-57]/home 10 [СОКРАЩЕНИЯ-57]\ufdd0192.0.2.-\ufdd024"
        "\ufdd0\ufdd2\ufdd02\ufdd0Контроллер\ufdd0[УЗЕЛ-7]\ufdd04\ufdd08\ufdd0100"
        "\ufdd0/var 60 [СОКРАЩЕНИЯ-57]/var/log 30 [СОКРАЩЕНИЯ-57]\ufdd0[IP-8]\ufdd024"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "qzz-dhcpv-0001" not in result.text
    assert "192.0.2.-" not in result.text
    assert "/boot" not in result.text
    assert "/home" not in result.text
    assert "/var" not in result.text
    assert "/var/log" not in result.text
    assert "4\ufdd08\ufdd0100" not in result.text
    assert result.counts.get("УЗЕЛ") == 1
    assert result.text.count("[МЕТРИКА-") >= 8
    assert "1\ufdd0Основной сервер" in result.text

    second = Anonymizer().anonymize(result.text)
    assert second.text == result.text
    assert second.mapping == {}


def test_directory_group_names_and_internal_service_ids_are_masked():
    source = (
        "qzz_ald_global_admins, qzz_acm_admins, qzz_sso_support. "
        "Сервис сертификатов (certificate-authority-service), "
        "сервис хранения (storage-service). Адаптер для подключения (ca-adapter-service)"
    )

    result = Anonymizer().anonymize(source)

    for value in ("qzz_ald_global_admins", "qzz_acm_admins", "qzz_sso_support"):
        assert value not in result.text
    assert result.text.count("[СТРУКТУРА-AD-") == 3
    assert "certificate-authority-service" not in result.text
    assert "storage-service" not in result.text
    assert "ca-adapter-service" not in result.text
    assert result.text.count("[СИСТЕМА-") == 3


def test_password_policy_and_retention_metric_variants_are_masked():
    source = (
        "Требования к паролям: не менее 12 символов; максимальный срок действия — 120 дней. "
        "Пороговое значение блокировки: 7 неуспешных попыток в течение 10 минут. "
        "Длительность блокировки - 3600 минут. Не совпадать из пяти предыдущих паролей. "
        "Пароли содержат не менее чем трёх групп из четырёх. "
        "Данные в журнале изменений хранятся в течение 45 дней. "
        "Срок локального оперативного хранения журналов определен равным 14 дням."
    )

    result = Anonymizer().anonymize(source)

    for value in (
        "12 символов", "120 дней", "7 неуспешных", "10 минут", "3600 минут",
        "пяти", "трёх групп из четырёх", "45 дней", "14 дням",
    ):
        assert value not in result.text
    assert result.text.count("[МЕТРИКА-") == 9


def test_role_matrix_location_aliases_are_masked_without_a_city_dictionary():
    source = (
        "Каталог ou=Зыряновск, сайт Зыряновск. Региональный оператор (Зыряновск). "
        "([ГОРОД-1], Зыряновск). Региональные администраторы (Зыряновск). "
        "Специалист региональной поддержки (Зыряновск). Статический каталог Зыряновск. "
        "Региональный оператор [СОКРАЩЕНИЯ-50] (Зыряновск). ([ГОРОД-1], Зыряновск\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "Зыряновск" not in result.text
    assert result.counts.get("ГОРОД") == 9


def test_software_inventory_masks_product_and_version_cells():
    source = (
        "Программное обеспечение\ufdd0\ufdd1\ufdd0№\ufdd0Подсистема\ufdd0ПО\ufdd0Версия\ufdd0Лицензия"
        "\ufdd0\ufdd2\ufdd01\ufdd0Службы каталога\ufdd0Qz Directory Suite\ufdd09.4\ufdd0Коммерческая"
        "\ufdd0\ufdd2\ufdd02\ufdd0Аутентификация\ufdd0Qz Identity\ufdd026.1\ufdd0Открытая"
        "\ufdd0\ufdd2\ufdd0Повтор: Qz Identity"
    )

    result = Anonymizer().anonymize(source)

    for value in ("Qz Directory Suite", "Qz Identity", "9.4", "26.1"):
        assert value not in result.text
    assert result.text.count("[ПРОГРАММА-") == 5


def test_short_customer_name_in_project_context_is_masked():
    source = "Обсуждение хода проекта по Qz&Co"

    result = Anonymizer().anonymize(source)

    assert "Qz&Co" not in result.text
    assert result.text.count("[ОРГАНИЗАЦИЯ-") == 1
    cyrillic = Anonymizer().anonymize("Обсуждение хода проекта по Заря К&К")
    assert "Заря К&К" not in cyrillic.text
    assert cyrillic.text.count("[ОРГАНИЗАЦИЯ-") == 1


def test_network_interaction_table_masks_complete_port_cells():
    source = (
        "Сетевое взаимодействие\ufdd0\ufdd1\ufdd0Источник\ufdd0Назначение\ufdd0Порт\ufdd0Протокол\ufdd0Пояснение"
        "\ufdd0\ufdd2\ufdd0Клиент\ufdd0Сервер\ufdd0464, 749\ufdd0TCP\ufdd0Администрирование"
        "\ufdd0\ufdd2\ufdd0Клиент\ufdd0Сервер\ufdd080, 443\ufdd0TCP\ufdd0Загрузка"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "464, 749" not in result.text
    assert "80, 443" not in result.text
    assert result.text.count("[ПОРТ-") == 2
    assert "Клиент" in result.text
    assert "Сервер" in result.text


def test_keycloak_role_identifiers_are_directory_structure():
    source = "Роль Keycloak: view-users, manage-users, realm-admin, view-events и view-realm."

    result = Anonymizer().anonymize(source)

    for value in ("view-users", "manage-users", "realm-admin", "view-events", "view-realm"):
        assert value not in result.text
    assert result.text.count("[СТРУКТУРА-AD-") == 5


def test_project_capacity_and_service_hours_are_metrics():
    source = (
        "Пилотная группа до 30 пользователей; 3 сервера; "
        "кластерные аэропорты — 5 шт.; тиражирование на 24 аэропортах; "
        "консультационная поддержка 300 часов"
    )

    result = Anonymizer().anonymize(source)

    for value in ("30", "3 сервера", "5 шт.", "24 аэропортах", "300 часов"):
        assert value not in result.text
    assert result.text.count("[МЕТРИКА-") == 5


def test_meeting_and_project_dates_are_document_metadata():
    source = (
        "2030-01-02-Обсуждение проекта\ufdd0"
        "Проект длился с 01.02.2030 по 03.04.2031. На 05.06.2030 подтверждений нет.\ufdd0"
        "Янв 2031 — проверка\ufdd07–13 апр 2031 — обновление\ufdd0"
        "Дирекция – 09.08.2030 [ОРГАНИЗАЦИЯ-1]. Сопровождение"
    )

    result = Anonymizer().anonymize(source)

    for value in ("2030-01-02", "01.02.2030", "03.04.2031", "05.06.2030", "Янв 2031", "7–13 апр 2031", "09.08.2030"):
        assert value not in result.text
    assert result.text.count("[ДОКУМЕНТ-") == 7


def test_software_inventory_generates_vendor_acronym_alias():
    source = (
        "ПО\ufdd0\ufdd1\ufdd0№\ufdd0Подсистема\ufdd0ПО\ufdd0Версия\ufdd0Лицензия"
        "\ufdd0\ufdd2\ufdd01\ufdd0Сертификация\ufdd0Qz Enterprise Certificate Authority\ufdd09.4\ufdd0Коммерческая"
        "\ufdd0\ufdd2\ufdd0Повтор: Qz ECA"
    )

    result = Anonymizer().anonymize(source)

    assert "Qz Enterprise Certificate Authority" not in result.text
    assert "Qz ECA" not in result.text
    assert result.text.count("[ПРОГРАММА-") == 3


def test_role_context_product_names_and_aliases_are_masked():
    source = (
        "На базе Qzlog-NG. Веб-сервера (Qzweb2). Служба Qzagent. "
        "Программных продуктов Qz Enterprise Certificate Authority Certified Edition и Qzid. "
        "Компоненты Qz ECA. Центр сертификации Qz Enterprise Certification Authority. "
        "Open source решении Qzlog-ng. Централизованное управление (Qz Enterprise [СОКРАЩЕНИЯ-2]). "
        "Повтор: Qzlog-NG."
    )

    result = Anonymizer().anonymize(source)

    for value in (
        "Qzlog-NG", "Qzweb2", "Qzagent", "Qz Enterprise Certificate Authority Certified Edition",
        "Qzid", "Qz ECA", "Qz Enterprise Certification Authority", "Qzlog-ng", "Qz Enterprise",
    ):
        assert value not in result.text
    assert result.text.count("Qzlog-NG") == 0


def test_quantity_column_and_marker_site_counts_are_metrics():
    source = (
        "Размещение\ufdd0\ufdd1\ufdd0Площадка\ufdd0Количество [СОКРАЩЕНИЯ-34]\ufdd0Размещение"
        "\ufdd0\ufdd2\ufdd0[СОКРАЩЕНИЯ-13] (9 шт.)\ufdd07\ufdd0На каждом узле"
        "\ufdd0\ufdd2\ufdd0[СОКРАЩЕНИЯ-14]\ufdd03\ufdd0На каждом узле"
        "\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "9 шт." not in result.text
    assert "\ufdd07\ufdd0" not in result.text
    assert "\ufdd03\ufdd0" not in result.text
    assert result.text.count("[МЕТРИКА-") == 3
