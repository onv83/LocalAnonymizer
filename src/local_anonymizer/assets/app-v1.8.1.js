const $ = s => document.querySelector(s);
const APP_VERSION='1.8';
let last = {mapping:{}, candidates:[], counts:{}, parts:[], total:0, hintCount:0, warnings:[]};
let selected = '', reviewIndex = -1, debounceTimer = 0, generation = 0, importGeneration = 0, lastEscape = 0;
let filePreview = false, fileDirty = false, loadingPreview = false, documentsById = {}, currentPreviewFormat = '';
let previewFullscreen = false;
let previewScrollResetToken = 0;
let anonymizedPreviewFullscreen = false;
let anonymizedPreviewScrollResetToken = 0;
const reviewedHints = new Set();
const restoredParts = new Set();
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const disabled = () => [...document.querySelectorAll('.category:not(:checked)')].flatMap(x=>x.dataset.categories.split(','));
const warningText = w => typeof w === 'string' ? w : (w.message || w.msg || String(w));
const compactMarkerLabels={ФИО:'Ф',ОРГАНИЗАЦИЯ:'ОРГ',ПОЧТА:'ПЧ',ТЕЛЕФОН:'ТЕЛ',АККАУНТ:'АКК',ЛОГИН:'ЛОГ',ДОМЕН:'ДОМ',УЗЕЛ:'УЗЛ',ССЫЛКА:'URL',СИСТЕМА:'СИС',ПРОИЗВОДИТЕЛЬ:'ПРЗ',ДОЛЖНОСТЬ:'ДОЛЖ',ГОРОД:'ГОР',СПЕЦКАТЕГОРИЯ:'СПЕЦ',СКРЫТО:'СКР','ДАТА-РОЖДЕНИЯ':'ДР',ТАБЕЛЬНЫЙ:'ТАБ',ГОСНОМЕР:'ГРЗ',ДОГОВОР:'ДОГ',ДОКУМЕНТ:'ДОК',СУММА:'СУМ',СТАВКА:'СТВ'};

function outputText(){return (last.parts||[]).map((p,i)=>restoredParts.has(i)?p.orig:p.s).join('');}
function showMapping(mapping){
  last.mapping=mapping||{};
  $('#mapping').innerHTML=Object.entries(last.mapping).map(([k,v])=>`<div class="maprow" data-ph="${esc(k)}" tabindex="0"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join('')||'<div class="muted">Пока пусто.</div>';
  $('#mapCount').textContent=Object.keys(last.mapping).length;
}
function showLibrary(documents){
  const previous=selected;
  documentsById=Object.fromEntries(documents.map(d=>[d.id,d]));
  const list=$('#library'); list.innerHTML='';
  if(!documents.length){list.innerHTML='<option>Документы не импортированы</option>';selected='';return;}
  documents.forEach(d=>{const o=document.createElement('option');o.value=d.id;o.textContent=`${d.display_name} — ${d.status}`;list.appendChild(o);});
  if(previous&&documentsById[previous])list.value=previous;
  selected=list.value; list.onchange=async()=>{selected=list.value;await loadDocumentPreview();};
}
function setDocxPreviewMode(formatted){
  const available=currentPreviewFormat==='docx';
  $('#docxPreviewControls').hidden=!available;
  $('#docxPreview').hidden=!(available&&formatted);
  $('#textPreview').hidden=available&&formatted;
  $('#showFormatted').ariaPressed=String(available&&formatted);
  $('#showTextPreview').ariaPressed=String(!available||!formatted);
}
function setPreviewFullscreen(enabled){previewFullscreen=enabled;$('#docxPreview').classList.toggle('docx-preview-fullscreen',enabled);$('#docxPreviewControls').classList.toggle('docx-preview-controls-fullscreen',enabled);$('#previewFullscreen').textContent=enabled?'Закрыть полный экран':'На весь экран';}
function cancelDocxPreviewScrollReset(){previewScrollResetToken++;}
function resetDocxPreviewScroll(){const rich=$('#docxPreview'),token=++previewScrollResetToken,apply=()=>{if(token===previewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function setAnonymizedPreviewMode(formatted){const available=filePreview&&currentPreviewFormat==='docx'&&!!$('#anonymizedDocxPreview').innerHTML;$('#anonymizedPreviewControls').hidden=!available;$('#anonymizedDocxPreview').hidden=!(available&&formatted);$('#richOutput').hidden=available&&formatted;$('#showAnonymizedFormatted').ariaPressed=String(available&&formatted);$('#showAnonymizedText').ariaPressed=String(!available||!formatted);}
function setAnonymizedPreviewFullscreen(enabled){anonymizedPreviewFullscreen=enabled;$('#anonymizedDocxPreview').classList.toggle('docx-preview-fullscreen',enabled);$('#anonymizedPreviewControls').classList.toggle('docx-preview-controls-fullscreen',enabled);$('#anonymizedPreviewFullscreen').textContent=enabled?'Закрыть полный экран':'На весь экран';}
function cancelAnonymizedPreviewScrollReset(){anonymizedPreviewScrollResetToken++;}
function resetAnonymizedPreviewScroll(){const rich=$('#anonymizedDocxPreview'),token=++anonymizedPreviewScrollResetToken,apply=()=>{if(token===anonymizedPreviewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function leaveAnonymizedPreview(){setAnonymizedPreviewFullscreen(false);$('#anonymizedDocxPreview').innerHTML='';$('#anonymizedPreviewCompleteness').textContent='';$('#anonymizedPreviewControls').hidden=true;$('#richOutput').hidden=false;}
function leaveDocumentPreview(){setPreviewFullscreen(false);leaveAnonymizedPreview();currentPreviewFormat='';$('#docxPreview').innerHTML='';$('#previewCompleteness').textContent='';setDocxPreviewMode(false);}
async function loadDocumentPreview(){
  if(!selected)return;const documentId=selected,ticket=++generation;const preview=await pywebview.api.preview_document(documentId);
  if(ticket!==generation||documentId!==selected)return;
  loadingPreview=true;$('#source').value=preview.text;loadingPreview=false;filePreview=true;fileDirty=false;
  currentPreviewFormat=preview.format||'';const rich=$('#docxPreview');rich.innerHTML=preview.rich_html||'';resetDocxPreviewScroll();$('#previewCompleteness').textContent=preview.format==='docx'?`Текст документа загружен полностью · таблиц: ${rich.querySelectorAll('.docx-table').length}. Визуальные элементы без текста могут не отображаться.`:'';setDocxPreviewMode(preview.format==='docx');
  const analysisTicket=generation+1;await anonymizeText();if(analysisTicket!==generation||documentId!==selected)return;
  $('#fileStatus').textContent=`Предпросмотр: ${preview.display_name} — ${preview.status}`;
}
function renderWarnings(){
  const items=(last.warnings||[]).map(warningText);
  $('#warning').textContent=items.length?items.join('\n'):(last.hintCount?`Жёлтых подсказок: ${last.hintCount}. Просмотрите каждую.`:'Финальная ручная проверка обязательна.');
  $('#warning').classList.toggle('stop',(last.warnings||[]).some(w=>typeof w==='object'&&w.level==='stop'));
}
function renderStats(){
  const reviewed=[...reviewedHints].filter(k=>k.startsWith(generation+'|')).length;
  $('#stats').textContent=`Версия ${APP_VERSION} · Замен: ${last.total||0} · легенда: ${Object.keys(last.mapping||{}).length} · жёлтых: ${last.hintCount||0}, проверено ${reviewed}`;
  const groups={"Люди":['ФИО','ЛОГИН','ДАТА-РОЖДЕНИЯ'],"Организации":['ОРГАНИЗАЦИЯ','СИСТЕМА','ПРОИЗВОДИТЕЛЬ'],"Места":['ГОРОД'],"Сеть":['IP','MAC','ССЫЛКА','ДОМЕН','УЗЕЛ','DN'],"Контакты":['ПОЧТА','ТЕЛЕФОН','АККАУНТ'],"Реквизиты":['ИНН','ОГРН','КПП','СНИЛС','СЧЁТ','КАРТА','БИК','ПАСПОРТ','VIN','ДОГОВОР','ДОКУМЕНТ'],"Финансы":['СУММА','СТАВКА'],"Секреты":['SECRET']};
  $('#chips').innerHTML=Object.entries(groups).map(([name,cats])=>`<span>${name}: ${cats.reduce((n,c)=>n+(last.counts?.[c]||0),0)}</span>`).join('')+`<span class="yellow">проверить: ${Math.max(0,(last.hintCount||0)-reviewed)}</span>`;
}
function renderMirror(){
  const source=$('#source').value, marks=(last.parts||[]).filter(p=>p.t!=='text').slice().sort((a,b)=>a.s0-b.s0);
  let at=0, html='';
  marks.forEach((p,i)=>{if(p.s0<at)return;html+=esc(source.slice(at,p.s0));const cls=p.t==='hint'?'hint-source':(p.secret?'secret-source':'');html+=`<span class="source-mark ${cls}" data-part="${i}">${esc(source.slice(p.s0,p.s1))}</span>`;at=p.s1;});
  html+=esc(source.slice(at));$('#sourceMirror').innerHTML=html+'\n';
}
function renderOutput(){
  $('#richOutput').innerHTML=(last.parts||[]).map((p,i)=>{
    if(p.t==='text')return esc(p.s);
    if(restoredParts.has(i))return `<span class="restored" data-part="${i}">${esc(p.orig)}</span>`;
    if(p.t==='hint'){const key=`${generation}|${p.kind}|${p.s0}|${p.orig}`;return `<mark class="mark-hint ${reviewedHints.has(key)?'reviewed':''}" data-part="${i}" data-s0="${p.s0}" data-kind="${esc(p.kind)}" title="${esc(p.kind)}">${esc(p.s)}</mark>`;}
    return `<mark class="${p.secret?'mark-secret':'mark-replacement'}" data-part="${i}" data-s0="${p.s0}" data-ph="${esc(p.s)}" title="${p.secret?'Удалено безвозвратно':'Щёлкните, чтобы вернуть это значение'}">${esc(p.s)}</mark>`;
  }).join('');
  $('#output').value=outputText();
  $('#undoChips').innerHTML=[...restoredParts].map(i=>`<button class="undo-chip" data-undo="${i}">Отменить возврат ${esc(last.parts[i]?.s||'')}</button>`).join('');
  renderMirror(); renderStats(); updateReviewPosition();
}
function marks(){return [...$('#richOutput').querySelectorAll('.mark-replacement,.mark-secret,.mark-hint')];}
function focusMark(index){const all=marks();if(!all.length){reviewIndex=-1;updateReviewPosition();return;}reviewIndex=(index+all.length)%all.length;all.forEach(x=>x.classList.remove('mark-current'));all[reviewIndex].classList.add('mark-current');const sourceOffset=Number(all[reviewIndex].dataset.s0||0);all[reviewIndex].scrollIntoView({block:'center'});if(sourceOffset)$('#source').setSelectionRange(sourceOffset,sourceOffset);updateReviewPosition();}
function updateReviewPosition(){const all=marks();$('#reviewPos').textContent=all.length&&reviewIndex>=0?`${reviewIndex+1} из ${all.length}`:`0 из ${all.length}`;}
function restoreReplacement(index){
  const p=last.parts[index]; if(!p||p.t!=='ph'||p.secret)return;
  restoredParts.add(index);addDecisionLine('#whitelist',p.orig);if(filePreview)fileDirty=true;renderOutput();
}
function addDecisionLine(selector,value){const el=$(selector),lines=el.value.split('\n').filter(Boolean);if(!lines.includes(value)){lines.push(value);el.value=lines.join('\n');}}
function removeDecisionLine(selector,value){const el=$(selector);el.value=el.value.split('\n').filter(x=>x&&x!==value).join('\n');}
function currentHint(){const all=marks(),el=all[reviewIndex];if(!el||!el.classList.contains('mark-hint'))return null;return {el,index:Number(el.dataset.part),part:last.parts[Number(el.dataset.part)]};}
function keepHint(){const h=currentHint();if(!h)return;reviewedHints.add(`${generation}|${h.part.kind}|${h.part.s0}|${h.part.orig}`);addDecisionLine('#whitelist',h.part.orig);if(filePreview)fileDirty=true;renderOutput();}
function hideHint(){
  const h=currentHint();if(!h)return;
  const labels={'город':'ГОРОД','должность':'ДОЛЖНОСТЬ','спецкатегория ПДн':'СПЕЦКАТЕГОРИЯ','возможная фамилия':'ФИО','возможное ФИО':'ФИО','возможное имя заказчика':'ОРГАНИЗАЦИЯ','возможное имя собственное':'СКРЫТО'};
  const label=labels[h.part.kind]||'СКРЫТО';addDecisionLine('#rules',`${h.part.orig} => ${label}`);if(filePreview)fileDirty=true;
  const markerLabel=$('#compactMarkers').checked?(compactMarkerLabels[label]||label):label;
  let n=1;while(last.mapping[`[${markerLabel}-${n}]`]||$('#source').value.includes(`[${markerLabel}-${n}]`))n++;
  const marker=`[${markerLabel}-${n}]`;h.part.t='ph';h.part.s=marker;h.part.cat=label;h.part.secret=false;
  last.mapping[marker]=h.part.orig;last.hintCount=Math.max(0,last.hintCount-1);last.total=(last.total||0)+1;last.counts[label]=(last.counts[label]||0)+1;
  showMapping(last.mapping);renderOutput();
}
async function anonymizeText(){
  const text=$('#source').value;if(!text){clearResult();return;}
  const ticket=++generation;
  const settings=[$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked];
  const needsFormattedPreview=filePreview&&selected&&currentPreviewFormat==='docx';
  if(needsFormattedPreview){$('#anonymizedPreviewControls').hidden=false;$('#anonymizedPreviewCompleteness').textContent='Формирую обезличенный документ с таблицами и оформлением…';}
  const formatted=needsFormattedPreview
    ?pywebview.api.preview_anonymized_document(selected,...settings):Promise.resolve(null);
  const [result,formattedPreview]=await Promise.all([pywebview.api.anonymize_text(text,...settings),formatted]);
  if(ticket!==generation)return;
  last=result;restoredParts.clear();reviewIndex=-1;showMapping(last.mapping);renderOutput();renderWarnings();
  if(formattedPreview?.format==='docx'){
    const rich=$('#anonymizedDocxPreview');rich.innerHTML=formattedPreview.rich_html||'';resetAnonymizedPreviewScroll();$('#anonymizedPreviewCompleteness').textContent=`Обезличенный текст документа загружен полностью · таблиц: ${rich.querySelectorAll('.docx-table').length}. Визуальные элементы без текста могут не отображаться.`;setAnonymizedPreviewMode(true);
  }else leaveAnonymizedPreview();
}
function scheduleAnonymize(){clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>anonymizeText(),320);renderMirror();}
function clearResult(){generation++;last={mapping:{},candidates:[],counts:{},parts:[],total:0,hintCount:0,warnings:[]};restoredParts.clear();reviewedHints.clear();showMapping({});renderOutput();renderWarnings();}
async function anonymizeSelected(){
  if(filePreview&&selected){
    const current=selected,ticket=++generation;
    const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked);
    if(ticket!==generation||current!==selected)return;
    fileDirty=false;showMapping(r.mapping||last.mapping);last.warnings=r.warnings||[];last.total=r.replacement_count||last.total;last.hintCount=r.candidate_count||0;renderStats();renderWarnings();
    $('#fileStatus').textContent=`${r.status}. Обезличенный файл готов к скачиванию.`;const documents=await pywebview.api.list_documents();if(ticket!==generation||current!==selected)return;showLibrary(documents);selected=current;$('#library').value=current;return;
  }
  if($('#source').value.trim())return anonymizeText();
  if(!selected)return alert('Введите текст или импортируйте файл.');
  const current=selected,ticket=++generation;const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked);
  if(ticket!==generation||current!==selected)return;
  last={mapping:r.mapping||{},candidates:r.candidates||[],counts:{},parts:[],total:r.replacement_count||0,hintCount:r.candidate_count||0,warnings:r.warnings||[]};showMapping(last.mapping);renderStats();renderWarnings();
  $('#fileStatus').textContent=`${r.ready?'Готов':'Требуется ручная проверка'}. Обезличенный файл готов к скачиванию.`;const documents=await pywebview.api.list_documents();if(ticket!==generation||current!==selected)return;showLibrary(documents);
}

$('#source').addEventListener('input',()=>{if(!loadingPreview){filePreview=false;fileDirty=false;leaveDocumentPreview();}scheduleAnonymize();});$('#anonymize').onclick=anonymizeSelected;
$('#showFormatted').onclick=()=>setDocxPreviewMode(true);$('#showTextPreview').onclick=()=>setDocxPreviewMode(false);$('#previewTop').onclick=()=>{cancelDocxPreviewScrollReset();$('#docxPreview').scrollTop=0;};$('#previewBottom').onclick=()=>{cancelDocxPreviewScrollReset();const rich=$('#docxPreview');rich.scrollTop=rich.scrollHeight;};$('#previewFullscreen').onclick=()=>setPreviewFullscreen(!previewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#docxPreview').addEventListener(name,cancelDocxPreviewScrollReset));
$('#showAnonymizedFormatted').onclick=()=>setAnonymizedPreviewMode(true);$('#showAnonymizedText').onclick=()=>setAnonymizedPreviewMode(false);$('#anonymizedPreviewTop').onclick=()=>{cancelAnonymizedPreviewScrollReset();$('#anonymizedDocxPreview').scrollTop=0;};$('#anonymizedPreviewBottom').onclick=()=>{cancelAnonymizedPreviewScrollReset();const rich=$('#anonymizedDocxPreview');rich.scrollTop=rich.scrollHeight;};$('#anonymizedPreviewFullscreen').onclick=()=>setAnonymizedPreviewFullscreen(!anonymizedPreviewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#anonymizedDocxPreview').addEventListener(name,cancelAnonymizedPreviewScrollReset));
$('#richOutput').onclick=e=>{const mark=e.target.closest('mark');if(!mark)return;focusMark(marks().indexOf(mark));const i=Number(mark.dataset.part);if(mark.classList.contains('mark-replacement'))restoreReplacement(i);};
$('#undoChips').onclick=e=>{const b=e.target.closest('[data-undo]');if(b){const i=Number(b.dataset.undo);removeDecisionLine('#whitelist',last.parts[i]?.orig||'');restoredParts.delete(i);if(filePreview)fileDirty=true;renderOutput();}};
$('#mapping').onclick=e=>{const row=e.target.closest('.maprow');if(!row)return;const all=marks(),target=all.find(x=>x.dataset.ph===row.dataset.ph);if(target)focusMark(all.indexOf(target));};
$('#reviewPrev').onclick=()=>focusMark(reviewIndex-1);$('#reviewNext').onclick=()=>focusMark(reviewIndex+1);$('#hideCandidate').onclick=hideHint;$('#keepCandidate').onclick=keepHint;
$('#choose').onclick=async()=>{const ticket=++importGeneration;generation++;const r=await pywebview.api.choose_files();if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent=`Ошибка: ${(r.errors||[]).map(x=>x.error).join(', ')}`;};$('#dropChoose').onclick=$('#choose').onclick;
$('#deleteDoc').onclick=async()=>{if(selected&&confirm('Удалить запись и файлы приложения? Исходный файл пользователя сохранится.')){const r=await pywebview.api.delete_document(selected);$('#source').value='';filePreview=false;fileDirty=false;leaveDocumentPreview();clearResult();showLibrary(r.documents);}};
$('#downloadAnon').onclick=async()=>{if(!selected)return alert('Сначала выберите готовый документ.');const status=documentsById[selected]?.status;if(status==='Экспорт запрещён')return alert('Экспорт запрещён из-за критического предупреждения.');if(!['Готов','Требуется ручная проверка'].includes(status))return alert('Сначала обезличьте выбранный документ.');if(fileDirty)return alert('Сначала повторно обезличьте документ: решения предпросмотра ещё не применены к файлу.');let confirmation=false;if(status==='Требуется ручная проверка'){if(!confirm('Документ имеет предупреждения. Вы подтверждаете ручную проверку и хотите экспортировать?'))return;confirmation=true;}const r=await pywebview.api.export_anonymized(selected,confirmation);if(r.ok)$('#fileStatus').textContent=`Экспортирован: ${r.path}`;};
$('#downloadAll').onclick=async()=>{const r=await pywebview.api.export_all_anonymized();if(r.ok)$('#fileStatus').textContent=`ZIP экспортирован без таблиц соответствий: ${r.path}`;};
$('#csv').onclick=async()=>{if(!selected)return alert('Выберите документ.');if(confirm('CSV содержит чувствительные значения. Экспортировать отдельно?')){const r=await pywebview.api.export_mapping(selected);if(r.ok)$('#fileStatus').textContent=`Карта экспортирована: ${r.path}`;}};
$('#restoreFile').onclick=async()=>{if(!selected)return alert('Выберите связанный документ.');const r=await pywebview.api.restore_document(selected);if(r.ok)$('#fileStatus').textContent=`Восстановленный файл сохранён: ${r.path}; неизвестных маркеров: ${r.unknown_markers.length}`;};
$('#clear').onclick=()=>{filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='';clearResult();};
$('#sample').onclick=()=>{filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='Подрядчик «строй-гарант плюс» обслуживает АС «Паутина». login admin_db; старый qwerty123. Версия 1.7.5.16, SLA 99,9%, НДС 20%, порт 8080.';scheduleAnonymize();};
$('#paste').onclick=async()=>{const r=await pywebview.api.read_clipboard_text();filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value=r.text||'';scheduleAnonymize();};
$('#copy').onclick=()=>navigator.clipboard.writeText(outputText());
$('#restore').onclick=async()=>{$('#restored').value=(await pywebview.api.restore_text($('#reverse').value,last.mapping)).text;};$('#copyRestored').onclick=()=>navigator.clipboard.writeText($('#restored').value);
$('#selftest').onclick=async()=>{$('#testResult').textContent=(await pywebview.api.engine_self_test()).ok?' Движок исправен':' Ошибка проверки';};
$('#help').onclick=()=>alert('Все правила выполняются локально. Синие маркеры обратимы по текущей таблице, серые секреты удалены без исходных значений, жёлтые фрагменты требуют решения. Таблица и исходные значения в справку не включаются.');
$('#mono').onchange=e=>document.querySelectorAll('textarea,.mirror,.rich-output').forEach(x=>x.classList.toggle('mono',e.target.checked));
async function refreshProfiles(select){const names=await pywebview.api.list_profiles();$('#profile').innerHTML=names.map(x=>`<option>${esc(x)}</option>`).join('');if(select)$('#profile').value=select;}
$('#profile').onchange=async()=>{const p=await pywebview.api.load_profile($('#profile').value);$('#rules').value=Object.entries(p.dictionary).map(([k,v])=>`${k} => ${v}`).join('\n');$('#whitelist').value=p.whitelist.join('\n');$('#paranoid').checked=p.paranoid;scheduleAnonymize();};
$('#newProfile').onclick=async()=>{const n=prompt('Название профиля');if(n){await pywebview.api.save_profile(n,$('#rules').value,$('#whitelist').value,$('#paranoid').checked);refreshProfiles(n);}};
$('#deleteProfile').onclick=async()=>{const n=$('#profile').value;if(n!=='Общий'&&confirm(`Удалить профиль «${n}»?`)){await pywebview.api.delete_profile(n);refreshProfiles('Общий');}};$('#exportProfile').onclick=()=>pywebview.api.export_profile($('#profile').value);$('#importProfile').onclick=async()=>{const r=await pywebview.api.import_profile();if(r.ok)refreshProfiles(r.name);};
function markSettingsDirty(){if(filePreview)fileDirty=true;scheduleAnonymize();}
['#rules','#whitelist','#paranoid','#compactMarkers'].forEach(s=>$(s).addEventListener('input',markSettingsDirty));
document.querySelectorAll('.category').forEach(x=>x.addEventListener('change',markSettingsDirty));
let syncing=false;$('#source').addEventListener('scroll',()=>{if(syncing)return;syncing=true;$('#sourceMirror').scrollTop=$('#source').scrollTop;const max=$('#source').scrollHeight-$('#source').clientHeight;$('#richOutput').scrollTop=max?$('#source').scrollTop/max*($('#richOutput').scrollHeight-$('#richOutput').clientHeight):0;syncing=false;});$('#richOutput').addEventListener('scroll',()=>{if(syncing)return;syncing=true;const max=$('#richOutput').scrollHeight-$('#richOutput').clientHeight;$('#source').scrollTop=max?$('#richOutput').scrollTop/max*($('#source').scrollHeight-$('#source').clientHeight):0;$('#sourceMirror').scrollTop=$('#source').scrollTop;syncing=false;});
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();$('#copy').click();}if(e.key==='Escape'){if(previewFullscreen){setPreviewFullscreen(false);return;}if(anonymizedPreviewFullscreen){setAnonymizedPreviewFullscreen(false);return;}const now=Date.now();if(now-lastEscape<800){$('#clear').click();lastEscape=0;}else lastEscape=now;}});
['dragenter','dragover'].forEach(n=>document.addEventListener(n,e=>e.preventDefault()));document.addEventListener('drop',async e=>{e.preventDefault();const paths=[...e.dataTransfer.files].map(f=>f.path).filter(Boolean);if(paths.length){const ticket=++importGeneration;generation++;const r=await pywebview.api.import_paths(paths);if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent='Ошибка импорта';}});
window.addEventListener('pywebviewready',async()=>{showLibrary(await pywebview.api.list_documents());await refreshProfiles('Общий');if(selected)await loadDocumentPreview();else renderOutput();});
