const $ = s => document.querySelector(s);
const APP_VERSION='1.8';
const THEME_KEY='local-anonymizer-theme';
const DESIGN_KEY='designMode';
async function applyDesignMode(mode,persist=false){const value=mode==='legacy'?'legacy':'new';document.body.dataset.design=value;$('#designMode').value=value;$('#detectionCategories').open=false;if(persist){localStorage.setItem('designMode',value);await pywebview.api.set_design_mode(value);}}
function preferredTheme(){
  try{const saved=localStorage.getItem(THEME_KEY);if(saved==='light'||saved==='dark')return saved;}catch(_error){}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches?'dark':'light';
}
function applyTheme(theme,persist=false){
  const selected=theme==='dark'?'dark':'light';
  if(document.documentElement)document.documentElement.dataset.theme=selected;
  const button=$('#themeToggle');
  if(button){button.setAttribute?.('aria-pressed',String(selected==='dark'));button.textContent=selected==='dark'?'☀️ Светлая тема':'🌙 Тёмная тема';}
  if(persist){try{localStorage.setItem(THEME_KEY,selected);}catch(_error){}}
}
applyTheme(preferredTheme());
let last = {mapping:{}, candidates:[], counts:{}, parts:[], total:0, hintCount:0, warnings:[]};
let textRestoreMapping = {};
let selected = '', reviewIndex = -1, debounceTimer = 0, generation = 0, settingsGeneration = 0, importGeneration = 0, restoreGeneration = 0, lastEscape = 0;
let filePreview = false, fileDirty = false, loadingPreview = false, documentsById = {}, currentPreviewFormat = '';
let previewFullscreen = false, fullscreenReturnFocus = null;
let previousInert = new Map();
let previewScrollResetToken = 0;
let anonymizedPreviewFullscreen = false;
let anonymizedPreviewScrollResetToken = 0;
let lastReviewDecision = '';
const reviewedHints = new Set();
const restoredParts = new Set();
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let tooltipButton=null;
function tooltipText(button){
  const text=button?.dataset?.tooltip||button?.getAttribute?.('title')||'';
  if(text&&button?.getAttribute?.('title')){button.dataset.tooltip=text;button.removeAttribute('title');button.setAttribute('aria-describedby','buttonTooltip');}
  return text;
}
function showButtonTooltip(button){
  const tip=$('#buttonTooltip'),text=tooltipText(button);if(!tip||!text)return;
  tooltipButton=button;tip.textContent=text;tip.hidden=false;
  const box=button.getBoundingClientRect(),pad=8;
  tip.style.left=`${Math.max(pad,Math.min(box.left,(window.innerWidth||box.right)-tip.offsetWidth-pad))}px`;
  let top=box.bottom+pad;if(top+tip.offsetHeight>(window.innerHeight||top+tip.offsetHeight))top=Math.max(pad,box.top-tip.offsetHeight-pad);
  tip.style.top=`${top}px`;
}
function hideButtonTooltip(button){const tip=$('#buttonTooltip');if(!tip||button&&tooltipButton!==button)return;tip.hidden=true;tip.textContent='';tooltipButton=null;}
document.addEventListener('pointerover',e=>{const button=e.target.closest?.('button');if(button)showButtonTooltip(button);});
document.addEventListener('pointerout',e=>{const button=e.target.closest?.('button');if(button&&!button.contains(e.relatedTarget))hideButtonTooltip(button);});
document.addEventListener('focusin',e=>{const button=e.target.closest?.('button');if(button)showButtonTooltip(button);});
document.addEventListener('focusout',e=>{const button=e.target.closest?.('button');if(button)hideButtonTooltip(button);});
document.addEventListener('scroll',()=>hideButtonTooltip(),true);
const disabled = () => [...document.querySelectorAll('.category:not(:checked)')].flatMap(x=>x.dataset.categories.split(','));
const warningText = w => typeof w === 'string' ? w : (w.message || w.msg || String(w));
const compactMarkerLabels={ФИО:'Ф',ОРГАНИЗАЦИЯ:'ОРГ',ПОЧТА:'ПЧ',ТЕЛЕФОН:'ТЕЛ',АККАУНТ:'АКК',ЛОГИН:'ЛОГ',ДОМЕН:'ДОМ',УЗЕЛ:'УЗЛ','СТРУКТУРА-AD':'AD',ДИСК:'ДСК',ПУТЬ:'ПУТЬ',ПРОГРАММА:'ПО',СКРИПТЫ:'СКРП',ССЫЛКА:'URL',СИСТЕМА:'СИС',ПРОИЗВОДИТЕЛЬ:'ПРЗ',ДОЛЖНОСТЬ:'ДОЛЖ',ГОРОД:'ГОР',СПЕЦКАТЕГОРИЯ:'СПЕЦ',СКРЫТО:'СКР','ДАТА-РОЖДЕНИЯ':'ДР',ТАБЕЛЬНЫЙ:'ТАБ',ГОСНОМЕР:'ГРЗ',ДОГОВОР:'ДОГ',ДОКУМЕНТ:'ДОК',СУММА:'СУМ',СТАВКА:'СТВ'};
function updateCategoryMarkerExamples(){
  const compact=$('#compactMarkers').checked;
  document.querySelectorAll('label:has(> input.category)').forEach(label=>{
    const input=label.querySelector('input.category'),code=label.querySelector('code');if(!code)return;
    const category=input.dataset.categories;if(category==='уязвимость'||category==='CUSTOM')return;
    const marker=compact?(compactMarkerLabels[category]||category):category;code.textContent=`[${marker}-N]`;
  });
}

function outputText(){return (last.parts||[]).map((p,i)=>restoredParts.has(i)?p.orig:p.s).join('');}
function showMapping(mapping){
  last.mapping=mapping||{};
}
function showLibrary(documents){
  const previous=selected;
  documentsById=Object.fromEntries(documents.map(d=>[d.id,d]));
  const list=$('#library'); list.innerHTML='';
  if(!documents.length){list.innerHTML='<option>Документы не импортированы</option>';selected='';updateRestoreContext();return;}
  documents.forEach(d=>{const o=document.createElement('option');o.value=d.id;o.textContent=`${d.display_name} — ${d.status}`;list.appendChild(o);});
  if(previous&&documentsById[previous])list.value=previous;
  selected=list.value;updateRestoreContext();list.onchange=async()=>{selected=list.value;updateRestoreContext();await loadDocumentPreview();};
}
function updateRestoreContext(){}
function setDocxPreviewMode(formatted){
  const available=currentPreviewFormat==='docx';
  $('#docxPreviewControls').hidden=!available;
  $('#docxPreview').hidden=!(available&&formatted);
  $('#textPreview').hidden=available&&formatted;
  $('#showFormatted').ariaPressed=String(available&&formatted);
  $('#showTextPreview').ariaPressed=String(!available||!formatted);
}
function setModalIsolation(surface,enabled){if(enabled){previousInert=new Map();let child=surface,ancestor=surface.parentElement;while(ancestor){[...(ancestor.children||[])].forEach(sibling=>{if(sibling!==child&&!previousInert.has(sibling)){previousInert.set(sibling,!!sibling.inert);sibling.inert=true;}});if(ancestor===document.body)break;child=ancestor;ancestor=ancestor.parentElement;}}else{previousInert.forEach((value,element)=>{element.inert=value;});previousInert.clear();}}
function modalFocusables(surface){return [...surface.querySelectorAll('button:not([disabled]),select:not([disabled]),textarea:not([disabled]),[href],[tabindex]:not([tabindex="-1"])')].filter(el=>!el.hidden&&!el.inert);}
function trapModalFocus(event,surface){if(event.key!=='Tab')return;const items=modalFocusables(surface);if(!items.length){event.preventDefault();surface.focus();return;}const first=items[0],last=items[items.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
function setFullscreenSemantics(surface,button,enabled,label){if(enabled){fullscreenReturnFocus=document.activeElement;surface.setAttribute('role','dialog');surface.ariaModal='true';surface.setAttribute('aria-label',label);surface.tabIndex=-1;surface.onkeydown=event=>trapModalFocus(event,surface);setModalIsolation(surface,true);button.setAttribute('aria-pressed','true');button.focus();}else{setModalIsolation(surface,false);surface.removeAttribute('role');surface.removeAttribute('aria-modal');surface.removeAttribute('aria-label');surface.removeAttribute('tabindex');surface.onkeydown=null;button.setAttribute('aria-pressed','false');if(fullscreenReturnFocus){fullscreenReturnFocus.focus();fullscreenReturnFocus=null;}}}
function setPreviewFullscreen(enabled){if(enabled===previewFullscreen)return;previewFullscreen=enabled;const surface=$('#docxPreviewSurface'),button=$('#previewFullscreen');surface.classList.toggle('preview-surface-fullscreen',enabled);button.textContent=enabled?'Закрыть полный экран':'На весь экран';setFullscreenSemantics(surface,button,enabled,'Полноэкранный просмотр исходного документа');}
function cancelDocxPreviewScrollReset(){previewScrollResetToken++;}
function resetDocxPreviewScroll(){const rich=$('#docxPreview'),token=++previewScrollResetToken,apply=()=>{if(token===previewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function setAnonymizedPreviewMode(formatted){const available=filePreview&&currentPreviewFormat==='docx'&&!!$('#anonymizedDocxPreview').innerHTML;$('#anonymizedPreviewControls').hidden=!available;$('#anonymizedDocxPreview').hidden=!(available&&formatted);$('#richOutput').hidden=available&&formatted;$('#showAnonymizedFormatted').ariaPressed=String(available&&formatted);$('#showAnonymizedText').ariaPressed=String(!available||!formatted);}
function setAnonymizedPreviewFullscreen(enabled){if(enabled===anonymizedPreviewFullscreen)return;anonymizedPreviewFullscreen=enabled;const surface=$('#anonymizedPreviewSurface'),button=$('#anonymizedPreviewFullscreen');surface.classList.toggle('preview-surface-fullscreen',enabled);button.textContent=enabled?'Закрыть полный экран':'На весь экран';setFullscreenSemantics(surface,button,enabled,'Полноэкранный просмотр обезличенного документа');}
function cancelAnonymizedPreviewScrollReset(){anonymizedPreviewScrollResetToken++;}
function resetAnonymizedPreviewScroll(){const rich=$('#anonymizedDocxPreview'),token=++anonymizedPreviewScrollResetToken,apply=()=>{if(token===anonymizedPreviewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function leaveAnonymizedPreview(){setAnonymizedPreviewFullscreen(false);$('#anonymizedDocxPreview').innerHTML='';$('#anonymizedPreviewCompleteness').textContent='';$('#anonymizedPreviewControls').hidden=true;$('#richOutput').hidden=false;}
function leaveDocumentPreview(){setPreviewFullscreen(false);leaveAnonymizedPreview();currentPreviewFormat='';$('#docxPreview').innerHTML='';$('#previewCompleteness').textContent='';setDocxPreviewMode(false);}
function updatePrimaryAction(keepStatus=false){
  const button=$('#anonymize'),status=$('#settingsStatus'),apply=$('#applyNow'),exportButton=$('#exportNow'),lifecycle=$('#fileLifecycleStatus');
  if(filePreview&&selected){const ready=['Готов','Требуется ручная проверка'].includes(documentsById[selected]?.status);button.disabled=false;button.textContent=fileDirty?'Применить настройки к файлу':'Пересоздать файл с текущими настройками';apply.disabled=false;exportButton.disabled=fileDirty||!ready;lifecycle.textContent=fileDirty?'Настройки изменены — экспортируемый файл требует повторной обработки':ready?'Файл обработан и готов к сохранению':'Предпросмотр готов — примените настройки к файлу';if(!fileDirty&&!keepStatus)status.textContent='Предпросмотр и экспортируемый файл используют текущие настройки.';return;}
  button.disabled=true;apply.disabled=true;exportButton.disabled=true;button.textContent=$('#source').value.trim()?'Текст проверяется автоматически':'Сначала выберите файл';lifecycle.textContent=$('#source').value.trim()?'Предпросмотр текста обновляется автоматически':'Выберите документ — обработка выполняется только на этом компьютере';status.textContent=$('#source').value.trim()?'Для вставленного текста настройки применяются автоматически. Отдельная кнопка не нужна.':'Сначала выберите файл. Для вставленного текста изменения применяются автоматически.';
}
async function loadDocumentPreview(){
  if(!selected)return;$('#fileLifecycleStatus').textContent='Создаётся предпросмотр…';const documentId=selected,ticket=++generation;let preview;
  try{preview=await pywebview.api.preview_document(documentId);}
  catch(error){$('#fileLifecycleStatus').textContent=`Ошибка предпросмотра: ${String(error?.message||error)}`;return;}
  if(ticket!==generation||documentId!==selected)return;
  loadingPreview=true;$('#source').value=preview.text;loadingPreview=false;filePreview=true;fileDirty=false;updatePrimaryAction();
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
  const pending=Math.max(0,(last.hintCount||0)-reviewed),all=(last.hintCount||0);$('#stats').textContent=`Найдено замен: ${last.total||0} · Требуют решения: ${pending} · Проверено: ${reviewed} из ${all}`;
  const groups={"Люди":['ФИО','ЛОГИН','ДАТА-РОЖДЕНИЯ'],"Организации":['ОРГАНИЗАЦИЯ','СИСТЕМА','ПРОИЗВОДИТЕЛЬ'],"Места":['ГОРОД'],"Сеть":['IP','MAC','IMEI','ССЫЛКА','ДОМЕН','УЗЕЛ','DN'],"Контакты":['ПОЧТА','ТЕЛЕФОН','АККАУНТ'],"Реквизиты":['ИНН','ОГРН','КПП','СНИЛС','СЧЁТ','КАРТА','БИК','ПАСПОРТ','VIN','ДОГОВОР','ДОКУМЕНТ'],"Финансы":['СУММА','СТАВКА'],"Секреты":['SECRET']};
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
    if(p.t==='hint'){const key=`${generation}|${p.kind}|${p.s0}|${p.orig}`;return `<button type="button" class="mark-hint ${reviewedHints.has(key)?'reviewed':''}" data-part="${i}" data-s0="${p.s0}" data-kind="${esc(p.kind)}" aria-label="Проверить спорное место: ${esc(p.orig)}. ${esc(p.kind)}" title="${esc(p.kind)}">${esc(p.s)}</button>`;}
    return `<button type="button" class="${p.secret?'mark-secret':'mark-replacement'}" data-part="${i}" data-s0="${p.s0}" data-ph="${esc(p.s)}" aria-label="${p.secret?'Значение удалено безвозвратно':`Вернуть исходное значение для ${esc(p.s)}`}" title="${p.secret?'Удалено безвозвратно':'Щёлкните, чтобы вернуть это значение'}">${esc(p.s)}</button>`;
  }).join('');
  $('#output').value=outputText();
  $('#undoChips').innerHTML=[...restoredParts].map(i=>`<button class="undo-chip" data-undo="${i}" title="Отменить возврат значения и снова показать маркер">Отменить возврат ${esc(last.parts[i]?.s||'')}</button>`).join('');
  renderMirror(); renderStats(); updateReviewPosition();
}
function marks(){return [...$('#richOutput').querySelectorAll('.mark-replacement,.mark-secret,.mark-hint')];}
function hintMarks(){return [...$('#richOutput').querySelectorAll('.mark-hint:not(.reviewed)')];}
function scrollReviewMarkWithinOutput(mark){const rich=$('#richOutput'),box=rich.getBoundingClientRect(),target=mark.getBoundingClientRect();rich.scrollTop+=target.top-box.top-(rich.clientHeight-target.height)/2;}
function focusMark(i){setAnonymizedPreviewMode(false);const all=hintMarks();if(!all.length){reviewIndex=-1;updateReviewPosition();return;}reviewIndex=(i+all.length)%all.length;marks().forEach(x=>x.classList.remove('mark-current'));all[reviewIndex].classList.add('mark-current');const sourceOffset=Number(all[reviewIndex].dataset.s0||0);scrollReviewMarkWithinOutput(all[reviewIndex]);if(sourceOffset)$('#source').setSelectionRange(sourceOffset,sourceOffset);updateReviewPosition();}
function reviewDisabledReason(){if($('#paranoid').checked)return 'Ручная проверка отключена: включено «Автоматически скрывать спорное без подтверждения». Чтобы решать спорные места по одному, снимите «Автоматически скрывать спорное без подтверждения».';const hints=document.querySelector('.category[data-categories="HINTS"]');if(hints&&!hints.checked)return 'Ручная проверка отключена: выключено «Искать спорные места для ручной проверки». Спорные фрагменты останутся без изменения и не появятся в очереди.';return 'Спорных мест не найдено.';}
function updateReviewPosition(){const all=hintMarks();if(reviewIndex>=all.length)reviewIndex=all.length?0:-1;if(reviewIndex<0&&all.length)reviewIndex=all.length?0:-1;const hasCurrent=all.length>0&&reviewIndex>=0;const reviewed=[...reviewedHints].filter(k=>k.startsWith(generation+'|')).length,remaining=all.length,total=remaining+reviewed;const reason=reviewDisabledReason(),emptyProgress=reason.startsWith('Ручная проверка отключена:')?'Ручная проверка отключена':'Спорных мест нет';$('#reviewPos').textContent=total?`Осталось ${remaining} из ${total} · решено ${reviewed}`:emptyProgress;$('#reviewCurrent').textContent=hasCurrent?`Текущее спорное место: «${all[reviewIndex].textContent.trim()}» — ${all[reviewIndex].dataset.kind||'возможные чувствительные данные'}.`:reason;if(hasCurrent){const part=last.parts[Number(all[reviewIndex].dataset.part)],needle=(part?.orig||'').toLocaleLowerCase('ru-RU'),occurrences=(last.parts||[]).filter(p=>p.t==='hint'&&(p.orig||'').toLocaleLowerCase('ru-RU')===needle).length;$('#reviewMeta').textContent=`Найдено: ${occurrences} одинаковых вхождений · Категория: ${all[reviewIndex].dataset.kind||'не определена'} · Решение сохранится в наборе правил «${$('#profile').value||'Общий'}».`;}else $('#reviewMeta').textContent='';$('#reviewDecision').textContent=lastReviewDecision||(hasCurrent?'Выберите одно из двух решений ниже.':(reviewed?'Очередь разобрана. Все спорные места получили решение.':'Решение ещё не принято.'));$('#reviewPrev').disabled=!hasCurrent;$('#reviewNext').disabled=!hasCurrent;$('#hideCandidate').disabled=!hasCurrent;$('#keepCandidate').disabled=!hasCurrent;$('#reviewFinish').innerHTML=hasCurrent?'Разберите оставшиеся места. Для файлов после этого нажмите <b>«Применить настройки к файлу»</b>.':(reviewed?(filePreview?'Очередь разобрана. Нажмите <b>«Применить настройки к файлу»</b>, чтобы пересоздать экспортируемую копию.':'Очередь разобрана. Все решения уже применены к тексту.'):'После появления жёлтых мест разберите их здесь по одному.');$('#reviewFinish').classList.toggle('complete',!hasCurrent&&reviewed>0);if(lastReviewDecision&&!(last.warnings||[]).length)$('#warning').textContent=hasCurrent?`Осталось спорных мест: ${remaining}.`:'Ручная проверка завершена: все спорные места разобраны.';if(lastReviewDecision&&!hasCurrent)$('#resultStatus').textContent=filePreview?'Ручная проверка завершена. Теперь примените настройки к файлу.':'Ручная проверка завершена. Все решения применены к тексту.';}
function restoreReplacement(index){
  const p=last.parts[index]; if(!p||p.t!=='ph'||p.secret)return;
  restoredParts.add(index);addDecisionLine('#whitelist',p.orig);settingsGeneration++;if(filePreview)fileDirty=true;renderOutput();
}
function addDecisionLine(selector,value){const el=$(selector),lines=el.value.split('\n').filter(Boolean);if(!lines.includes(value)){lines.push(value);el.value=lines.join('\n');}}
function removeDecisionLine(selector,value){const el=$(selector);el.value=el.value.split('\n').filter(x=>x&&x!==value).join('\n');}
function currentHint(){const all=hintMarks(),el=all[reviewIndex];if(!el)return null;return {el,index:Number(el.dataset.part),part:last.parts[Number(el.dataset.part)]};}
function keepHint(){const h=currentHint();if(!h)return;reviewedHints.add(`${generation}|${h.part.kind}|${h.part.s0}|${h.part.orig}`);addDecisionLine('#whitelist',h.part.orig);settingsGeneration++;lastReviewDecision='Решение принято: фрагмент оставлен без изменения и добавлен в исключения текущих настроек.';if(filePreview)fileDirty=true;renderOutput();}
async function hideHint(){
  const h=currentHint();if(!h)return;
  const labels={'город':'ГОРОД','должность':'ДОЛЖНОСТЬ','спецкатегория ПДн':'СПЕЦКАТЕГОРИЯ','возможная фамилия':'ФИО','возможное ФИО':'ФИО','возможное имя заказчика':'ОРГАНИЗАЦИЯ','возможное имя собственное':'СКРЫТО'};
  const label=labels[h.part.kind]||'СКРЫТО',value=h.part.orig;
  const customCategory=$('.category[data-categories="CUSTOM"]');if(customCategory)customCategory.checked=true;
  removeDecisionLine('#whitelist',value);addDecisionLine('#rules',`${value} => ${label}`);settingsGeneration++;if(filePreview)fileDirty=true;
  const profileName=$('#profile').value||'Общий';
  try{
    const saved=await pywebview.api.save_profile($('#profile').value,$('#rules').value,$('#whitelist').value,$('#paranoid').checked);
    if(!saved?.ok)throw new Error(saved?.error||'Не удалось сохранить профиль');
  }catch(error){
    lastReviewDecision=`Правило добавлено в текущие настройки, но не сохранено в профиле «${profileName}»: ${error}`;
    updateReviewPosition();return;
  }
  await anonymizeText();
  lastReviewDecision=`Решение принято: Все одинаковые вхождения «${value}» заменены маркером; правило сохранено в профиле «${profileName}».`;
  updateReviewPosition();
}
async function anonymizeText(){
  const text=$('#source').value;if(!text){clearResult();return;}
  const ticket=++generation;
  const settings=[$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked];
  const needsFormattedPreview=filePreview&&selected&&currentPreviewFormat==='docx';
  let formatted=null;
  if(needsFormattedPreview){
    $('#showAnonymizedFormatted').disabled=true;
    $('#anonymizedPreviewControls').hidden=false;
    $('#anonymizedPreviewCompleteness').textContent='Сначала обновляю текстовый предпросмотр; форматированный вид будет готов следом…';
    setAnonymizedPreviewMode(false);
    formatted=pywebview.api.preview_anonymized_document(selected,...settings,$('#redactDocxGraphics').checked);
  }
  const result=await pywebview.api.anonymize_text(text,...settings);
  if(ticket!==generation)return;
  last=result;if(Object.keys(last.mapping||{}).length)textRestoreMapping={...last.mapping};lastReviewDecision='';restoredParts.clear();reviewIndex=0;showMapping(last.mapping);renderOutput();renderWarnings();
  $('#settingsStatus').textContent=fileDirty
    ?'Предпросмотр обновлён. Экспортируемый файл пока использует прежние настройки — нажмите «Применить настройки к файлу».'
    :'Предпросмотр обновлён.';
  if(needsFormattedPreview){
    let formattedPreview=null;
    try{formattedPreview=await formatted;}catch(error){formattedPreview={error:String(error)}}
    if(ticket!==generation)return;
    $('#showAnonymizedFormatted').disabled=false;
    if(formattedPreview?.format==='docx'){
      const rich=$('#anonymizedDocxPreview');rich.innerHTML=formattedPreview.rich_html||'';resetAnonymizedPreviewScroll();$('#anonymizedPreviewCompleteness').textContent=`Форматированный вид готов · таблиц: ${rich.querySelectorAll('.docx-table').length}. Текстовый предпросмотр уже соответствует выбранным галочкам.`;setAnonymizedPreviewMode(false);
    }else{
      leaveAnonymizedPreview();
      if(formattedPreview?.error)$('#anonymizedPreviewCompleteness').textContent=`Форматированный предпросмотр недоступен: ${formattedPreview.error}`;
    }
  }else leaveAnonymizedPreview();
  if(!filePreview)updatePrimaryAction();
}
function scheduleAnonymize(){clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>anonymizeText(),320);renderMirror();}
function clearResult(){generation++;last={mapping:{},candidates:[],counts:{},parts:[],total:0,hintCount:0,warnings:[]};textRestoreMapping={};restoredParts.clear();reviewedHints.clear();showMapping({});renderOutput();renderWarnings();}
async function anonymizeSelected(){
  if(filePreview&&selected){
    const current=selected,ticket=++generation,settingsVersion=settingsGeneration,button=$('#anonymize');
    button.disabled=true;button.textContent='Применяю настройки…';$('#fileLifecycleStatus').textContent='Обрабатывается файл… исходный файл не изменяется';$('#settingsStatus').textContent='Создаю экспортируемый файл с выбранными настройками. Большой документ Office может обрабатываться несколько минут…';$('#fileStatus').textContent='Обезличивание документа…';
    try{
      const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked,$('#redactDocxGraphics').checked);
      if(current!==selected)return;
      if(settingsVersion!==settingsGeneration){
        if(ticket===generation)await anonymizeText();
        if(current!==selected)return;
        fileDirty=true;$('#fileStatus').textContent=`${r.status}. Файл создан с предыдущими настройками и не готов к экспорту.`;$('#settingsStatus').textContent='Изменения настроек ещё не применены к экспортируемому файлу. Проверьте обновлённый предпросмотр и нажмите «Применить настройки к файлу».';return;
      }
      if(ticket!==generation)return;
      fileDirty=false;showMapping(r.mapping||last.mapping);last.warnings=r.warnings||[];last.total=r.replacement_count||last.total;last.hintCount=r.candidate_count||0;renderStats();renderWarnings();
      await anonymizeText();
      if(current!==selected)return;
      const refreshedGeneration=generation;
      setAnonymizedPreviewMode(false);$('#richOutput').scrollTop=0;
      $('#fileStatus').textContent=`${r.status}. Обезличенный файл готов к скачиванию.`;const documents=await pywebview.api.list_documents();if(refreshedGeneration!==generation||current!==selected)return;showLibrary(documents);selected=current;$('#library').value=current;$('#settingsStatus').textContent='Настройки применены. Файл готов к экспорту. Предпросмотр обновлён.';return;
    }catch(error){
      if(current===selected)$('#fileStatus').textContent=`Ошибка обезличивания: ${error?.message||error}`;
      throw error;
    }finally{
      if(current===selected)updatePrimaryAction(true);
    }
  }
  if($('#source').value.trim())return anonymizeText();
  if(!selected)return alert('Введите текст или импортируйте файл.');
  const current=selected,ticket=++generation;const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked,$('#redactDocxGraphics').checked);
  if(ticket!==generation||current!==selected)return;
  last={mapping:r.mapping||{},candidates:r.candidates||[],counts:{},parts:[],total:r.replacement_count||0,hintCount:r.candidate_count||0,warnings:r.warnings||[]};if(Object.keys(last.mapping).length)textRestoreMapping={...last.mapping};showMapping(last.mapping);renderStats();renderWarnings();
  $('#fileStatus').textContent=`${r.ready?'Готов':'Требуется ручная проверка'}. Обезличенный файл готов к скачиванию.`;const documents=await pywebview.api.list_documents();if(ticket!==generation||current!==selected)return;showLibrary(documents);
}

$('#source').addEventListener('input',()=>{if(!loadingPreview){filePreview=false;fileDirty=false;leaveDocumentPreview();}updatePrimaryAction();scheduleAnonymize();});$('#anonymize').onclick=anonymizeSelected;
$('#showFormatted').onclick=()=>setDocxPreviewMode(true);$('#showTextPreview').onclick=()=>setDocxPreviewMode(false);$('#previewTop').onclick=()=>{cancelDocxPreviewScrollReset();$('#docxPreview').scrollTop=0;};$('#previewBottom').onclick=()=>{cancelDocxPreviewScrollReset();const rich=$('#docxPreview');rich.scrollTop=rich.scrollHeight;};$('#previewFullscreen').onclick=()=>setPreviewFullscreen(!previewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#docxPreview').addEventListener(name,cancelDocxPreviewScrollReset));
$('#showAnonymizedFormatted').onclick=()=>setAnonymizedPreviewMode(true);$('#showAnonymizedText').onclick=()=>setAnonymizedPreviewMode(false);$('#anonymizedPreviewTop').onclick=()=>{cancelAnonymizedPreviewScrollReset();$('#anonymizedDocxPreview').scrollTop=0;};$('#anonymizedPreviewBottom').onclick=()=>{cancelAnonymizedPreviewScrollReset();const rich=$('#anonymizedDocxPreview');rich.scrollTop=rich.scrollHeight;};$('#anonymizedPreviewFullscreen').onclick=()=>setAnonymizedPreviewFullscreen(!anonymizedPreviewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#anonymizedDocxPreview').addEventListener(name,cancelAnonymizedPreviewScrollReset));
$('#richOutput').onclick=e=>{const mark=e.target.closest('.mark-replacement,.mark-secret,.mark-hint');if(!mark)return;const i=Number(mark.dataset.part);if(mark.classList.contains('mark-hint'))focusMark(hintMarks().indexOf(mark));if(mark.classList.contains('mark-replacement'))restoreReplacement(i);};
$('#undoChips').onclick=e=>{const b=e.target.closest('[data-undo]');if(b){const i=Number(b.dataset.undo);removeDecisionLine('#whitelist',last.parts[i]?.orig||'');restoredParts.delete(i);settingsGeneration++;if(filePreview)fileDirty=true;renderOutput();}};
$('#reviewPrev').onclick=()=>focusMark(reviewIndex-1);$('#reviewNext').onclick=()=>focusMark(reviewIndex+1);$('#hideCandidate').onclick=hideHint;$('#keepCandidate').onclick=keepHint;
$('#choose').onclick=async()=>{const ticket=++importGeneration;generation++;const r=await pywebview.api.choose_files();if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent=`Ошибка: ${(r.errors||[]).map(x=>x.error).join(', ')}`;};$('#dropChoose').onclick=$('#choose').onclick;
$('#deleteDoc').onclick=async()=>{if(selected&&confirm('Удалить запись и файлы приложения? Исходный файл пользователя сохранится.')){const r=await pywebview.api.delete_document(selected);$('#source').value='';filePreview=false;fileDirty=false;leaveDocumentPreview();clearResult();showLibrary(r.documents);}};
$('#downloadAnon').onclick=async()=>{if(!selected)return alert('Сначала выберите готовый документ.');const status=documentsById[selected]?.status;if(status==='Экспорт запрещён')return alert('Экспорт запрещён из-за критического предупреждения.');if(!['Готов','Требуется ручная проверка'].includes(status))return alert('Сначала обезличьте выбранный документ.');if(fileDirty)return alert('Сначала повторно обезличьте документ: решения предпросмотра ещё не применены к файлу.');let confirmation=false;if(status==='Требуется ручная проверка'){if(!confirm('Документ имеет предупреждения. Вы подтверждаете ручную проверку и хотите экспортировать?'))return;confirmation=true;}const r=await pywebview.api.export_anonymized(selected,confirmation);if(r.ok)$('#fileStatus').textContent=`Сохранена пара: ${r.path} + ${r.recovery_path}`;};
$('#downloadAll').onclick=async()=>{if(fileDirty)return alert('Сначала примените импортированные настройки к выбранному файлу. Экспорт ZIP остановлен.');const r=await pywebview.api.export_all_anonymized();if(r.ok)$('#fileStatus').textContent=`ZIP экспортирован без таблиц соответствий: ${r.path}`;};
async function chooseRestorePair(){const ticket=++restoreGeneration;$('#restoreFile').disabled=true;$('#restoreRecordName').textContent='Проверяем пару…';try{const r=await pywebview.api.choose_restore_pair();if(ticket!==restoreGeneration)return;if(!r.ok){$('#restoreRecordName').textContent='Пара пока не выбрана.';$('#restoreStatus').textContent='Выбор отменён.';return;}$('#restoreRecordName').textContent=`Пара найдена: ${r.anonymized_name} + ${r.recovery_name}`;$('#restoreStatus').textContent='Пара подтверждена по внутреннему идентификатору. Можно восстанавливать.';$('#restoreFile').disabled=false;}catch(error){if(ticket!==restoreGeneration)return;$('#restoreRecordName').textContent='Подходящая пара не найдена.';$('#restoreStatus').textContent=String(error?.message||error);}}
async function restoreMatchedFile(){if($('#restoreFile').disabled)return;$('#restoreStatus').textContent='Выберите место для восстановленного файла.';const r=await pywebview.api.restore_matched_file();if(r.ok){const message=`Готово. Восстановленный файл сохранён: ${r.path}; неизвестных маркеров: ${r.unknown_markers.length}`;$('#restoreStatus').textContent=message;$('#fileStatus').textContent=message;}else $('#restoreStatus').textContent='Восстановление отменено. Исходные файлы не изменены.';}
$('#chooseRestoreFile').onclick=chooseRestorePair;
$('#restoreFile').onclick=restoreMatchedFile;
$('#clear').onclick=()=>{if($('#source').value.trim()&&!confirm('Очистить введённый текст и текущий результат?'))return;filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='';clearResult();};
$('#sample').onclick=()=>{filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='Подрядчик «строй-гарант плюс» обслуживает АС «Паутина». login admin_db; старый qwerty123. Версия 1.7.5.16, SLA 99,9%, НДС 20%, порт 8080.';scheduleAnonymize();};
$('#paste').onclick=async()=>{const r=await pywebview.api.read_clipboard_text();filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value=r.text||'';scheduleAnonymize();};
$('#copy').onclick=()=>navigator.clipboard.writeText(outputText());
$('#restore').onclick=async()=>{clearTimeout(debounceTimer);const source=$('#source');if(!source.value.trim())return alert('Вставьте текст с маркерами в поле «Исходный текст».');if(!Object.keys(textRestoreMapping).length)return alert('Нет данных для обратной замены. Сначала обезличьте исходный текст.');const ticket=++generation;const result=await pywebview.api.restore_text($('#source').value,textRestoreMapping);if(ticket!==generation)return;$('#source').value=result.text;filePreview=false;fileDirty=false;leaveDocumentPreview();updatePrimaryAction();scheduleAnonymize();};
$('#selftest').onclick=async()=>{$('#testResult').textContent=(await pywebview.api.engine_self_test()).ok?' Движок исправен':' Ошибка проверки';};
$('#help').onclick=()=>alert('Все правила выполняются локально. Синие маркеры обратимы по текущей таблице, серые секреты удалены без исходных значений, жёлтые фрагменты требуют решения. Таблица и исходные значения в справку не включаются.');
$('#themeToggle').onclick=async()=>{const theme=document.documentElement?.dataset?.theme==='dark'?'light':'dark';applyTheme(theme,true);await pywebview.api.set_theme(theme);};
$('#designMode').onchange=async e=>await applyDesignMode(e.target.value,true);
$('#applyNow').onclick=()=>$('#anonymize').click();
$('#exportNow').onclick=()=>$('#downloadAnon').click();
$('#mono').onchange=e=>document.querySelectorAll('textarea,.mirror,.rich-output').forEach(x=>x.classList.toggle('mono',e.target.checked));
async function refreshProfiles(select){const names=await pywebview.api.list_profiles();$('#profile').innerHTML=names.map(x=>`<option>${esc(x)}</option>`).join('');if(select)$('#profile').value=select;}
async function loadProfileIntoEditor(name){const p=await pywebview.api.load_profile(name);$('#rules').value=Object.entries(p.dictionary).map(([k,v])=>`${k} => ${v}`).join('\n');$('#whitelist').value=p.whitelist.join('\n');$('#paranoid').checked=p.paranoid;markSettingsDirty();}
$('#profile').onchange=()=>loadProfileIntoEditor($('#profile').value);
$('#newProfile').onclick=async()=>{const n=prompt('Название профиля');if(n){await pywebview.api.save_profile(n,$('#rules').value,$('#whitelist').value,$('#paranoid').checked);await refreshProfiles(n);$('#settingsStatus').textContent=`Профиль «${n}» сохранён.`;}};
$('#deleteProfile').onclick=async()=>{const n=$('#profile').value;if(n!=='Общий'&&confirm(`Удалить профиль «${n}»?`)){await pywebview.api.delete_profile(n);await refreshProfiles('Общий');await loadProfileIntoEditor('Общий');}};
$('#exportProfile').onclick=async()=>{const n=$('#profile').value;try{const r=await pywebview.api.export_profile(n,$('#rules').value,$('#whitelist').value,$('#paranoid').checked);if(r.ok)$('#settingsStatus').textContent=`Профиль «${n}» экспортирован.`;else $('#settingsStatus').textContent=r.error||'Экспорт профиля отменён.';}catch(e){$('#settingsStatus').textContent='Не удалось экспортировать профиль. Проверьте правила и выбранный файл.';}};
$('#importProfile').onclick=async()=>{try{const r=await pywebview.api.import_profile();if(r.ok){await refreshProfiles(r.name);await loadProfileIntoEditor(r.name);$('#settingsStatus').textContent=fileDirty?`Профиль «${r.name}» импортирован и загружен. Примените настройки к файлу перед экспортом.`:`Профиль «${r.name}» импортирован и загружен.`;}else if(r.error){$('#settingsStatus').textContent=r.error;}}catch(e){$('#settingsStatus').textContent='Не удалось импортировать профиль.';}};
function markSettingsDirty(){settingsGeneration++;if(filePreview){fileDirty=true;$('#settingsStatus').textContent='Изменения настроек ещё не применены к экспортируемому файлу. Проверьте обновлённый предпросмотр и нажмите «Применить настройки к файлу».';}updatePrimaryAction();scheduleAnonymize();}
['#rules','#whitelist','#paranoid','#redactDocxGraphics'].forEach(s=>$(s).addEventListener('input',markSettingsDirty));
$('#compactMarkers').addEventListener('input',()=>{updateCategoryMarkerExamples();markSettingsDirty();});
document.querySelectorAll('.category').forEach(x=>x.addEventListener('change',markSettingsDirty));
let syncing=false;$('#source').addEventListener('scroll',()=>{if(syncing)return;syncing=true;$('#sourceMirror').scrollTop=$('#source').scrollTop;const max=$('#source').scrollHeight-$('#source').clientHeight;$('#richOutput').scrollTop=max?$('#source').scrollTop/max*($('#richOutput').scrollHeight-$('#richOutput').clientHeight):0;syncing=false;});$('#richOutput').addEventListener('scroll',()=>{if(syncing)return;syncing=true;const max=$('#richOutput').scrollHeight-$('#richOutput').clientHeight;$('#source').scrollTop=max?$('#richOutput').scrollTop/max*($('#source').scrollHeight-$('#source').clientHeight):0;$('#sourceMirror').scrollTop=$('#source').scrollTop;syncing=false;});
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();$('#copy').click();}if(e.key==='Escape'){if(previewFullscreen){setPreviewFullscreen(false);return;}if(anonymizedPreviewFullscreen){setAnonymizedPreviewFullscreen(false);}}});
['dragenter','dragover'].forEach(n=>document.addEventListener(n,e=>e.preventDefault()));document.addEventListener('drop',async e=>{e.preventDefault();const paths=[...e.dataTransfer.files].map(f=>f.path).filter(Boolean);if(paths.length){const ticket=++importGeneration;generation++;const r=await pywebview.api.import_paths(paths);if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent='Ошибка импорта';}});
window.addEventListener('pywebviewready',async()=>{const savedDesign=await pywebview.api.get_design_mode();await applyDesignMode(savedDesign||localStorage.getItem(DESIGN_KEY)||'new');$('#detectionCategories').open=false;const savedTheme=await pywebview.api.get_theme();if(savedTheme)applyTheme(savedTheme);updateCategoryMarkerExamples();showLibrary(await pywebview.api.list_documents());await refreshProfiles('Общий');await loadProfileIntoEditor('Общий');if(selected)await loadDocumentPreview();else{renderOutput();updatePrimaryAction();}});

$('#languageMode').onchange=async e=>{const value=e.target.value;await pywebview.api.set_language(value);window.location.href=value==='ru'?'index-v1.8.18.html':'index-en-v1.8.18.html';};
