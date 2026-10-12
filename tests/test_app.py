import base64
import json
from pathlib import Path
from html.parser import HTMLParser
import re
import sys
from types import SimpleNamespace

import pytest

import local_anonymizer.app as app_module
from local_anonymizer.app import AppApi, asset_path, smoke_check
from local_anonymizer.engine import Anonymizer
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def test_bundled_ui_and_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    index = asset_path("index-v1.8.18.html")
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    for label in ("Исходный текст", "Обезличенный текст", "Вернуть исходные значения", "Настройки", "Проверка движка"):
        assert label in html
    assert "http://" not in html and "https://" not in html
    assert smoke_check()["ok"] is True
    summary = AppApi().engine_self_test()
    assert summary["ok"] is True
    assert summary["vm_node_ok"] is True
    assert summary["graphics_roundtrip_ok"] is True
    assert "Иванов" not in str(summary)


def test_profile_json_export_import_roundtrip_restores_exact_settings(tmp_path):
    profile_file = tmp_path / "Общий.json"

    class Window:
        def create_file_dialog(self, *args, **kwargs):
            return [str(profile_file)]

    api = AppApi(tmp_path / "data")
    api.set_window(Window())
    rules = "Переключение => СКРЫТО\nПоведение => ТЕРМИН"
    assert api.save_profile("Общий", rules, "Оставить\nРазрешено", True)["ok"] is True
    assert api.export_profile("Общий")["ok"] is True

    exported = profile_file.read_text(encoding="utf-8")
    assert '"version": 1' in exported
    assert '"Переключение": "СКРЫТО"' in exported
    api.save_profile("Общий", "", "", False)

    result = api.import_profile()
    assert result["ok"] is True
    assert result["name"] == "Общий"
    assert api.load_profile("Общий") == {
        "version": 1,
        "name": "Общий",
        "dictionary": {"Переключение": "СКРЫТО", "Поведение": "ТЕРМИН"},
        "whitelist": ["Оставить", "Разрешено"],
        "paranoid": True,
    }


def test_cancelled_profile_export_does_not_persist_visible_settings(tmp_path):
    class Window:
        def create_file_dialog(self, *args, **kwargs):
            return None

    api = AppApi(tmp_path / "data")
    api.save_profile("Общий", "Старое => ПРАВИЛО", "Старый список", False)
    before = api.load_profile("Общий")
    api.set_window(Window())

    result = api.export_profile("Общий", "Новое => ПРАВИЛО", "Новый список", True)

    assert result == {"ok": False}
    assert api.load_profile("Общий") == before


def test_profile_json_import_reports_invalid_file_without_overwriting_profile(tmp_path):
    profile_file = tmp_path / "broken.json"
    profile_file.write_text('{"version": 1, "name": "Общий", "dictionary": ', encoding="utf-8")

    class Window:
        def create_file_dialog(self, *args, **kwargs):
            return [str(profile_file)]

    api = AppApi(tmp_path / "data")
    api.save_profile("Общий", "Переключение => СКРЫТО", "Оставить", False)
    before = api.load_profile("Общий")
    api.set_window(Window())

    result = api.import_profile()
    assert result == {"ok": False, "error": "Файл профиля содержит некорректный JSON."}
    assert api.load_profile("Общий") == before

    profile_file.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "Общий",
                "dictionary": [],
                "whitelist": [],
                "paranoid": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = api.import_profile()
    assert result["ok"] is False
    assert result["error"].startswith("Профиль не импортирован:")
    assert api.load_profile("Общий") == before


def test_text_previews_share_the_top_row_and_manual_review_is_below_them():
    class LayoutParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.parents = {}
            self.children = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            node = attrs.get("id") or (
                "columns" if tag == "main" and "columns" in attrs.get("class", "").split() else None
            )
            parent = next((item for item in reversed(self.stack) if item), None)
            if node:
                self.parents[node] = parent
                self.children.setdefault(parent, []).append(node)
            self.stack.append(node)

        def handle_endtag(self, tag):
            self.stack.pop()

    parser = LayoutParser()
    parser.feed(asset_path("index-v1.8.18.html").read_text(encoding="utf-8"))

    assert parser.parents["source"] == "textPreview"
    assert parser.parents["anonymizedDocxPreview"] == "anonymizedPreviewSurface"
    assert parser.parents["anonymizedPreviewSurface"] == "columns"
    assert parser.parents["manualReview"] == "columns"
    assert parser.parents["warning"] == "manualReview"
    assert parser.children["columns"].index("manualReview") > parser.children["columns"].index("anonymizedPreviewSurface")


def test_settings_have_one_checkbox_per_actual_replacement_class():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    controls = re.findall(
        r'<input class="category" data-categories="([^"]+)"[^>]*>\s*([^<]+)',
        html,
    )
    categories = [category for category, _label in controls]
    assert len(categories) == len(set(categories))
    assert all("," not in category for category in categories)

    expected = {
        "уязвимость", "ПОЧТА", "ТЕЛЕФОН", "АККАУНТ", "IP", "MAC", "IMEI", "ССЫЛКА",
        "ДОМЕН", "УЗЕЛ", "DN", "СТРУКТУРА-AD", "ДИСК", "ПУТЬ", "СЗИ",
        "ПРОГРАММА", "СКРИПТЫ", "ПРОИЗВОДИТЕЛЬ", "ИНН", "ОГРН", "СНИЛС",
        "КАРТА", "КПП", "СЧЁТ", "БИК", "ПАСПОРТ", "VIN", "КАДАСТР",
        "ГОСНОМЕР", "ТАБЕЛЬНЫЙ", "ДОГОВОР", "ДОКУМЕНТ", "ДАТА-РОЖДЕНИЯ",
        "СУММА", "СТАВКА", "ФИО", "ЛОГИН", "ОРГАНИЗАЦИЯ", "СИСТЕМА",
        "ЗАДАЧА", "ГОРОД", "ДОЛЖНОСТЬ", "СПЕЦКАТЕГОРИЯ", "СКРЫТО",
        "CUSTOM", "HINTS",
    }
    assert set(categories) == expected

    assert "IP-адрес → <code>[IP-N]</code>" in html
    assert "Домен → <code>[ДОМЕН-N]</code>" in html
    assert "Электронная почта → <code>[ПОЧТА-N]</code>" in html
    assert "Ссылка → <code>[ССЫЛКА-N]</code>" in html
    assert "Уязвимость → <code>[уязвимость]</code>" in html
    assert "Дополнительные правила → <code>[МЕТКА-N]</code>" in html
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    assert "function updateCategoryMarkerExamples()" in javascript
    assert "updateCategoryMarkerExamples();markSettingsDirty()" in javascript


def test_disabling_one_replacement_class_does_not_disable_or_enable_another():
    source = "Узел 198.51.100.23 доступен как node.example.test."

    no_ip = Anonymizer(disabled_categories={"IP"}).anonymize(source)
    assert "198.51.100.23" in no_ip.text
    assert "[IP-" not in no_ip.text
    assert "[ДОМЕН-" in no_ip.text

    no_domain = Anonymizer(disabled_categories={"ДОМЕН"}).anonymize(source)
    assert "node.example.test" in no_domain.text
    assert "[ДОМЕН-" not in no_domain.text
    assert "[IP-" in no_domain.text


def test_disabled_outer_class_is_not_partially_replaced_by_fallback_detectors():
    source = "Пишите на user@example.test или откройте https://portal.example.test/path."

    result = Anonymizer(disabled_categories={"ПОЧТА", "ССЫЛКА"}).anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_interface_contains_complete_collapsed_usage_and_restore_guide():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    required = (
        "Как пользоваться программой",
        "Выбрать исходные файлы…",
        "Применить настройки к файлу",
        "Сохранить два файла…",
        "решения вручную",
        "Как вернуть исходные значения после экспорта",
        "Восстановить файл…",
        "Программа автоматически найдёт",
        "переносимый",
        "Windows и Linux",
        "содержит исходные значения",
        "NETBIOS",
        "OU",
        "названия дисков",
        "списки программ",
    )
    assert all(text in html for text in required)
    assert "зашифрован средствами Windows" not in html
    assert "профиле Windows" not in html
    assert '<details class="card usage-guide">' in html
    assert '<details class="card usage-guide" open>' not in html
    assert "guide.open" not in javascript
    assert 'id="stats">Версия 1.8' in html
    assert 'id="stats">Версия 1.7' not in html


def test_gui_loads_default_profile_rules_on_startup():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert (
        "showLibrary(await pywebview.api.list_documents());await refreshProfiles('Общий');"
        "await loadProfileIntoEditor('Общий');"
    ) in javascript



def test_native_window_handle_is_private_to_avoid_pywebview_bridge_introspection(tmp_path):
    api = AppApi(root=tmp_path)
    sentinel = object()
    api.set_window(sentinel)
    assert not hasattr(api, "window")
    assert api._window is sentinel


def test_new_design_exposes_primary_four_step_workflow_and_file_state():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    assert 'id="workflowSteps"' in html
    for label in ("Документ", "Проверка", "Применение", "Экспорт"):
        assert label in html
    assert 'id="fileLifecycleStatus"' in html
    assert 'id="applyNow"' in html
    assert 'id="exportNow"' in html


def test_header_describes_all_sensitive_data_not_only_personal_data():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    assert "Персональные и другие чувствительные данные заменяются маркерами или удаляются." in html
    assert "Персональные данные заменяются маркерами." not in html


def test_new_design_styles_define_contrast_actions_targets_and_focus():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    css = asset_path("new-design-v1.7.css").read_text(encoding="utf-8") if asset_path("new-design-v1.7.css").exists() else ""

    assert 'new-design-v1.7.css' in html
    for token in ("--text-primary", "--text-secondary", "--surface", "--border", "--action-primary", "--danger", "--warning", "--success"):
        assert token in css
    assert ":focus-visible" in css
    assert "min-height:40px" in css
    assert 'body[data-design="new"]>details{order:6}' in css
    assert 'body[data-design="legacy"]' in css
    assert "--border:#647c92" in css
    assert "--focus:#0069c0" in css
    assert "summary{min-height:24px" in css


def test_dark_new_design_stat_chips_have_explicit_readable_colors():
    css = asset_path("new-design-v1.7.css").read_text(encoding="utf-8")

    assert 'html[data-theme="dark"] body[data-design="new"] .chips span{' in css
    assert "background:var(--surface-raised)" in css
    assert "color:var(--text-primary)" in css
    assert 'html[data-theme="dark"] body[data-design="new"] .chips .yellow{' in css
    assert "background:#fff5c5" in css
    assert "color:#725a00" in css


def test_new_design_current_review_text_has_explicit_readable_color():
    css = asset_path("new-design-v1.7.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"] #reviewCurrent{color:var(--text-primary)}' in css


def test_new_design_hides_empty_review_result_status():
    css = asset_path("new-design-v1.7.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"] #resultStatus:empty{display:none}' in css


def test_new_design_has_labels_headings_live_status_and_sensitive_artifact_warnings():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    assert '<label for="source"' in html
    assert '<h2 id="reviewTitle">Ручная проверка спорных мест</h2>' in html
    assert 'id="fileLifecycleStatus"' in html and 'role="status"' in html
    assert "локальный архив документов и ключей восстановления" in html.lower()
    assert "профиль может содержать исходные чувствительные значения" in html.lower()
    for field in ("library", "profile"):
        assert f'<label for="{field}"' in html
    for status in ("fileStatus", "restoreStatus", "testResult", "warning"):
        assert f'id="{status}"' in html
    assert 'id="richOutput"' in html and 'role="region"' in html
    assert '<h2 id="sourceHeading">Исходный текст</h2>' in html
    assert '<h2 id="outputHeading">Обезличенный текст</h2>' in html


def test_new_design_uses_plain_language_stats_review_context_and_operation_states():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert 'id="reviewMeta"' in html
    for text in ("Найдено замен:", "Требуют решения:", "Проверено:", "Создаётся предпросмотр", "Обрабатывается файл"):
        assert text in javascript
    assert "одинаковых вхождений" in javascript
    assert "Решение сохранится в наборе правил" in javascript


def test_generated_markers_use_native_buttons():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert 'class="maprow"' not in javascript
    assert '<button type="button" class="mark-hint' in javascript
    assert '<button type="button" class="${p.secret?' in javascript
    assert 'role="button" tabindex="0"' not in javascript
    assert "activateKeyboardAction" not in javascript


def test_fullscreen_preview_uses_modal_semantics_and_restores_focus():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert 'id="docxPreviewSurface"' in html
    assert 'id="anonymizedPreviewSurface"' in html
    assert "setAttribute('role','dialog')" in javascript
    assert "ariaModal" in javascript
    assert "function setModalIsolation" in javascript
    assert "function trapModalFocus" in javascript
    assert "previousInert" in javascript
    assert "fullscreenReturnFocus" in javascript


def test_desktop_window_allows_760px_accessibility_layout():
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "min_size=(720, 700)" in source


def test_double_escape_no_longer_silently_clears_user_work():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "now-lastEscape<800" not in javascript
    assert "confirm('Очистить введённый текст" in javascript


def test_ui_offers_persistent_new_and_legacy_design_modes():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert 'id="designMode"' in html
    assert '<option value="new">Новый дизайн</option>' in html
    assert '<option value="legacy">Старый дизайн</option>' in html
    assert "function applyDesignMode" in javascript
    assert "localStorage.setItem('designMode'" in javascript
    assert "pywebview.api.get_design_mode()" in javascript
    assert "pywebview.api.set_design_mode" in javascript
    assert "document.body.dataset.design" in javascript


def test_ui_offers_complete_persistent_english_interface():
    russian_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    english_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")
    russian_js = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    english_js = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert '<html lang="ru">' in russian_html
    assert '<html lang="en">' in english_html
    assert '<script src="app-v1.8.15.js"></script>' in russian_html
    assert '<script src="app-en-v1.8.15.js"></script>' in english_html
    assert 'id="languageMode"' in russian_html and 'id="languageMode"' in english_html
    assert "Anonymize text or a document" in english_html
    assert "Manual review of uncertain items" in english_html
    assert "Local library" in english_html
    assert 'aria-label="Anonymized text"' in english_html
    assert "pywebview.api.set_language(value)" in russian_js
    assert "pywebview.api.set_language(value)" in english_js

    id_pattern = re.compile(r'id="([^"]+)"')
    assert set(id_pattern.findall(russian_html)) == set(id_pattern.findall(english_html))


def test_english_interface_localizes_backend_statuses_profile_and_review_kinds():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "function documentStatusText(status)" in javascript
    assert "`${d.display_name} — ${documentStatusText(d.status)}`" in javascript
    assert "`Preview: ${preview.display_name} — ${documentStatusText(preview.status)}`" in javascript
    assert "function profileDisplayName(name)" in javascript
    assert "o.textContent=profileDisplayName(n)" in javascript
    assert "function hintKindText(kind)" in javascript
    assert "hintKindText(p.kind)" in javascript
    assert "hintKindText(all[reviewIndex].dataset.kind)" in javascript


def test_english_interface_never_falls_back_to_raw_unknown_backend_status():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "||status;" not in javascript
    assert "'Unknown status'" in javascript


def test_english_interface_localizes_profile_names_in_result_messages():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "`Profile “${profileDisplayName(n)}” saved.`" in javascript
    assert "`Profile “${profileDisplayName(n)}” exported.`" in javascript
    assert "`Profile “${profileDisplayName(r.name)}” imported and loaded." in javascript


def test_english_interface_localizes_backend_warning_messages_without_changing_contract_keys():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    for warning_kind in (
        "ГОСТАЙНА", "ДСП", "КИИ", "ЗАКУПКИ", "МАССИВ-ПДН",
        "XLSX_FORMULA_BLOCKED", "XLSX_HYPERLINK", "XLSX_HEADER_FOOTER",
        "XLSX_DATA_VALIDATION", "XLSX_DEFINED_NAME", "XLSX_EXTERNAL_LINK",
        "XLSX_UNSUPPORTED_PART", "UNSUPPORTED_OFFICE_CONTENT",
    ):
        assert f"'{warning_kind}'" in javascript
    assert "function warningText(w)" in javascript
    assert "Manual review required:" in javascript


def test_english_interface_does_not_show_russian_profile_api_errors():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "function profileErrorText(operation)" in javascript
    assert "profileErrorText('export')" in javascript
    assert "profileErrorText('import')" in javascript
    assert "textContent=r.error;" not in javascript


def test_english_interface_localizes_post_anonymization_status_and_review_profile():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "`${documentStatusText(r.status)}. The file was created" in javascript
    assert "`${documentStatusText(r.status)}. The anonymized file is ready" in javascript
    assert "const profileName=profileDisplayName($('#profile').value||'Общий')" in javascript
    assert 'const profileName=$(\'#profile\').value||\'Общий\'' not in javascript


def test_english_interface_never_renders_raw_bridge_errors():
    javascript = asset_path("app-en-v1.8.15.js").read_text(encoding="utf-8")

    assert "function bridgeErrorText(operation)" in javascript
    assert "saved?.error||'Could not save profile'" not in javascript
    assert "${error}" not in javascript
    assert "String(error)" not in javascript
    assert "${formattedPreview.error}" not in javascript
    assert "${error?.message||error}" not in javascript
    assert ".map(x=>x.error)" not in javascript
    for operation in ("profile-save", "formatted-preview", "anonymize", "import", "restore"):
        assert f"bridgeErrorText('{operation}')" in javascript


def test_language_variants_do_not_duplicate_numbers_in_ordered_workflow_steps():
    for name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        workflow = html[html.index('id="workflowSteps"'):html.index("</nav>")]
        assert not re.search(r"<li>\d+\s", workflow)


def test_language_choice_is_persisted_by_backend_and_preserves_other_ui_settings(tmp_path):
    root = tmp_path / "app"
    first = AppApi(root=root)
    assert first.get_language() == "ru"
    assert first.set_theme("dark") == {"ok": True, "theme": "dark"}
    assert first.set_language("en") == {"ok": True, "language": "en"}

    second = AppApi(root=root)
    assert second.get_language() == "en"
    assert second.get_theme() == "dark"
    with pytest.raises(ValueError, match="язык"):
        second.set_language("de")


def test_rare_categories_are_forced_closed_on_every_launch():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "$('#detectionCategories').open=false" in javascript


def test_gui_entry_url_is_versioned_to_bypass_stale_webview_cache(tmp_path, monkeypatch):
    captured = {}

    def create_window(title, url, **kwargs):
        captured["url"] = url
        return object()

    fake_webview = SimpleNamespace(
        create_window=create_window,
        start=lambda **kwargs: captured.setdefault("start", kwargs),
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    assert app_module.main([]) == 0
    assert captured["url"].endswith("/index-v1.8.18.html")
    html = app_module.asset_path(app_module.INDEX_ASSET).read_text(encoding="utf-8")
    assert '<script src="app-v1.8.15.js"></script>' in html


def test_gui_starts_in_the_persisted_english_language(tmp_path, monkeypatch):
    captured = {}

    def create_window(title, url, **kwargs):
        captured.update(title=title, url=url)
        return object()

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    AppApi().set_language("en")
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=create_window, start=lambda **kwargs: None),
    )

    assert app_module.main([]) == 0
    assert captured["url"].endswith("/index-en-v1.8.18.html")
    assert captured["title"] == "Local Document Anonymizer"


def test_clipboard_read_is_exposed_through_native_api(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "_read_clipboard_text", lambda: "ВСТАВКА-АУДИТ")

    assert AppApi(root=tmp_path).read_clipboard_text() == {"text": "ВСТАВКА-АУДИТ"}


def test_app_api_exposes_compact_marker_mode(tmp_path):
    api = AppApi(root=tmp_path / "app")

    result = api.anonymize_text(
        "Иванов Иван Иванович работает в ООО «Ромашка».",
        compact_markers=True,
    )

    assert "[Ф-1]" in result["text"]
    assert "[ОРГ-1]" in result["text"]
    assert result["mapping"]["[Ф-1]"] == "Иванов Иван Иванович"


def test_compact_marker_checkbox_is_wired_to_all_anonymization_paths():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert 'id="compactMarkers"' in html
    assert "Сохранять компоновку" in html
    assert "$('#compactMarkers').checked" in javascript
    assert "'#compactMarkers'" in javascript


def test_paste_button_uses_native_api_instead_of_webview_clipboard_permission():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "pywebview.api.read_clipboard_text()" in javascript
    assert "navigator.clipboard.readText()" not in javascript


def test_every_button_has_a_meaningful_hover_tooltip():
    class ButtonParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.buttons = []

        def handle_starttag(self, tag, attrs):
            if tag == "button":
                self.buttons.append(dict(attrs))

    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    parser = ButtonParser()
    parser.feed(html)

    expected_ids = {
        "choose", "downloadAll", "deleteDoc", "paste", "sample", "clear",
        "previewTop", "previewBottom", "previewFullscreen", "showFormatted",
        "showTextPreview", "dropChoose", "copy", "downloadAnon", "help",
        "reviewPrev", "reviewNext", "hideCandidate", "keepCandidate",
        "anonymizedPreviewTop", "anonymizedPreviewBottom",
        "anonymizedPreviewFullscreen", "showAnonymizedFormatted",
        "showAnonymizedText", "anonymize", "restore",
        "chooseRestoreFile", "restoreFile", "newProfile", "deleteProfile", "exportProfile",
        "importProfile", "selftest", "themeToggle", "applyNow", "exportNow",
    }
    buttons = {button.get("id"): button for button in parser.buttons}
    assert set(buttons) == expected_ids
    missing = [button_id for button_id, button in buttons.items()
               if len(button.get("title", "").strip()) < 12]
    assert missing == []

    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    assert 'class="undo-chip"' in javascript
    assert 'title="Отменить возврат значения' in javascript

    assert 'id="buttonTooltip"' in html
    assert 'role="tooltip"' in html
    assert "pointerover" in javascript
    assert "showButtonTooltip" in javascript
    assert "hideButtonTooltip" in javascript


def test_manual_review_next_keeps_button_stationary_and_scrolls_only_the_text_preview():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    css = asset_path("style-v1.1.css").read_text(encoding="utf-8")

    focus_mark = javascript[javascript.index("function focusMark("):javascript.index("function reviewDisabledReason(")]
    assert "scrollReviewMarkWithinOutput" in focus_mark
    assert ".scrollIntoView(" not in focus_mark
    assert "rich.scrollTop" in javascript
    assert ".review-candidate{" in css
    candidate_rule = css[css.index(".review-candidate{"):css.index("}", css.index(".review-candidate{"))]
    assert "height:" in candidate_rule
    assert "overflow:auto" in candidate_rule


def test_hide_and_remember_reanonymizes_all_exact_repetitions_immediately():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    hide_hint = javascript[javascript.index("async function hideHint("):javascript.index("async function anonymizeText(")]

    assert "await anonymizeText()" in hide_hint
    assert "customCategory.checked=true" in hide_hint
    assert "Все одинаковые вхождения" in hide_hint
    assert "все одинаковые вхождения" in html


def test_hide_and_remember_persists_rule_in_the_active_profile_before_refreshing_preview():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    hide_hint = javascript[javascript.index("async function hideHint("):javascript.index("async function anonymizeText(")]

    save = "await pywebview.api.save_profile($('#profile').value,$('#rules').value,$('#whitelist').value,$('#paranoid').checked)"
    assert save in hide_hint
    assert hide_hint.index(save) < hide_hint.index("await anonymizeText()")
    assert "правило сохранено в профиле" in hide_hint


def test_gui_has_persistent_light_and_dark_theme_switch():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    css = asset_path("style-v1.1.css").read_text(encoding="utf-8")

    assert 'id="themeToggle"' in html
    assert 'aria-pressed="false"' in html
    assert "local-anonymizer-theme" in javascript
    assert "function applyTheme" in javascript
    assert "document.documentElement" in javascript and "dataset.theme" in javascript
    assert "localStorage.setItem" in javascript
    assert "pywebview.api.get_theme()" in javascript
    assert "pywebview.api.set_theme" in javascript
    assert "prefers-color-scheme: dark" in javascript
    assert ':root[data-theme="dark"]' in css
    assert "color-scheme:dark" in css


def test_theme_choice_is_persisted_by_the_local_backend(tmp_path):
    first = AppApi(root=tmp_path / "app")
    assert first.get_theme() is None
    assert first.set_theme("dark") == {"ok": True, "theme": "dark"}

    second = AppApi(root=tmp_path / "app")
    assert second.get_theme() == "dark"
    assert second.set_theme("light") == {"ok": True, "theme": "light"}
    assert AppApi(root=tmp_path / "app").get_theme() == "light"


def test_design_choice_is_persisted_by_backend_and_preserves_theme(tmp_path):
    root = tmp_path / "app"
    first = AppApi(root=root)
    assert first.get_design_mode() is None
    assert first.set_theme("dark") == {"ok": True, "theme": "dark"}
    assert first.set_design_mode("legacy") == {"ok": True, "design_mode": "legacy"}

    second = AppApi(root=root)
    assert second.get_design_mode() == "legacy"
    assert second.get_theme() == "dark"
    assert second.set_design_mode("new") == {"ok": True, "design_mode": "new"}
    assert AppApi(root=root).get_design_mode() == "new"
    assert AppApi(root=root).get_theme() == "dark"


def test_settings_offer_docx_graphics_as_an_explicit_checkbox():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    assert "Секреты и ключи защищаются всегда" in html
    assert "checkbox\" checked disabled" not in html
    assert 'id="redactDocxGraphics"' in html
    assert 'data-object-scope="docx-static-graphics"' in html
    assert "DOCX: скрывать встроенные рисунки и статические схемы" in html
    assert "схемы скрываются всегда" not in html
    assert "[СХЕМА-N]" in html
    assert "изображение удаляется целиком" in html
    assert "Текст внутри пикселей отдельно не распознаётся" in html
    assert "SmartArt, диаграммы, OLE и графика XLSX" in html
    assert "экспорт блокируется" in html
    assert "Отключённые категории останутся в документе без замены" in html
    for control_id in ("paranoid", "compactMarkers", "mono"):
        assert f'id="{control_id}"' in html
    for explanation in (
        "заменяет все жёлтые подсказки",
        "укорачивает подписи маркеров",
        "меняет только отображение текста",
    ):
        assert explanation in html

    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    assert "$('#redactDocxGraphics').checked" in javascript
    assert "['#rules','#whitelist','#paranoid','#redactDocxGraphics']" in javascript


def test_settings_and_primary_action_explain_their_real_effect():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    settings_start = html.index("Настройки обезличивания")
    action_position = html.index('id="anonymize"')
    assert settings_start < action_position
    assert "Предпросмотр меняется автоматически" in html
    assert "Применить настройки к файлу" in html
    assert 'id="settingsStatus"' in html
    assert "Изменения настроек ещё не применены к экспортируемому файлу" in javascript
    assert "Настройки применены. Файл готов к экспорту." in javascript


def test_new_design_shows_only_one_apply_and_one_export_action():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    css = asset_path("new-design-v1.7.css").read_text(encoding="utf-8")

    assert 'id="exportNow" title="Сохранить обезличенный документ и переносимый файл восстановления рядом">Сохранить документ и файл восстановления</button>' in html
    assert 'body[data-design="new"] #anonymize,body[data-design="new"] #downloadAnon{display:none!important}' in css


def test_detection_categories_are_a_separate_collapsed_section_at_the_very_bottom():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    section_start = html.index('<details class="card" id="detectionCategories">')
    section_end = html.index("</details>", section_start)
    settings_end = html.index("</details>", html.index("Настройки обезличивания"))
    selftest_start = html.index("Проверка движка")
    footer_start = html.index("<footer>")

    assert settings_end < selftest_start < section_start < section_end < footer_start
    assert "open" not in html[section_start : html.index(">", section_start)]
    assert "Категории поиска и замены" in html[section_start:section_end]
    assert "Что искать и заменять" in html[section_start:section_end]
    assert "Секреты и ключи защищаются всегда" in html[section_start:section_end]
    assert 'id="redactDocxGraphics"' in html[section_start:section_end]
    assert 'data-categories="IP"' in html[section_start:section_end]
    assert 'data-categories="СТАВКА"' in html[section_start:section_end]
    assert "Что искать и заменять" not in html[html.index("Настройки обезличивания") : settings_end]


def test_category_change_renders_text_result_before_slow_formatted_preview():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    text_await = "const result=await pywebview.api.anonymize_text(text,...settings);"
    formatted_await = "formattedPreview=await formatted"
    assert text_await in javascript
    assert formatted_await in javascript
    render_after_text = javascript.index("renderOutput()", javascript.index(text_await))
    assert javascript.index(text_await) < render_after_text < javascript.index(formatted_await)
    assert "setAnonymizedPreviewMode(false)" in javascript
    assert "Предпросмотр обновлён" in javascript


def test_review_navigation_is_limited_to_actionable_yellow_hints():
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "function hintMarks()" in javascript
    assert "const all=hintMarks()" in javascript
    assert "reviewIndex=all.length?0:-1" in javascript
    assert "$('#hideCandidate').disabled=!hasCurrent" in javascript
    assert "$('#keepCandidate').disabled=!hasCurrent" in javascript


def test_local_library_is_compact_inside_the_source_editor():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    source_start = html.index('aria-labelledby="sourceHeading"')
    source_end = html.index('</section>', source_start)
    source_section = html[source_start:source_end]
    assert '<details id="sourceLibrary" class="source-library">' in source_section
    assert '<summary>Файлы и библиотека</summary>' in source_section
    assert 'id="library"' in source_section
    assert 'id="choose"' in source_section
    assert 'id="fileStatus"' in source_section
    assert 'id="downloadAll"' in source_section
    assert 'id="deleteDoc"' in source_section
    assert '<details id="sourceLibrary" class="source-library" open>' not in html
    assert '<section class="library card"' not in html


def test_pasted_text_restoration_reuses_the_main_source_editor():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    source_section = html[html.index('aria-labelledby="sourceHeading"'):html.index('</section>', html.index('aria-labelledby="sourceHeading"'))]
    assert 'id="restore"' in source_section
    assert "Вернуть исходные значения" in source_section
    assert "Восстановление текста — Обратная замена маркеров" not in html
    assert 'id="reverse"' not in html
    assert 'id="restored"' not in html
    assert 'id="copyRestored"' not in html
    assert "restore_text($('#source').value,textRestoreMapping)" in javascript
    assert "$('#source').value=result.text" in javascript
    assert "$('#reverse')" not in javascript
    assert "$('#restored')" not in javascript
    assert "$('#copyRestored')" not in javascript


def test_legacy_mapping_table_and_csv_export_are_not_exposed_in_ui():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "Таблица соответствий" not in html
    assert "Экспорт CSV (чувствительные данные)" not in html
    assert 'id="mapping"' not in html
    assert 'id="mapCount"' not in html
    assert 'id="csv"' not in html
    assert "$('#mapping')" not in javascript
    assert "$('#mapCount')" not in javascript
    assert "$('#csv')" not in javascript
    assert "export_mapping" not in javascript
    assert "last.mapping=mapping||{}" in javascript


def test_manual_review_owns_its_search_and_display_controls():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    review_start = html.index('id="manualReview"')
    review_end = html.index("</section>", review_start)
    review = html[review_start:review_end]
    settings_start = html.index("Настройки обезличивания")
    categories_start = html.index('id="detectionCategories"')

    for control_id in ("reviewHints", "paranoid", "compactMarkers", "mono"):
        assert f'id="{control_id}"' in review
    assert "Искать спорные места для ручной проверки" in review
    assert "Дополнительные режимы" in review
    assert 'data-categories="HINTS"' not in html[categories_start:]
    assert 'id="paranoid"' not in html[settings_start:categories_start]


def test_manual_review_panel_explains_actions_progress_result_and_completion():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    for text in (
        "Ручная проверка спорных мест",
        "Почему оно здесь",
        "Скрыть и запомнить правило",
        "Оставить и добавить в исключения",
        "заменён маркером",
        "останется без изменения",
        "Как закончить проверку",
    ):
        assert text in html
    assert 'id="reviewDecision"' in html
    assert 'id="reviewFinish"' in html
    assert 'id="resultStatus"' in html
    assert "Осталось ${remaining} из ${total}" in javascript
    assert "Решение принято:" in javascript
    assert "Очередь разобрана." in javascript
    assert "нажмите «Применить настройки к файлу»" in javascript
    assert "Ручная проверка завершена." in javascript
    assert "Теперь примените настройки к файлу." in javascript
    assert "$('#warning').textContent=hasCurrent?`Осталось спорных мест: ${remaining}.`:'Ручная проверка завершена: все спорные места разобраны.'" in javascript


def test_manual_review_makes_paranoid_conflict_and_current_candidate_obvious():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "Автоматически скрывать спорное без подтверждения" in html
    assert "жёлтой очереди для ручного решения не будет" in html
    assert 'id="reviewCurrent"' in html
    assert "Ручная проверка отключена" in javascript
    assert "снимите «Автоматически скрывать спорное без подтверждения»" in javascript
    assert "setAnonymizedPreviewMode(false)" in javascript
    assert "Текущее спорное место:" in javascript


def test_document_export_has_a_visible_matching_restore_import_action():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")

    assert "Сохранить два файла…" in html
    assert "информация для восстановления.larecovery" in html
    assert html.count('id="chooseRestoreFile"') == 1
    assert html.count('id="restoreFile"') == 1
    assert "Восстановить файл…" in html
    assert "Импортировать для восстановления…" not in html
    assert "function chooseRestorePair()" in javascript
    assert "function restoreMatchedFile()" in javascript
    assert "restoreFileTop" not in javascript
    assert "$('#chooseRestoreFile').onclick=chooseRestorePair" in javascript
    assert "$('#restoreFile').onclick=restoreMatchedFile" in javascript


def test_app_api_import_library_and_anonymize(tmp_path):
    source = tmp_path / "sample.docx"
    doc = Document(); doc.add_paragraph("Иванов Сергей Петрович"); doc.save(source)
    api = AppApi(root=tmp_path / "app")
    imported = api.import_paths([str(source)])
    assert imported["ok"] and len(api.list_documents()) == 1
    report = api.anonymize_document(imported["ids"][0])
    assert report["ready"]
    assert Path(api.service.storage.get_document(imported["ids"][0])["output_path"]).exists()
    assert "output_path" not in report and "operation_id" not in report and "document_id" not in report
    api.save_profile("Тест", "Вымпел => СИСТЕМА", "Казань", True)
    assert "Тест" in api.list_profiles()
    profile = api.load_profile("Тест")
    assert profile["dictionary"] == {"Вымпел": "СИСТЕМА"}
    api.delete_profile("Тест")
    assert "Тест" not in api.list_profiles()


def test_preview_document_extracts_docx_and_text_without_modifying_sources(tmp_path):
    text_source = tmp_path / "note.txt"
    text_source.write_text("login admin_db", encoding="utf-8")
    docx_source = tmp_path / "note.docx"
    doc = Document(); doc.add_paragraph("Иванов Сергей Петрович")
    table = doc.add_table(rows=1, cols=1); table.cell(0, 0).text = "АС «Паутина»"
    doc.save(docx_source)
    api = AppApi(root=tmp_path / "app")
    ids = api.import_paths([str(text_source), str(docx_source)])["ids"]
    previews = [api.preview_document(doc_id) for doc_id in ids]
    assert previews[0]["text"] == "login admin_db"
    assert "Иванов Сергей Петрович" in previews[1]["text"]
    assert "АС «Паутина»" in previews[1]["text"]
    assert text_source.read_text(encoding="utf-8") == "login admin_db"


def test_docx_preview_is_formatted_ordered_and_escaped_without_links(tmp_path):
    source = tmp_path / "rich.docx"
    doc = Document()
    heading = doc.add_heading("Заголовок <script>alert(1)</script>", level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph = doc.add_paragraph()
    bold = paragraph.add_run("жирный")
    bold.bold = True
    italic = paragraph.add_run(" курсив")
    italic.italic = True
    underline = paragraph.add_run(" подчёркнутый")
    underline.underline = True
    styled = paragraph.add_run(" цвет")
    styled.font.size = Pt(18)
    styled.font.color.rgb = RGBColor(0x12, 0x34, 0x56)
    styled.add_break()
    styled.add_tab()
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "rEvil")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "безопасная подпись"
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "ячейка"
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "вложенная"
    header = doc.sections[0].header.paragraphs[0]
    header.text = "Верхний колонтитул"
    footer = doc.sections[0].footer.paragraphs[0]
    footer.text = "Нижний колонтитул"
    doc.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    preview = api.preview_document(document_id)
    rich = preview["rich_html"]

    assert set(preview) == {"display_name", "text", "status", "kind", "format", "rich_html"}
    assert preview["kind"] == "document" and preview["format"] == "docx"
    assert rich.index("<h1") < rich.index("<table")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rich and "<script" not in rich
    assert "<strong>жирный</strong>" in rich
    assert "<em> курсив</em>" in rich
    assert "<u> подчёркнутый</u>" in rich
    assert 'class="docx-paragraph align-center"' in rich
    assert 'style="font-size:18pt;color:#123456"' in rich
    assert rich.count('class="docx-table"') >= 2
    assert "ячейка" in rich and "вложенная" in rich
    assert 'class="docx-header"' in rich and "Верхний колонтитул" in rich
    assert 'class="docx-footer"' in rich and "Нижний колонтитул" in rich
    assert "<br>" in rich and 'class="docx-tab"' in rich
    assert "rEvil" not in rich and "relationship" not in rich and "href=" not in rich
    assert document_id not in repr(preview) and str(tmp_path) not in repr(preview)


def test_docx_preview_renders_safe_embedded_png_but_anonymized_preview_only_shows_marker(tmp_path):
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    image = tmp_path / "synthetic.png"
    source = tmp_path / "with-image.docx"
    image.write_bytes(image_bytes)
    document = Document()
    document.add_paragraph("До схемы")
    document.add_picture(str(image), width=Inches(2))
    document.add_paragraph("После схемы")
    document.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    source_html = api.preview_document(document_id)["rich_html"]
    anonymized_html = api.preview_anonymized_document(document_id)["rich_html"]

    encoded = base64.b64encode(image_bytes).decode("ascii")
    assert f'src="data:image/png;base64,{encoded}"' in source_html
    assert source_html.index("До схемы") < source_html.index("<img") < source_html.index("После схемы")
    assert str(tmp_path) not in source_html and "rId" not in source_html
    assert "data:image/" not in anonymized_html
    assert "[СХЕМА-1]" in anonymized_html


def test_docx_preview_malformed_custom_style_id_falls_back_safely(tmp_path):
    source = tmp_path / "malformed-style.docx"
    document = Document()
    paragraph = document.add_paragraph("Текст <script>alert(1)</script>")
    style = OxmlElement("w:pStyle")
    style.set(qn("w:val"), "Custom'\"Style")
    paragraph._p.get_or_add_pPr().append(style)
    document.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    preview = api.preview_document(document_id)

    assert '<p class="docx-paragraph">' in preview["rich_html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in preview["rich_html"]
    assert "<script" not in preview["rich_html"]
    assert "Custom" not in preview["rich_html"]


class DialogSequence:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def create_file_dialog(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def test_restore_document_chooses_edited_docx_then_saves_to_user_destination(tmp_path):
    source = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)
    internal_output = Path(api.service.storage.get_document(document_id)["output_path"])

    edited = tmp_path / "edited-anonymized.docx"
    edited.write_bytes(internal_output.read_bytes())
    edited_document = Document(edited)
    edited_document.add_paragraph("Новая правка [ФИО-999]")
    edited_document.save(edited)
    destination = tmp_path / "chosen" / "restored.docx"
    window = DialogSequence([str(edited)], [str(destination)])
    api.set_window(window)

    report = api.restore_document(document_id)

    assert report == {
        "ok": True,
        "path": str(destination),
        "unknown_markers": ["[ФИО-999]"],
    }
    assert destination.is_file()
    restored_text = "\n".join(p.text for p in Document(destination).paragraphs)
    assert "Иванов Сергей Петрович" in restored_text and "Новая правка [ФИО-999]" in restored_text
    assert [call[0][0] for call in window.calls] == [10, 30]
    assert window.calls[0][1]["directory"] == str(internal_output.parent)
    assert Path(window.calls[0][1]["directory"]).is_absolute()
    assert window.calls[1][1]["directory"] == str(edited.parent)
    assert Path(window.calls[1][1]["directory"]).is_absolute()
    assert window.calls[1][1]["file_types"] == ("DOCX (*.docx)",)
    assert "output_path" not in repr(report) and "operation_id" not in repr(report)
    assert document_id not in repr(report) and str(api.service.storage.root) not in repr(report)


def test_restore_document_cancelled_save_does_not_restore_or_leak_paths(tmp_path, monkeypatch):
    edited = tmp_path / "edited.docx"
    edited.write_bytes(b"not opened because save is cancelled")
    api = AppApi(root=tmp_path / "app")
    window = DialogSequence([str(edited)], None)
    api.set_window(window)
    monkeypatch.setattr(
        api.service,
        "restore",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("restore must not run")),
    )

    assert api.restore_document("opaque-selection") == {"ok": False}
    assert len(window.calls) == 2


def test_ui_offers_docx_preview_modes_and_explains_word_restore_workflow():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.15.js").read_text(encoding="utf-8")
    css = asset_path("style-v1.1.css").read_text(encoding="utf-8")

    for element_id in (
        "docxPreviewControls",
        "showFormatted",
        "showTextPreview",
        "previewTop",
        "previewBottom",
        "previewFullscreen",
        "previewCompleteness",
        "docxPreview",
        "anonymizedPreviewControls",
        "showAnonymizedFormatted",
        "showAnonymizedText",
        "anonymizedDocxPreview",
    ):
        assert f'id="{element_id}"' in html
    for label in (
        "Форматированный вид",
        "Текст и подсветка",
        "В начало",
        "В конец",
        "На весь экран",
        "Восстановить файл…",
        "1. Выберите обезличенный файл",
        "2. Программа подтвердит пару",
        "3. Нажмите «Восстановить файл»",
        "соответствие проверяется по внутреннему идентификатору пары",
        "Вернуть исходные значения",
    ):
        assert label in html
    assert html.count('id="restoreFile"') == 1
    assert 'id="restoreFileTop"' not in html
    assert "Выбрать обезличенный файл…" in html
    assert "Восстановить исправленный файл" not in html
    assert javascript.count("$('#chooseRestoreFile').onclick=chooseRestorePair") == 1
    assert javascript.count("$('#restoreFile').onclick=restoreMatchedFile") == 1
    assert "restoreFileTop" not in javascript
    assert "Обезличенный файл" in javascript
    assert "Выберите место для восстановленного файла" in javascript
    assert "preview.rich_html" in javascript
    assert "preview.format==='docx'" in javascript
    assert "preview_anonymized_document" in javascript
    assert "Версия 1.8" in html and "APP_VERSION='1.8'" in javascript
    assert 'src="app-v1.8.15.js"' in html
    assert "Текст документа загружен полностью" in javascript
    assert "Визуальные элементы без текста могут не отображаться" in javascript
    assert "rich.scrollTop=0" in javascript
    assert "rich.scrollTop=rich.scrollHeight" in javascript
    assert "preview-surface-fullscreen" in javascript
    assert "r.path" in javascript and "r.output_path" not in javascript
    assert ".docx-preview" in css and ".docx-table" in css
    assert ".docx-preview-fullscreen" in css


def test_docx_preview_preserves_horizontal_and_vertical_merged_cells(tmp_path):
    source = tmp_path / "merged.docx"
    document = Document()
    table = document.add_table(rows=3, cols=3)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "горизонтальное объединение"
    table.cell(1, 2).merge(table.cell(2, 2)).text = "вертикальное объединение"
    document.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    rich = api.preview_document(document_id)["rich_html"]

    assert rich.count("горизонтальное объединение") == 1
    assert rich.count("вертикальное объединение") == 1
    assert 'colspan="2"' in rich
    assert 'rowspan="2"' in rich


def test_anonymized_docx_preview_keeps_table_and_run_formatting(tmp_path):
    source = tmp_path / "formatted-sensitive.docx"
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Иванов Сергей Петрович").bold = True
    paragraph.add_run(" обычный текст").italic = True
    table = document.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).merge(table.cell(0, 1)).text = "Владелец Иванов Сергей Петрович"
    table.cell(1, 0).merge(table.cell(2, 0)).text = "Вертикальное объединение"
    document.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    preview = api.preview_anonymized_document(document_id)

    assert preview["format"] == "docx"
    assert "Иванов Сергей Петрович" not in preview["rich_html"]
    assert "[ФИО-1]" in preview["rich_html"]
    assert "<strong>" in preview["rich_html"]
    assert '<em>' in preview["rich_html"]
    assert 'class="docx-table"' in preview["rich_html"]
    assert preview["rich_html"].count("Вертикальное объединение") == 1
    assert 'colspan="2"' in preview["rich_html"]
    assert 'rowspan="2"' in preview["rich_html"]


def test_docx_preview_omits_malformed_optional_formatting_instead_of_crashing(tmp_path):
    source = tmp_path / "malformed-formatting.docx"
    document = Document()
    paragraph = document.add_paragraph("Безопасный текст")
    paragraph._p.get_or_add_pPr().append(OxmlElement("w:jc"))
    document.save(source)

    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]

    assert "Безопасный текст" in api.preview_document(document_id)["rich_html"]
