/* v1.8.22: production editor for #rules and #whitelist. */
(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const lang=document.documentElement.lang==='en'?'en':'ru';
  const copy={
    ru:{
      rules:'Скрывать дополнительно',white:'Белый список',add:'Добавить…',addRule:'Добавить правило',editRule:'Изменить правило',addWhite:'Добавить исключение',
      phrase:'Что скрывать',keep:'Что оставить без замены',replace:'На что заменять',cancel:'Отмена',save:'Сохранить изменения',delete:'Удалить',confirm:'Точно удалить?',
      noRules:'Дополнительных правил пока нет.',noWhite:'Исключений пока нет.',actions:'Действия',rule:'Правило',exception:'Исключение',
      selectionPriority:'Приоритет над жёлтым кандидатом до снятия выделения',selectionReady:'Выделение готово: «{value}». Выберите «Скрыть…» или «Оставить…».',
      sourceHelp:'Выделите здесь мышью слово или фразу, затем используйте кнопки в «Ручной проверке». Выделение не открывает никаких окон и ничего не сохраняет само.',
      empty:'Введите текст, который нужно скрывать',newline:'Фраза с переносом строки не найдёт совпадений. Укажите фрагмент в пределах одной строки',tooLong:'Фраза длиннее 120 символов — сократите',arrow:'Фраза не должна содержать «=>»',marker:'Нельзя добавлять уже заменённый маркер',label:'Выберите метку',duplicate:'Правило для этого текста уже существует',
      conflict:'Для этой фразы уже есть другая метка. Заменить её?',occurrences:'Будет заменено вхождений: {count}',none:'Совпадений в исходном тексте нет',secret:'Значение попадёт в незашифрованный файл восстановления `.larecovery`. Храните его как исходный документ.',
      categoryDisabled:'категория выключена',saved:'{kind} сохранено.',deleted:'{kind} удалено.',saveError:'Изменение активно в текущем сеансе, но не сохранено в профиль.',deleteText:'Будет удалено: {value}',reviewCandidate:'Жёлтый кандидат очереди',profileRules:'Правила: «{profile}»',
      edit:'Изменить правило',deleteRule:'Удалить правило',deleteWhite:'Удалить исключение',special:'Особые',normal:'Категории',dictionary:'СЛОВАРЬ',secretLabel:'СЕКРЕТ',
      hide:'Скрыть и запомнить правило',keepAction:'Оставить и добавить в исключения',invalidSelection:'Выделение нельзя добавить: проверьте длину, переносы строк и символ «=>».',usageTitle:'Как добавить правило или исключение',
      usageText:'Есть два равноправных способа: откройте «Скрывать дополнительно» или «Белый список» и нажмите «Добавить…»; либо выделите фразу в исходной области и выберите действие в «Ручной проверке». Само выделение ничего не сохраняет и не открывает.'
    },
    en:{
      rules:'Hide additionally',white:'Allow list',add:'Add…',addRule:'Add rule',editRule:'Edit rule',addWhite:'Add exception',
      phrase:'Text to hide',keep:'Text to keep unchanged',replace:'Replace with',cancel:'Cancel',save:'Save changes',delete:'Delete',confirm:'Delete this item?',
      noRules:'No additional rules yet.',noWhite:'No exceptions yet.',actions:'Actions',rule:'Rule',exception:'Exception',
      selectionPriority:'The source selection takes priority over the yellow candidate until cleared',selectionReady:'Selection is ready: “{value}”. Choose Hide or Keep.',
      sourceHelp:'Select a word or phrase here, then use the actions in Manual review. Selecting text does not open a form or save anything.',
      empty:'Enter the text to hide',newline:'A phrase with a line break cannot be matched. Select text within one line',tooLong:'The phrase is longer than 120 characters — shorten it',arrow:'The phrase must not contain “=>”',marker:'An already replaced marker cannot be added',label:'Choose a label',duplicate:'A rule with this text and label already exists',
      conflict:'This text already has a different label. Replace it?',occurrences:'Occurrences to replace: {count}',none:'No matches in the source text',secret:'The value will be stored in the unencrypted `.larecovery` recovery file. Protect it like the source document.',
      categoryDisabled:'category disabled',saved:'{kind} saved.',deleted:'{kind} deleted.',saveError:'The change is active in this session but was not saved to the profile.',deleteText:'This will be deleted: {value}',reviewCandidate:'Yellow queue candidate',profileRules:'Rules: “{profile}”',
      edit:'Edit rule',deleteRule:'Delete rule',deleteWhite:'Delete exception',special:'Special',normal:'Categories',dictionary:'DICTIONARY',secretLabel:'SECRET',
      hide:'Hide and remember rule',keepAction:'Keep and add to exceptions',invalidSelection:'The selection cannot be added: check its length, line breaks, and “=>”.',usageTitle:'How to add a rule or exception',
      usageText:'There are two equal ways: open Hide additionally or Allow list and choose Add…; or select a phrase in the source area and choose an action in Manual review. Selecting text alone neither saves nor opens anything.'
    }
  }[lang];
  const t=(key,vars={})=>String(copy[key]||key).replace(/\{(\w+)\}/g,(_,name)=>vars[name]??'');
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const normalise=value=>String(value??'').trim().replace(/\s+/gu,' ');
  const fold=value=>normalise(value).toLocaleLowerCase(lang==='ru'?'ru':'en');
  const rulesInput=$('#rules'),whiteInput=$('#whitelist'),editor=$('#anonymizationSettings .settings-editor');
  if(!rulesInput||!whiteInput||!editor)return;

  let mode='rule',editing=-1,pendingDelete=null,selection='',selectionTimer=0,dialogReturnFocus=null,deleteReturnFocus=null,unsavedProfileWarning='';
  const parseRules=()=>rulesInput.value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean).map(line=>{
    const split=line.indexOf('=>');
    return split<0?{phrase:line,label:'СЛОВАРЬ'}:{phrase:normalise(line.slice(0,split)),label:normalise(line.slice(split+2))};
  }).filter(row=>row.phrase);
  const parseWhite=()=>whiteInput.value.split(/\r?\n/).map(normalise).filter(Boolean);
  const writeRules=rows=>{rulesInput.value=rows.map(row=>`${row.phrase} => ${row.label}`).join('\n');rulesInput.dispatchEvent(new Event('input',{bubbles:true}));};
  const writeWhite=rows=>{whiteInput.value=rows.join('\n');whiteInput.dispatchEvent(new Event('input',{bubbles:true}));};
  const setStatus=(text,overrideUnsavedWarning=false)=>{const visible=unsavedProfileWarning&&!overrideUnsavedWarning?unsavedProfileWarning:text;for(const selector of ['#settingsStatus','#fileLifecycleStatus','#resultStatus']){const node=$(selector);if(node)node.textContent=visible;}};
  const markDirty=()=>{if(typeof markSettingsDirty==='function')markSettingsDirty();};
  const syncCustom=()=>{const custom=document.querySelector('.category[data-categories="CUSTOM"]');if(custom&&!custom.checked){custom.checked=true;custom.dispatchEvent(new Event('change',{bubbles:true}));}};
  const profileName=()=>$('#profile')?.value||'Общий';
  async function persist(){
    try{
      const bridge=window.pywebview?.api;
      if(!bridge?.save_profile)return true;
      const response=await bridge.save_profile(profileName(),rulesInput.value,whiteInput.value,$('#paranoid')?.checked||false,$('#uncertainMode')?.value);
      if(!response?.ok)throw new Error('profile-save');
      unsavedProfileWarning='';
      delete document.body?.dataset?.dictionaryUnsavedProfileWarning;
      return true;
    }catch(_error){
      unsavedProfileWarning=t('saveError');
      if(document.body)document.body.dataset.dictionaryUnsavedProfileWarning=unsavedProfileWarning;
      setStatus(unsavedProfileWarning,true);
      return false;
    }
  }
  function categories(){
    const entries=[];
    document.querySelectorAll('#detectionCategories .category-section').forEach(section=>{
      const heading=section.querySelector('b')?.textContent?.trim()||t('normal');
      const values=[...section.querySelectorAll('input.category[data-categories]')].map(input=>({
        label:input.dataset.categories,
        title:normalise(input.parentElement.textContent.replace(/\[[^\]]+\]/g,'')),
        disabled:!input.checked,
        group:heading
      })).filter(item=>item.label&&item.label!=='CUSTOM'&&item.label!=='HINTS'&&item.label!=='уязвимость');
      if(values.length)entries.push(...values);
    });
    entries.push({label:'СЕКРЕТ',title:t('secretLabel'),disabled:false,group:t('special')});
    entries.push({label:'СЛОВАРЬ',title:t('dictionary'),disabled:false,group:t('special')});
    return entries;
  }
  function preferredLabel(phrase){
    const raw=normalise(phrase);
    if(/^[-\d\s]{4,20}$/u.test(raw))return 'ПАСПОРТ';
    if(raw.includes('@'))return 'ПОЧТА';
    if(/^(?:[A-ZА-ЯЁ][\p{L}-]+\s+){1,2}[A-ZА-ЯЁ][\p{L}-]+$/u.test(raw))return 'ФИО';
    try{return localStorage.getItem('selectionRuleLastLabel')||'СКРЫТО';}catch(_error){return 'СКРЫТО';}
  }
  function countMatches(phrase){
    const source=$('#source')?.value||'';
    if(!phrase||!source)return 0;
    const quoted=phrase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    try{return [...source.matchAll(new RegExp(`(?:^|[^\\p{L}\\p{N}_])${quoted}(?=$|[^\\p{L}\\p{N}_])`,'giu'))].length;}catch(_error){return 0;}
  }
  function dialogHtml(){
    editor.insertAdjacentHTML('beforeend',`<aside id="dictionaryRuleDialog" class="dictionary-rule-dialog" role="dialog" aria-modal="true" aria-labelledby="dictionaryRuleTitle" hidden>
      <div class="dictionary-rule-dialog-head"><h3 id="dictionaryRuleTitle"></h3><button type="button" class="dictionary-rule-dialog-close" id="dictionaryRuleClose" aria-label="${esc(t('cancel'))}">×</button></div>
      <label class="dictionary-rule-field" for="dictionaryRulePhrase"><span id="dictionaryRulePhraseLabel"></span><input id="dictionaryRulePhrase" maxlength="120" autocomplete="off"></label>
      <section id="dictionaryRuleLabels"><b>${esc(t('replace'))}</b><div id="dictionaryRuleLabelList" class="dictionary-rule-label-list" role="listbox" tabindex="0" aria-label="${esc(t('replace'))}"></div></section>
      <div id="dictionaryRuleCount" class="dictionary-rule-count"></div><div id="dictionaryRuleSecret" class="dictionary-rule-secret" hidden></div><div id="dictionaryRuleError" class="dictionary-rule-error" role="alert"></div>
      <div class="dictionary-rule-actions"><button type="button" id="dictionaryRuleCancel">${esc(t('cancel'))}</button><button type="button" class="primary" id="dictionaryRuleSave"></button></div>
    </aside>
    <aside id="dictionaryDeleteDialog" class="dictionary-rule-dialog" role="dialog" aria-modal="true" aria-labelledby="dictionaryDeleteTitle" hidden>
      <div class="dictionary-rule-dialog-head"><h3 id="dictionaryDeleteTitle">${esc(t('confirm'))}</h3><button type="button" class="dictionary-rule-dialog-close" id="dictionaryDeleteClose" aria-label="${esc(t('cancel'))}">×</button></div><p id="dictionaryDeleteText"></p>
      <div class="dictionary-rule-actions"><button type="button" id="dictionaryDeleteCancel">${esc(t('cancel'))}</button><button type="button" id="dictionaryDeleteApprove" class="primary danger">${esc(t('delete'))}</button></div>
    </aside>`);
  }
  dialogHtml();
  const dialog=$('#dictionaryRuleDialog'),deleteDialog=$('#dictionaryDeleteDialog'),phraseInput=$('#dictionaryRulePhrase'),labelList=$('#dictionaryRuleLabelList'),error=$('#dictionaryRuleError'),count=$('#dictionaryRuleCount'),secret=$('#dictionaryRuleSecret');
  function renderLabels(selected){
    let lastGroup='';
    labelList.innerHTML=categories().map((item,index)=>{
      const group=item.group!==lastGroup?(lastGroup=item.group,`<div class="dictionary-rule-label-group" role="presentation">${esc(item.group)}</div>`):'';
      const chosen=item.label===selected;
      const disabled=item.disabled?`<small>${esc(t('categoryDisabled'))}</small>`:'';
      return `${group}<div id="dictionaryRuleOption-${index}" class="dictionary-rule-label-option" role="option" tabindex="-1" data-dictionary-label="${esc(item.label)}" aria-selected="${chosen}"><span>[${esc(item.label)}-N] ${esc(item.title)}</span>${disabled}</div>`;
    }).join('');
  }
  function selectLabel(label){
    const option=[...labelList.querySelectorAll('[role="option"]')].find(node=>node.dataset.dictionaryLabel===label);
    if(!option)return;
    labelList.querySelectorAll("[role='option']").forEach(node=>node.setAttribute('aria-selected',String(node===option)));
    labelList.setAttribute('aria-activedescendant',option.id);
    refreshDialogDetails();
  }
  function selectedLabel(){return labelList.querySelector('[role="option"][aria-selected="true"]')?.dataset.dictionaryLabel||'';}
  function refreshDialogDetails(){
    const phrase=normalise(phraseInput.value),isRule=mode==='rule',label=selectedLabel();
    count.textContent=isRule?(countMatches(phrase)?t('occurrences',{count:countMatches(phrase)}):t('none')):'';
    const isSecret=label==='СЕКРЕТ';secret.hidden=!isSecret;secret.textContent=isSecret?t('secret'):'';
    error.textContent='';
  }
  function restoreFocus(node){if(node?.isConnected)node.focus?.();}
  function openDialog(kind,index=-1,prefill='',invoker=document.activeElement){
    dialogReturnFocus=invoker;
    mode=kind;editing=index;
    const isRule=kind==='rule',row=isRule?parseRules()[index]:parseWhite()[index];
    $('#dictionaryRuleTitle').textContent=isRule?(index<0?t('addRule'):t('editRule')):t('addWhite');
    $('#dictionaryRulePhraseLabel').textContent=isRule?t('phrase'):t('keep');
    $('#dictionaryRuleLabels').hidden=!isRule;
    $('#dictionaryRuleSave').textContent=index<0?(isRule?t('addRule'):t('addWhite')):t('save');
    phraseInput.value=prefill||(!row?'':(isRule?row.phrase:row));
    renderLabels(isRule?(row?.label||preferredLabel(phraseInput.value)): '');
    refreshDialogDetails();dialog.hidden=false;phraseInput.focus();phraseInput.select();
  }
  function closeDialog(restore=true){const opener=dialogReturnFocus;dialog.hidden=true;error.textContent='';editing=-1;if(restore)restoreFocus(opener);dialogReturnFocus=null;return opener;}
  const markerLiteral=/\[(?:[А-ЯA-ZЁа-яё][А-ЯA-ZЁа-яё0-9_-]{0,63}-\p{Nd}+|уязвимость)\]/u;
  function validate(phrase,label){
    const normalized=normalise(phrase);
    if(!normalized)return t('empty');
    if(/[\r\n]/u.test(phrase))return t('newline');
    if(normalized.length>120)return t('tooLong');
    if(normalized.includes('=>'))return t('arrow');
    if(markerLiteral.test(normalized))return t('marker');
    if(mode==='rule'&&!label)return t('label');
    return '';
  }
  async function saveDialog(){
    const raw=phraseInput.value,label=selectedLabel(),validation=validate(raw,label),phrase=normalise(raw);
    if(validation){error.textContent=validation;phraseInput.focus();return;}
    if(mode==='rule'){
      const rows=parseRules(),same=rows.findIndex(row=>fold(row.phrase)===fold(phrase));
      if(same>=0&&same!==editing&&rows[same].label===label){error.textContent=t('duplicate');return;}
      if(same>=0&&rows[same].label!==label&&!window.confirm(t('conflict')))return;
      if(editing>=0)rows.splice(editing,1);
      const existing=rows.findIndex(row=>fold(row.phrase)===fold(phrase));
      if(existing>=0)rows[existing]={phrase,label};else rows.push({phrase,label});
      writeRules(rows);writeWhite(parseWhite().filter(value=>fold(value)!==fold(phrase)));syncCustom();
      try{localStorage.setItem('selectionRuleLastLabel',label);}catch(_error){}
    }else{
      const rows=parseWhite();
      if(rows.some(value=>fold(value)===fold(phrase))&&editing!==rows.findIndex(value=>fold(value)===fold(phrase))){error.textContent=t('duplicate');return;}
      if(editing>=0)rows.splice(editing,1);
      if(!rows.some(value=>fold(value)===fold(phrase)))rows.push(phrase);
      writeWhite(rows);writeRules(parseRules().filter(row=>fold(row.phrase)!==fold(phrase)));
    }
    markDirty();const persisted=await persist(),opener=closeDialog(false);render();focusAfterRender(opener);if(persisted)setStatus(t('saved',{kind:mode==='rule'?t('rule'):t('exception')}));
  }
  function askDelete(kind,index,invoker=document.activeElement){
    const item=kind==='rule'?parseRules()[index]:parseWhite()[index];if(!item)return;
    pendingDelete={kind,index};deleteReturnFocus=invoker;
    $('#dictionaryDeleteText').textContent=t('deleteText',{value:kind==='rule'?`${item.phrase} → ${item.label}`:item});
    deleteDialog.hidden=false;$('#dictionaryDeleteApprove').focus();
  }
  function closeDelete(restore=true){const opener=deleteReturnFocus;deleteDialog.hidden=true;pendingDelete=null;if(restore)restoreFocus(opener);deleteReturnFocus=null;return opener;}
  async function applyDelete(){
    if(!pendingDelete)return;
    const {kind,index}=pendingDelete;
    if(kind==='rule'){const rows=parseRules();rows.splice(index,1);writeRules(rows);}else{const rows=parseWhite();rows.splice(index,1);writeWhite(rows);}
    markDirty();const persisted=await persist(),opener=closeDelete(false);render();focusAfterRender(opener);if(persisted)setStatus(t('deleted',{kind:kind==='rule'?t('rule'):t('exception')}));
  }
  function icon(kind){return kind==='edit'?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 11v5m4-5v5"/></svg>';
  }
  function focusAfterRender(opener){
    const addKind=opener?.dataset?.dictionaryAdd;
    const editIndex=opener?.dataset?.dictionaryEdit;
    if(addKind){document.querySelector(`[data-dictionary-add="${addKind}"]`)?.focus();return;}
    if(editIndex!==undefined){document.querySelector(`[data-dictionary-edit="${editIndex}"]`)?.focus();return;}
    document.querySelector('#settingsTab-rules')?.focus();
  }
  function buildPanel(panel,kind){
    const backstore=kind==='rule'?rulesInput:whiteInput;
    const content=document.createElement('div');content.className='dictionary-rule-panel';
    content.innerHTML=`<div class="dictionary-rule-head"><h3>${esc(kind==='rule'?t('rules'):t('white'))}</h3><button type="button" class="primary" data-dictionary-add="${kind}">${esc(t('add'))}</button></div><div class="dictionary-rule-scroll"><table class="dictionary-rule-table"><thead><tr>${kind==='rule'?`<th>${esc(t('phrase'))}</th><th>${esc(t('replace'))}</th>`:`<th>${esc(t('keep'))}</th>`}<th aria-label="${esc(t('actions'))}"></th></tr></thead><tbody></tbody></table><div class="dictionary-rule-empty" hidden></div></div>`;
    backstore.classList.add('dictionary-rule-backstore');panel.replaceChildren(content,backstore);
  }
  buildPanel($('#settingsPanel-rules'),'rule');buildPanel($('#settingsPanel-whitelist'),'white');
  function renderPanel(panel,kind){
    const rows=kind==='rule'?parseRules():parseWhite(),tbody=panel.querySelector('tbody'),empty=panel.querySelector('.dictionary-rule-empty');
    tbody.innerHTML=rows.map((row,index)=>kind==='rule'?`<tr><td>${esc(row.phrase)}</td><td>[${esc(row.label)}-N]</td><td><button type="button" class="dictionary-rule-icon" data-dictionary-edit="${index}" title="${esc(t('edit'))}" aria-label="${esc(t('edit'))}">${icon('edit')}</button><button type="button" class="dictionary-rule-icon danger" data-dictionary-delete="${index}" title="${esc(t('deleteRule'))}" aria-label="${esc(t('deleteRule'))}">${icon('delete')}</button></td></tr>`:`<tr><td>${esc(row)}</td><td><button type="button" class="dictionary-rule-icon danger" data-dictionary-delete="${index}" title="${esc(t('deleteWhite'))}" aria-label="${esc(t('deleteWhite'))}">${icon('delete')}</button></td></tr>`).join('');
    empty.hidden=rows.length>0;empty.textContent=kind==='rule'?t('noRules'):t('noWhite');
  }
  function render(){renderPanel($('#settingsPanel-rules'),'rule');renderPanel($('#settingsPanel-whitelist'),'white');}
  editor.addEventListener('click',event=>{
    const add=event.target.closest('[data-dictionary-add]');if(add){if(selection||selectedSourceText()){void saveSelected(add.dataset.dictionaryAdd);return;}openDialog(add.dataset.dictionaryAdd,-1,'',add);return;}
    const edit=event.target.closest('[data-dictionary-edit]');if(edit){openDialog('rule',Number(edit.dataset.dictionaryEdit),'',edit);return;}
    const remove=event.target.closest('[data-dictionary-delete]');if(remove){const panel=remove.closest('#settingsPanel-rules')?'rule':'white';askDelete(panel,Number(remove.dataset.dictionaryDelete),remove);}
  });
  $('#dictionaryRuleClose').onclick=$('#dictionaryRuleCancel').onclick=closeDialog;
  $('#dictionaryRuleSave').onclick=saveDialog;
  $('#dictionaryDeleteClose').onclick=$('#dictionaryDeleteCancel').onclick=closeDelete;
  $('#dictionaryDeleteApprove').onclick=applyDelete;
  phraseInput.addEventListener('input',refreshDialogDetails);
  labelList.addEventListener('click',event=>{const option=event.target.closest('[role="option"]');if(option){selectLabel(option.dataset.dictionaryLabel);}});
  labelList.addEventListener('keydown',event=>{
    const options=[...labelList.querySelectorAll('[role="option"]')];if(!options.length)return;
    const selected=Math.max(0,options.findIndex(option=>option.getAttribute('aria-selected')==='true'));
    let index=selected;
    if(event.key==='ArrowDown')index=(selected+1)%options.length;else if(event.key==='ArrowUp')index=(selected-1+options.length)%options.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=options.length-1;else if(event.key==='Enter'||event.key===' '){event.preventDefault();refreshDialogDetails();return;}else return;
    event.preventDefault();selectLabel(options[index].dataset.dictionaryLabel);options[index].scrollIntoView({block:'nearest'});
  });
  phraseInput.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();saveDialog();}});
  function trapDialogFocus(event,pane){
    if(event.key!=='Tab')return;
    const nodes=[...pane.querySelectorAll('button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter(node=>!node.hidden);
    if(!nodes.length)return;
    const first=nodes[0],last=nodes[nodes.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
  document.addEventListener('keydown',event=>{
    const activeDialog=!dialog.hidden?dialog:(!deleteDialog.hidden?deleteDialog:null);
    if(!activeDialog)return;
    if(event.key==='Escape'){event.preventDefault();if(activeDialog===dialog)closeDialog();else closeDelete();return;}
    trapDialogFocus(event,activeDialog);
  });

  const sourcePane=$('#sourceColumn .pane'),sourceHeading=$('#sourceHeading');
  if(sourcePane&&sourceHeading&&!$('#sourceInstructionHelp'))sourceHeading.insertAdjacentHTML('beforeend',` <button type="button" id="sourceInstructionHelp" class="dictionary-rule-source-help" title="${esc(t('sourceHelp'))}" aria-label="${esc(t('sourceHelp'))}">?</button>`);
  if(sourcePane)sourcePane.title=t('sourceHelp');if($('#source'))$('#source').title=t('sourceHelp');
  const review=$('#manualReview');
  if(review){
    review.classList.add('dictionary-review-v24');
    review.querySelector('.review-heading-help')?.remove();
    const controls=['reviewHintsMode','paranoid','compactMarkers','mono'].map(id=>$("#"+id)).filter(Boolean);
    if(controls.length&&!review.querySelector('.dictionary-review-options')){
      const fieldset=document.createElement('fieldset');fieldset.className='dictionary-review-options';fieldset.setAttribute('aria-label',t('rules'));
      controls.forEach(control=>{const label=control.closest('label');if(label)fieldset.appendChild(label);});
      const status=$('#resultStatus');if(status)status.before(fieldset);else review.appendChild(fieldset);
    }
    controls.forEach(control=>{control.addEventListener('change',()=>{if(control.id==='mono')document.querySelectorAll('textarea,.mirror,.rich-output').forEach(node=>node.classList.toggle('mono',control.checked));markDirty();});});
  }
  function selectedSourceText(){
    const source=$('#source');
    const text=String(source?.value.slice(source.selectionStart,source.selectionEnd)||'').trim();
    if(text)return text;
    const chosen=String(window.getSelection?.().toString()||'').trim();
    const webSelection=window.getSelection?.();
    const range=webSelection?.rangeCount?webSelection.getRangeAt(0):null;
    const formattedSource=$('#docxPreview');
    const isInside=node=>Boolean(node&&formattedSource?.contains(node));
    return chosen&&range&&isInside(range.startContainer)&&isInside(range.endContainer)?chosen:'';
  }
  function refreshSelection(){
    const nextSelection=selectedSourceText(),hadSelection=Boolean(selection);
    selection=nextSelection;
    if(!selection){window.syncSourceSelectionToOutput?.('');if(hadSelection)clearSelectionPriority(true);return;}
    const current=$('#reviewCurrent'),meta=$('#reviewMeta');
    if(current){current.textContent=`«${selection}» · ${lang==='ru'?'выделение исходного текста':'source selection'}`;current.title=current.textContent;}
    if(meta){meta.textContent=t('selectionPriority');meta.title=t('selectionPriority');}
    ['#hideCandidate','#keepCandidate'].forEach(selector=>{const action=$(selector);if(action)action.disabled=false;});
    setStatus(t('selectionReady',{value:selection}));
    window.syncSourceSelectionToOutput?.(selection);
  }
  function clearSelectionPriority(force=false){
    if(!selection&&!force)return;
    selection='';
    window.syncSourceSelectionToOutput?.('');
    const source=$('#source');if(source)source.setSelectionRange(source.selectionEnd,source.selectionEnd);
    window.getSelection?.().removeAllRanges?.();
    if(typeof window.updateReviewPosition==='function')window.updateReviewPosition();
    else{
      const current=$('#reviewCurrent'),meta=$('#reviewMeta');
      if(current)current.textContent='';
      if(meta)meta.textContent=t('reviewCandidate');
    }
  }
  ['select','mouseup','keyup'].forEach(type=>$('#source')?.addEventListener(type,()=>{clearTimeout(selectionTimer);selectionTimer=setTimeout(refreshSelection,0);}));
  ['scroll','input'].forEach(type=>$('#source')?.addEventListener(type,clearSelectionPriority));
  const formattedSource=$('#docxPreview');
  formattedSource?.addEventListener('scroll',clearSelectionPriority);
  ['#showFormatted','#showTextPreview'].forEach(selector=>$(selector)?.addEventListener('click',clearSelectionPriority));
  const sourcePreviewObserver=typeof MutationObserver==='undefined'||!formattedSource?null:new MutationObserver(clearSelectionPriority);
  if(sourcePreviewObserver)sourcePreviewObserver.observe(formattedSource,{childList:true,subtree:true});
  $('#library')?.addEventListener('change',clearSelectionPriority);
  $('#source')?.addEventListener('select',refreshSelection);
  document.addEventListener('selectionchange',()=>{if(!sourcePane)return;clearTimeout(selectionTimer);selectionTimer=setTimeout(refreshSelection,0);});
  function selectionIsValid(value){return !validate(value,'СКРЫТО');}
  async function saveSelected(kind){
    const raw=selection||selectedSourceText();
    const validation=validate(raw,'СКРЫТО');
    const value=normalise(raw);
    if(validation){
      const message=`${t('invalidSelection')} ${validation}`;
      setStatus(message);
      setTimeout(()=>setStatus(message),25);
      return false;
    }
    if(kind==='rule'){
      const rows=parseRules(),index=rows.findIndex(row=>fold(row.phrase)===fold(value));
      if(index<0)rows.push({phrase:value,label:'СКРЫТО'});else rows[index].label='СКРЫТО';
      writeRules(rows);writeWhite(parseWhite().filter(item=>fold(item)!==fold(value)));syncCustom();
    }else{
      const rows=parseWhite();if(!rows.some(item=>fold(item)===fold(value)))rows.push(value);
      writeWhite(rows);writeRules(parseRules().filter(row=>fold(row.phrase)!==fold(value)));
    }
    markDirty();const persisted=await persist();render();selection='';
    const source=$('#source');if(source)source.setSelectionRange(source.selectionEnd,source.selectionEnd);
    window.syncSourceSelectionToOutput?.('');
    await window.refreshAnonymizedPreviewImmediately?.();
    if(persisted)setStatus(t('saved',{kind:kind==='rule'?t('rule'):t('exception')}));return true;
  }
  const originalHide=$('#hideCandidate')?.onclick,originalKeep=$('#keepCandidate')?.onclick;
  if($('#hideCandidate'))$('#hideCandidate').onclick=async event=>{if(selection||selectedSourceText())await saveSelected('rule');else{await originalHide?.call(event.currentTarget,event);setTimeout(render,0);}};
  if($('#keepCandidate'))$('#keepCandidate').onclick=async event=>{if(selection||selectedSourceText())await saveSelected('white');else{await originalKeep?.call(event.currentTarget,event);setTimeout(render,0);}};
  const guide=$('.usage-guide');
  if(guide&&!guide.querySelector('[data-dictionary-usage]'))guide.insertAdjacentHTML('beforeend',`<section data-dictionary-usage><h3>${esc(t('usageTitle'))}</h3><p>${esc(t('usageText'))}</p></section>`);
  const profile=$('#profile');
  rulesInput.addEventListener('input',render);
  whiteInput.addEventListener('input',render);
  document.addEventListener('dictionary-rules-sync',()=>{unsavedProfileWarning='';delete document.body?.dataset?.dictionaryUnsavedProfileWarning;render();});
  if(profile){const baseChange=profile.onchange;profile.onchange=async event=>{await baseChange?.call(profile,event);render();};}
  render();
})();
