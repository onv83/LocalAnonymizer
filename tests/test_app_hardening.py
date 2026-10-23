import json
import subprocess
from pathlib import Path

import pytest

from local_anonymizer.app import AppApi, asset_path


class SaveWindow:
    def __init__(self, target: Path):
        self.target = target

    def create_file_dialog(self, *_args, **_kwargs):
        return [str(self.target)]


def test_webview_document_list_is_strict_allowlist(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Иванов Сергей Петрович", encoding="utf-8")
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)

    rows = api.list_documents()
    assert rows
    assert set(rows[0]) == {"id", "display_name", "status"}
    assert str(tmp_path) not in repr(rows)
    assert "operation_id" not in repr(rows)


def test_text_restore_uses_explicit_current_mapping_without_shared_api_state(tmp_path):
    api = AppApi(root=tmp_path / "app")
    first = api.anonymize_text("Иванов Сергей Петрович")
    second = api.anonymize_text("Петров Иван Сергеевич")

    assert not hasattr(api, "mapping")
    assert api.restore_text(first["text"], first["mapping"])["text"] == "Иванов Сергей Петрович"
    assert api.restore_text(second["text"], second["mapping"])["text"] == "Петров Иван Сергеевич"
    assert api.restore_text(first["text"], second["mapping"])["text"] == "Петров Иван Сергеевич"


def test_ad_hoc_rules_enforce_the_shared_marker_label_contract(tmp_path):
    api = AppApi(root=tmp_path / "app")

    valid = api.anonymize_text("alpha beta", rules="alpha beta => CASE_ID2")

    assert valid["text"] == "[CASE_ID2-1]"
    assert api.restore_text(valid["text"], valid["mapping"])["text"] == "alpha beta"
    with pytest.raises(ValueError, match="метк"):
        api.anonymize_text("alpha beta", rules="alpha beta => CASE ID2")


def test_app_export_forwards_explicit_manual_review_confirmation(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Иванов Сергей Петрович", encoding="utf-8")
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)
    api.service.storage.connection.execute(
        "update documents set status=? where id=?", ("Требуется ручная проверка", document_id)
    )
    api.service.storage.connection.commit()
    api.set_window(SaveWindow(tmp_path / "export.txt"))

    with pytest.raises(PermissionError):
        api.export_anonymized(document_id)
    assert api.export_anonymized(document_id, confirmation=True)["ok"] is True


def test_ui_binds_async_results_and_restore_to_current_result(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    assert "restore_text($('#source').value,textRestoreMapping)" in javascript
    assert "if(Object.keys(last.mapping||{}).length)textRestoreMapping={...last.mapping}" in javascript
    assert "export_anonymized(selected,confirmation)" in javascript
    assert "if(ticket!==generation||current!==selected)return" in javascript
    assert "if(ticket!==previewGeneration||documentId!==selected)return" in javascript


def test_hide_hint_runtime_reanonymizes_all_exact_repetitions(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    source_text = "2) Переключение на новую платформу:\n– Переключение доступа"
    backend_result = AppApi(root=tmp_path / "app").anonymize_text(
        source_text, rules="Переключение => СКРЫТО"
    )
    assert backend_result["text"].count("[СКРЫТО-1]") == 2
    assert "Переключение" not in backend_result["text"]

    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const calls=[];
const saves=[];
const pywebview={api:{
  save_profile:async(name,rules,whitelist,paranoid,uncertainMode)=>{
    saves.push({name,rules,whitelist,paranoid,uncertainMode});return {ok:true};
  },
  anonymize_text:async(text,paranoid,rules)=>{
    calls.push({text,rules});elements.get('#richOutput').querySelectorAll=()=>[];
    return __BACKEND_RESULT__;
  }
}};
""".replace("__BACKEND_RESULT__", json.dumps(backend_result, ensure_ascii=False))
    scenario = r"""
elements.get('#source').value='2) Переключение на новую платформу:\n– Переключение доступа';
elements.get('#profile').value='Общий';
applyUncertainMode('review');
last={mapping:{},candidates:[],counts:{},parts:[{t:'text',s:'2) '},{t:'hint',kind:'возможное имя собственное',orig:'Переключение',s0:3,s:'Переключение'},{t:'text',s:' на новую платформу:\n– '},{t:'hint',kind:'возможное имя собственное',orig:'Переключение',s0:39,s:'Переключение'},{t:'text',s:' доступа'}],total:0,hintCount:2,warnings:[]};
reviewIndex=0;
const hintMark=new FakeElement();hintMark.dataset.part='1';hintMark.classList.contains=name=>name==='mark-hint';
elements.get('#richOutput').querySelectorAll=()=>[hintMark];
(async()=>{await hideHint();console.log(JSON.stringify({text:elements.get('#output').value,rules:elements.get('#rules').value,calls,saves,decision:lastReviewDecision,mapping:last.mapping,counts:last.counts}));})();
"""
    script = tmp_path / "hide-hint-runtime.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    result = json.loads(completed.stdout)
    assert result["text"].count("[СКРЫТО-1]") == 2
    assert "Переключение" not in result["text"]
    assert result["rules"] == "Переключение => СКРЫТО"
    assert result["saves"] == [{"name": "Общий", "rules": "Переключение => СКРЫТО", "whitelist": "", "paranoid": False, "uncertainMode": "review"}]
    assert result["calls"] == [{"text": source_text, "rules": "Переключение => СКРЫТО"}]
    assert "Все одинаковые вхождения «Переключение» заменены" in result["decision"]
    assert "правило сохранено в профиле «Общий»" in result["decision"]
    assert result["mapping"] == {"[СКРЫТО-1]": "Переключение"}
    assert result["counts"] == {"СКРЫТО": 2}


def test_profile_export_saves_visible_settings_and_import_loads_them(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=false;this.disabled=false;}
  addEventListener(){} appendChild(){} querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];},createElement(){return new FakeElement();},addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alerts=[];const alert=x=>alerts.push(x);const confirm=()=>true;const prompt=()=>null;
const calls=[];
const imported={dictionary:{'Переключение':'СКРЫТО','Поведение':'ТЕРМИН'},whitelist:['Оставить'],paranoid:true};
const pywebview={api:{
  list_profiles:async()=>['Общий','Импортированный'],
  load_profile:async name=>{calls.push(['load',name]);return imported;},
  save_profile:async(name,rules,whitelist,paranoid,uncertainMode)=>{calls.push(['save',name,rules,whitelist,paranoid,uncertainMode]);return {ok:true};},
  export_profile:async(name,rules,whitelist,paranoid,uncertainMode)=>{calls.push(['export',name,rules,whitelist,paranoid,uncertainMode]);return {ok:true};},
  import_profile:async()=>{calls.push(['import']);return {ok:true,name:'Импортированный'};}
}};
"""
    scenario = r"""
elements.get('#profile').value='Общий';
elements.get('#rules').value='Переключение => СКРЫТО';
elements.get('#whitelist').value='Разрешено';
applyUncertainMode('auto');
(async()=>{
  await elements.get('#exportProfile').onclick();
  filePreview={};fileDirty=false;
  elements.get('#rules').value='';elements.get('#whitelist').value='';elements.get('#paranoid').checked=false;
  await elements.get('#importProfile').onclick();
  selected='doc';documentsById={doc:{status:'Готов'}};
  await elements.get('#downloadAnon').onclick();
  await elements.get('#downloadAll').onclick();
  console.log(JSON.stringify({calls,alerts,rules:elements.get('#rules').value,whitelist:elements.get('#whitelist').value,paranoid:elements.get('#paranoid').checked,uncertainMode:elements.get('#uncertainMode').value,profile:elements.get('#profile').value,fileDirty,status:elements.get('#settingsStatus').textContent}));
  process.exit(0);
})();
"""
    script = tmp_path / "profile-roundtrip-runtime.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )
    result = json.loads(completed.stdout)
    assert result == {
        "calls": [
            ["export", "Общий", "Переключение => СКРЫТО", "Разрешено", True, "auto"],
            ["import"],
            ["load", "Импортированный"],
        ],
        "rules": "Переключение => СКРЫТО\nПоведение => ТЕРМИН",
        "whitelist": "Оставить",
        "paranoid": True,
        "uncertainMode": "auto",
        "profile": "Импортированный",
        "fileDirty": True,
        "alerts": [
            "Сначала повторно обезличьте документ: решения предпросмотра ещё не применены к файлу.",
            "Сначала примените импортированные настройки к выбранному файлу. Экспорт ZIP остановлен.",
        ],
        "status": "Профиль «Импортированный» импортирован и загружен. Примените настройки к файлу перед экспортом.",
    }


def test_auto_hide_mode_keeps_review_progress_compact(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pywebview={api:{}};
"""
    scenario = r"""
applyUncertainMode('auto');
updateReviewPosition();
console.log(JSON.stringify({progress:elements.get('#reviewPos').textContent,current:elements.get('#reviewCurrent').textContent}));
"""
    script = tmp_path / "auto-hide-review-layout.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    result = json.loads(completed.stdout)
    assert result["progress"] == "Ручная проверка отключена"
    assert "Автоматически скрывать спорное без подтверждения" in result["current"]
    assert len(result["current"]) > len(result["progress"])


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_clear_after_formatted_document_collapses_both_preview_hosts(tmp_path, asset_name):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){}
  click(){if(typeof this.onclick==='function')this.onclick();}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];},createElement(){return new FakeElement();},addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pywebview={api:{}};
"""
    scenario = r"""
filePreview=true;
currentPreviewFormat='docx';
elements.get('#docxPreview').innerHTML='<p>source</p>';
elements.get('#anonymizedDocxPreview').innerHTML='<p>output</p>';
setDocxPreviewMode(true);
setAnonymizedPreviewMode(true);
clearResult=()=>{};
elements.get('#clear').click();
console.log(JSON.stringify({
  sourceHidden:elements.get('#source').hidden,
  outputHidden:elements.get('#richOutput').hidden,
  sourcePreviewHidden:elements.get('#docxPreview').hidden,
  outputPreviewHidden:elements.get('#anonymizedDocxPreview').hidden,
  sourcePreviewHtml:elements.get('#docxPreview').innerHTML,
  outputPreviewHtml:elements.get('#anonymizedDocxPreview').innerHTML
}));
"""
    script = tmp_path / f"clear-formatted-preview-{asset_name}.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "sourceHidden": False,
        "outputHidden": False,
        "sourcePreviewHidden": True,
        "outputPreviewHidden": True,
        "sourcePreviewHtml": "",
        "outputPreviewHtml": "",
    }


@pytest.mark.parametrize(
    ("asset_name", "loading_text"),
    [
        ("app-v1.8.18.js", "Форматированный вид готовится…"),
        ("app-en-v1.8.18.js", "Preparing formatted view…"),
    ],
)
def test_anonymized_preview_controls_are_visible_while_formatted_view_loads(
    tmp_path, asset_name, loading_text
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;} setAttribute(){} removeAttribute(){} focus(){}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];},createElement(){return new FakeElement();},addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const never=new Promise(()=>{});
const pywebview={api:{
  anonymize_text(){return never;},
  preview_anonymized_document(){return never;}
}};
"""
    scenario = r"""
filePreview=true;
selected='doc-1';
currentPreviewFormat='docx';
elements.get('#source').value='document text';
anonymizeText();
console.log(JSON.stringify({
  controlsHidden:elements.get('#anonymizedPreviewControls').hidden,
  status:elements.get('#anonymizedPreviewCompleteness').textContent,
  topDisabled:elements.get('#anonymizedPreviewTop').disabled,
  bottomDisabled:elements.get('#anonymizedPreviewBottom').disabled,
  fullscreenDisabled:elements.get('#anonymizedPreviewFullscreen').disabled,
  formattedDisabled:elements.get('#showAnonymizedFormatted').disabled,
  textDisabled:elements.get('#showAnonymizedText').disabled,
  textVisible:!elements.get('#richOutput').hidden,
  formattedHidden:elements.get('#anonymizedDocxPreview').hidden
}));
"""
    script = tmp_path / f"formatted-preview-loading-{asset_name}.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "controlsHidden": False,
        "status": loading_text,
        "topDisabled": True,
        "bottomDisabled": True,
        "fullscreenDisabled": True,
        "formattedDisabled": True,
        "textDisabled": False,
        "textVisible": True,
        "formattedHidden": True,
    }


def test_same_document_anonymization_ignores_out_of_order_response(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pending=[];
const pywebview={api:{
  anonymize_document(){return new Promise(resolve=>pending.push(resolve));},
  anonymize_text:async()=>({mapping:{'[ФИО-2]':'new'},counts:{ФИО:1},parts:[],total:1,hintCount:0,warnings:[]}),
  list_documents:async()=>[{id:'doc-1',display_name:'one.txt',status:'Готов'}]
}};
"""
    scenario = r"""
(async()=>{
  selected='doc-1';filePreview=true;elements.get('#source').value='preview';
  const first=anonymizeSelected();
  const second=anonymizeSelected();
  pending[1]({mapping:{'[ФИО-2]':'new'},warnings:[],replacement_count:1,candidate_count:0,status:'Готов',output_path:'new.txt'});
  await second;
  pending[0]({mapping:{'[ФИО-1]':'stale'},warnings:[],replacement_count:1,candidate_count:0,status:'Готов',output_path:'stale.txt'});
  await first;
  console.log(JSON.stringify(last.mapping));
})();
"""
    script = tmp_path / "same-document-race.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {"[ФИО-2]": "new"}


def test_settings_changed_during_document_anonymization_keep_export_dirty(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
let finish;const documentRules=[];const previewRules=[];
const pywebview={api:{
  anonymize_document(_id,_paranoid,rules){documentRules.push(rules);return new Promise(resolve=>{finish=resolve;});},
  anonymize_text:async(_text,_paranoid,rules)=>{previewRules.push(rules);return {mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]};},
  list_documents:async()=>[{id:'doc-1',display_name:'source.docx',status:'Готов'}]
}};
"""
    scenario = r"""
(async()=>{
  selected='doc-1';filePreview=true;fileDirty=true;elements.get('#source').value='Яндекс';elements.get('#rules').value='Яндекс => OLD';
  const operation=anonymizeSelected();
  await new Promise(resolve=>setImmediate(resolve));
  elements.get('#rules').value='Яндекс => NEW';markSettingsDirty();clearTimeout(debounceTimer);
  finish({mapping:{'[OLD-1]':'Яндекс'},warnings:[],replacement_count:1,candidate_count:0,status:'Готов'});
  await operation;
  console.log(JSON.stringify({documentRules,previewRules,fileDirty,status:elements.get('#settingsStatus').textContent,button:elements.get('#anonymize').textContent}));
})();
"""
    script = tmp_path / "settings-change-document-race.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    result = json.loads(completed.stdout)
    assert result["documentRules"] == ["Яндекс => OLD"]
    assert result["previewRules"] == ["Яндекс => NEW"]
    assert result["fileDirty"] is True
    assert result["button"] == "Применить настройки к файлу"
    assert "ещё не применены" in result["status"]


def test_manual_restore_changes_during_document_anonymization_keep_export_dirty(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alerts=[];const alert=message=>alerts.push(message);const confirm=()=>true;const prompt=()=>null;
let finish;let exportCalls=0;const previewWhitelists=[];
const pywebview={api:{
  anonymize_document(){return new Promise(resolve=>{finish=resolve;});},
  anonymize_text:async(_text,_paranoid,_rules,whitelist)=>{previewWhitelists.push(whitelist);return {mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]};},
  list_documents:async()=>[{id:'doc-1',display_name:'source.docx',status:'Готов'}],
  export_anonymized:async()=>{exportCalls++;return {ok:true,path:'out.docx',recovery_path:'out.larecovery'};}
}};
"""
    scenario = r"""
async function runCase(action){
  selected='doc-1';filePreview=true;fileDirty=true;settingsGeneration=0;showLibrary([{id:'doc-1',display_name:'source.docx',status:'Готов'}]);
  elements.get('#source').value='Иванов';elements.get('#whitelist').value=action==='undo'?'Иванов':'';
  last={mapping:{},candidates:[],counts:{},parts:[{t:'ph',secret:false,orig:'Иванов',s:'[ФИО-1]'}],total:1,hintCount:0,warnings:[]};
  restoredParts.clear();if(action==='undo')restoredParts.add(0);
  const operation=anonymizeSelected();
  await new Promise(resolve=>setImmediate(resolve));
  if(action==='restore')restoreReplacement(0);
  else elements.get('#undoChips').onclick({target:{closest(){return {dataset:{undo:'0'}};}}});
  finish({mapping:{'[ФИО-1]':'Иванов'},warnings:[],replacement_count:1,candidate_count:0,status:'Готов'});
  await operation;
  const result={action,fileDirty,status:elements.get('#settingsStatus').textContent,whitelist:elements.get('#whitelist').value};
  await elements.get('#downloadAnon').onclick();result.alert=alerts.pop();return result;
}
(async()=>{console.log(JSON.stringify([await runCase('restore'),await runCase('undo')]))})();
"""
    script = tmp_path / "manual-restore-document-race.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    results = json.loads(completed.stdout)
    assert [result["action"] for result in results] == ["restore", "undo"]
    assert [result["whitelist"] for result in results] == ["Иванов", ""]
    for result in results:
        assert result["fileDirty"] is True
        assert "ещё не применены" in result["status"]
        assert "Сначала повторно обезличьте документ" in result["alert"]


def test_document_anonymize_button_shows_progress_and_reveals_marker_view(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=17;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
let finish;
const pywebview={api:{
  anonymize_document(){return new Promise(resolve=>{finish=resolve;});},
  list_documents:async()=>[{id:'doc-1',display_name:'source.doc',status:'Требуется ручная проверка'}]
}};
"""
    scenario = r"""
(async()=>{
  selected='doc-1';filePreview=true;currentPreviewFormat='docx';
  document.querySelector('#fileStatus');document.querySelector('#anonymize');
  elements.get('#anonymizedDocxPreview').innerHTML='<p>formatted</p>';
  elements.get('#richOutput').hidden=true;
  const operation=anonymizeSelected();
  await new Promise(resolve=>setImmediate(resolve));
  const during={disabled:elements.get('#anonymize').disabled,status:elements.get('#fileStatus').textContent};
  finish({mapping:{'[ОРГАНИЗАЦИЯ-1]':'value'},warnings:[],replacement_count:1,candidate_count:0,status:'Требуется ручная проверка'});
  await operation;
  console.log(JSON.stringify({during,disabled:elements.get('#anonymize').disabled,status:elements.get('#fileStatus').textContent,textVisible:!elements.get('#richOutput').hidden,formattedHidden:elements.get('#anonymizedDocxPreview').hidden,scrollTop:elements.get('#richOutput').scrollTop}));
})();
"""
    script = tmp_path / "anonymize-progress.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "during": {"disabled": True, "status": "Обезличивание документа…"},
        "disabled": False,
        "status": "Требуется ручная проверка. Обезличенный файл готов к скачиванию.",
        "textVisible": True,
        "formattedHidden": True,
        "scrollTop": 0,
    }


def test_preview_status_ignores_stale_analysis_after_document_switch(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pendingAnalysis=[];let pendingNewPreview;
const pywebview={api:{
  preview_document(id){
    if(id==='doc-1')return Promise.resolve({text:'old preview',display_name:'old.txt',status:'Импортирован'});
    return new Promise(resolve=>{pendingNewPreview=resolve;});
  },
  anonymize_text(){return new Promise(resolve=>pendingAnalysis.push(resolve));}
}};
"""
    scenario = r"""
(async()=>{
  document.querySelector('#fileStatus').textContent='unchanged';
  selected='doc-1';
  const oldLoad=loadDocumentPreview();
  await new Promise(resolve=>setImmediate(resolve));
  selected='doc-2';
  loadDocumentPreview();
  pendingAnalysis[0]({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]});
  await oldLoad;
  console.log(JSON.stringify({selected,fileStatus:elements.get('#fileStatus').textContent}));
})();
"""
    script = tmp_path / "preview-document-switch-race.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "selected": "doc-2",
        "fileStatus": "unchanged",
    }


def test_source_formatted_preview_survives_automatic_analysis_while_loading(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;this.style={};}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  setAttribute(){} removeAttribute(){} getAttribute(){return null;} contains(){return false;}
  querySelectorAll(){return [];} closest(){return null;} getBoundingClientRect(){return {top:0,bottom:1,left:0,right:1};}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  documentElement:{dataset:{}},body:{dataset:{}},
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){},matchMedia(){return {matches:false};}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const sourceRich='<article class="docx-page">formatted source</article>';
const anonymizedRich='<article class="docx-page">formatted output</article>';
let resolveSourceRich=null,sourceFormattedInFlight=false,concurrentFormattedStarts=0;
const pywebview={api:{
  start_document_preview:async()=>({token:'source-text',text_length:4,format:'docx',display_name:'source.docx',status:'Импортирован'}),
  start_formatted_document_preview:async()=>{sourceFormattedInFlight=true;return {token:'source-rich',rich_html_length:sourceRich.length,format:'docx',display_name:'source.docx',status:'Импортирован'};},
  start_anonymized_document_preview:async()=>{if(sourceFormattedInFlight)concurrentFormattedStarts++;return {token:'anonymized-rich',rich_html_length:anonymizedRich.length,format:'docx'};},
  read_document_preview_chunk(token,field){
    if(token==='source-text')return Promise.resolve({chunk:'TEXT',next_offset:4});
    if(token==='source-rich')return new Promise(resolve=>{resolveSourceRich=()=>{sourceFormattedInFlight=false;resolve({chunk:sourceRich,next_offset:sourceRich.length});};});
    return Promise.resolve({chunk:anonymizedRich,next_offset:anonymizedRich.length});
  },
  finish_document_preview:async()=>{},
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  selected='doc-1';
  const loading=loadDocumentPreview();
  while(!resolveSourceRich)await new Promise(resolve=>setImmediate(resolve));
  await anonymizeText();
  resolveSourceRich();
  await loading;
  console.log(JSON.stringify({
    concurrentFormattedStarts,
    plainHidden:elements.get('#textPreview').hidden,
    formattedHidden:elements.get('#docxPreview').hidden,
    formattedHtml:elements.get('#docxPreview').innerHTML,
    lifecycle:elements.get('#fileLifecycleStatus').textContent
  }));
})();
"""
    script = tmp_path / "source-formatted-preview-analysis-race.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "concurrentFormattedStarts": 0,
        "plainHidden": True,
        "formattedHidden": False,
        "formattedHtml": '<article class="docx-page">formatted source</article>',
        "lifecycle": "Предпросмотр готов — примените настройки к файлу",
    }


@pytest.mark.parametrize(
    ("asset_name", "pending_message"),
    [
        ("app-v1.8.18.js", "Форматированный вид готовится…"),
        ("app-en-v1.8.18.js", "Preparing formatted view…"),
    ],
)
def test_source_formatted_preview_is_default_while_rich_html_is_loading(
    tmp_path, asset_name, pending_message
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;this.style={};}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  setAttribute(){} removeAttribute(){} getAttribute(){return null;} contains(){return false;}
  querySelectorAll(){return [];} closest(){return null;} getBoundingClientRect(){return {top:0,bottom:1,left:0,right:1};}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  documentElement:{dataset:{}},body:{dataset:{}},
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){},matchMedia(){return {matches:false};}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const sourceRich='<article class="docx-page">formatted source</article>';
let resolveSourceRich=null;
const pywebview={api:{
  start_document_preview:async()=>({token:'source-text',text_length:4,format:'docx',display_name:'source.docx',status:'Импортирован'}),
  start_formatted_document_preview:async()=>({token:'source-rich',rich_html_length:sourceRich.length,format:'docx',display_name:'source.docx',status:'Импортирован'}),
  start_anonymized_document_preview:async()=>({token:'anonymized-rich',rich_html_length:0,format:'docx'}),
  read_document_preview_chunk(token){
    if(token==='source-text')return Promise.resolve({chunk:'TEXT',next_offset:4});
    if(token==='source-rich')return new Promise(resolve=>{resolveSourceRich=()=>resolve({chunk:sourceRich,next_offset:sourceRich.length});});
    throw new Error('unexpected preview token');
  },
  finish_document_preview:async()=>{},
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  document.querySelector('#docxPreviewControls').hidden=true;
  document.querySelector('#docxPreview').hidden=true;
  document.querySelector('#textPreview').hidden=false;
  selected='doc-1';
  const loading=loadDocumentPreview();
  while(!resolveSourceRich)await new Promise(resolve=>setImmediate(resolve));
  const during={
    plainHidden:document.querySelector('#textPreview').hidden,
    formattedHidden:document.querySelector('#docxPreview').hidden,
    controlsHidden:document.querySelector('#docxPreviewControls').hidden,
    status:document.querySelector('#previewCompleteness').textContent,
    topDisabled:document.querySelector('#previewTop').disabled,
    bottomDisabled:document.querySelector('#previewBottom').disabled,
    fullscreenDisabled:document.querySelector('#previewFullscreen').disabled,
    formattedDisabled:document.querySelector('#showFormatted').disabled,
    textDisabled:document.querySelector('#showTextPreview').disabled
  };
  resolveSourceRich();
  await loading;
  console.log(JSON.stringify({during,finalFormattedDisabled:document.querySelector('#showFormatted').disabled}));
})();
"""
    script = tmp_path / f"{asset_name}-source-formatted-preview-loading.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "during": {
            "plainHidden": True,
            "formattedHidden": False,
            "controlsHidden": False,
            "status": pending_message,
            "topDisabled": True,
            "bottomDisabled": True,
            "fullscreenDisabled": True,
            "formattedDisabled": True,
            "textDisabled": False,
        },
        "finalFormattedDisabled": False,
    }


def test_clear_leaves_formatted_docx_preview_and_returns_to_text_editor(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){if(this.onclick)this.onclick();}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pywebview={api:{}};
"""
    scenario = r"""
currentPreviewFormat='docx';
document.querySelector('#docxPreview').innerHTML='<article>formatted</article>';
setDocxPreviewMode(true);
document.querySelector('#clear').onclick();
console.log(JSON.stringify({
  format:currentPreviewFormat,
  controlsHidden:document.querySelector('#docxPreviewControls').hidden,
  previewHidden:document.querySelector('#docxPreview').hidden,
  textHidden:document.querySelector('#textPreview').hidden,
  rich:document.querySelector('#docxPreview').innerHTML
}));
"""
    script = tmp_path / "clear-formatted-preview.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "format": "",
        "controlsHidden": True,
        "previewHidden": True,
        "textHidden": False,
        "rich": "",
    }


def test_recreate_file_refreshes_the_visible_anonymized_preview(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.disabled=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){if(this.onclick)return this.onclick();}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  documentElement:{dataset:{}},
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){},matchMedia(){return {matches:false}}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
let textRefreshes=0, formattedRefreshes=0;
const pywebview={api:{
  anonymize_document:async()=>({mapping:{'[СКРЫТО-1]':'Яндекс'},replacement_count:2,candidate_count:0,warnings:[],status:'Готов'}),
  anonymize_text:async()=>{textRefreshes++;return {mapping:{'[СКРЫТО-1]':'Яндекс'},counts:{СКРЫТО:2},parts:[{t:'ph',s:'[СКРЫТО-1]',orig:'Яндекс',s0:0,s1:6},{t:'text',s:' 360 и '},{t:'ph',s:'[СКРЫТО-1]',orig:'Яндекс',s0:13,s1:19}],total:2,hintCount:0,warnings:[]};},
  preview_anonymized_document:async()=>{formattedRefreshes++;return {format:'docx',rich_html:'<article>[СКРЫТО-1] 360 и [СКРЫТО-1]</article>'};},
  list_documents:async()=>[{id:'doc-1',display_name:'report.docx',status:'Готов'}]
}};
"""
    scenario = r"""
(async()=>{
  selected='doc-1';filePreview=true;fileDirty=false;currentPreviewFormat='docx';
  document.querySelector('#source').value='Яндекс 360 и Яндекс';
  document.querySelector('#rules').value='Яндекс => СКРЫТО';
  document.querySelector('#richOutput').innerHTML='Яндекс 360 и Яндекс';
  await anonymizeSelected();
  console.log(JSON.stringify({
    textRefreshes,formattedRefreshes,
    visible:document.querySelector('#richOutput').innerHTML,
    formatted:document.querySelector('#anonymizedDocxPreview').innerHTML
  }));
})();
"""
    script = tmp_path / "recreate-refreshes-preview.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    result = json.loads(completed.stdout)
    assert result["textRefreshes"] == 1
    assert result["formattedRefreshes"] == 1
    assert "Яндекс" not in result["visible"]
    assert result["formatted"].count("[СКРЫТО-1]") == 2


def test_drop_docx_selects_imported_document_and_loads_formatted_preview(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.children=[];this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} setSelectionRange(){} scrollIntoView(){} click(){}
  appendChild(child){this.children.push(child);if(!this.value&&child.value)this.value=child.value;}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map(), listeners={};
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();},
  addEventListener(name,handler){listeners[name]=handler;}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pywebview={api:{
  import_paths:async()=>({ok:true,ids:['doc-new'],errors:[],documents:[{id:'doc-old',display_name:'old.txt',status:'Импортирован'},{id:'doc-new',display_name:'new.docx',status:'Импортирован'}]}),
  preview_document:async id=>({text:'Иванов',display_name:'new.docx',status:'Импортирован',format:'docx',rich_html:`<article>${id}</article>`}),
  preview_anonymized_document:async()=>({format:'docx',rich_html:'<article>ANONYMIZED</article>'}),
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  document.querySelector('#docxPreview').scrollTop=999;
  await listeners.drop({preventDefault(){},dataTransfer:{files:[{path:'C:/new.docx'}]}});
  document.querySelector('#docxPreview').scrollHeight=777;
  document.querySelector('#previewBottom').onclick();
  await new Promise(resolve=>setTimeout(resolve,200));
  console.log(JSON.stringify({
    selected,
    library:document.querySelector('#library').value,
    rich:document.querySelector('#docxPreview').innerHTML,
    scrollTop:document.querySelector('#docxPreview').scrollTop,
    bottomSurvivesDelayedReset:document.querySelector('#docxPreview').scrollTop===777,
    previewHidden:document.querySelector('#docxPreview').hidden,
    status:document.querySelector('#fileStatus').textContent
  }));
})();
"""
    script = tmp_path / "drop-docx-preview.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "selected": "doc-new",
        "library": "doc-new",
        "rich": "<article>doc-new</article>",
        "scrollTop": 777,
        "bottomSurvivesDelayedReset": True,
        "previewHidden": False,
        "status": "Предпросмотр: new.docx — Импортирован",
    }


def test_picker_selects_newly_imported_document_instead_of_keeping_old_selection(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.children=[];this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} setSelectionRange(){} scrollIntoView(){} click(){if(this.onclick)return this.onclick();}
  appendChild(child){this.children.push(child);if(!this.value&&child.value)this.value=child.value;}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map(), listeners={};
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();},
  addEventListener(name,handler){listeners[name]=handler;}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const previewCalls=[];
const pywebview={api:{
  choose_files:async()=>({ok:true,ids:['doc-new'],errors:[],documents:[
    {id:'doc-old',display_name:'old.docx',status:'Импортирован'},
    {id:'doc-new',display_name:'new.docx',status:'Импортирован'}
  ]}),
  preview_document:async id=>{previewCalls.push(id);return {text:id,display_name:`${id}.docx`,status:'Импортирован',format:'docx',rich_html:`<article>${id}</article>`};},
  preview_anonymized_document:async()=>({format:'docx',rich_html:'<article>ANONYMIZED</article>'}),
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  showLibrary([{id:'doc-old',display_name:'old.docx',status:'Импортирован'}]);
  await document.querySelector('#choose').onclick();
  console.log(JSON.stringify({
    selected,
    library:document.querySelector('#library').value,
    source:document.querySelector('#source').value,
    rich:document.querySelector('#docxPreview').innerHTML,
    status:document.querySelector('#fileStatus').textContent,
    previewCalls
  }));
})();
"""
    script = tmp_path / "picker-new-document-preview.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "selected": "doc-new",
        "library": "doc-new",
        "source": "doc-new",
        "rich": "<article>doc-new</article>",
        "status": "Предпросмотр: doc-new.docx — Импортирован",
        "previewCalls": ["doc-new"],
    }


def test_latest_import_invocation_wins_across_choose_and_two_drops(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.children=[];this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} setSelectionRange(){} scrollIntoView(){} click(){if(this.onclick)return this.onclick();}
  appendChild(child){this.children.push(child);if(!this.value&&child.value)this.value=child.value;}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map(), listeners={};
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();},
  addEventListener(name,handler){listeners[name]=handler;}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pendingChoose=[],pendingDrops=[],previewCalls=[];
const pywebview={api:{
  choose_files(){return new Promise(resolve=>pendingChoose.push(resolve));},
  import_paths(){return new Promise(resolve=>pendingDrops.push(resolve));},
  preview_document:async id=>{previewCalls.push(id);return {text:id,display_name:`${id}.docx`,status:'Импортирован',format:'docx',rich_html:`<article>${id}</article>`};},
  preview_anonymized_document:async()=>({format:'docx',rich_html:'<article>ANONYMIZED</article>'}),
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  const rendered=[];
  const realShowLibrary=showLibrary;
  showLibrary=documents=>{rendered.push(documents.map(d=>d.id));realShowLibrary(documents);};
  document.querySelector('#fileStatus').textContent='initial';
  const choose=$('#choose').onclick();
  const firstDrop=listeners.drop({preventDefault(){},dataTransfer:{files:[{path:'C:/first.docx'}]}});
  const latestDrop=listeners.drop({preventDefault(){},dataTransfer:{files:[{path:'C:/latest.docx'}]}});
  pendingDrops[1]({ok:true,ids:['doc-latest'],errors:[],documents:[{id:'doc-latest',display_name:'doc-latest.docx',status:'Импортирован'}]});
  await latestDrop;
  pendingDrops[0]({ok:true,ids:['doc-first'],errors:[],documents:[{id:'doc-first',display_name:'doc-first.docx',status:'Импортирован'}]});
  await firstDrop;
  pendingChoose[0]({ok:true,ids:['doc-chosen'],errors:[],documents:[{id:'doc-chosen',display_name:'doc-chosen.docx',status:'Импортирован'}]});
  await choose;
  console.log(JSON.stringify({
    selected,
    library:document.querySelector('#library').value,
    rich:document.querySelector('#docxPreview').innerHTML,
    status:document.querySelector('#fileStatus').textContent,
    rendered,
    previewCalls
  }));
})();
"""
    script = tmp_path / "latest-import-invocation.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "selected": "doc-latest",
        "library": "doc-latest",
        "rich": "<article>doc-latest</article>",
        "status": "Предпросмотр: doc-latest.docx — Импортирован",
        "rendered": [["doc-latest"]],
        "previewCalls": ["doc-latest"],
    }


def test_new_import_invocation_invalidates_preview_started_by_prior_import(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.children=[];this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} setSelectionRange(){} scrollIntoView(){} click(){}
  appendChild(child){this.children.push(child);if(!this.value&&child.value)this.value=child.value;}
  querySelectorAll(){return [];} closest(){return null;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map(), listeners={};
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();},
  addEventListener(name,handler){listeners[name]=handler;}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pendingImports=[],pendingPreviews={};
const pywebview={api:{
  import_paths(){return new Promise(resolve=>pendingImports.push(resolve));},
  preview_document(id){return new Promise(resolve=>{pendingPreviews[id]=resolve;});},
  preview_anonymized_document:async()=>({format:'docx',rich_html:'<article>ANONYMIZED</article>'}),
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
}};
"""
    scenario = r"""
(async()=>{
  document.querySelector('#source').value='initial source';
  document.querySelector('#fileStatus').textContent='initial status';
  const first=listeners.drop({preventDefault(){},dataTransfer:{files:[{path:'C:/first.docx'}]}});
  pendingImports[0]({ok:true,ids:['doc-first'],errors:[],documents:[{id:'doc-first',display_name:'first.docx',status:'Импортирован'}]});
  await new Promise(resolve=>setImmediate(resolve));
  const second=listeners.drop({preventDefault(){},dataTransfer:{files:[{path:'C:/second.docx'}]}});
  pendingPreviews['doc-first']({text:'STALE PREVIEW',display_name:'first.docx',status:'Импортирован',format:'docx',rich_html:'<article>STALE</article>'});
  await first;
  const afterStale={source:document.querySelector('#source').value,rich:document.querySelector('#docxPreview').innerHTML,status:document.querySelector('#fileStatus').textContent};
  pendingImports[1]({ok:true,ids:['doc-second'],errors:[],documents:[{id:'doc-second',display_name:'second.docx',status:'Импортирован'}]});
  await new Promise(resolve=>setImmediate(resolve));
  pendingPreviews['doc-second']({text:'CURRENT PREVIEW',display_name:'second.docx',status:'Импортирован',format:'docx',rich_html:'<article>CURRENT</article>'});
  await second;
  console.log(JSON.stringify({afterStale,selected,source:document.querySelector('#source').value,rich:document.querySelector('#docxPreview').innerHTML,status:document.querySelector('#fileStatus').textContent}));
})();
"""
    script = tmp_path / "import-invalidates-prior-preview.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "afterStale": {"source": "initial source", "rich": "", "status": "initial status"},
        "selected": "doc-second",
        "source": "CURRENT PREVIEW",
        "rich": "<article>CURRENT</article>",
        "status": "Предпросмотр: second.docx — Импортирован",
    }


def test_checkbox_refresh_shows_text_result_before_formatted_preview_finishes(tmp_path):
    javascript = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    harness = r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.hidden=false;this.disabled=false;this.scrollTop=0;this.scrollHeight=1;this.clientHeight=1;}
  addEventListener(){} appendChild(){} setSelectionRange(){} scrollIntoView(){} click(){}
  querySelectorAll(){return [];} closest(){return null;} contains(){return false;}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];}, createElement(){return new FakeElement();}, addEventListener(){}
};
const window={addEventListener(){}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
let finishFormatted;
const pywebview={api:{
  anonymize_text:async()=>({text:'[УЯЗВИМОСТЬ-1]',mapping:{'[УЯЗВИМОСТЬ-1]':'synthetic'},counts:{УЯЗВИМОСТЬ:1},parts:[{t:'ph',s:'[УЯЗВИМОСТЬ-1]',orig:'synthetic',s0:0,s1:9,cat:'УЯЗВИМОСТЬ',secret:false}],total:1,hintCount:0,warnings:[]}),
  preview_anonymized_document(){return new Promise(resolve=>{finishFormatted=resolve;});}
}};
"""
    scenario = r"""
(async()=>{
  document.querySelector('#source').value='synthetic';
  selected='doc-1';filePreview=true;fileDirty=true;currentPreviewFormat='docx';
  document.querySelector('#anonymizedDocxPreview').innerHTML='<p>STALE</p>';
  const operation=anonymizeText();
  await new Promise(resolve=>setImmediate(resolve));
  const during={
    text:document.querySelector('#output').value,
    textVisible:!document.querySelector('#richOutput').hidden,
    formattedHidden:document.querySelector('#anonymizedDocxPreview').hidden,
    formattedDisabled:document.querySelector('#showAnonymizedFormatted').disabled,
    status:document.querySelector('#settingsStatus').textContent
  };
  finishFormatted({format:'docx',rich_html:'<p>FRESH</p>'});
  await operation;
  console.log(JSON.stringify({during,formatted:document.querySelector('#anonymizedDocxPreview').innerHTML,formattedDisabled:document.querySelector('#showAnonymizedFormatted').disabled}));
})();
"""
    script = tmp_path / "checkbox-preview-order.js"
    script.write_text(harness + javascript + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    state = json.loads(completed.stdout)
    assert state["during"] == {
        "text": "[УЯЗВИМОСТЬ-1]",
        "textVisible": True,
        "formattedHidden": True,
        "formattedDisabled": True,
        "status": "Предпросмотр обновлён. Экспортируемый файл пока использует прежние настройки — нажмите «Применить настройки к файлу».",
    }
    assert state["formatted"] == "<p>FRESH</p>"
    assert state["formattedDisabled"] is False


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_formatted_scroll_maps_matching_blocks_when_wrapping_changes_scrollable_tail(
    tmp_path, asset_name
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("const sourcePreviewAlignment=")
    scroll_logic = javascript[start:end]
    harness = r"""
function makeContainer(scrollHeight,clientHeight,scrollTop,offsets){
  const container={scrollHeight,clientHeight,scrollTop,hidden:false};
  container.getBoundingClientRect=()=>({top:0});
  container.querySelectorAll=()=>offsets.map(offset=>({
    getBoundingClientRect:()=>({top:offset-container.scrollTop})
  }));
  return container;
}
"""
    scenario = r"""
const source=makeContainer(1000,200,600,[100,300,600,780,900]);
const target=makeContainer(700,200,0,[80,250,450,540,620]);
console.log(JSON.stringify({mapped:mapPreviewScroll(source,target)}));
"""
    script = tmp_path / f"formatted-scroll-logical-blocks-{asset_name}.js"
    script.write_text(scroll_logic + harness + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {"mapped": 450}


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_formatted_scroll_matches_shared_structural_anchor_when_blocks_are_removed(
    tmp_path, asset_name
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("const sourcePreviewAlignment=")
    scroll_logic = javascript[start:end]
    harness = r"""
function makeContainer(scrollHeight,clientHeight,scrollTop,anchors){
  const container={scrollHeight,clientHeight,scrollTop,hidden:false};
  container.getBoundingClientRect=()=>({top:0});
  container.querySelectorAll=()=>anchors.map(([key,offset])=>({
    dataset:{previewAnchor:key},
    getBoundingClientRect:()=>({top:offset-container.scrollTop})
  }));
  return container;
}
"""
    scenario = r"""
const source=makeContainer(1200,200,600,[['a',100],['removed',300],['shared',600],['tail',950]]);
const target=makeContainer(700,200,0,[['a',80],['shared',250],['tail',470]]);
console.log(JSON.stringify({mapped:mapPreviewScroll(source,target)}));
"""
    script = tmp_path / f"formatted-scroll-shared-anchors-{asset_name}.js"
    script.write_text(scroll_logic + harness + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {"mapped": 250}


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_formatted_scroll_sorts_visual_anchors_from_nested_and_multicolumn_tables(
    tmp_path, asset_name
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("const sourcePreviewAlignment=")
    scroll_logic = javascript[start:end]
    scenario = r"""
const container={scrollHeight:700,clientHeight:200,scrollTop:0,hidden:false};
container.getBoundingClientRect=()=>({top:0});
container.querySelectorAll=()=>[
  {dataset:{previewAnchor:'row'},getBoundingClientRect:()=>({top:100})},
  {dataset:{previewAnchor:'left-lower'},getBoundingClientRect:()=>({top:320})},
  {dataset:{previewAnchor:'right-nested'},getBoundingClientRect:()=>({top:180})},
  {dataset:{previewAnchor:'next-row'},getBoundingClientRect:()=>({top:450})}
];
console.log(JSON.stringify({anchors:collectPreviewAnchors(container)}));
"""
    script = tmp_path / f"formatted-scroll-visual-order-{asset_name}.js"
    script.write_text(scroll_logic + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {"anchors": [0, 100, 180, 320, 450, 500]}


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_formatted_scroll_realigns_after_late_image_layout_change(tmp_path, asset_name):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("const sourcePreviewAlignment=")
    scroll_logic = javascript[start:end]
    harness = r"""
function makeContainer(scrollHeight,clientHeight,scrollTop,anchors){
  const container={scrollHeight,clientHeight,scrollTop,anchors,hidden:false};
  container.getBoundingClientRect=()=>({top:0});
  container.querySelectorAll=()=>container.anchors.map(([key,offset])=>({
    dataset:{previewAnchor:key},
    getBoundingClientRect:()=>({top:offset-container.scrollTop})
  }));
  return container;
}
"""
    scenario = r"""
const source=makeContainer(1000,200,600,[['a',100],['shared',600],['tail',780]]);
const target=makeContainer(700,200,0,[['a',80],['shared',250],['tail',450]]);
syncPreviewScroll(source,target);
const before=target.scrollTop;
target.anchors=[['a',80],['shared',350],['tail',470]];
refreshPreviewLayout(source,target);
console.log(JSON.stringify({before,after:target.scrollTop}));
"""
    script = tmp_path / f"formatted-scroll-image-reflow-{asset_name}.js"
    script.write_text(scroll_logic + harness + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {"before": 250, "after": 350}


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_formatted_scroll_sync_fallback_cache_hidden_and_mode_contracts(
    tmp_path, asset_name
):
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    start = javascript.index("let previewScrollSyncDepth=0;")
    end = javascript.index("const sourcePreviewAlignment=")
    scroll_logic = javascript[start:end]
    switch_start = javascript.index("function switchPreviewMode(")
    switch_end = javascript.index("function setDocxPreviewMode(")
    switch_logic = javascript[switch_start:switch_end]
    harness = r"""
function makeContainer(scrollHeight,clientHeight,scrollTop,offsets){
  const container={scrollHeight,clientHeight,scrollTop,offsets,hidden:false};
  container.getBoundingClientRect=()=>({top:0});
  container.querySelectorAll=()=>container.offsets.map(offset=>({
    getBoundingClientRect:()=>({top:offset-container.scrollTop})
  }));
  return container;
}
const plain=makeContainer(1000,200,600,[100,300,600,780,900]);
const formatted=makeContainer(700,200,0,[80,250,450,540,620]);
let activeSource=plain;
function activeSourcePreview(){return activeSource;}
function activeAnonymizedPreview(){return formatted;}
function setDocxPreviewMode(value){activeSource=value?formatted:plain;}
function setAnonymizedPreviewMode(){}
"""
    scenario = r"""
const unequalSource=makeContainer(1000,200,400,[100,400,700]);
const unequalTarget=makeContainer(700,200,0,[100,300]);
const unequalMapped=mapPreviewScroll(unequalSource,unequalTarget);
const cached=makeContainer(700,200,0,[80,250,450]);
const anchorsBefore=collectPreviewAnchors(cached).slice();
cached.offsets=[50,200,400];
const anchorsWhileCached=collectPreviewAnchors(cached).slice();
invalidatePreviewAnchors(cached);
const anchorsAfterInvalidation=collectPreviewAnchors(cached).slice();
const hiddenSource=makeContainer(1000,200,400,[100,400,700]);
const hiddenTarget=makeContainer(700,200,17,[100,300]);
hiddenSource.hidden=true;
syncPreviewScroll(hiddenSource,hiddenTarget);
switchPreviewMode(setDocxPreviewMode,true);
console.log(JSON.stringify({
  unequalMapped,anchorsBefore,anchorsWhileCached,anchorsAfterInvalidation,
  hiddenTargetScroll:hiddenTarget.scrollTop,modeScroll:formatted.scrollTop
}));
"""
    script = tmp_path / f"formatted-scroll-contracts-{asset_name}.js"
    script.write_text(scroll_logic + harness + switch_logic + scenario, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )

    assert json.loads(completed.stdout) == {
        "unequalMapped": 250,
        "anchorsBefore": [0, 80, 250, 450, 500],
        "anchorsWhileCached": [0, 80, 250, 450, 500],
        "anchorsAfterInvalidation": [0, 50, 200, 400, 500],
        "hiddenTargetScroll": 17,
        "modeScroll": 450,
    }


def _preview_async_harness() -> str:
    return r"""
class FakeElement {
  constructor(){this.value='';this.innerHTML='';this.textContent='';this.dataset={};this.checked=true;this.disabled=false;this.hidden=false;this.scrollTop=0;this.scrollHeight=1000;this.clientHeight=200;this.clientWidth=400;this.style={};this.children=[];this.listeners={};}
  addEventListener(type,handler){(this.listeners[type]||(this.listeners[type]=[])).push(handler);} appendChild(child){this.children.push(child);if(!this.value&&child.value)this.value=child.value;} setSelectionRange(){} scrollIntoView(){} click(){if(this.onclick)return this.onclick();}
  setAttribute(name,value){this[name]=value;} removeAttribute(name){delete this[name];} getAttribute(){return null;} contains(){return false;} focus(){}
  querySelectorAll(){return [];} querySelector(){return null;} closest(){return null;} getBoundingClientRect(){return {top:0,bottom:200,left:0,right:400,height:200};}
  classList={add(){},remove(){},toggle(){},contains(){return false;}};
}
const elements=new Map();
const document={
  documentElement:{dataset:{}},body:{dataset:{},children:[]},activeElement:null,
  querySelector(selector){if(!elements.has(selector))elements.set(selector,new FakeElement());return elements.get(selector);},
  querySelectorAll(){return [];},createElement(){return new FakeElement();},addEventListener(){}
};
const window={addEventListener(){},matchMedia(){return {matches:false};}};
const navigator={clipboard:{readText:async()=>'',writeText(){}}};
const alert=()=>{};const confirm=()=>true;const prompt=()=>null;
const pywebview={api:{}};
"""


def _run_preview_async_scenario(tmp_path, asset_name: str, scenario: str) -> dict:
    javascript = asset_path(asset_name).read_text(encoding="utf-8")
    script = tmp_path / f"{asset_name}-preview-async-regression.js"
    script.write_text(_preview_async_harness() + javascript + scenario, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_document_load_invalidates_inflight_analysis(tmp_path, asset_name):
    scenario = r"""
let resolveStaleAnalysis;
pywebview.api={
  anonymize_text(){return new Promise(resolve=>{resolveStaleAnalysis=resolve;});},
  preview_document(){return new Promise(()=>{});}
};
(async()=>{
  selected='doc-a';filePreview=true;loadingPreview=false;
  document.querySelector('#source').value='A';last={marker:'INITIAL',mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]};
  const stale=anonymizeText();
  while(!resolveStaleAnalysis)await new Promise(resolve=>setImmediate(resolve));
  selected='doc-b';document.querySelector('#source').value='B';
  loadDocumentPreview();
  resolveStaleAnalysis({marker:'A-STALE',mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]});
  await stale;
  console.log(JSON.stringify({marker:last.marker,source:document.querySelector('#source').value,selected}));
})();
"""

    assert _run_preview_async_scenario(tmp_path, asset_name, scenario) == {
        "marker": "INITIAL",
        "source": "B",
        "selected": "doc-b",
    }


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_settings_changed_during_preview_load_remain_dirty_and_block_export(tmp_path, asset_name):
    scenario = r"""
let resolvePreview;
pywebview.api={
  preview_document(){return new Promise(resolve=>{resolvePreview=resolve;});},
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
};
(async()=>{
  selected='doc-1';documentsById={'doc-1':{status:'Готов'}};
  const loading=loadDocumentPreview();
  while(!resolvePreview)await new Promise(resolve=>setImmediate(resolve));
  settingsGeneration++;fileDirty=true;updatePrimaryAction();
  resolvePreview({text:'TEXT',display_name:'source.txt',status:'Готов',format:'txt',rich_html:''});
  await loading;
  console.log(JSON.stringify({fileDirty,exportDisabled:document.querySelector('#exportNow').disabled}));
})();
"""

    assert _run_preview_async_scenario(tmp_path, asset_name, scenario) == {
        "fileDirty": True,
        "exportDisabled": True,
    }


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_text_mode_and_scroll_survive_formatted_preview_completion(tmp_path, asset_name):
    scenario = r"""
const richHtml='<article class="docx-page">FORMATTED</article>';
let resolveRich;
pywebview.api={
  start_document_preview:async()=>({token:'text',text_length:4,format:'docx',display_name:'source.docx',status:'Импортирован'}),
  start_formatted_document_preview:async()=>({token:'rich',rich_html_length:richHtml.length,format:'docx',display_name:'source.docx',status:'Импортирован'}),
  read_document_preview_chunk(token){
    if(token==='text')return Promise.resolve({chunk:'TEXT',next_offset:4});
    return new Promise(resolve=>{resolveRich=()=>resolve({chunk:richHtml,next_offset:richHtml.length});});
  },
  finish_document_preview:async()=>{},
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]}),
  preview_anonymized_document:async()=>({format:'docx',rich_html:'<article>ANON</article>'})
};
(async()=>{
  document.querySelector('#docxPreview').hidden=true;
  document.querySelector('#textPreview').hidden=false;
  selected='doc-1';
  const loading=loadDocumentPreview();
  while(!resolveRich)await new Promise(resolve=>setImmediate(resolve));
  document.querySelector('#showTextPreview').onclick();
  document.querySelector('#source').scrollTop=321;
  resolveRich();
  await loading;
  console.log(JSON.stringify({
    textHidden:document.querySelector('#textPreview').hidden,
    formattedHidden:document.querySelector('#docxPreview').hidden,
    sourceScroll:document.querySelector('#source').scrollTop,
    rich:document.querySelector('#docxPreview').innerHTML
  }));
})();
"""

    assert _run_preview_async_scenario(tmp_path, asset_name, scenario) == {
        "textHidden": False,
        "formattedHidden": True,
        "sourceScroll": 321,
        "rich": '<article class="docx-page">FORMATTED</article>',
    }


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_anonymized_formatted_preview_completion_realigns_to_current_source_block(
    tmp_path, asset_name
):
    scenario = r"""
function useOffsets(element,scrollHeight,clientHeight,scrollTop,offsets){
  element.scrollHeight=scrollHeight;element.clientHeight=clientHeight;element.scrollTop=scrollTop;
  element.getBoundingClientRect=()=>({top:0,bottom:clientHeight,left:0,right:400,height:clientHeight});
  element.querySelectorAll=selector=>selector==='.docx-paragraph,li,tr'?offsets.map(offset=>({
    getBoundingClientRect:()=>({top:offset-element.scrollTop})
  })):[];
}
const sourcePreview=document.querySelector('#docxPreview');
const formattedOutput=document.querySelector('#anonymizedDocxPreview');
const textOutput=document.querySelector('#richOutput');
useOffsets(sourcePreview,1000,200,300,[100,300,600,780,900]);
useOffsets(formattedOutput,700,200,0,[80,250,450,540,620]);
useOffsets(textOutput,1000,200,0,[]);
sourcePreview.hidden=false;formattedOutput.hidden=false;textOutput.hidden=true;
let resolveFormatted;
pywebview.api={
  preview_anonymized_document(){return new Promise(resolve=>{resolveFormatted=resolve;});},
  anonymize_text:async()=>({mapping:{},counts:{},parts:[],total:0,hintCount:0,warnings:[]})
};
(async()=>{
  selected='doc-1';filePreview=true;loadingPreview=false;currentPreviewFormat='docx';
  document.querySelector('#source').value='TEXT';
  const loading=anonymizeText();
  while(!resolveFormatted)await new Promise(resolve=>setImmediate(resolve));
  sourcePreview.scrollTop=600;
  syncFormattedSourceScroll();
  const interimTextScroll=textOutput.scrollTop;
  resolveFormatted({format:'docx',rich_html:'<article>ANON</article>'});
  await loading;
  console.log(JSON.stringify({interimTextScroll,formattedScroll:formattedOutput.scrollTop}));
})();
"""

    assert _run_preview_async_scenario(tmp_path, asset_name, scenario) == {
        "interimTextScroll": 600,
        "formattedScroll": 450,
    }


@pytest.mark.parametrize("asset_name", ["app-v1.8.18.js", "app-en-v1.8.18.js"])
def test_late_formatted_image_load_automatically_realigns_visible_previews(
    tmp_path, asset_name
):
    scenario = r"""
function useKeyedOffsets(element,scrollHeight,clientHeight,scrollTop,anchors){
  element.scrollHeight=scrollHeight;element.clientHeight=clientHeight;element.scrollTop=scrollTop;element.anchors=anchors;
  element.getBoundingClientRect=()=>({top:0,bottom:clientHeight,left:0,right:400,height:clientHeight});
  element.querySelectorAll=selector=>selector==='.docx-paragraph,li,tr'?element.anchors.map(([key,offset])=>({
    dataset:{previewAnchor:key},getBoundingClientRect:()=>({top:offset-element.scrollTop})
  })):[];
}
const sourcePreview=document.querySelector('#docxPreview');
const formattedOutput=document.querySelector('#anonymizedDocxPreview');
const textOutput=document.querySelector('#richOutput');
useKeyedOffsets(sourcePreview,1000,200,600,[['a',100],['shared',600],['tail',780]]);
useKeyedOffsets(formattedOutput,700,200,0,[['a',80],['shared',250],['tail',450]]);
sourcePreview.hidden=false;formattedOutput.hidden=false;textOutput.hidden=true;
(async()=>{
  currentPreviewFormat='docx';filePreview=true;
  syncFormattedSourceScroll();
  const before=formattedOutput.scrollTop;
  formattedOutput.anchors=[['a',80],['shared',350],['tail',470]];
  (formattedOutput.listeners.load||[]).forEach(handler=>handler({target:{tagName:'IMG'}}));
  await new Promise(resolve=>setTimeout(resolve,20));
  console.log(JSON.stringify({before,after:formattedOutput.scrollTop}));
})();
"""

    assert _run_preview_async_scenario(tmp_path, asset_name, scenario) == {
        "before": 250,
        "after": 350,
    }
