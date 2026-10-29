const $ = s => document.querySelector(s);
const APP_VERSION='1.8';
const THEME_KEY='local-anonymizer-theme';
const UNCERTAIN_MODES=new Set(['off','review','auto']);
function normalizeUncertainMode(mode,paranoid=false,reviewHints=true){return UNCERTAIN_MODES.has(mode)?mode:(paranoid?'auto':(reviewHints?'review':'off'));}
function applyUncertainMode(mode){const normalized=normalizeUncertainMode(mode);$('#uncertainMode').value=normalized;$('#reviewHints').checked=normalized!=='off';$('#reviewHintsMode').checked=normalized==='review';$('#paranoid').checked=normalized==='auto';return normalized;}
function syncUncertainModeFromCheckboxes(){return applyUncertainMode($('#paranoid').checked?'auto':($('#reviewHintsMode').checked?'review':'off'));}
async function applyCurrentDesign(){document.body.dataset.design='new';$('#detectionCategories').open=false;try{localStorage.setItem('designMode','new');}catch(_error){}try{await pywebview.api.set_design_mode('new')}catch(_error){}}
function preferredTheme(){
  try{const saved=localStorage.getItem(THEME_KEY);if(saved==='light'||saved==='dark')return saved;}catch(_error){}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches?'dark':'light';
}
function applyTheme(theme,persist=false){
  const selected=theme==='dark'?'dark':'light';
  if(document.documentElement)document.documentElement.dataset.theme=selected;
  const button=$('#themeToggle');
  if(button){button.setAttribute?.('aria-pressed',String(selected==='dark'));button.textContent=selected==='dark'?'☀️ Light theme':'🌙 Dark theme';}
  if(persist){try{localStorage.setItem(THEME_KEY,selected);}catch(_error){}}
}
applyTheme(preferredTheme());
function initSettingsTabs(){
  const tabs=[...document.querySelectorAll('.settings-nav [role="tab"]')];
  const select=tab=>{
    tabs.forEach(item=>{const active=item===tab;item.setAttribute('aria-selected',String(active));item.tabIndex=active?0:-1;const panel=document.getElementById(item.getAttribute('aria-controls'));if(panel)panel.hidden=!active;});
  };
  tabs.forEach((tab,index)=>{
    tab.addEventListener('click',()=>select(tab));
    tab.addEventListener('keydown',event=>{let next=index;if(event.key==='ArrowDown'||event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowUp'||event.key==='ArrowLeft')next=(index-1+tabs.length)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();select(tabs[next]);tabs[next].focus();});
  });
  const selected=tabs.find(tab=>tab.getAttribute('aria-selected')==='true')||tabs[0];if(selected)select(selected);
}
initSettingsTabs();
let last = {mapping:{}, candidates:[], counts:{}, parts:[], total:0, hintCount:0, warnings:[]};
let textRestoreMapping = {};
let selected = '', reviewIndex = -1, debounceTimer = 0, generation = 0, previewGeneration = 0, settingsGeneration = 0, importGeneration = 0, restoreGeneration = 0, lastEscape = 0;
let filePreview = false, fileDirty = false, loadingPreview = false, documentsById = {}, currentPreviewFormat = '';
let previewFullscreen = false, fullscreenReturnFocus = null;
let previousInert = new Map();
let previewScrollResetToken = 0;
let anonymizedPreviewFullscreen = false;
let anonymizedPreviewScrollResetToken = 0;
let lastReviewDecision = '';
let reviewFocusFrame = null;
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
function warningText(w){
  if(typeof w==='string')return w.startsWith('Требуется ручная проверка: ')?`Manual review required: ${w.slice('Требуется ручная проверка: '.length)}`:w;
  const message=w?.message||w?.msg||String(w),localized=({
    'ГОСТАЙНА':'A secrecy classification was detected. This is an expected anonymization case and does not block export; review the anonymized result.',
    'ДСП':'An official-use-only or confidentiality marking was detected. This is an expected anonymization case and does not block export; review the anonymized result.',
    'КИИ':'Critical information infrastructure is mentioned; recheck system objects and identifiers.',
    'ЗАКУПКИ':'OKPD2/KTRU data was found; check the code, description, quantity, and customer together.',
    'МАССИВ-ПДН':'The document may contain a personal-data collection; manual review is required.',
    'XLSX_FORMULA_BLOCKED':'A dangerous formula was neutralized.',
    'XLSX_HYPERLINK':'Hyperlink targets were removed; manual review is required.',
    'XLSX_HEADER_FOOTER':'Headers and footers were cleared; manual review is required.',
    'XLSX_DATA_VALIDATION':'Data-validation messages were cleared; manual review is required.',
    'XLSX_DEFINED_NAME':'Named ranges were removed; manual review is required.',
    'XLSX_EXTERNAL_LINK':'An external link was removed; manual XLSX review is required.',
    'XLSX_UNSUPPORTED_PART':'Manual XLSX review is required.',
    'UNSUPPORTED_OFFICE_CONTENT':'Unsupported Office content was found. Export is blocked.'
  })[w?.kind];
  if(!localized)return message;
  const detail=message.includes(': ')?message.slice(message.indexOf(': ')+2).replace(/\. Экспорт запрещён\.$/,''):'';
  return detail&&['XLSX_FORMULA_BLOCKED','XLSX_UNSUPPORTED_PART','UNSUPPORTED_OFFICE_CONTENT'].includes(w.kind)?`${localized} ${detail}`:localized;
}
function documentStatusText(status){return ({'Импортирован':'Imported','Преобразован из DOC':'Converted from DOC','Готов':'Ready','Требуется ручная проверка':'Manual review required','Экспорт запрещён':'Export blocked','Ошибка':'Error'})[status]||(status?'Unknown status':'');}
function profileDisplayName(name){return name==='Общий'?'General':name;}
function profileErrorText(operation){return operation==='export'?'Could not export the profile. Check its name and rules, then try again.':'Could not import the profile. Check that it is a valid UTF-8 JSON profile file.';}
function bridgeErrorText(operation){return ({
  'profile-save':'Could not save the profile. The rule remains in the current settings.',
  'formatted-preview':'Formatted preview is unavailable. Use the text preview and review the exported file.',
  'anonymize':'Could not anonymize the document. The source file was not changed.',
  'import':'Could not import the selected file. Check that its format is supported and try again.',
  'restore':'Could not verify or restore this file pair. Check that both matching files are valid.'
})[operation]||'The operation could not be completed.';}
function hintKindText(kind){return ({'город':'city','должность':'job title','спецкатегория ПДн':'special category of personal data','возможная фамилия':'possible surname','возможное ФИО':'possible full name','возможное имя заказчика':'possible customer name','возможное имя собственное':'possible proper name'})[kind]||kind;}
const compactMarkerLabels={ФИО:'Ф',ОРГАНИЗАЦИЯ:'ОРГ',ПОЧТА:'ПЧ',ТЕЛЕФОН:'ТЕЛ',АККАУНТ:'АКК',ЛОГИН:'ЛОГ',ДОМЕН:'ДОМ',ПОРТ:'ПРТ',УЗЕЛ:'УЗЛ','СТРУКТУРА-AD':'AD',ДИСК:'ДСК',ПУТЬ:'ПУТЬ',ПРОГРАММА:'ПО',СОКРАЩЕНИЯ:'СОКР',СКРИПТЫ:'СКРП',ССЫЛКА:'URL',СИСТЕМА:'СИС',ПРОИЗВОДИТЕЛЬ:'ПРЗ',ДОЛЖНОСТЬ:'ДОЛЖ',ГОРОД:'ГОР',АДРЕС:'АДР',ИНДЕКС:'ИНД',СПЕЦКАТЕГОРИЯ:'СПЕЦ',СКРЫТО:'СКР','ДАТА-РОЖДЕНИЯ':'ДР',ТАБЕЛЬНЫЙ:'ТАБ',ГОСНОМЕР:'ГРЗ',ДОГОВОР:'ДОГ',ДОКУМЕНТ:'ДОК',СУММА:'СУМ',СТАВКА:'СТВ'};
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
  if(!documents.length){list.innerHTML='<option>No documents imported</option>';selected='';updateRestoreContext();return;}
  documents.forEach(d=>{const o=document.createElement('option');o.value=d.id;o.textContent=`${d.display_name} — ${documentStatusText(d.status)}`;list.appendChild(o);});
  if(previous&&documentsById[previous])list.value=previous;
  selected=list.value;updateRestoreContext();list.onchange=async()=>{selected=list.value;updateRestoreContext();await loadDocumentPreview();};
}
function updateRestoreContext(){}
function hasFormattedDocumentPreview(format){return format==='docx'||format==='odt';}
let previewScrollSyncDepth=0;
let lastPreviewScrollSource=null;
let reviewScrollSyncLocked=false,reviewScrollUnlockFrame=null;
const previewAnchorCache=new WeakMap(),programmaticPreviewScrollTargets=new WeakMap();
function holdReviewScrollSync(){reviewScrollSyncLocked=true;if(reviewScrollUnlockFrame!==null)cancelAnimationFrame(reviewScrollUnlockFrame);reviewScrollUnlockFrame=requestAnimationFrame(()=>{reviewScrollUnlockFrame=requestAnimationFrame(()=>{reviewScrollUnlockFrame=null;reviewScrollSyncLocked=false;});});}
function invalidatePreviewAnchors(container){previewAnchorCache.delete(container);}
function collectPreviewAnchorModel(container){
  const cached=previewAnchorCache.get(container);
  if(cached&&cached.scrollHeight===container.scrollHeight&&cached.clientHeight===container.clientHeight)return cached.model;
  const max=Math.max(0,container.scrollHeight-container.clientHeight);
  if(typeof container.getBoundingClientRect!=='function'){
    const model={offsets:max?[0,max]:[0],keyed:[],byKey:new Map()};
    previewAnchorCache.set(container,{scrollHeight:container.scrollHeight,clientHeight:container.clientHeight,model});return model;
  }
  const bounds=container.getBoundingClientRect(),points=[];
  container.querySelectorAll('.docx-paragraph,li,tr').forEach((node,index)=>{
    const offset=Math.max(0,Math.min(max,node.getBoundingClientRect().top-bounds.top+container.scrollTop));
    points.push({offset,key:String(node.dataset?.previewAnchor||''),index});
  });
  points.sort((left,right)=>left.offset-right.offset||left.index-right.index);
  const keyed=points.filter(point=>point.key),byKey=new Map();
  keyed.forEach(point=>{if(!byKey.has(point.key))byKey.set(point.key,point.offset);});
  const model={offsets:[0,...points.map(point=>point.offset),max],keyed,byKey};
  previewAnchorCache.set(container,{scrollHeight:container.scrollHeight,clientHeight:container.clientHeight,model});
  return model;
}
function collectPreviewAnchors(container){return collectPreviewAnchorModel(container).offsets;}
function proportionalPreviewScroll(source,target){
  const sourceMax=Math.max(0,source.scrollHeight-source.clientHeight),targetMax=Math.max(0,target.scrollHeight-target.clientHeight);
  return sourceMax?source.scrollTop/sourceMax*targetMax:0;
}
function previewScrollPosition(source){
  const sourceMax=Math.max(0,source.scrollHeight-source.clientHeight),ratio=sourceMax?Math.max(0,Math.min(1,source.scrollTop/sourceMax)):0;
  const model=collectPreviewAnchorModel(source),anchors=model.offsets;
  if(anchors.length<2)return{ratio,anchorCount:0,logical:ratio,sourceOffset:source.scrollTop,sourceMax,keyedAnchors:model.keyed};
  let low=0,high=anchors.length-1;
  while(low+1<high){const middle=Math.floor((low+high)/2);if(anchors[middle]<=source.scrollTop)low=middle;else high=middle;}
  const start=anchors[low],end=anchors[Math.min(low+1,anchors.length-1)],fraction=end>start?(source.scrollTop-start)/(end-start):0;
  return{ratio,anchorCount:anchors.length,logical:(low+fraction)/(anchors.length-1),sourceOffset:source.scrollTop,sourceMax,keyedAnchors:model.keyed};
}
function previewScrollForPosition(position,target){
  const targetMax=Math.max(0,target.scrollHeight-target.clientHeight),model=collectPreviewAnchorModel(target),anchors=model.offsets;
  if(position.keyedAnchors?.length&&model.byKey.size){
    const pairs=[{sourceOffset:0,targetOffset:0},...position.keyedAnchors.filter(point=>model.byKey.has(point.key)).map(point=>({sourceOffset:point.offset,targetOffset:model.byKey.get(point.key)})),{sourceOffset:position.sourceMax,targetOffset:targetMax}]
      .sort((left,right)=>left.sourceOffset-right.sourceOffset||left.targetOffset-right.targetOffset);
    const monotonic=[];
    pairs.forEach(pair=>{
      const previous=monotonic[monotonic.length-1];
      if(previous&&pair.sourceOffset===previous.sourceOffset){if(pair.targetOffset>previous.targetOffset)monotonic[monotonic.length-1]=pair;return;}
      if(!previous||pair.targetOffset>=previous.targetOffset)monotonic.push(pair);
    });
    if(monotonic.length>1){
      const sourceOffset=Math.max(0,Math.min(position.sourceMax,position.sourceOffset));
      let high=monotonic.findIndex(pair=>pair.sourceOffset>=sourceOffset);if(high<0)high=monotonic.length-1;
      const low=Math.max(0,high-1),start=monotonic[low],end=monotonic[high];
      const fraction=end.sourceOffset>start.sourceOffset?(sourceOffset-start.sourceOffset)/(end.sourceOffset-start.sourceOffset):0;
      return start.targetOffset+(end.targetOffset-start.targetOffset)*fraction;
    }
  }
  if(position.anchorCount<2||anchors.length!==position.anchorCount)return position.ratio*targetMax;
  const targetPosition=Math.max(0,Math.min(anchors.length-1,position.logical*(anchors.length-1)));
  const index=Math.min(Math.floor(targetPosition),anchors.length-2),fraction=targetPosition-index;
  return anchors[index]+(anchors[index+1]-anchors[index])*fraction;
}
function mapPreviewScroll(source,target){return previewScrollForPosition(previewScrollPosition(source),target);}
function restorePreviewPosition(position,target){
  if(!target||target.hidden||!target.clientHeight)return;
  programmaticPreviewScrollTargets.set(target,previewScrollForPosition(position,target));
  target.scrollTop=programmaticPreviewScrollTargets.get(target);
}
function refreshPreviewLayout(source,target){
  if(reviewScrollSyncLocked)return;
  if(typeof hintMarks==='function'&&hintMarks().length&&(!$('#docxPreview').hidden||!$('#anonymizedDocxPreview').hidden)){refreshFormattedReviewFocus();return;}
  invalidatePreviewAnchors(source);invalidatePreviewAnchors(target);
  if(!source||!target||source.hidden||target.hidden||!source.clientHeight||!target.clientHeight)return;
  const leader=lastPreviewScrollSource===target?target:source,follower=leader===source?target:source;
  restorePreviewPosition(previewScrollPosition(leader),follower);
}
function syncPreviewScroll(source,target){
  if(reviewScrollSyncLocked){programmaticPreviewScrollTargets.delete(source);return;}
  const expected=programmaticPreviewScrollTargets.get(source);
  if(expected!==undefined){programmaticPreviewScrollTargets.delete(source);if(Math.abs(source.scrollTop-expected)<1)return;}
  if(previewScrollSyncDepth||!source||!target||source.hidden||target.hidden||!source.clientHeight||!target.clientHeight)return;
  lastPreviewScrollSource=source;
  previewScrollSyncDepth++;
  try{
    const mapped=mapPreviewScroll(source,target);
    programmaticPreviewScrollTargets.set(target,mapped);
    target.scrollTop=mapped;
  }finally{previewScrollSyncDepth--;}
}
const sourcePreviewAlignment=$('#sourcePreviewAlignment');
const outputPreviewAlignment=$('#outputPreviewAlignment');
const sourcePanelAlignment=$('#sourcePanelAlignment');
const outputPanelAlignment=$('#outputPanelAlignment');
const canAlignPreviewTops=sourcePreviewAlignment?.classList?.contains('preview-alignment-spacer')&&outputPreviewAlignment?.classList?.contains('preview-alignment-spacer')&&sourcePanelAlignment&&outputPanelAlignment;
function activeSourcePreview(){return $('#docxPreview').hidden?$('#source'):$('#docxPreview');}
function activeAnonymizedPreview(){return $('#anonymizedDocxPreview').hidden?$('#richOutput'):$('#anonymizedDocxPreview');}
let previewLayoutRefreshFrame=0;
function refreshActivePreviewLayout(){previewLayoutRefreshFrame=0;refreshPreviewLayout(activeSourcePreview(),activeAnonymizedPreview());}
function schedulePreviewLayoutRefresh(){
  if(previewLayoutRefreshFrame)return;
  const run=()=>{if(!previewLayoutRefreshFrame)return;refreshActivePreviewLayout();};
  previewLayoutRefreshFrame=typeof requestAnimationFrame==='function'?requestAnimationFrame(run):setTimeout(run,0);
}
const formattedPreviewContainers=[$('#docxPreview'),$('#anonymizedDocxPreview')];
formattedPreviewContainers.forEach(preview=>preview.addEventListener?.('load',event=>{if(String(event.target?.tagName||'').toUpperCase()==='IMG')schedulePreviewLayoutRefresh();},true));
const previewLayoutMutationObserver=typeof MutationObserver==='undefined'?null:new MutationObserver(schedulePreviewLayoutRefresh);
if(previewLayoutMutationObserver)formattedPreviewContainers.forEach(preview=>previewLayoutMutationObserver.observe(preview,{childList:true,subtree:true}));
window.addEventListener('resize',schedulePreviewLayoutRefresh);
if(document.fonts?.ready)document.fonts.ready.then(schedulePreviewLayoutRefresh);
function isPreviewActive(preview){return Boolean(preview&&!preview.hidden&&preview.clientWidth>0&&preview.clientHeight>0);}
let previewAlignmentFrame=0;
function syncPreviewTopAlignment(){
  if(!canAlignPreviewTops)return;
  sourcePreviewAlignment.style.height='0px';outputPreviewAlignment.style.height='0px';
  sourcePanelAlignment.style.height='0px';outputPanelAlignment.style.height='0px';
  if(previewFullscreen||anonymizedPreviewFullscreen)return;
  const sourcePreview=activeSourcePreview(),outputPreview=activeAnonymizedPreview();
  const sourcePane=sourcePreview.closest('.pane'),outputPane=outputPreview.closest('.pane');
  if(!sourcePane||!outputPane||Math.abs(sourcePane.getBoundingClientRect().top-outputPane.getBoundingClientRect().top)>2)return;
  if(!isPreviewActive(sourcePreview)||!isPreviewActive(outputPreview))return;
  const difference=sourcePreview.getBoundingClientRect().top-outputPreview.getBoundingClientRect().top;
  if(difference>0.5)outputPreviewAlignment.style.height=`${difference}px`;
  else if(difference<-.5)sourcePreviewAlignment.style.height=`${-difference}px`;
  const panelDifference=sourcePane.getBoundingClientRect().bottom-outputPane.getBoundingClientRect().bottom;
  if(panelDifference>0.5)outputPanelAlignment.style.height=`${panelDifference}px`;
  else if(panelDifference<-.5)sourcePanelAlignment.style.height=`${-panelDifference}px`;
}
function schedulePreviewTopAlignment(){
  if(previewAlignmentFrame)return;
  const run=()=>{if(!previewAlignmentFrame)return;previewAlignmentFrame=0;syncPreviewTopAlignment();};
  previewAlignmentFrame=requestAnimationFrame(run);
  if(typeof setTimeout==='function')setTimeout(run,100);
}
const previewAlignmentResizeObserver=!canAlignPreviewTops||typeof ResizeObserver==='undefined'?null:new ResizeObserver(schedulePreviewTopAlignment);
if(previewAlignmentResizeObserver){
  [$('#sourceLibrary'),$('#docxPreviewControls'),$('#anonymizedPreviewControls'),$('#source').closest('.pane'),$('#richOutput').closest('.pane'),$('#source').closest('.pane')?.querySelector('.bar'),$('#richOutput').closest('.pane')?.querySelector('.bar')].filter(Boolean).forEach(element=>previewAlignmentResizeObserver.observe(element));
}
const previewAlignmentMutationObserver=!canAlignPreviewTops||typeof MutationObserver==='undefined'?null:new MutationObserver(schedulePreviewTopAlignment);
if(previewAlignmentMutationObserver){
  [$('#sourceLibrary'),$('#docxPreviewControls'),$('#docxPreview'),$('#anonymizedPreviewControls'),$('#anonymizedDocxPreview'),$('#textPreview'),$('#richOutput')].filter(Boolean).forEach(element=>previewAlignmentMutationObserver.observe(element,{attributes:true,attributeFilter:['hidden','open','class']}));
}
if(canAlignPreviewTops){
  window.addEventListener('resize',schedulePreviewTopAlignment);
  if(document.fonts?.ready)document.fonts.ready.then(schedulePreviewTopAlignment);
  schedulePreviewTopAlignment();
}
function syncFormattedSourceScroll(){if($('#docxPreview').hidden)return;syncPreviewScroll($('#docxPreview'),activeAnonymizedPreview());}
function syncFormattedAnonymizedScroll(){if($('#anonymizedDocxPreview').hidden)return;syncPreviewScroll($('#anonymizedDocxPreview'),activeSourcePreview());}
function switchPreviewMode(setMode,formatted){
  const source=setMode===setDocxPreviewMode?activeSourcePreview():activeAnonymizedPreview(),position=previewScrollPosition(source);
  setMode(formatted);
  const target=setMode===setDocxPreviewMode?activeSourcePreview():activeAnonymizedPreview();
  if(target!==source)restorePreviewPosition(position,target);
}
function setDocxPreviewMode(formatted){
  const available=hasFormattedDocumentPreview(currentPreviewFormat);
  $('#docxPreviewControls').hidden=!available;
  $('#docxPreview').hidden=!(available&&formatted);
  $('#textPreview').hidden=available&&formatted;
  $('#showFormatted').ariaPressed=String(available&&formatted);
  $('#showTextPreview').ariaPressed=String(!available||!formatted);
}
function setSourcePreviewLoading(loading){
  ['#previewTop','#previewBottom','#previewFullscreen','#showFormatted'].forEach(selector=>{$(selector).disabled=loading;});
  $('#showTextPreview').disabled=false;
  if(loading&&hasFormattedDocumentPreview(currentPreviewFormat))setDocxPreviewMode(true);
}
function setModalIsolation(surface,enabled){if(enabled){previousInert=new Map();let child=surface,ancestor=surface.parentElement;while(ancestor){[...(ancestor.children||[])].forEach(sibling=>{if(sibling!==child&&!previousInert.has(sibling)){previousInert.set(sibling,!!sibling.inert);sibling.inert=true;}});if(ancestor===document.body)break;child=ancestor;ancestor=ancestor.parentElement;}}else{previousInert.forEach((value,element)=>{element.inert=value;});previousInert.clear();}}
function modalFocusables(surface){return [...surface.querySelectorAll('button:not([disabled]),select:not([disabled]),textarea:not([disabled]),[href],[tabindex]:not([tabindex="-1"])')].filter(el=>!el.hidden&&!el.inert);}
function trapModalFocus(event,surface){if(event.key!=='Tab')return;const items=modalFocusables(surface);if(!items.length){event.preventDefault();surface.focus();return;}const first=items[0],last=items[items.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
function setFullscreenSemantics(surface,button,enabled,label){if(enabled){fullscreenReturnFocus=document.activeElement;surface.setAttribute('role','dialog');surface.ariaModal='true';surface.setAttribute('aria-label',label);surface.tabIndex=-1;surface.onkeydown=event=>trapModalFocus(event,surface);setModalIsolation(surface,true);button.setAttribute('aria-pressed','true');button.focus();}else{setModalIsolation(surface,false);surface.removeAttribute('role');surface.removeAttribute('aria-modal');surface.removeAttribute('aria-label');surface.removeAttribute('tabindex');surface.onkeydown=null;button.setAttribute('aria-pressed','false');if(fullscreenReturnFocus){fullscreenReturnFocus.focus();fullscreenReturnFocus=null;}}}
function setPreviewFullscreen(enabled){if(enabled===previewFullscreen)return;previewFullscreen=enabled;const surface=$('#docxPreviewSurface'),button=$('#previewFullscreen');surface.classList.toggle('preview-surface-fullscreen',enabled);button.textContent=enabled?'Exit full screen':'Full screen';setFullscreenSemantics(surface,button,enabled,'Full-screen source document preview');schedulePreviewTopAlignment();}
function cancelDocxPreviewScrollReset(){previewScrollResetToken++;}
function resetDocxPreviewScroll(){const rich=$('#docxPreview'),token=++previewScrollResetToken,apply=()=>{if(token===previewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function setAnonymizedPreviewMode(formatted){const available=filePreview&&hasFormattedDocumentPreview(currentPreviewFormat)&&!!$('#anonymizedDocxPreview').innerHTML;$('#anonymizedPreviewControls').hidden=!available;$('#anonymizedDocxPreview').hidden=!(available&&formatted);$('#richOutput').hidden=available&&formatted;$('#showAnonymizedFormatted').ariaPressed=String(available&&formatted);$('#showAnonymizedText').ariaPressed=String(!available||!formatted);}
function setAnonymizedPreviewLoading(loading){['#anonymizedPreviewTop','#anonymizedPreviewBottom','#anonymizedPreviewFullscreen','#showAnonymizedFormatted'].forEach(selector=>{$(selector).disabled=loading;});$('#showAnonymizedText').disabled=false;if(loading)$('#anonymizedPreviewControls').hidden=false;}
function setAnonymizedPreviewFullscreen(enabled){if(enabled===anonymizedPreviewFullscreen)return;anonymizedPreviewFullscreen=enabled;const surface=$('#anonymizedPreviewSurface'),button=$('#anonymizedPreviewFullscreen');surface.classList.toggle('preview-surface-fullscreen',enabled);button.textContent=enabled?'Exit full screen':'Full screen';setFullscreenSemantics(surface,button,enabled,'Full-screen anonymized document preview');schedulePreviewTopAlignment();}
function cancelAnonymizedPreviewScrollReset(){anonymizedPreviewScrollResetToken++;}
function resetAnonymizedPreviewScroll(){const rich=$('#anonymizedDocxPreview'),token=++anonymizedPreviewScrollResetToken,apply=()=>{if(token===anonymizedPreviewScrollResetToken)rich.scrollTop=0;};apply();if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,150);}
function leaveAnonymizedPreview(){setAnonymizedPreviewFullscreen(false);const rich=$('#anonymizedDocxPreview');invalidatePreviewAnchors(rich);rich.innerHTML='';rich.hidden=true;$('#anonymizedPreviewCompleteness').textContent='';$('#anonymizedPreviewControls').hidden=true;$('#richOutput').hidden=false;}
function leaveDocumentPreview(){previewGeneration++;loadingPreview=false;setSourcePreviewLoading(false);setPreviewFullscreen(false);leaveAnonymizedPreview();currentPreviewFormat='';const rich=$('#docxPreview');invalidatePreviewAnchors(rich);rich.innerHTML='';$('#previewCompleteness').textContent='';setDocxPreviewMode(false);}
function updatePrimaryAction(keepStatus=false){
  const button=$('#anonymize'),status=$('#settingsStatus'),apply=$('#applyNow'),exportButton=$('#exportNow'),lifecycle=$('#fileLifecycleStatus');
  if(filePreview&&selected){const ready=['Готов','Требуется ручная проверка'].includes(documentsById[selected]?.status);button.disabled=false;button.textContent=fileDirty?'Apply settings to file':'Rebuild file with current settings';apply.disabled=false;exportButton.disabled=fileDirty||!ready;lifecycle.textContent=fileDirty?'Settings changed — reprocess the exportable file':ready?'File processed and ready to save':'Preview ready — apply settings to file';if(!fileDirty&&!keepStatus)status.textContent='The preview and exportable file use the current settings.';return;}
  button.disabled=true;apply.disabled=true;exportButton.disabled=true;button.textContent=$('#source').value.trim()?'Text is checked automatically':'Select a file first';lifecycle.textContent=$('#source').value.trim()?'Text preview updates automatically':'Select a document — processing stays on this computer';status.textContent=$('#source').value.trim()?'Settings apply automatically to pasted text. No separate action is needed.':'Select a file first. Changes apply automatically to pasted text.';
}
async function readDocumentPreviewChunks(token,field,length){let value='';let offset=0;while(offset<length){const result=await pywebview.api.read_document_preview_chunk(token,field,offset);if(result.next_offset<=offset)throw new Error('Invalid preview chunk');value+=result.chunk;offset=result.next_offset;}return value;}
async function requestDocumentPreview(documentId,onText){if(!pywebview.api.start_document_preview)return pywebview.api.preview_document(documentId);const manifest=await pywebview.api.start_document_preview(documentId);let text='';try{text=await readDocumentPreviewChunks(manifest.token,'text',manifest.text_length);if(onText)onText({...manifest,text,rich_html:''});}finally{await pywebview.api.finish_document_preview(manifest.token);}if(!pywebview.api.start_formatted_document_preview)return{...manifest,text,rich_html:''};const formatted=await pywebview.api.start_formatted_document_preview(documentId);try{const rich=await readDocumentPreviewChunks(formatted.token,'rich_html',formatted.rich_html_length);return{...manifest,...formatted,text,rich_html:rich};}finally{await pywebview.api.finish_document_preview(formatted.token);}}
async function requestAnonymizedDocumentPreview(documentId,...settings){if(!pywebview.api.start_anonymized_document_preview)return pywebview.api.preview_anonymized_document(documentId,...settings);const manifest=await pywebview.api.start_anonymized_document_preview(documentId,...settings);try{const rich=await readDocumentPreviewChunks(manifest.token,'rich_html',manifest.rich_html_length);return{...manifest,rich_html:rich};}finally{await pywebview.api.finish_document_preview(manifest.token);}}
async function loadDocumentPreview(){
  if(!selected)return;const documentId=selected,ticket=++previewGeneration,settingsVersion=settingsGeneration;generation++;loadingPreview=true;filePreview=false;fileDirty=false;let preview,showedPartial=false;updatePrimaryAction();$('#fileLifecycleStatus').textContent='Creating preview…';
  const showTextEarly=partial=>{if(ticket!==previewGeneration||documentId!==selected)return;showedPartial=true;$('#source').value=partial.text;filePreview=true;fileDirty=settingsGeneration!==settingsVersion;currentPreviewFormat=partial.format||'';if(hasFormattedDocumentPreview(currentPreviewFormat)){const rich=$('#docxPreview');invalidatePreviewAnchors(rich);rich.innerHTML='';$('#previewCompleteness').textContent='Preparing formatted view…';setSourcePreviewLoading(true);}updatePrimaryAction();$('#fileLifecycleStatus').textContent='Text loaded · preparing formatted view…';};
  try{preview=await requestDocumentPreview(documentId,showTextEarly);}
  catch(error){if(ticket===previewGeneration&&documentId===selected){loadingPreview=false;setSourcePreviewLoading(false);currentPreviewFormat='';setDocxPreviewMode(false);$('#fileLifecycleStatus').textContent=`Preview error: ${String(error?.message||error)}`;}return;}
  if(ticket!==previewGeneration||documentId!==selected)return;
  const keepFormatted=!showedPartial||!$('#docxPreview').hidden;$('#source').value=preview.text;loadingPreview=false;setSourcePreviewLoading(false);filePreview=true;fileDirty=fileDirty||settingsGeneration!==settingsVersion;updatePrimaryAction();
  currentPreviewFormat=preview.format||'';const rich=$('#docxPreview');invalidatePreviewAnchors(rich);rich.innerHTML=preview.rich_html||'';resetDocxPreviewScroll();$('#previewCompleteness').textContent=hasFormattedDocumentPreview(preview.format)?`Full document text loaded · Tables: ${rich.querySelectorAll('.docx-table').length}. Visual elements without text may not appear.`:'';switchPreviewMode(setDocxPreviewMode,hasFormattedDocumentPreview(preview.format)&&keepFormatted);
  const analysisTicket=generation+1;await anonymizeText();if(analysisTicket!==generation||documentId!==selected)return;
  $('#fileStatus').textContent=`Preview: ${preview.display_name} — ${documentStatusText(preview.status)}`;
}
function renderWarnings(){
  const items=(last.warnings||[]).map(warningText);
  const warning=$('#warning'),hasWarnings=items.length>0;
  warning.textContent=hasWarnings?items.join('\n'):'';
  warning.classList.toggle('sr-only',!hasWarnings);
  warning.classList.toggle('stop',(last.warnings||[]).some(w=>typeof w==='object'&&w.level==='stop'));
}
function renderStats(){
  const reviewed=[...reviewedHints].filter(k=>k.startsWith(generation+'|')).length;
  const pending=Math.max(0,(last.hintCount||0)-reviewed),all=(last.hintCount||0);$('#stats').textContent=`Replacements found: ${last.total||0} · Need decisions: ${pending} · Reviewed: ${reviewed} of ${all}`;
  const groups={"People":['ФИО','ЛОГИН','ДАТА-РОЖДЕНИЯ'],"Organizations":['ОРГАНИЗАЦИЯ','СИСТЕМА','ПРОИЗВОДИТЕЛЬ'],"Abbreviations":['СОКРАЩЕНИЯ'],"Places":['ГОРОД','АДРЕС','ИНДЕКС'],"Network":['IP','ПОРТ','MAC','IMEI','ССЫЛКА','ДОМЕН','УЗЕЛ','DN'],"Contacts":['ПОЧТА','ТЕЛЕФОН','АККАУНТ'],"Identifiers":['ИНН','ОГРН','КПП','СНИЛС','СЧЁТ','КАРТА','БИК','ПАСПОРТ','VIN','ДОГОВОР','ДОКУМЕНТ'],"Finance":['СУММА','СТАВКА'],"Secrets":['SECRET']};
  $('#chips').innerHTML=Object.entries(groups).map(([name,cats])=>`<span>${name}: ${cats.reduce((n,c)=>n+(last.counts?.[c]||0),0)}</span>`).join('')+`<span class="yellow">review: ${Math.max(0,(last.hintCount||0)-reviewed)}</span>`;
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
    if(p.t==='hint'){const key=`${generation}|${p.kind}|${p.s0}|${p.orig}`,kind=hintKindText(p.kind);return `<button type="button" class="mark-hint ${reviewedHints.has(key)?'reviewed':''}" data-part="${i}" data-s0="${p.s0}" data-kind="${esc(p.kind)}" aria-label="Review uncertain item: ${esc(p.orig)}. ${esc(kind)}" title="${esc(kind)}">${esc(p.s)}</button>`;}
    return `<button type="button" class="${p.secret?'mark-secret':'mark-replacement'}" data-part="${i}" data-s0="${p.s0}" data-ph="${esc(p.s)}" aria-label="${p.secret?'Value permanently removed':`Restore original value for ${esc(p.s)}`}" title="${p.secret?'Permanently removed':'Click to restore this value'}">${esc(p.s)}</button>`;
  }).join('');
  $('#output').value=outputText();
  $('#undoChips').innerHTML=[...restoredParts].map(i=>`<button class="undo-chip" data-undo="${i}" title="Undo restoration and show the marker again">Undo restoration of ${esc(last.parts[i]?.s||'')}</button>`).join('');
  renderMirror(); renderStats(); updateReviewPosition(); refreshFormattedReviewFocus();
}
function marks(){return [...$('#richOutput').querySelectorAll('.mark-replacement,.mark-secret,.mark-hint')];}
function hintMarks(){return [...$('#richOutput').querySelectorAll('.mark-hint:not(.reviewed)')];}
function scrollReviewMarkWithinOutput(mark){const rich=$('#richOutput'),box=rich.getBoundingClientRect(),target=mark.getBoundingClientRect();rich.scrollTop+=target.top-box.top-(rich.clientHeight-target.height)/2;}
function clearFormattedReviewHighlight(){
  [$('#docxPreview'),$('#anonymizedDocxPreview')].forEach(root=>root.querySelectorAll('.preview-review-current').forEach(node=>node.classList.remove('preview-review-current')));
  if(globalThis.CSS&&CSS.highlights)CSS.highlights.delete('current-review');
}
function occurrenceBefore(text,needle,offset){if(!needle)return 0;let count=0,from=0,index=0;const haystack=String(text||'').toLocaleLowerCase(),target=String(needle).toLocaleLowerCase(),limit=Math.max(0,Number(offset)||0);while((index=haystack.indexOf(target,from))>=0&&index<limit){count++;from=index+Math.max(1,target.length);}return count;}
function textRangeForOccurrence(root,needle,occurrence){
  if(!root||!needle||typeof document.createTreeWalker!=='function')return null;
  const nodes=[],walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),target=String(needle),foldedTarget=target.toLocaleLowerCase();let node,text='';
  while((node=walker.nextNode())){nodes.push({node,start:text.length,end:text.length+node.nodeValue.length});text+=node.nodeValue;}
  let at=-1,from=0;const folded=text.toLocaleLowerCase();for(let n=0;n<=occurrence;n++){at=folded.indexOf(foldedTarget,from);if(at<0)return null;from=at+Math.max(1,target.length);}
  const start=nodes.find(item=>item.start<=at&&at<item.end),finishAt=at+target.length,finish=nodes.find(item=>item.start<finishAt&&finishAt<=item.end);
  if(!start||!finish)return null;
  const range=document.createRange();range.setStart(start.node,at-start.start);range.setEnd(finish.node,finishAt-finish.start);
  const element=start.node.parentElement,block=element&&element.closest?element.closest('[data-preview-anchor]'):null;
  return {range,block:block||element};
}
function sourceContextRange(text,offset){const value=String(text||''),at=Math.max(0,Math.min(Number(offset)||0,value.length)),start=value.lastIndexOf('\n',Math.max(0,at-1))+1,next=value.indexOf('\n',at);return{value:value.slice(start,next<0?value.length:next),localOffset:at-start,start};}
function normalizedReviewText(value){return String(value||'').replace(/\s+/g,' ').trim().toLocaleLowerCase();}
function textRangeForSourceOffset(root,needle,sourceText,sourceOffset,fallbackOccurrence){
 const context=sourceContextRange(sourceText,sourceOffset),foldedNeedle=normalizedReviewText(needle),foldedContext=normalizedReviewText(context.value);
 if(foldedContext&&foldedContext!==foldedNeedle&&foldedContext.length>foldedNeedle.length+3){const localOccurrence=occurrenceBefore(context.value,needle,context.localOffset),sourceLines=String(sourceText||'').split('\n'),duplicateIndex=String(sourceText||'').slice(0,context.start).split('\n').filter(line=>normalizedReviewText(line)===foldedContext).length,sourceDuplicateCount=sourceLines.filter(line=>normalizedReviewText(line)===foldedContext).length,blocks=[...root.querySelectorAll('[data-preview-anchor]')].filter(block=>{const foldedBlock=normalizedReviewText(block.textContent);return foldedBlock&&(foldedBlock===foldedContext||(sourceDuplicateCount===1&&(foldedBlock.includes(foldedContext)||foldedContext.includes(foldedBlock))));}),block=blocks.length===sourceDuplicateCount?blocks[duplicateIndex]:null;if(block){const match=textRangeForOccurrence(block,needle,localOccurrence);if(match)return match;}}
 return textRangeForOccurrence(root,needle,fallbackOccurrence);
}
function centerPreviewTarget(container,target){if(!container||!target||container.hidden)return;const box=container.getBoundingClientRect(),rect=target.getBoundingClientRect();const next=Math.max(0,Math.min(container.scrollHeight-container.clientHeight,container.scrollTop+rect.top-box.top-(container.clientHeight-rect.height)/2));programmaticPreviewScrollTargets.set(container,next);container.scrollTop=next;}
function focusFormattedReview(part,sourceOffset){
  clearFormattedReviewHighlight();
  const needle=part&&part.orig?String(part.orig):'';if(!needle)return false;
  holdReviewScrollSync();
  const sourceRoot=$('#docxPreview'),outputRoot=$('#anonymizedDocxPreview'),globalOccurrence=occurrenceBefore($('#source').value,needle,sourceOffset);
  const sourceMatch=textRangeForSourceOffset(sourceRoot,needle,$('#source').value,sourceOffset,globalOccurrence);let outputMatch=null,anchor='';
  if(sourceMatch&&sourceMatch.block){anchor=sourceMatch.block.dataset&&sourceMatch.block.dataset.previewAnchor||'';const prefix=document.createRange();prefix.selectNodeContents(sourceMatch.block);prefix.setEnd(sourceMatch.range.startContainer,sourceMatch.range.startOffset);const prefixText=prefix.toString(),localOccurrence=occurrenceBefore(prefixText,needle,prefixText.length);const outputBlock=anchor?[...outputRoot.querySelectorAll('[data-preview-anchor]')].find(node=>node.dataset.previewAnchor===anchor):null;outputMatch=textRangeForOccurrence(outputBlock||outputRoot,needle,outputBlock?localOccurrence:globalOccurrence);}
  else outputMatch=textRangeForOccurrence(outputRoot,needle,globalOccurrence);
  const ranges=[],sourceVisible=sourceMatch&&!sourceRoot.hidden,outputVisible=outputMatch&&!outputRoot.hidden;
  if(sourceVisible){ranges.push(sourceMatch.range);centerPreviewTarget(sourceRoot,sourceMatch.range);}
  if(outputVisible){ranges.push(outputMatch.range);centerPreviewTarget(outputRoot,outputMatch.range);}
  const exactHighlight=ranges.length&&globalThis.CSS&&CSS.highlights&&typeof Highlight==='function';
  if(exactHighlight)CSS.highlights.set('current-review',new Highlight(...ranges));
  else{if(sourceVisible)sourceMatch.block.classList.add('preview-review-current');if(outputVisible)outputMatch.block.classList.add('preview-review-current');}
  return ranges.length>0;
}
function focusMark(i){
  const all=hintMarks();if(!all.length){reviewIndex=-1;clearFormattedReviewHighlight();updateReviewPosition();return;}
  cancelDocxPreviewScrollReset();cancelAnonymizedPreviewScrollReset();
  reviewIndex=(i+all.length)%all.length;marks().forEach(x=>x.classList.remove('mark-current'));const mark=all[reviewIndex];mark.classList.add('mark-current');const sourceOffset=Number(mark.dataset.s0||0),part=(last.parts||[]).find(item=>item.t==='hint'&&Number(item.s0||0)===sourceOffset)||{orig:mark.textContent};
  const formattedFocused=focusFormattedReview(part,sourceOffset);if(!formattedFocused||$('#anonymizedDocxPreview').hidden)scrollReviewMarkWithinOutput(mark);if(Number.isFinite(sourceOffset))$('#source').setSelectionRange(sourceOffset,sourceOffset);
  if($('#docxPreview').hidden&&$('#anonymizedDocxPreview').hidden){const output=activeAnonymizedPreview(),source=activeSourcePreview();restorePreviewPosition(previewScrollPosition(output),source);}
  updateReviewPosition();
}
function refreshFormattedReviewFocus(){
  if(reviewFocusFrame!==null){cancelAnimationFrame(reviewFocusFrame);reviewFocusFrame=null;}
  if(!hintMarks().length){clearFormattedReviewHighlight();return;}
  focusMark(reviewIndex);
  reviewFocusFrame=requestAnimationFrame(()=>{reviewFocusFrame=requestAnimationFrame(()=>{reviewFocusFrame=null;focusMark(reviewIndex);});});
}
function reviewDisabledReason(){if($('#paranoid').checked)return 'Manual review is disabled because automatic hiding is enabled. To decide uncertain items one by one, clear “Automatically hide uncertain items without confirmation”.';const hints=document.querySelector('.category[data-categories="HINTS"]');if(hints&&!hints.checked)return 'Manual review is disabled because uncertain-item detection is off. Uncertain items will remain unchanged and will not appear in the queue.';return 'No uncertain items found.';}
function reviewDisabledSummary(){if($('#paranoid').checked)return 'Automatic hiding is enabled';const hints=document.querySelector('.category[data-categories="HINTS"]');if(hints&&!hints.checked)return 'Uncertain-item detection is off';return 'No uncertain items found';}
function updateReviewPosition(){const all=hintMarks();if(reviewIndex>=all.length)reviewIndex=all.length?0:-1;if(reviewIndex<0&&all.length)reviewIndex=all.length?0:-1;const hasCurrent=all.length>0&&reviewIndex>=0;const reviewed=[...reviewedHints].filter(k=>k.startsWith(generation+'|')).length,remaining=all.length,total=remaining+reviewed;const reason=reviewDisabledReason(),summary=reviewDisabledSummary(),emptyProgress=reason.startsWith('Manual review is disabled')?'Manual review is disabled':'No uncertain items';$('#reviewPos').textContent=total?`Remaining: ${remaining} of ${total} · Decided: ${reviewed}`:emptyProgress;const reviewCurrent=$('#reviewCurrent');reviewCurrent.textContent=hasCurrent?`“${all[reviewIndex].textContent.trim()}” · ${hintKindText(all[reviewIndex].dataset.kind)||'possibly sensitive data'}`:summary;reviewCurrent.title=hasCurrent?'':reason;reviewCurrent.ariaLabel=hasCurrent?reviewCurrent.textContent:reason;if(hasCurrent){const part=last.parts[Number(all[reviewIndex].dataset.part)],needle=(part?.orig||'').toLocaleLowerCase('ru-RU'),occurrences=(last.parts||[]).filter(p=>p.t==='hint'&&(p.orig||'').toLocaleLowerCase('ru-RU')===needle).length;$('#reviewMeta').textContent=`${occurrences} match(es) · Rules: “${profileDisplayName($('#profile').value||'Общий')}”`;}else $('#reviewMeta').textContent='';$('#reviewDecision').textContent=lastReviewDecision||(hasCurrent?'Choose one of the two options below.':(reviewed?'Queue complete. Every uncertain item has a decision.':'No decision yet.'));$('#reviewPrev').disabled=!hasCurrent;$('#reviewNext').disabled=!hasCurrent;$('#hideCandidate').disabled=!hasCurrent;$('#keepCandidate').disabled=!hasCurrent;$('#reviewFinish').innerHTML=hasCurrent?'Review the remaining items. For files, then click <b>“Apply settings to file”</b>.':(reviewed?(filePreview?'Queue complete. Click <b>“Apply settings to file”</b> to rebuild the exportable copy.':'Queue complete. All decisions are already applied to the text.'):'When yellow items appear, review them here one by one.');$('#reviewFinish').classList.toggle('complete',!hasCurrent&&reviewed>0);if(lastReviewDecision&&!(last.warnings||[]).length)$('#warning').textContent=hasCurrent?`Uncertain items remaining: ${remaining}.`:'Manual review complete: all uncertain items were reviewed.';if(lastReviewDecision&&!hasCurrent)$('#resultStatus').textContent=filePreview?'Manual review complete. Now apply the settings to the file.':'Manual review complete. All decisions were applied to the text.';}
function restoreReplacement(index){
  const p=last.parts[index]; if(!p||p.t!=='ph'||p.secret)return;
  restoredParts.add(index);addDecisionLine('#whitelist',p.orig);settingsGeneration++;if(filePreview)fileDirty=true;renderOutput();
}
function addDecisionLine(selector,value){const el=$(selector),lines=el.value.split('\n').filter(Boolean);if(!lines.includes(value)){lines.push(value);el.value=lines.join('\n');}}
function removeDecisionLine(selector,value){const el=$(selector);el.value=el.value.split('\n').filter(x=>x&&x!==value).join('\n');}
function currentHint(){const all=hintMarks(),el=all[reviewIndex];if(!el)return null;return {el,index:Number(el.dataset.part),part:last.parts[Number(el.dataset.part)]};}
function keepHint(){const h=currentHint();if(!h)return;reviewedHints.add(`${generation}|${h.part.kind}|${h.part.s0}|${h.part.orig}`);addDecisionLine('#whitelist',h.part.orig);settingsGeneration++;lastReviewDecision='Decision saved: the item remains unchanged and was added to the current settings’ exceptions.';if(filePreview)fileDirty=true;renderOutput();}
async function hideHint(){
  const h=currentHint();if(!h)return;
  const labels={'город':'ГОРОД','должность':'ДОЛЖНОСТЬ','спецкатегория ПДн':'СПЕЦКАТЕГОРИЯ','возможная фамилия':'ФИО','возможное ФИО':'ФИО','возможное имя заказчика':'ОРГАНИЗАЦИЯ','возможное имя собственное':'СКРЫТО'};
  const label=labels[h.part.kind]||'СКРЫТО',value=h.part.orig;
  const customCategory=$('.category[data-categories="CUSTOM"]');if(customCategory)customCategory.checked=true;
  removeDecisionLine('#whitelist',value);addDecisionLine('#rules',`${value} => ${label}`);settingsGeneration++;if(filePreview)fileDirty=true;
  const profileName=profileDisplayName($('#profile').value||'Общий');
  try{
    const saved=await pywebview.api.save_profile($('#profile').value,$('#rules').value,$('#whitelist').value,$('#paranoid').checked,$('#uncertainMode').value);
    if(!saved?.ok)throw new Error('profile-save');
  }catch(error){
    lastReviewDecision=`The rule was added to current settings but not saved in profile “${profileName}”. ${bridgeErrorText('profile-save')}`;
    updateReviewPosition();return;
  }
  await anonymizeText();
  lastReviewDecision=`Decision saved: all matching occurrences of “${value}” were replaced with a marker; the rule was saved in profile “${profileName}”.`;
  updateReviewPosition();
}
async function anonymizeText(){
  const text=$('#source').value;if(!text){clearResult();return;}
  const ticket=++generation;
  const settings=[$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked];
  const needsFormattedPreview=filePreview&&!loadingPreview&&selected&&hasFormattedDocumentPreview(currentPreviewFormat);
  let formatted=null;
  if(needsFormattedPreview){
    switchPreviewMode(setAnonymizedPreviewMode,false);
    setAnonymizedPreviewLoading(true);
    $('#anonymizedPreviewCompleteness').textContent='Preparing formatted view…';
    formatted=requestAnonymizedDocumentPreview(selected,...settings,$('#redactDocxGraphics').checked);
  }
  const result=await pywebview.api.anonymize_text(text,...settings);
  if(ticket!==generation)return;
  last=result;if(Object.keys(last.mapping||{}).length)textRestoreMapping={...last.mapping};lastReviewDecision='';restoredParts.clear();reviewIndex=0;showMapping(last.mapping);renderOutput();renderWarnings();
  $('#settingsStatus').textContent=fileDirty
    ?'Preview updated. The exportable file still uses the previous settings — click “Apply settings to file”.'
    :'Preview updated.';
  if(needsFormattedPreview){
    let formattedPreview=null;
    try{formattedPreview=await formatted;}catch(error){formattedPreview={error:true}}
    if(ticket!==generation)return;
    setAnonymizedPreviewLoading(false);
    if(hasFormattedDocumentPreview(formattedPreview?.format)){
      const sourcePosition=previewScrollPosition(activeSourcePreview()),rich=$('#anonymizedDocxPreview');invalidatePreviewAnchors(rich);rich.innerHTML=formattedPreview.rich_html||'';rich.scrollTop=0;$('#anonymizedPreviewCompleteness').textContent=`Formatted view ready · Tables: ${rich.querySelectorAll('.docx-table').length}. The text preview already reflects the selected options.`;setAnonymizedPreviewMode(true);restorePreviewPosition(sourcePosition,rich);refreshFormattedReviewFocus();
    }else{
      leaveAnonymizedPreview();
      if(formattedPreview?.error)$('#anonymizedPreviewCompleteness').textContent=bridgeErrorText('formatted-preview');
    }
  }else leaveAnonymizedPreview();
  if(!filePreview)updatePrimaryAction();
}
function scheduleAnonymize(){clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>anonymizeText(),320);renderMirror();}
function clearResult(){generation++;last={mapping:{},candidates:[],counts:{},parts:[],total:0,hintCount:0,warnings:[]};textRestoreMapping={};restoredParts.clear();reviewedHints.clear();showMapping({});renderOutput();renderWarnings();}
async function anonymizeSelected(){
  if(filePreview&&selected){
    const current=selected,ticket=++generation,settingsVersion=settingsGeneration,button=$('#anonymize');
    button.disabled=true;button.textContent='Applying settings…';$('#fileLifecycleStatus').textContent='Processing file… the source file remains unchanged';$('#settingsStatus').textContent='Creating an exportable file with the selected settings. A large Office document may take several minutes…';$('#fileStatus').textContent='Anonymizing document…';
    try{
      const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked,$('#redactDocxGraphics').checked);
      if(current!==selected)return;
      if(settingsVersion!==settingsGeneration){
        if(ticket===generation)await anonymizeText();
        if(current!==selected)return;
        fileDirty=true;$('#fileStatus').textContent=`${documentStatusText(r.status)}. The file was created with previous settings and is not ready to export.`;$('#settingsStatus').textContent='Setting changes are not yet applied to the exportable file. Review the updated preview and click “Apply settings to file”.';return;
      }
      if(ticket!==generation)return;
      fileDirty=false;showMapping(r.mapping||last.mapping);last.warnings=r.warnings||[];last.total=r.replacement_count||last.total;last.hintCount=r.candidate_count||0;renderStats();renderWarnings();
      await anonymizeText();
      if(current!==selected)return;
      const refreshedGeneration=generation;
      setAnonymizedPreviewMode(false);$('#richOutput').scrollTop=0;
      $('#fileStatus').textContent=`${documentStatusText(r.status)}. The anonymized file is ready to save.`;const documents=await pywebview.api.list_documents();if(refreshedGeneration!==generation||current!==selected)return;showLibrary(documents);selected=current;$('#library').value=current;$('#settingsStatus').textContent='Settings applied. The file is ready to export. Preview updated.';return;
    }catch(error){
      if(current===selected)$('#fileStatus').textContent=bridgeErrorText('anonymize');
      throw error;
    }finally{
      if(current===selected)updatePrimaryAction(true);
    }
  }
  if($('#source').value.trim())return anonymizeText();
  if(!selected)return alert('Enter text or import a file.');
  const current=selected,ticket=++generation;const r=await pywebview.api.anonymize_document(current,$('#paranoid').checked,$('#rules').value,$('#whitelist').value,disabled(),$('#compactMarkers').checked,$('#redactDocxGraphics').checked);
  if(ticket!==generation||current!==selected)return;
  last={mapping:r.mapping||{},candidates:r.candidates||[],counts:{},parts:[],total:r.replacement_count||0,hintCount:r.candidate_count||0,warnings:r.warnings||[]};if(Object.keys(last.mapping).length)textRestoreMapping={...last.mapping};showMapping(last.mapping);renderStats();renderWarnings();
  $('#fileStatus').textContent=`${r.ready?'Ready':'Manual review required'}. The anonymized file is ready to save.`;const documents=await pywebview.api.list_documents();if(ticket!==generation||current!==selected)return;showLibrary(documents);
}

$('#source').addEventListener('input',()=>{if(!loadingPreview){filePreview=false;fileDirty=false;leaveDocumentPreview();}updatePrimaryAction();scheduleAnonymize();});$('#anonymize').onclick=anonymizeSelected;
$('#showFormatted').onclick=()=>switchPreviewMode(setDocxPreviewMode,true);$('#showTextPreview').onclick=()=>{switchPreviewMode(setDocxPreviewMode,false);$('#sourceMirror').scrollTop=$('#source').scrollTop;};$('#previewTop').onclick=()=>{cancelDocxPreviewScrollReset();$('#docxPreview').scrollTop=0;};$('#previewBottom').onclick=()=>{cancelDocxPreviewScrollReset();const rich=$('#docxPreview');rich.scrollTop=rich.scrollHeight;};$('#previewFullscreen').onclick=()=>setPreviewFullscreen(!previewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#docxPreview').addEventListener(name,cancelDocxPreviewScrollReset));
$('#showAnonymizedFormatted').onclick=()=>switchPreviewMode(setAnonymizedPreviewMode,true);$('#showAnonymizedText').onclick=()=>switchPreviewMode(setAnonymizedPreviewMode,false);$('#anonymizedPreviewTop').onclick=()=>{cancelAnonymizedPreviewScrollReset();$('#anonymizedDocxPreview').scrollTop=0;};$('#anonymizedPreviewBottom').onclick=()=>{cancelAnonymizedPreviewScrollReset();const rich=$('#anonymizedDocxPreview');rich.scrollTop=rich.scrollHeight;};$('#anonymizedPreviewFullscreen').onclick=()=>setAnonymizedPreviewFullscreen(!anonymizedPreviewFullscreen);['wheel','pointerdown','touchstart'].forEach(name=>$('#anonymizedDocxPreview').addEventListener(name,cancelAnonymizedPreviewScrollReset));
$('#docxPreview').addEventListener('scroll',syncFormattedSourceScroll);
$('#anonymizedDocxPreview').addEventListener('scroll',syncFormattedAnonymizedScroll);
window.addEventListener('resize',()=>{invalidatePreviewAnchors($('#docxPreview'));invalidatePreviewAnchors($('#anonymizedDocxPreview'));});
function hasSelectionInside(root){
 const selection=window.getSelection?.();
 if(!root||!selection||selection.isCollapsed||!selection.rangeCount)return false;
 return [selection.anchorNode,selection.focusNode].some(node=>node&&(node===root||root.contains(node)));
}
$('#richOutput').onclick=e=>{const mark=e.target.closest('.mark-replacement,.mark-secret,.mark-hint');if(!mark||hasSelectionInside($('#richOutput')))return;const i=Number(mark.dataset.part);if(mark.classList.contains('mark-hint'))focusMark(hintMarks().indexOf(mark));if(mark.classList.contains('mark-replacement'))restoreReplacement(i);};
$('#undoChips').onclick=e=>{const b=e.target.closest('[data-undo]');if(b){const i=Number(b.dataset.undo);removeDecisionLine('#whitelist',last.parts[i]?.orig||'');restoredParts.delete(i);settingsGeneration++;if(filePreview)fileDirty=true;renderOutput();}};
$('#reviewPrev').onclick=()=>focusMark(reviewIndex-1);$('#reviewNext').onclick=()=>focusMark(reviewIndex+1);$('#hideCandidate').onclick=hideHint;$('#keepCandidate').onclick=keepHint;
$('#choose').onclick=async()=>{const ticket=++importGeneration;generation++;previewGeneration++;const r=await pywebview.api.choose_files();if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent=bridgeErrorText('import');};$('#dropChoose').onclick=$('#choose').onclick;
$('#deleteDoc').onclick=async()=>{if(selected&&confirm('Delete the record and app files? The user’s source file will remain.')){const r=await pywebview.api.delete_document(selected);$('#source').value='';filePreview=false;fileDirty=false;leaveDocumentPreview();clearResult();showLibrary(r.documents);}};
$('#downloadAnon').onclick=async()=>{if(!selected)return alert('Select a ready document first.');const status=documentsById[selected]?.status;if(status==='Экспорт запрещён')return alert('Export is blocked by a critical warning.');if(!['Готов','Требуется ручная проверка'].includes(status))return alert('Anonymize the selected document first.');if(fileDirty)return alert('Anonymize the document again first: preview decisions are not yet applied to the file.');let confirmation=false;if(status==='Требуется ручная проверка'){if(!confirm('The document has warnings. Do you confirm manual review and want to export?'))return;confirmation=true;}const r=await pywebview.api.export_anonymized(selected,confirmation);if(r.ok)$('#fileStatus').textContent=`Saved pair: ${r.path} + ${r.recovery_path}`;};
$('#downloadAll').onclick=async()=>{if(fileDirty)return alert('Apply the imported settings to the selected file first. ZIP export was stopped.');const r=await pywebview.api.export_all_anonymized();if(r.ok)$('#fileStatus').textContent=`ZIP exported without mapping tables: ${r.path}`;};
async function chooseRestorePair(){const ticket=++restoreGeneration;$('#restoreFile').disabled=true;$('#restoreRecordName').textContent='Verifying pair…';try{const r=await pywebview.api.choose_restore_pair();if(ticket!==restoreGeneration)return;if(!r.ok){$('#restoreRecordName').textContent='No pair selected yet.';$('#restoreStatus').textContent='Selection canceled.';return;}$('#restoreRecordName').textContent=`Pair found: ${r.anonymized_name} + ${r.recovery_name}`;$('#restoreStatus').textContent='Pair verified by internal ID. Ready to restore.';$('#restoreFile').disabled=false;}catch(error){if(ticket!==restoreGeneration)return;$('#restoreRecordName').textContent='No matching pair found.';$('#restoreStatus').textContent=bridgeErrorText('restore');}}
async function restoreMatchedFile(){if($('#restoreFile').disabled)return;try{$('#restoreStatus').textContent='Choose where to save the restored file.';const r=await pywebview.api.restore_matched_file();if(r.ok){const message=`Done. Restored file saved: ${r.path}; unknown markers: ${r.unknown_markers.length}`;$('#restoreStatus').textContent=message;$('#fileStatus').textContent=message;}else $('#restoreStatus').textContent='Restore canceled. Source files were not changed.';}catch{const message='Could not restore the file. Check the file pair, document format and access to the destination folder. Source files were not changed.';$('#restoreStatus').textContent=message;$('#fileStatus').textContent=message;}}
$('#chooseRestoreFile').onclick=chooseRestorePair;
$('#restoreFile').onclick=restoreMatchedFile;
$('#clear').onclick=()=>{if($('#source').value.trim()&&!confirm('Clear the entered text and current result?'))return;filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='';clearResult();};
$('#sample').onclick=()=>{filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value='Contractor “Build Guarantee Plus” supports the Web system. Login admin_db; old password qwerty123. Version 1.7.5.16, SLA 99.9%, VAT 20%, port 8080.';scheduleAnonymize();};
$('#paste').onclick=async()=>{const r=await pywebview.api.read_clipboard_text();filePreview=false;fileDirty=false;leaveDocumentPreview();$('#source').value=r.text||'';scheduleAnonymize();};
$('#copy').onclick=async()=>{try{const result=await pywebview.api.write_clipboard_text(outputText());if(!result.ok)throw new Error('copy');}catch{$('#fileStatus').textContent='Could not copy text.';}};
$('#restore').onclick=async()=>{clearTimeout(debounceTimer);const source=$('#source');if(!source.value.trim())return alert('Paste text with markers into the “Source text” field.');if(!Object.keys(textRestoreMapping).length)return alert('No data is available for reverse replacement. Anonymize the source text first.');const ticket=++generation;const result=await pywebview.api.restore_text($('#source').value,textRestoreMapping);if(ticket!==generation)return;$('#source').value=result.text;filePreview=false;fileDirty=false;leaveDocumentPreview();updatePrimaryAction();scheduleAnonymize();};
$('#selftest').onclick=async()=>{$('#testResult').textContent=(await pywebview.api.engine_self_test()).ok?' Engine OK':' Test failed';};
$('#help').onclick=()=>alert('All rules run locally. Blue markers are reversible with the current mapping, gray secrets are removed without original values, and yellow items require a decision. The mapping and original values are not included in Help.');
$('#themeToggle').onclick=async()=>{const theme=document.documentElement?.dataset?.theme==='dark'?'light':'dark';applyTheme(theme,true);await pywebview.api.set_theme(theme);};

$('#applyNow').onclick=()=>$('#anonymize').click();
$('#exportNow').onclick=()=>$('#downloadAnon').click();
$('#mono').onchange=e=>document.querySelectorAll('textarea,.mirror,.rich-output').forEach(x=>x.classList.toggle('mono',e.target.checked));
async function refreshProfiles(select){const names=await pywebview.api.list_profiles(),list=$('#profile');list.innerHTML='';names.forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=profileDisplayName(n);list.appendChild(o);});if(select)list.value=select;}
async function loadProfileIntoEditor(name){const p=await pywebview.api.load_profile(name);$('#rules').value=Object.entries(p.dictionary).map(([k,v])=>`${k} => ${v}`).join('\n');$('#whitelist').value=p.whitelist.join('\n');applyUncertainMode(normalizeUncertainMode(p.uncertain_mode,p.paranoid,true));markSettingsDirty();}
$('#profile').onchange=()=>loadProfileIntoEditor($('#profile').value);
$('#newProfile').onclick=async()=>{const n=prompt('Profile name');if(n){await pywebview.api.save_profile(n,$('#rules').value,$('#whitelist').value,$('#paranoid').checked,$('#uncertainMode').value);await refreshProfiles(n);$('#settingsStatus').textContent=`Profile “${profileDisplayName(n)}” saved.`;}};
$('#deleteProfile').onclick=async()=>{const n=$('#profile').value;if(n!=='Общий'&&confirm(`Delete profile “${n}”?`)){await pywebview.api.delete_profile(n);await refreshProfiles('Общий');await loadProfileIntoEditor('Общий');}};
$('#exportProfile').onclick=async()=>{const n=$('#profile').value;try{const r=await pywebview.api.export_profile(n,$('#rules').value,$('#whitelist').value,$('#paranoid').checked,$('#uncertainMode').value);if(r.ok)$('#settingsStatus').textContent=`Profile “${profileDisplayName(n)}” exported.`;else $('#settingsStatus').textContent=r.error?profileErrorText('export'):'Profile export canceled.';}catch(e){$('#settingsStatus').textContent=profileErrorText('export');}};
$('#importProfile').onclick=async()=>{try{const r=await pywebview.api.import_profile();if(r.ok){await refreshProfiles(r.name);await loadProfileIntoEditor(r.name);$('#settingsStatus').textContent=fileDirty?`Profile “${profileDisplayName(r.name)}” imported and loaded. Apply settings to the file before export.`:`Profile “${profileDisplayName(r.name)}” imported and loaded.`;}else if(r.error){$('#settingsStatus').textContent=profileErrorText('import');}}catch(e){$('#settingsStatus').textContent=profileErrorText('import');}};
function markSettingsDirty(){settingsGeneration++;if(filePreview){fileDirty=true;$('#settingsStatus').textContent='Setting changes are not yet applied to the exportable file. Review the updated preview and click “Apply settings to file”.';}updatePrimaryAction();scheduleAnonymize();}
['#rules','#whitelist','#redactDocxGraphics'].forEach(s=>$(s).addEventListener('input',markSettingsDirty));
$('#reviewHintsMode').onchange=async()=>{if($('#reviewHintsMode').checked)$('#paranoid').checked=false;syncUncertainModeFromCheckboxes();markSettingsDirty();};
$('#paranoid').onchange=async()=>{if($('#paranoid').checked)$('#reviewHintsMode').checked=false;syncUncertainModeFromCheckboxes();markSettingsDirty();};
$('#compactMarkers').addEventListener('input',()=>{updateCategoryMarkerExamples();markSettingsDirty();});
document.querySelectorAll('.category:not(#reviewHints)').forEach(x=>x.addEventListener('change',markSettingsDirty));
$('#source').addEventListener('scroll',()=>{$('#sourceMirror').scrollTop=$('#source').scrollTop;syncPreviewScroll($('#source'),activeAnonymizedPreview());});$('#richOutput').addEventListener('scroll',()=>{syncPreviewScroll($('#richOutput'),activeSourcePreview());$('#sourceMirror').scrollTop=$('#source').scrollTop;});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();$('#copy').click();}if(e.key==='Escape'){if(previewFullscreen){setPreviewFullscreen(false);return;}if(anonymizedPreviewFullscreen){setAnonymizedPreviewFullscreen(false);}}});
['dragenter','dragover'].forEach(n=>document.addEventListener(n,e=>e.preventDefault()));document.addEventListener('drop',async e=>{e.preventDefault();const paths=[...e.dataTransfer.files].map(f=>f.path).filter(Boolean);if(paths.length){const ticket=++importGeneration;generation++;previewGeneration++;const r=await pywebview.api.import_paths(paths);if(ticket!==importGeneration)return;showLibrary(r.documents||[]);if(r.ok&&r.ids?.length){selected=r.ids[0];$('#library').value=selected;await loadDocumentPreview();}else $('#fileStatus').textContent='Import error';}});
window.addEventListener('pywebviewready',async()=>{await applyCurrentDesign();const savedTheme=await pywebview.api.get_theme();if(savedTheme)applyTheme(savedTheme);updateCategoryMarkerExamples();showLibrary(await pywebview.api.list_documents());await refreshProfiles('Общий');await loadProfileIntoEditor('Общий');if(selected)await loadDocumentPreview();else{renderOutput();updatePrimaryAction();}});

$('#languageMode').onchange=async e=>{const value=e.target.value;await pywebview.api.set_language(value);};
