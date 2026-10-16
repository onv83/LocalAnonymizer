import base64
import html as html_module
import json
from pathlib import Path
from html.parser import HTMLParser
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

import local_anonymizer.app as app_module
from local_anonymizer.app import AppApi, asset_path, platform_smoke_check, smoke_check
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
    assert summary["abbreviation_ok"] is True
    assert summary["abbreviation_unicode_ok"] is True
    assert summary["domain_toc_ok"] is True
    assert summary["port_ok"] is True
    assert summary["graphics_roundtrip_ok"] is True
    assert "Иванов" not in str(summary)


def test_platform_smoke_checks_secure_storage_and_native_clipboard_without_reading_it():
    class Protector:
        def __bool__(self):
            return False

        def protect(self, data, purpose):
            return b"protected:" + purpose.encode() + b":" + data

        def unprotect(self, envelope, purpose):
            prefix = b"protected:" + purpose.encode() + b":"
            assert envelope.startswith(prefix)
            return envelope[len(prefix):]

    class Clipboard:
        available = True

        def __bool__(self):
            return False

        def read_text(self):
            raise AssertionError("platform smoke must not read user clipboard")

        def write_text(self, text):
            raise AssertionError("platform smoke must not overwrite user clipboard")

    result = platform_smoke_check(
        platform_name="linux",
        protector=Protector(),
        clipboard=Clipboard(),
    )

    assert result == {
        "ok": True,
        "platform": "linux",
        "secure_storage": True,
        "clipboard": True,
    }


def test_platform_smoke_fails_closed_without_secure_storage_or_clipboard():
    class BrokenProtector:
        def protect(self, data, purpose):
            raise RuntimeError("backend unavailable")

        def unprotect(self, envelope, purpose):
            raise AssertionError("protect must fail first")

    result = platform_smoke_check(
        platform_name="darwin",
        protector=BrokenProtector(),
        clipboard=SimpleNamespace(available=False),
    )

    assert result["ok"] is False
    assert result["secure_storage"] is False
    assert result["clipboard"] is False
    assert result["error"] == "RuntimeError: backend unavailable"


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


def test_manual_review_follows_both_aligned_text_preview_panes():
    class LayoutParser(HTMLParser):
        VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

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
            if tag not in self.VOID_TAGS:
                self.stack.append(node)

        def handle_endtag(self, tag):
            if tag not in self.VOID_TAGS:
                self.stack.pop()

    parser = LayoutParser()
    parser.feed(asset_path("index-v1.8.18.html").read_text(encoding="utf-8"))

    assert parser.parents["source"] == "textPreview"
    assert parser.parents["anonymizedDocxPreview"] == "anonymizedPreviewSurface"
    assert parser.parents["anonymizedPreviewSurface"] == "columns"
    assert parser.parents["manualReview"] == "columns"
    assert parser.parents["warning"] == "manualReview"
    assert parser.children["columns"].index("manualReview") > parser.children["columns"].index("sourceHeading")
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
        "уязвимость", "ПОЧТА", "ТЕЛЕФОН", "АККАУНТ", "IP", "ПОРТ", "MAC", "IMEI", "ССЫЛКА",
        "ДОМЕН", "УЗЕЛ", "DN", "СТРУКТУРА-AD", "ДИСК", "ПУТЬ", "СЗИ",
        "ПРОГРАММА", "СОКРАЩЕНИЯ", "СКРИПТЫ", "ПРОИЗВОДИТЕЛЬ", "ИНН", "ОГРН", "СНИЛС",
        "КАРТА", "КПП", "СЧЁТ", "БИК", "ПАСПОРТ", "VIN", "КАДАСТР",
        "ГОСНОМЕР", "ТАБЕЛЬНЫЙ", "ДОГОВОР", "ДОКУМЕНТ", "ДАТА-РОЖДЕНИЯ",
        "СУММА", "СТАВКА", "ФИО", "ЛОГИН", "ОРГАНИЗАЦИЯ", "СИСТЕМА",
        "ЗАДАЧА", "ГОРОД", "АДРЕС", "ИНДЕКС", "ДОЛЖНОСТЬ", "СПЕЦКАТЕГОРИЯ", "СКРЫТО",
        "CUSTOM", "HINTS",
    }
    assert set(categories) == expected

    assert "IP-адрес → <code>[IP-N]</code>" in html
    assert "Порт → <code>[ПОРТ-N]</code>" in html
    assert "Домен → <code>[ДОМЕН-N]</code>" in html
    assert "Электронная почта → <code>[ПОЧТА-N]</code>" in html
    assert "Ссылка → <code>[ССЫЛКА-N]</code>" in html
    assert "Уязвимость → <code>[уязвимость]</code>" in html
    assert "Дополнительные правила → <code>[МЕТКА-N]</code>" in html
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    english_javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")
    assert "function updateCategoryMarkerExamples()" in javascript
    assert "updateCategoryMarkerExamples();markSettingsDirty()" in javascript
    assert "СОКРАЩЕНИЯ:'СОКР'" in javascript
    assert "ПОРТ:'ПРТ'" in javascript
    assert "\"Сокращения\":['СОКРАЩЕНИЯ']" in javascript
    assert "СОКРАЩЕНИЯ:'СОКР'" in english_javascript
    assert "ПОРТ:'ПРТ'" in english_javascript
    assert "\"Abbreviations\":['СОКРАЩЕНИЯ']" in english_javascript


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


def test_interface_contains_current_collapsed_usage_and_restore_guide_in_both_languages():
    localized = {
        "index-v1.8.18.html": (
            "Как пользоваться программой",
            "«Открыть»",
            "перетащите их в окно программы",
            "откроется автоматически",
            "Исходный текст",
            "Обезличенный текст",
            "Ручная проверка спорных мест",
            "Скрыть и запомнить правило",
            "Оставить и добавить в исключения",
            "Применить настройки к файлу",
            "исходный файл не изменяется",
            "Сохранить документ и файл восстановления",
            "Как восстановить исходный документ",
            "1. Выбрать обезличенный файл…",
            "2. Восстановить файл…",
            "Windows, Linux и macOS",
        ),
        "index-en-v1.8.18.html": (
            "How to use the app",
            "“Open”",
            "drag them into the app window",
            "opens automatically",
            "Source text",
            "Anonymized text",
            "Manual review of uncertain items",
            "Hide and remember rule",
            "Keep and add to exceptions",
            "Apply settings to file",
            "source file is not modified",
            "Save document and recovery file",
            "How to restore the original document",
            "1. Select anonymized file…",
            "2. Restore file…",
            "Windows, Linux, and macOS",
        ),
    }

    for asset_name, required in localized.items():
        html = asset_path(asset_name).read_text(encoding="utf-8")
        assert all(text in html for text in required)
        assert '<details class="card usage-guide">' in html
        assert '<details class="card usage-guide" open>' not in html

    ru_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    en_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    assert "Нажмите <b>«Выбрать исходные файлы…»</b>" not in ru_html
    assert "Выберите документ в <b>«Локальной библиотеке»</b>" not in ru_html
    assert "Click <b>“Select source files…”</b>" not in en_html
    assert "Select the document in the <b>“Local library”</b>" not in en_html
    assert "зашифрован средствами Windows" not in ru_html
    assert "профиле Windows" not in ru_html
    assert "guide.open" not in javascript
    assert 'id="stats">Версия 1.8' in ru_html
    assert 'id="stats">Версия 1.7' not in ru_html


def test_gui_loads_default_profile_rules_on_startup():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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


def test_new_design_omits_redundant_workflow_steps_but_keeps_file_state():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")

    assert 'id="workflowSteps"' not in html
    assert 'class="workflow-steps"' not in html
    assert 'id="fileLifecycleStatus"' in html
    assert 'id="applyNow"' in html
    assert 'id="exportNow"' in html


def test_header_omits_redundant_sensitive_data_subtitle_in_both_languages():
    ru_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    en_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")

    assert "Персональные и другие чувствительные данные заменяются маркерами или удаляются." not in ru_html
    assert "Всё выполняется локально." not in ru_html
    assert "Personal and other sensitive data is replaced with markers or removed." not in en_html
    assert "Everything runs locally." not in en_html


def test_open_file_button_is_first_source_action_with_localized_tooltip():
    localized = {
        "index-v1.8.18.html": (
            ">Открыть</button>",
            'title="Открыть документ или несколько файлов и импортировать их в локальную библиотеку"',
        ),
        "index-en-v1.8.18.html": (
            ">Open</button>",
            'title="Open one or more documents and import them into the local library"',
        ),
    }

    for name, (label, tooltip) in localized.items():
        html = asset_path(name).read_text(encoding="utf-8")
        source_bar = html.split('aria-labelledby="sourceHeading">', 1)[1].split("</div>", 1)[0]
        assert source_bar.index('id="dropChoose"') < source_bar.index('id="paste"')
        assert label in source_bar
        assert tooltip in source_bar
        assert html.count('id="dropChoose"') == 1


def test_new_design_styles_define_contrast_actions_targets_and_focus():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8") if asset_path("new-design-v1.11.css").exists() else ""

    assert 'new-design-v1.11.css' in html
    for token in ("--text-primary", "--text-secondary", "--surface", "--border", "--action-primary", "--danger", "--warning", "--success"):
        assert token in css
    assert ":focus-visible" in css
    assert "min-height:40px" in css
    assert 'body[data-design="new"]>details{order:6}' in css
    assert 'body[data-design="legacy"]' in css
    assert "--border:#647c92" in css
    assert "--focus:#0069c0" in css
    assert "summary{min-height:24px" in css


def test_all_collapsible_sections_show_right_or_down_disclosure_arrow():
    for name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        assert 'new-design-v1.11.css' in html

    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    assert 'body[data-design="new"] details>summary{list-style:none' in css
    assert 'body[data-design="new"] details>summary::-webkit-details-marker{display:none}' in css
    assert 'body[data-design="new"] details:not([open])>summary::before{content:"▶"}' in css
    assert 'body[data-design="new"] details[open]>summary::before{content:"▼"}' in css


def test_source_pane_omits_redundant_visible_label_and_storage_notice():
    localized_copy = {
        "index-v1.8.18.html": (
            "Исходный текст или текст выбранного документа",
            "Исходник остаётся на компьютере; перед передачей нужна ручная проверка.",
        ),
        "index-en-v1.8.18.html": (
            "Source text or text from the selected document",
            "The source stays on this computer. Review it manually before sharing.",
        ),
    }

    for name, (accessible_label, storage_notice) in localized_copy.items():
        html = asset_path(name).read_text(encoding="utf-8")
        assert f'<label for="source" class="sr-only">{accessible_label}</label>' in html
        assert 'class="sr-label"' not in html
        assert 'id="events"' not in html
        assert storage_notice not in html
        assert '<div class="drop">' not in html

    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    assert '.sr-label{' not in css


def test_empty_undo_row_collapses_only_when_empty(tmp_path):
    edge_candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    edge = next((candidate for candidate in edge_candidates if candidate.exists()), None)
    if edge is None:
        pytest.skip("Microsoft Edge is required for the Windows layout regression")

    for html_name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(html_name).read_text(encoding="utf-8")
        assert 'new-design-v1.11.css' in html
        assert 'id="undoChips" class="undo-chips"' in html

    for script_name in ("app-v1.8.18.js", "app-en-v1.8.18.js"):
        javascript = asset_path(script_name).read_text(encoding="utf-8")
        assert "$('#undoChips').innerHTML=" in javascript
        assert "$('#undoChips').onclick=" in javascript

    links = "".join(
        f'<link rel="stylesheet" href="{asset_path(name).as_uri()}">'
        for name in ("style-v1.1.css", "new-design-v1.11.css")
    )
    for width in (320, 1430):
        probe = tmp_path / f"empty-undo-row-{width}.html"
        probe.write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            + links
            + "</head><body data-design=\"new\"><section class=\"card pane\">"
            + "<div id=\"richOutput\" class=\"rich-output\"></div>"
            + "<div id=\"undoChips\" class=\"undo-chips\"></div>"
            + "<div id=\"chips\" class=\"chips\"><span>People: 0</span></div>"
            + "</section><pre id=\"probe\"></pre><script>"
            + "const rich=document.querySelector('#richOutput'),undo=document.querySelector('#undoChips'),chips=document.querySelector('#chips');"
            + "const metrics=()=>({undoDisplay:getComputedStyle(undo).display,undoHeight:undo.getBoundingClientRect().height,gap:chips.getBoundingClientRect().top-rich.getBoundingClientRect().bottom});"
            + "const empty=metrics();undo.innerHTML='<button class=\"undo-chip\">Undo</button>';const populated=metrics();"
            + "document.querySelector('#probe').textContent=JSON.stringify({empty,populated,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth});"
            + "</script></body></html>",
            encoding="utf-8",
        )
        profile = tmp_path / f"edge-profile-empty-undo-{width}"
        result = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile}",
                f"--window-size={width},923",
                "--dump-dom",
                probe.as_uri(),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        match = re.search(r'<pre id="probe">(.*?)</pre>', result.stdout, re.DOTALL)
        assert match is not None
        metrics = json.loads(html_module.unescape(match.group(1)))
        assert metrics["empty"]["undoDisplay"] == "none", (width, metrics)
        assert metrics["empty"]["undoHeight"] == 0, (width, metrics)
        assert metrics["empty"]["gap"] <= 8.5, (width, metrics)
        assert metrics["populated"]["undoDisplay"] != "none", (width, metrics)
        assert metrics["populated"]["undoHeight"] >= 28, (width, metrics)
        assert metrics["overflow"] is False, (width, metrics)


def test_entity_summary_uses_the_free_space_above_output_preview_in_both_languages():
    for html_name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(html_name).read_text(encoding="utf-8")
        output = html[html.index('aria-labelledby="outputHeading"'):html.index('id="manualReview"')]

        chips = output.index('id="chips"')
        alignment = output.index('id="outputPreviewAlignment"')
        preview = output.index('id="anonymizedPreviewSurface"')
        undo = output.index('id="undoChips"')

        assert chips < alignment < preview < undo

    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    assert 'body[data-design="new"] .pane>.chips{' in css
    assert "flex-wrap:nowrap" in css
    assert 'body[data-design="new"] .pane>.chips span{' in css


def test_new_design_uses_compact_interface_text_without_scaling_document_preview():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"]{display:flex;flex-direction:column;background:var(--surface-raised);color:var(--text-primary);font-size:13px;' in css
    assert 'body[data-design="new"] textarea{font-size:13px;' in css
    assert 'body[data-design="new"] h2{font-size:16px;' in css
    assert 'body[data-design="new"] .docx-preview{' not in css


def test_new_design_aligns_remaining_header_controls_on_one_level():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    ru_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    en_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")

    assert 'body[data-design="new"] .language-switch{display:flex;align-items:center;gap:6px;white-space:nowrap}' in css
    assert 'body[data-design="new"] .header-actions select,body[data-design="new"] #themeToggle{height:34px;min-height:34px;padding:4px 9px;box-sizing:border-box}' in css
    assert 'body[data-design="new"] #themeToggle{white-space:nowrap}' in css
    for html in (ru_html, en_html):
        assert 'class="language-switch"' in html
        assert 'class="design-switch"' not in html


def test_compact_header_reclaims_height_for_document_previews():
    for name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        assert 'new-design-v1.11.css' in html

    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    assert 'body[data-design="new"]{display:flex;flex-direction:column;background:var(--surface-raised);color:var(--text-primary);font-size:13px;line-height:1.45;max-width:1920px;margin:auto;padding:8px 20px 90px}' in css
    assert 'body[data-design="new"] header{order:0;position:sticky;top:0;z-index:80;background:var(--surface-raised);padding:3px 0 5px;margin-bottom:6px;' in css
    assert 'grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"title actions" "explanation explanation";align-items:center;gap:2px 12px' in css
    assert 'body[data-design="new"] header>div:first-child{display:contents}' in css
    assert 'body[data-design="new"] header p{grid-area:explanation;margin:0;min-width:0;font-size:11px;line-height:1.2;white-space:normal;overflow:visible}' in css
    assert 'body[data-design="new"] .header-actions #stats{font-size:12px;line-height:1.2;white-space:nowrap}' in css
    assert 'body[data-design="new"] .header-actions select,body[data-design="new"] #themeToggle{height:34px;min-height:34px;padding:4px 9px;box-sizing:border-box}' in css
    assert 'body[data-design="new"] header h1{white-space:normal;overflow-wrap:anywhere;line-height:1.2}' in css
    assert 'body[data-design="new"] .header-actions #stats{white-space:normal;overflow-wrap:anywhere;text-align:left}' in css
    assert '@media(min-width:801px) and (min-height:761px) and (max-height:950px){body[data-design="new"] .pane .editor-stack,body[data-design="new"] .rich-output,body[data-design="new"] .docx-preview-host{height:min(calc(36vh + 46px),390px);min-height:346px}}' in css
    assert '@media(min-width:801px) and (max-height:760px){body[data-design="new"] .pane .editor-stack,body[data-design="new"] .rich-output,body[data-design="new"] .docx-preview-host{height:min(22vh,220px);min-height:170px}}' in css


def test_drop_prompt_is_removed_but_window_drop_import_remains_available():
    for name, prompt in (
        ("index-v1.8.18.html", "Перетащите файлы сюда"),
        ("index-en-v1.8.18.html", "Drag files here"),
    ):
        html = asset_path(name).read_text(encoding="utf-8")
        assert '<div class="drop">' not in html
        assert prompt not in html
        assert 'id="dropChoose"' in html

    for name in ("app-v1.8.18.js", "app-en-v1.8.18.js"):
        script = asset_path(name).read_text(encoding="utf-8")
        assert "$('#dropChoose').onclick=$('#choose').onclick;" in script
        assert "document.addEventListener('drop',async e=>" in script


def test_compact_header_renders_complete_without_horizontal_overflow(tmp_path):
    edge_candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    edge = next((candidate for candidate in edge_candidates if candidate.exists()), None)
    if edge is None:
        pytest.skip("Microsoft Edge is required for the Windows layout regression")

    statuses = {
        "index-v1.8.18.html": "Найдено замен: 374 · Требуют решения: 83 · Проверено: 0 из 83",
        "index-en-v1.8.18.html": "Replacements found: 374 · Need review: 83 · Reviewed: 0 of 83",
    }
    for html_name, status in statuses.items():
        page = asset_path(html_name).read_text(encoding="utf-8")
        header = page[page.index("<header>"):page.index("</header>") + len("</header>")]
        stylesheets = re.findall(r'<link rel="stylesheet" href="([^"]+)">', page)
        links = "".join(
            f'<link rel="stylesheet" href="{asset_path(name).as_uri()}">'
            for name in stylesheets
        )
        for width in (320, 1430):
            probe = tmp_path / f"header-{html_name}-{width}.html"
            body_style = ' style="width:305px;max-width:305px;margin:0"' if width == 320 else ""
            probe.write_text(
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                + links
                + f"</head><body data-design=\"new\"{body_style}>"
                + header
                + "<pre id=\"probe\"></pre><script>"
                + f"document.querySelector('#stats').textContent={json.dumps(status, ensure_ascii=False)};"
                + "const root=document.documentElement,title=document.querySelector('header h1'),"
                + "explanation=document.querySelector('header p'),stats=document.querySelector('#stats'),"
                + "headerBox=document.querySelector('header');"
                + "document.querySelector('#probe').textContent=JSON.stringify({"
                + "docOverflow:root.scrollWidth>root.clientWidth,"
                + "bodyOverflow:document.body.scrollWidth>document.body.clientWidth,"
                + "titleClipped:title.scrollWidth>title.clientWidth+1||title.scrollHeight>title.clientHeight+1,"
                + "explanationClipped:explanation?(explanation.scrollWidth>explanation.clientWidth+1||explanation.scrollHeight>explanation.clientHeight+1):false,"
                + "statsClipped:stats.scrollWidth>stats.clientWidth+1||stats.scrollHeight>stats.clientHeight+1,"
                + "headerHeight:headerBox.getBoundingClientRect().height});"
                + "</script></body></html>",
                encoding="utf-8",
            )
            profile = tmp_path / f"edge-profile-{html_name}-{width}"
            result = subprocess.run(
                [
                    str(edge),
                    "--headless=new",
                    "--disable-gpu",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile}",
                    f"--window-size={width},923",
                    "--dump-dom",
                    probe.as_uri(),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            match = re.search(r'<pre id="probe">(.*?)</pre>', result.stdout, re.DOTALL)
            assert match is not None
            metrics = json.loads(html_module.unescape(match.group(1)))
            assert metrics["docOverflow"] is False, (html_name, width, metrics)
            assert metrics["bodyOverflow"] is False, (html_name, width, metrics)
            assert metrics["titleClipped"] is False, (html_name, width, metrics)
            assert metrics["explanationClipped"] is False, (html_name, width, metrics)
            assert metrics["statsClipped"] is False, (html_name, width, metrics)
            if width == 1430:
                assert metrics["headerHeight"] <= 64, (html_name, width, metrics)


def test_dark_new_design_stat_chips_have_explicit_readable_colors():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    assert 'html[data-theme="dark"] body[data-design="new"] .chips span{' in css
    assert "background:var(--surface-raised)" in css
    assert "color:var(--text-primary)" in css
    assert 'html[data-theme="dark"] body[data-design="new"] .chips .yellow{' in css
    assert "background:#fff5c5" in css
    assert "color:#725a00" in css


def test_new_design_current_review_text_has_explicit_readable_color():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"] #reviewCurrent{color:var(--text-primary)}' in css


def test_new_design_manual_review_uses_dark_theme_surfaces_without_inner_scroll():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"] .review-candidate,body[data-design="new"] .review-actions>div{background:var(--surface-raised);color:var(--text-primary);border-color:var(--border)}' in css
    assert 'body[data-design="new"] .review-candidate{height:auto;min-height:52px;max-height:none;overflow:visible;padding:6px 8px;grid-template-columns:auto minmax(0,1fr);gap:2px 8px;align-content:start}' in css
    assert 'body[data-design="new"] .review-decision,body[data-design="new"] .review-finish{background:var(--surface-raised);color:var(--text-secondary)}' in css


def test_manual_review_is_below_both_preview_panes_and_compact_without_losing_controls():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    for name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        assert html.index('id="manualReview"') > html.index('id="sourceHeading"')
        assert html.index('id="manualReview"') > html.index('id="anonymizedPreviewSurface"')
        assert '<details class="review-controls-disclosure">' in html
        assert '<fieldset class="review-controls">' in html
        for control_id in ("reviewHints", "paranoid", "compactMarkers", "mono"):
            assert f'id="{control_id}"' in html

    assert 'grid-template-columns:minmax(260px,.85fr) minmax(420px,1.15fr)' in css
    assert 'body[data-design="new"] .manual-review-row{grid-column:1/-1;margin-top:0}' in css
    assert 'body[data-design="new"] .review-context{display:grid;grid-template-columns:1fr;gap:6px;min-width:0}' in css
    assert 'body[data-design="new"] .pane .editor-stack,body[data-design="new"] .rich-output,body[data-design="new"] .docx-preview-host{height:min(34vh,380px);min-height:250px}' in css
    assert '@media(min-width:801px) and (min-height:761px) and (max-height:950px){body[data-design="new"] .pane .editor-stack,body[data-design="new"] .rich-output,body[data-design="new"] .docx-preview-host{height:min(calc(36vh + 46px),390px);min-height:346px}}' in css
    assert '@media(min-width:801px) and (max-height:760px){body[data-design="new"] .pane .editor-stack,body[data-design="new"] .rich-output,body[data-design="new"] .docx-preview-host{height:min(22vh,220px);min-height:170px}}' in css
    assert 'body[data-design="new"] .review-candidate{height:auto;min-height:52px;max-height:none;overflow:visible;padding:6px 8px;grid-template-columns:auto minmax(0,1fr);gap:2px 8px;align-content:start}' in css
    assert 'body[data-design="new"] .review-navigation{display:flex;margin:0;gap:6px;flex-direction:row}' in css
    assert 'body[data-design="new"] .review-actions{display:grid;grid-template-columns:1fr;' in css
    assert 'body[data-design="new"] .review-actions>div{display:grid;grid-template-columns:minmax(180px,auto) minmax(0,1fr);align-items:start;gap:4px 8px;' in css


def test_review_candidate_and_actions_are_the_first_row_directly_beneath_the_panes():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    assert 'body[data-design="new"] .columns{column-gap:14px;row-gap:6px}' in css
    assert 'body[data-design="new"] .columns>.pane{margin-bottom:0}' in css
    assert 'body[data-design="new"] .manual-review-row{grid-column:1/-1;margin-top:0}' in css
    assert 'body[data-design="new"] .review-context,body[data-design="new"] .review-actions{order:-3}' in css


def test_populated_review_keeps_heading_and_action_help_readable():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

    base_css = css.split("@media", 1)[0]
    assert 'body[data-design="new"] .workflow-status{position:fixed;left:20px;right:20px;bottom:0;z-index:70;' in base_css
    assert '.workflow-status{position:static' not in css
    assert 'body[data-design="new"]{padding:10px 10px 210px}' in css
    assert 'body[data-design="new"] .workflow-status{left:10px;right:10px;flex-wrap:wrap}' in css
    assert 'body[data-design="new"] .review-heading,body[data-design="new"] .review-controls-disclosure{grid-column:1/-1}' in css
    assert 'body[data-design="new"] .review-heading{margin:0;gap:8px;align-items:center;display:grid;grid-template-columns:minmax(0,1fr) auto}' in css
    assert 'body[data-design="new"] .review-heading>div{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:baseline;gap:8px;min-width:0}' in css
    assert 'body[data-design="new"] .review-actions{display:grid;grid-template-columns:1fr;' in css
    assert 'body[data-design="new"] .review-actions>div{display:grid;grid-template-columns:minmax(180px,auto) minmax(0,1fr);align-items:start;gap:4px 8px;' in css
    assert 'body[data-design="new"] .review-actions button{justify-self:start;' in css
    assert '@media(max-width:800px){body[data-design="new"] .review{grid-template-columns:1fr}' in css
    assert 'body[data-design="new"] .review-actions>div{display:grid;grid-template-columns:1fr}' in css


def test_restore_steps_stack_on_narrow_screens_in_both_languages():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    ru = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    en = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")

    assert '@media(max-width:620px){body[data-design="new"] .restore-steps{grid-template-columns:minmax(0,1fr)}}' in css
    assert 'class="restore-steps"' in ru
    assert 'class="restore-steps"' in en


def test_new_design_hides_empty_review_result_status():
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert 'id="reviewMeta"' in html
    for text in ("Найдено замен:", "Требуют решения:", "Проверено:", "Создаётся предпросмотр", "Обрабатывается файл"):
        assert text in javascript
    assert "вхожд." in javascript
    assert "Правила: «" in javascript


def test_review_copy_stays_compact_when_a_candidate_appears_in_both_languages():
    ru_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    en_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")
    ru_js = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    en_js = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "Автопоиск не уверен — выберите действие." in ru_html
    assert "Detection is uncertain — choose an action." in en_html
    assert "`«${all[reviewIndex].textContent.trim()}» · ${all[reviewIndex].dataset.kind" in ru_js
    assert "`${occurrences} вхожд. · Правила: «${$('#profile').value||'Общий'}»`" in ru_js
    assert "`“${all[reviewIndex].textContent.trim()}” · ${hintKindText(all[reviewIndex].dataset.kind)" in en_js
    assert "`${occurrences} match(es) · Rules: “${profileDisplayName($('#profile').value||'Общий')}”`" in en_js

    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")
    assert 'body[data-design="new"] .review-candidate .review-help{grid-column:1;grid-row:2}' in css
    assert 'body[data-design="new"] .review-candidate small{grid-column:2;grid-row:2}' in css
    assert 'body[data-design="new"] .review-context,body[data-design="new"] .review-actions{min-width:0;min-height:108px}' in css


def test_document_preview_errors_are_reported_in_both_interfaces():
    russian = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    english = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "Ошибка предпросмотра:" in russian
    assert "Preview error:" in english
    assert "catch(error)" in russian
    assert "catch(error)" in english


def test_generated_markers_use_native_buttons():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert 'class="maprow"' not in javascript
    assert '<button type="button" class="mark-hint' in javascript
    assert '<button type="button" class="${p.secret?' in javascript
    assert 'role="button" tabindex="0"' not in javascript
    assert "activateKeyboardAction" not in javascript


def test_fullscreen_preview_uses_modal_semantics_and_restores_focus():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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


def test_desktop_window_opens_at_1600px_for_two_preview_panes(tmp_path, monkeypatch):
    captured = {}

    def create_window(title, url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=create_window, start=lambda **kwargs: None),
    )

    assert app_module.main([]) == 0
    assert captured["width"] == 1600
    assert captured["height"] == 920
    assert captured["min_size"] == (720, 700)


def test_desktop_window_clamps_preferred_size_to_primary_work_area(tmp_path, monkeypatch):
    captured = {}
    work_area = SimpleNamespace(X=0, Y=0, Width=1366, Height=728)
    primary_screen = SimpleNamespace(
        x=0,
        y=0,
        width=1366,
        height=768,
        frame=work_area,
    )

    def create_window(title, url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(
            screens=[primary_screen],
            create_window=create_window,
            start=lambda **kwargs: None,
        ),
    )

    assert app_module.main([]) == 0
    assert captured["width"] == 1366
    assert captured["height"] == 728
    assert captured["min_size"] == (720, 700)
    assert captured["x"] == 0
    assert captured["y"] == 0
    assert captured["screen"] is primary_screen


def test_double_escape_no_longer_silently_clears_user_work():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert "now-lastEscape<800" not in javascript
    assert "confirm('Очистить введённый текст" in javascript


def test_ui_uses_current_design_without_legacy_selector():
    russian_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    english_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")
    russian_javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    english_javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    for html in (russian_html, english_html):
        assert 'id="designMode"' not in html
        assert 'class="design-switch"' not in html
        assert '<body data-design="new">' in html
    for javascript in (russian_javascript, english_javascript):
        assert "function applyCurrentDesign" in javascript
        assert "document.body.dataset.design='new'" in javascript
        assert "pywebview.api.set_design_mode('new')" in javascript
        assert "try{await pywebview.api.set_design_mode('new')}catch(_error){}" in javascript
        assert "DESIGN_KEY" not in javascript
        assert "await applyCurrentDesign();" in javascript
        assert "get_design_mode" not in javascript
        assert "$('#designMode')" not in javascript


def test_ui_offers_complete_persistent_english_interface():
    russian_html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    english_html = asset_path("index-en-v1.8.18.html").read_text(encoding="utf-8")
    russian_js = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    english_js = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert '<html lang="ru">' in russian_html
    assert '<html lang="en">' in english_html
    assert '<script src="app-v1.8.18.js"></script>' in russian_html
    assert '<script src="app-en-v1.8.18.js"></script>' in english_html
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
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "function documentStatusText(status)" in javascript
    assert "`${d.display_name} — ${documentStatusText(d.status)}`" in javascript
    assert "`Preview: ${preview.display_name} — ${documentStatusText(preview.status)}`" in javascript
    assert "function profileDisplayName(name)" in javascript
    assert "o.textContent=profileDisplayName(n)" in javascript
    assert "function hintKindText(kind)" in javascript
    assert "hintKindText(p.kind)" in javascript
    assert "hintKindText(all[reviewIndex].dataset.kind)" in javascript


def test_english_interface_never_falls_back_to_raw_unknown_backend_status():
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "||status;" not in javascript
    assert "'Unknown status'" in javascript


def test_english_interface_localizes_profile_names_in_result_messages():
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "`Profile “${profileDisplayName(n)}” saved.`" in javascript
    assert "`Profile “${profileDisplayName(n)}” exported.`" in javascript
    assert "`Profile “${profileDisplayName(r.name)}” imported and loaded." in javascript


def test_english_interface_localizes_backend_warning_messages_without_changing_contract_keys():
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

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
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "function profileErrorText(operation)" in javascript
    assert "profileErrorText('export')" in javascript
    assert "profileErrorText('import')" in javascript
    assert "textContent=r.error;" not in javascript


def test_english_interface_localizes_post_anonymization_status_and_review_profile():
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "`${documentStatusText(r.status)}. The file was created" in javascript
    assert "`${documentStatusText(r.status)}. The anonymized file is ready" in javascript
    assert "const profileName=profileDisplayName($('#profile').value||'Общий')" in javascript
    assert 'const profileName=$(\'#profile\').value||\'Общий\'' not in javascript


def test_english_interface_never_renders_raw_bridge_errors():
    javascript = asset_path("app-en-v1.8.18.js").read_text(encoding="utf-8")

    assert "function bridgeErrorText(operation)" in javascript
    assert "saved?.error||'Could not save profile'" not in javascript
    assert "${error}" not in javascript
    assert "String(error)" not in javascript
    assert "${formattedPreview.error}" not in javascript
    assert "${error?.message||error}" not in javascript
    assert ".map(x=>x.error)" not in javascript
    for operation in ("profile-save", "formatted-preview", "anonymize", "import", "restore"):
        assert f"bridgeErrorText('{operation}')" in javascript


def test_language_variants_omit_redundant_workflow_steps():
    for name in ("index-v1.8.18.html", "index-en-v1.8.18.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        assert 'id="workflowSteps"' not in html
        assert 'class="workflow-steps"' not in html


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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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
    assert '<script src="app-v1.8.18.js"></script>' in html


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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert 'id="compactMarkers"' in html
    assert "Сохранять компоновку" in html
    assert "$('#compactMarkers').checked" in javascript
    assert "'#compactMarkers'" in javascript


def test_paste_button_uses_native_api_instead_of_webview_clipboard_permission():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert "pywebview.api.read_clipboard_text()" in javascript
    assert "navigator.clipboard.readText()" not in javascript


def test_source_and_anonymized_previews_scroll_together_by_logical_blocks():
    for name in ("app-v1.8.18.js", "app-en-v1.8.18.js"):
        javascript = asset_path(name).read_text(encoding="utf-8")

        # Text and formatted previews both synchronize in either direction.
        assert "function syncPreviewScroll(source,target)" in javascript
        assert "programmaticPreviewScrollTargets.get(source)" in javascript
        assert "programmaticPreviewScrollTargets.set(target" in javascript
        assert "function collectPreviewAnchors(container)" in javascript
        assert "function mapPreviewScroll(source,target)" in javascript
        assert "$('#docxPreview').addEventListener('scroll',syncFormattedSourceScroll)" in javascript
        assert "$('#anonymizedDocxPreview').addEventListener('scroll',syncFormattedAnonymizedScroll)" in javascript

        # Formatted documents use matching structural blocks and interpolation,
        # with a proportional fallback for incomplete or unusual documents.
        assert "'.docx-paragraph,li,tr'" in javascript
        assert "function previewScrollPosition(source)" in javascript
        assert "function previewScrollForPosition(position,target)" in javascript

        # Programmatic scrolling must not feed back into the opposite listener.
        assert "let previewScrollSyncDepth=0" in javascript
        assert "if(previewScrollSyncDepth||!source||!target" in javascript
        assert "const mapped=mapPreviewScroll(source,target)" in javascript
        assert "finally{previewScrollSyncDepth--;}" in javascript


def test_source_and_anonymized_preview_screens_stay_vertically_aligned():
    for html_name, javascript_name in (
        ("index-v1.8.18.html", "app-v1.8.18.js"),
        ("index-en-v1.8.18.html", "app-en-v1.8.18.js"),
    ):
        html = asset_path(html_name).read_text(encoding="utf-8")
        javascript = asset_path(javascript_name).read_text(encoding="utf-8")

        # Each pane has an independent spacer. Runtime geometry, rather than a
        # language-specific pixel offset, aligns whichever active previews are visible.
        assert 'id="sourcePreviewAlignment" class="preview-alignment-spacer"' in html
        assert 'id="outputPreviewAlignment" class="preview-alignment-spacer"' in html
        assert "function syncPreviewTopAlignment()" in javascript
        assert "sourcePreviewAlignment.style.height='0px'" in javascript
        assert "outputPreviewAlignment.style.height='0px'" in javascript
        assert "activeSourcePreview()" in javascript
        assert "activeAnonymizedPreview()" in javascript
        assert "function isPreviewActive(preview)" in javascript
        assert "getBoundingClientRect().top" in javascript
        assert "new ResizeObserver(schedulePreviewTopAlignment)" in javascript
        assert "new MutationObserver(schedulePreviewTopAlignment)" in javascript
        assert "window.addEventListener('resize',schedulePreviewTopAlignment)" in javascript
        assert "setTimeout(run,100)" in javascript
        assert javascript.count("schedulePreviewTopAlignment();}") >= 2


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_preview_top_alignment_runtime_handles_dynamic_and_stacked_layouts(tmp_path, asset_name):
    import json
    import subprocess

    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("const sourcePreviewAlignment=")
    end = javascript.index("function syncFormattedSourceScroll", start)
    implementation = javascript[start:end]
    harness = f"""
const vm=require('vm');
let sourceBase=200,outputBase=100;
const px=value=>Number.parseFloat(value||'0')||0;
const sourceSpacer={{style:{{height:'0px'}},classList:{{contains:name=>name==='preview-alignment-spacer'}}}};
const outputSpacer={{style:{{height:'0px'}},classList:{{contains:name=>name==='preview-alignment-spacer'}}}};
const sourcePane={{top:0,getBoundingClientRect(){{return{{top:this.top}};}},querySelector:()=>({{}})}};
const outputPane={{top:0,getBoundingClientRect(){{return{{top:this.top}};}},querySelector:()=>({{}})}};
const source={{hidden:false,clientWidth:500,clientHeight:405,closest:()=>sourcePane,getBoundingClientRect:()=>({{top:sourceBase+px(sourceSpacer.style.height)}})}};
const output={{hidden:false,clientWidth:500,clientHeight:405,closest:()=>outputPane,getBoundingClientRect:()=>({{top:outputBase+px(outputSpacer.style.height)}})}};
const hidden={{hidden:true,clientWidth:500,clientHeight:405,closest:()=>sourcePane,getBoundingClientRect:()=>({{top:0}})}};
const generic={{classList:{{contains:()=>false}},closest:()=>sourcePane}};
const elements={{sourcePreviewAlignment:sourceSpacer,outputPreviewAlignment:outputSpacer,source,richOutput:output,docxPreview:hidden,anonymizedDocxPreview:hidden,sourceLibrary:generic,docxPreviewControls:generic,anonymizedPreviewControls:generic,textPreview:generic}};
const queued=[];let timer=null;
const context={{Boolean,Math,Number,previewFullscreen:false,anonymizedPreviewFullscreen:false,$:selector=>elements[selector.slice(1)],requestAnimationFrame:fn=>{{queued.push(fn);return queued.length;}},setTimeout:fn=>{{timer=fn;}},ResizeObserver:class{{observe(){{}}}},MutationObserver:class{{observe(){{}}}},window:{{addEventListener(){{}}}},document:{{fonts:null}}}};
vm.createContext(context);
vm.runInContext({json.dumps(implementation + "this.api={syncPreviewTopAlignment};")},context);
if(!timer)throw new Error('missing throttled-animation fallback');
timer();
if(outputSpacer.style.height!=='100px')throw new Error('timer fallback did not align collapsed panes');
sourceBase=320;context.api.syncPreviewTopAlignment();
if(outputSpacer.style.height!=='220px')throw new Error('expanded library was not realigned');
sourceBase=90;context.api.syncPreviewTopAlignment();
if(sourceSpacer.style.height!=='10px'||outputSpacer.style.height!=='0px')throw new Error('shorter source side was not aligned');
outputPane.top=500;context.api.syncPreviewTopAlignment();
if(sourceSpacer.style.height!=='0px'||outputSpacer.style.height!=='0px')throw new Error('stacked cards must not be cross-aligned');
"""
    script = tmp_path / f"{asset_name}.alignment-runtime.js"
    script.write_text(harness, encoding="utf-8")
    completed = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_preview_scroll_runtime_handles_unequal_blocks_cache_and_hidden_panes(tmp_path, asset_name):
    import json
    import subprocess

    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("function setDocxPreviewMode", start)
    implementation = javascript[start:end]
    harness = f"""
const vm=require('vm');
function node(top){{return{{getBoundingClientRect:()=>({{top}})}};}}
function pane({{height=100,client=20,top=0,nodes=[],hidden=false}}={{}}){{
  return{{scrollHeight:height,clientHeight:client,scrollTop:top,hidden,
    getBoundingClientRect:()=>({{top:0}}),querySelectorAll:()=>nodes}};
}}
const elements={{docxPreview:pane(),anonymizedDocxPreview:pane(),source:pane(),richOutput:pane()}};
const context={{WeakMap,WeakSet,Math,requestAnimationFrame:(fn)=>fn(),$:s=>elements[s.slice(1)],window:{{addEventListener:()=>{{}}}},document:{{fonts:null}}}};
vm.createContext(context);
vm.runInContext({json.dumps(implementation + "function setDocxPreviewMode(formatted){$('#docxPreview').hidden=!formatted;$('#source').hidden=formatted;}function setAnonymizedPreviewMode(formatted){$('#anonymizedDocxPreview').hidden=!formatted;$('#richOutput').hidden=formatted;}this.api={mapPreviewScroll,collectPreviewAnchors,invalidatePreviewAnchors,syncFormattedSourceScroll,syncFormattedAnonymizedScroll,switchPreviewMode};")},context);
const source=pane({{height:120,client:20,top:50,nodes:[node(-30),node(0),node(30)]}});
const target=pane({{height:220,client:20,nodes:[node(40)]}});
if(context.api.mapPreviewScroll(source,target)!==100)throw new Error('unequal anchors must use proportional fallback');
const cached=pane({{height:120,client:20,nodes:[node(20)]}});
if(context.api.collectPreviewAnchors(cached)[1]!==20)throw new Error('initial anchor');
cached.nodes=[node(70)];cached.querySelectorAll=()=>cached.nodes;
context.api.invalidatePreviewAnchors(cached);
if(context.api.collectPreviewAnchors(cached)[1]!==70)throw new Error('stale anchor cache');
elements.docxPreview.hidden=true;elements.docxPreview.scrollTop=40;elements.anonymizedDocxPreview.scrollTop=33;
context.api.syncFormattedSourceScroll();
if(elements.anonymizedDocxPreview.scrollTop!==33)throw new Error('hidden pane changed active peer');
elements.source=pane({{height:100,client:20,top:40}});elements.source.hidden=false;
elements.docxPreview=pane({{height:200,client:20,top:0,hidden:true}});
context.api.switchPreviewMode(context.setDocxPreviewMode,true);
if(elements.docxPreview.hidden||!elements.source.hidden||elements.docxPreview.scrollTop!==90)throw new Error('mode switch lost visible position');
elements.anonymizedDocxPreview=pane({{height:200,client:20,top:0}});
context.api.syncFormattedSourceScroll();
if(elements.anonymizedDocxPreview.scrollTop!==0)throw new Error('mode restore feedback was not ignored');
elements.docxPreview.scrollTop=100;
context.api.syncFormattedSourceScroll();
if(elements.anonymizedDocxPreview.scrollTop!==100)throw new Error('forward formatted synchronization failed');
context.api.syncFormattedAnonymizedScroll();
if(elements.docxPreview.scrollTop!==100)throw new Error('programmatic feedback changed the source');
elements.anonymizedDocxPreview.scrollTop=135;
context.api.syncFormattedAnonymizedScroll();
if(elements.docxPreview.scrollTop!==135)throw new Error('real reverse scroll was swallowed');
"""
    script = tmp_path / "scroll_sync_runtime.js"
    script.write_text(harness, encoding="utf-8")
    completed = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_preview_mode_changes_preserve_visible_position_and_invalidate_dom_cache():
    for name in ("app-v1.8.18.js", "app-en-v1.8.18.js"):
        javascript = asset_path(name).read_text(encoding="utf-8")
        assert "function switchPreviewMode" in javascript
        assert "switchPreviewMode(setAnonymizedPreviewMode,true)" in javascript
        assert "rich.innerHTML=formattedPreview.rich_html||'';rich.scrollTop=0;" in javascript
        assert "resetAnonymizedPreviewScroll();$('#anonymizedPreviewCompleteness')" not in javascript
        assert "invalidatePreviewAnchors(rich);rich.innerHTML=" in javascript
        assert "if($('#docxPreview').hidden)return;" in javascript
        assert "if($('#anonymizedDocxPreview').hidden)return;" in javascript


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

    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    assert 'class="undo-chip"' in javascript
    assert 'title="Отменить возврат значения' in javascript

    assert 'id="buttonTooltip"' in html
    assert 'role="tooltip"' in html
    assert "pointerover" in javascript
    assert "showButtonTooltip" in javascript
    assert "hideButtonTooltip" in javascript


def test_manual_review_next_keeps_button_stationary_and_scrolls_only_the_text_preview():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    hide_hint = javascript[javascript.index("async function hideHint("):javascript.index("async function anonymizeText(")]

    assert "await anonymizeText()" in hide_hint
    assert "customCategory.checked=true" in hide_hint
    assert "Все одинаковые вхождения" in hide_hint
    assert "все одинаковые вхождения" in html


def test_hide_and_remember_persists_rule_in_the_active_profile_before_refreshing_preview():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    hide_hint = javascript[javascript.index("async function hideHint("):javascript.index("async function anonymizeText(")]

    save = "await pywebview.api.save_profile($('#profile').value,$('#rules').value,$('#whitelist').value,$('#paranoid').checked)"
    assert save in hide_hint
    assert hide_hint.index(save) < hide_hint.index("await anonymizeText()")
    assert "правило сохранено в профиле" in hide_hint


def test_gui_has_persistent_light_and_dark_theme_switch():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
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

    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    assert "$('#redactDocxGraphics').checked" in javascript
    assert "['#rules','#whitelist','#paranoid','#redactDocxGraphics']" in javascript


def test_settings_and_primary_action_explain_their_real_effect():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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
    css = asset_path("new-design-v1.11.css").read_text(encoding="utf-8")

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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    text_await = "const result=await pywebview.api.anonymize_text(text,...settings);"
    formatted_await = "formattedPreview=await formatted"
    assert text_await in javascript
    assert formatted_await in javascript
    render_after_text = javascript.index("renderOutput()", javascript.index(text_await))
    assert javascript.index(text_await) < render_after_text < javascript.index(formatted_await)
    assert "setAnonymizedPreviewMode(false)" in javascript
    assert "Предпросмотр обновлён" in javascript


def test_review_navigation_is_limited_to_actionable_yellow_hints():
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    for text in (
        "Ручная проверка спорных мест",
        "Автопоиск не уверен — выберите действие.",
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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

    assert "Автоматически скрывать спорное без подтверждения" in html
    assert "жёлтой очереди для ручного решения не будет" in html
    assert 'id="reviewCurrent"' in html
    assert "Ручная проверка отключена" in javascript
    assert "снимите «Автоматически скрывать спорное без подтверждения»" in javascript
    assert "setAnonymizedPreviewMode(false)" in javascript
    assert "`«${all[reviewIndex].textContent.trim()}» · ${all[reviewIndex].dataset.kind" in javascript


def test_document_export_has_a_visible_matching_restore_import_action():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")

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


def test_document_preview_bridge_is_chunked_and_reconstructs_large_text(tmp_path):
    source = tmp_path / "large.txt"
    text = "Иванов Сергей Петрович\n" * 8_000
    source.write_text(text, encoding="utf-8")
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    expected = source.read_bytes().decode("utf-8")

    manifest = api.start_document_preview(document_id)
    assert "text" not in manifest and "rich_html" not in manifest
    assert manifest["text_length"] == len(expected)
    chunks = []
    offset = 0
    while offset < manifest["text_length"]:
        result = api.read_document_preview_chunk(manifest["token"], "text", offset)
        assert len(result["chunk"]) <= 16_384
        chunks.append(result["chunk"])
        offset = result["next_offset"]
    assert "".join(chunks) == expected
    assert api.finish_document_preview(manifest["token"]) == {"ok": True}
    with pytest.raises(ValueError, match="устарел"):
        api.read_document_preview_chunk(manifest["token"], "text", 0)


def test_formatted_preview_bridge_uses_bounded_chunks(tmp_path, monkeypatch):
    api = AppApi(root=tmp_path / "app")
    rich_html = "<p>форматированный текст</p>" * 10_000
    monkeypatch.setattr(
        api.service,
        "preview_document",
        lambda _document_id, **_kwargs: {
            "display_name": "large.odt",
            "text": "текст",
            "status": "Импортирован",
            "kind": "document",
            "format": "odt",
            "rich_html": rich_html,
        },
    )

    manifest = api.start_formatted_document_preview("document-id")
    chunks = []
    offset = 0
    while offset < manifest["rich_html_length"]:
        result = api.read_document_preview_chunk(manifest["token"], "rich_html", offset)
        assert len(result["chunk"]) <= 16_384
        chunks.append(result["chunk"])
        offset = result["next_offset"]

    assert len(chunks) > 1
    assert "".join(chunks) == rich_html


def test_anonymized_formatted_preview_bridge_is_chunked(tmp_path, monkeypatch):
    api = AppApi(root=tmp_path / "app")
    rich_html = "<p>обезличенный форматированный текст</p>" * 8_000
    monkeypatch.setattr(
        api,
        "preview_anonymized_document",
        lambda *_args, **_kwargs: {"format": "odt", "rich_html": rich_html},
    )

    manifest = api.start_anonymized_document_preview("document-id")
    chunks = []
    offset = 0
    while offset < manifest["rich_html_length"]:
        result = api.read_document_preview_chunk(manifest["token"], "rich_html", offset)
        assert len(result["chunk"]) <= 16_384
        chunks.append(result["chunk"])
        offset = result["next_offset"]

    assert "rich_html" not in manifest
    assert "".join(chunks) == rich_html


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
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
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
    assert "function hasFormattedDocumentPreview(format){return format==='docx'||format==='odt';}" in javascript
    assert "setDocxPreviewMode(hasFormattedDocumentPreview(preview.format))" in javascript
    assert "filePreview&&selected&&hasFormattedDocumentPreview(currentPreviewFormat)" in javascript
    assert "filePreview&&hasFormattedDocumentPreview(currentPreviewFormat)" in javascript
    assert "requestAnonymizedDocumentPreview(selected,...settings" in javascript
    assert "preview_anonymized_document" in javascript
    assert "Версия 1.8" in html and "APP_VERSION='1.8'" in javascript
    assert 'src="app-v1.8.18.js"' in html
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
