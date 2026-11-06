const wsUrl = process.argv[2];
const viewportWidth = Number(process.argv[3] || 1600);
if (!wsUrl) throw new Error('Pass a DevTools page WebSocket URL');

const ws = new WebSocket(wsUrl);
let callId = 0;
const pending = new Map();
ws.onmessage = event => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
};
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++callId;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text||JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: viewportWidth, height: 920, deviceScaleFactor: 1, mobile: false });
await evaluate(`new Promise((resolve,reject)=>{let n=0;const ready=()=>{if(document.querySelector('#dictionaryRuleDialog')&&document.querySelector('#rules')&&document.querySelector('#docxPreview'))return resolve();if(++n>100)return reject(new Error('dictionary editor did not load'));setTimeout(ready,25)};ready()})`);

const result = await evaluate(`(async()=>{
  const $=s=>document.querySelector(s), wait=(ms=45)=>new Promise(r=>setTimeout(r,ms)), waitFor=async(predicate,timeout=1200)=>{const deadline=Date.now()+timeout;while(!predicate()&&Date.now()<deadline)await wait(25);return predicate();};
  let anonymizeCalls=0;
  const click=s=>$(s).click();
  window.pywebview={api:{save_profile:async()=>({ok:false}),anonymize_text:async()=>{anonymizeCalls++;return {mapping:{},parts:[],warnings:[],candidates:[],counts:{},total:0};}}};
  window.confirm=()=>false;

  const docx=$('#docxPreview'), output=$('#richOutput');
  docx.hidden=false; output.hidden=false;
  docx.innerHTML='<span id="inside">inside source</span>';
  output.innerHTML='<span id="outside">outside output</span>';
  await wait();
  const mixed=document.createRange();
  mixed.setStart($('#inside').firstChild,0); mixed.setEnd($('#outside').firstChild,6);
  getSelection().removeAllRanges(); getSelection().addRange(mixed); await wait();
  const mixedIgnored=!$('#reviewCurrent').textContent.includes('inside source');
  getSelection().removeAllRanges();
  docx.innerHTML='<div style="height:2400px"><span>ALD</span></div>';docx.scrollTop=520;await wait();
  last={mapping:{},candidates:[],counts:{},parts:[{t:'text',s:'padding\\n'.repeat(800)},{t:'ph',orig:'ALD',s:'[СКРЫТО-1]',s0:0,s1:3}],total:1,hintCount:0,warnings:[]};renderOutput();
  $('#source').value='ALD'; $('#source').setSelectionRange(0,3); $('#source').dispatchEvent(new Event('select')); await wait(100);
  const sourceSelectionActionable=$('#reviewCurrent').textContent.includes('ALD')&&!$('#hideCandidate').disabled&&!$('#keepCandidate').disabled;
  const sourceSelectionMirrored=Boolean($('#richOutput .source-selection-match')?.textContent.includes('[СКРЫТО-1]'));
  const sourceSelectionKeepsLeftScroll=Math.abs(docx.scrollTop-520)<=1;
  const formattedSelectionOutput=$('#anonymizedDocxPreview');formattedSelectionOutput.innerHTML='<p>[СКРЫТО-1]</p>';formattedSelectionOutput.hidden=false;output.hidden=true;$('#source').setSelectionRange(0,3);$('#source').dispatchEvent(new Event('select'));await wait(80);
  const sourceSelectionKeepsFormattedView=!formattedSelectionOutput.hidden&&output.hidden;
  const selectedAddPayload=[],nativeImmediateRefresh=window.refreshAnonymizedPreviewImmediately;window.refreshAnonymizedPreviewImmediately=async()=>{};window.pywebview.api.save_profile=async(...payload)=>{selectedAddPayload.push(payload);return {ok:true};};click('[data-dictionary-add="rule"]');await wait(80);
  const selectedAddMatchesHide=$('#dictionaryRuleDialog').hidden&&$('#rules').value.includes('ALD => СКРЫТО')&&selectedAddPayload.length===1&&selectedAddPayload[0][1].includes('ALD => СКРЫТО');
  $('#rules').value='';$('#rules').dispatchEvent(new Event('input',{bubbles:true}));window.pywebview.api.save_profile=async()=>({ok:false});clearTimeout(debounceTimer);formattedSelectionOutput.hidden=true;output.hidden=false;window.refreshAnonymizedPreviewImmediately=nativeImmediateRefresh;await wait();
  $('#source').setSelectionRange(0,0);$('#source').dispatchEvent(new Event('select'));await wait(100);
  last={mapping:{},candidates:[],counts:{},parts:[{t:'text',s:'пилотирования'}],total:0,hintCount:0,warnings:[]};renderOutput();
  const sourceSelectionUnchangedRange=Boolean(textRangeForOccurrence($('#richOutput'),'пилотирования',0)?.range);
  window.syncSourceSelectionToOutput('пилотирования');
  const sourceSelectionUnchangedMirrored=Boolean($('#richOutput .source-selection-match')?.textContent.includes('пилотирования'));
  const sourceSelectionUnchangedHtml=$('#richOutput').innerHTML;
  const sourceSelectionUnchangedCurrent=$('#reviewCurrent').textContent;
  const reviewOptions=$('.dictionary-review-options');
  const optionLabels=[...reviewOptions.querySelectorAll(':scope > label')];
  const reviewOptionsHaveFourTooltipOnlyRows=optionLabels.length===4&&optionLabels.every(label=>label.title&&getComputedStyle(label.querySelector('small')).display==='none')&&reviewOptions.getBoundingClientRect().bottom<=$('#manualReview').getBoundingClientRect().bottom;
  $('#source').setSelectionRange(0,0); $('#source').dispatchEvent(new Event('select')); await wait();
  getSelection().removeAllRanges();

  $('#source').value='[ФИО-١]'; $('#source').setSelectionRange(0,8); click('#hideCandidate'); await wait();
  const markerRejected=$('#rules').value==='' && !/saved\.|сохранено\./i.test($('#settingsStatus').textContent);
  $('#source').value='';$('#source').setSelectionRange(0,0);$('#source').dispatchEvent(new Event('select'));await wait();

  click('[data-dictionary-add="rule"]'); $('#dictionaryRulePhrase').value='   '; click('#dictionaryRuleSave');
  const whitespaceRejected=!$('#dictionaryRuleDialog').hidden && $('#dictionaryRuleError').textContent.length>0 && $('#rules').value==='';
  click('#dictionaryRuleCancel');

  $('#rules').value='synthetic phrase => ФИО'; $('#rules').dispatchEvent(new Event('input',{bubbles:true})); await wait();
  const ruleEmpty=$('#settingsPanel-rules .dictionary-rule-empty'),emptyHiddenWhenRulesExist=ruleEmpty.hidden&&getComputedStyle(ruleEmpty).display==='none';
  click('[data-dictionary-edit="0"]');
  [...$('#dictionaryRuleLabelList').querySelectorAll('[role="option"]')].find(n=>n.dataset.dictionaryLabel==='СЕКРЕТ').click();
  click('#dictionaryRuleSave'); await wait();
  const editConfirmed=!$('#dictionaryRuleDialog').hidden && $('#rules').value==='synthetic phrase => ФИО';
  click('#dictionaryRuleCancel');

  $('#rules').value=''; $('#rules').dispatchEvent(new Event('input',{bubbles:true})); await wait();
  const scroll=$('#settingsPanel-rules .dictionary-rule-scroll'),empty=$('#settingsPanel-rules .dictionary-rule-empty');
  const emptyBottomAligned=Math.abs(empty.getBoundingClientRect().bottom-scroll.getBoundingClientRect().bottom)<=1;

  click('[data-dictionary-add="rule"]');
  $('#dictionaryRulePhrase').value='persisted only in session';
  [...$('#dictionaryRuleLabelList').querySelectorAll('[role="option"]')].find(n=>n.dataset.dictionaryLabel==='СЕКРЕТ').click();
  click('#dictionaryRuleSave'); await wait(380);
  const failedSaveStatus=$('#settingsStatus').textContent,failedSaveDataset=document.body?.dataset?.dictionaryUnsavedProfileWarning||'';
  const failedSaveHonest=$('#rules').value.includes('persisted only in session') && /session|сеансе/i.test(failedSaveStatus);
  filePreview=true;$('#compactMarkers').checked=!$('#compactMarkers').checked;$('#compactMarkers').dispatchEvent(new Event('input',{bubbles:true}));await wait(380);
  const failedSaveSurvivesSettingsChange=/session|сеансе/i.test($('#settingsStatus').textContent)&&/session|сеансе/i.test(document.body?.dataset?.dictionaryUnsavedProfileWarning||'');

  const queueKeepPayload=[];
  $('#source').value='queue source';$('#source').setSelectionRange(0,0);$('#source').dispatchEvent(new Event('input',{bubbles:true}));getSelection().removeAllRanges();
  last={mapping:{},candidates:[],counts:{},parts:[{t:'hint',kind:'возможное имя собственное',orig:'queue exception',s0:0,s:'queue exception'}],total:0,hintCount:1,warnings:[]};reviewedHints.clear();reviewIndex=0;renderOutput();
  window.pywebview.api.save_profile=async(...payload)=>{queueKeepPayload.push(payload);return {ok:true};};
  const keepCallsBefore=anonymizeCalls;click('#keepCandidate');await wait();
  const queueKeepPersists=$('#whitelist').value.includes('queue exception')&&queueKeepPayload.length===1&&queueKeepPayload[0][2].includes('queue exception')&&anonymizeCalls>keepCallsBefore;

  $('#source').setSelectionRange(0,0);getSelection().removeAllRanges();
  last={mapping:{},candidates:[],counts:{},parts:[{t:'hint',kind:'возможное имя собственное',orig:'queue hide',s0:0,s:'queue hide'}],total:0,hintCount:1,warnings:[]};reviewedHints.clear();reviewIndex=0;renderOutput();
  window.pywebview.api.save_profile=async()=>({ok:false});
  click('#hideCandidate');await wait();
  const queueHideFailureVisible=/not saved|не сохранено/i.test($('#resultStatus').textContent)&&/not saved|не сохранено/i.test(document.body.dataset.dictionaryUnsavedProfileWarning||'');

  const queueHidePayload=[];
  $('#source').setSelectionRange(0,0);getSelection().removeAllRanges();
  last={mapping:{},candidates:[],counts:{},parts:[{t:'hint',kind:'возможное имя собственное',orig:'queue hide persisted',s0:0,s:'queue hide persisted'}],total:0,hintCount:1,warnings:[]};reviewedHints.clear();reviewIndex=0;renderOutput();
  window.pywebview.api.save_profile=async(...payload)=>{queueHidePayload.push(payload);return {ok:true};};
  click('#hideCandidate');await wait();
  const queueHidePersists=$('#rules').value.includes('queue hide persisted => СКРЫТО')&&queueHidePayload.length===1&&queueHidePayload[0][1].includes('queue hide persisted => СКРЫТО')&&$('#settingsPanel-rules tbody').textContent.includes('queue hide persisted');

  const savedPayload=[];
  window.pywebview.api.save_profile=async(...payload)=>{savedPayload.push(payload);return {ok:true};};
  click('[data-dictionary-add="rule"]');
  $('#dictionaryRulePhrase').value='persisted through bridge';
  click('#dictionaryRuleSave'); await wait();
  const successfulPersistence=savedPayload.length===1 && savedPayload[0][1].includes('persisted through bridge') && !/session|сеансе/i.test($('#settingsStatus').textContent);

  window.pywebview.api.load_profile=async()=>({dictionary:{'profile-loaded rule':'ФИО'},whitelist:['profile-loaded exception'],paranoid:false,uncertain_mode:'review'});
  await $('#profile').onchange(new Event('change')); await wait();
  const profileTabSynchronized=$('#settingsPanel-rules tbody').textContent.includes('profile-loaded rule') && $('#settingsPanel-whitelist tbody').textContent.includes('profile-loaded exception');

  click('[data-dictionary-add="rule"]');
  const dialog=$('#dictionaryRuleDialog').getBoundingClientRect(), list=$('#dictionaryRuleLabelList').getBoundingClientRect(), actions=$('.dictionary-rule-actions').getBoundingClientRect();
  const dialogContained=list.top>=dialog.top&&list.bottom<=dialog.bottom&&actions.bottom<=dialog.bottom;
  const keyboardListbox=$('#dictionaryRuleLabelList').getAttribute('role')==='listbox';
  const labelOptions=[...$('#dictionaryRuleLabelList').querySelectorAll('[role="option"]')];
  const categoryInventory=labelOptions.length===49&&!labelOptions.some(option=>option.dataset.dictionaryLabel==='HINTS');
  const narrowNoOverflow=document.documentElement.scrollWidth<=window.innerWidth;
  const box=node=>node.getBoundingClientRect();
  const sourceCard=box($('#sourceColumn>.pane')),outputCard=box($('#anonymizedColumn>.pane')),settingsCard=box($('#anonymizationSettings')),reviewCard=box($('#manualReview')),workbench=box($('#anonymizationSettings .settings-workbench')),sourceText=box($('#sourceColumn .editor-stack')),outputText=box($('#richOutput'));
  const close=(actual,expected)=>Math.abs(actual-expected)<=1;
  const desktopGeometry=window.innerWidth!==1600||(
    close(sourceCard.height,569)&&close(outputCard.height,569)&&close(sourceText.height,377)&&close(outputText.height,377)&&
    close(settingsCard.height,330)&&close(reviewCard.height,330)&&close(workbench.height,328)&&
    close(settingsCard.top-sourceCard.bottom,14)&&close(reviewCard.top-outputCard.bottom,14)&&
    close(sourceCard.top,outputCard.top)&&close(sourceCard.bottom,outputCard.bottom)&&close(settingsCard.top,reviewCard.top)&&close(settingsCard.bottom,reviewCard.bottom)
  );
  const geometryMetrics={sourceCard:sourceCard.height,outputCard:outputCard.height,sourceText:sourceText.height,outputText:outputText.height,settings:settingsCard.height,review:reviewCard.height,workbench:workbench.height,sourceGap:settingsCard.top-sourceCard.bottom,reviewGap:reviewCard.top-outputCard.bottom,sourceAligned:[sourceCard.top,outputCard.top,sourceCard.bottom,outputCard.bottom],lowerAligned:[settingsCard.top,reviewCard.top,settingsCard.bottom,reviewCard.bottom]};

  const sourceFormatted=$('#docxPreview');sourceFormatted.hidden=false;sourceFormatted.innerHTML='<div style="height:2400px"><span>preserve candidate</span></div>';sourceFormatted.scrollTop=520;
  $('#source').value='preserve candidate';filePreview=false;currentPreviewFormat='docx';
  window.pywebview.api.anonymize_text=async()=>({mapping:{},parts:[{t:'hint',kind:'возможное имя собственное',orig:'preserve candidate',s:'preserve candidate',s0:0}],warnings:[],candidates:[],counts:{},total:0});
  const sourceScrollBeforeRebuild=sourceFormatted.scrollTop;await anonymizeText();await wait(80);
  const sourceScrollAfterRebuild=sourceFormatted.scrollTop;
  const sourceFormattedScrollPositionPreserved=Math.abs(sourceScrollAfterRebuild-sourceScrollBeforeRebuild)<=1;

  sourceFormatted.hidden=false;sourceFormatted.innerHTML='<p data-preview-anchor="body/b0"><span data-source-start="0" data-source-end="3">ALD</span> <strong><span data-source-start="4" data-source-end="7">ООО</span></strong></p>';$('#source').value='ALD ООО';filePreview=true;selected='projection-document';currentPreviewFormat='docx';restoredParts.clear();last={mapping:{'[СКРЫТО-1]':'ALD'},candidates:[],counts:{'СКРЫТО':1},parts:[{t:'ph',s0:0,s1:3,orig:'ALD',s:'[СКРЫТО-1]'}, {t:'text',s:' ООО'}],total:1,hintCount:0,warnings:[]};
  const formattedProjectionMapSize=formattedProjectionMap($('#docxPreview')).length,formattedProjectionPartCount=formattedProjectionParts().length;
  const formattedProjectionRendered=typeof renderLiveFormattedProjection==='function'&&renderLiveFormattedProjection();
  const formattedProjectionHtml=$('#anonymizedDocxPreview').innerHTML;
  const formattedProjectionUpdatesLive=formattedProjectionRendered&&$('#anonymizedDocxPreview').textContent.includes('[СКРЫТО-1]')&&$('#anonymizedDocxPreview').textContent.includes('ООО')&&sourceFormatted.textContent==='ALD ООО';
  let liveFormattedBridgeCalls=0;window.pywebview.api.preview_anonymized_document=async()=>{liveFormattedBridgeCalls++;return {format:'docx',rich_html:'<p>unexpected backend preview</p>'};};window.pywebview.api.anonymize_text=async()=>({mapping:{'[СКРЫТО-1]':'ALD'},candidates:[],counts:{'СКРЫТО':1},parts:[{t:'ph',s0:0,s1:3,orig:'ALD',s:'[СКРЫТО-1]'}, {t:'text',s:' ООО'}],total:1,hintCount:0,warnings:[]});await anonymizeText();await wait(50);
  const formattedProjectionUpdatesOnSettingsChange=liveFormattedBridgeCalls===0&&!$('#anonymizedDocxPreview').hidden&&$('#anonymizedDocxPreview').textContent.includes('[СКРЫТО-1]');

  sourceFormatted.innerHTML='<p data-preview-anchor="body/b0"><span data-source-start="0" data-source-end="2">😀 </span><span data-source-start="2" data-source-end="5">ALD</span></p>';$('#source').value='😀 ALD';restoredParts.clear();last={mapping:{'[СКРЫТО-1]':'ALD'},candidates:[],counts:{'СКРЫТО':1},parts:[{t:'ph',s0:2,s1:5,orig:'ALD',s:'[СКРЫТО-1]'}],total:1,hintCount:0,warnings:[]};
  const formattedProjectionKeepsUnicodeOffsets=renderLiveFormattedProjection()&&$('#anonymizedDocxPreview').textContent.includes('[СКРЫТО-1]');

  sourceFormatted.innerHTML='<p data-preview-anchor="body/b0"><span data-source-start="0" data-source-end="8">P-before</span></p><table><tbody><tr data-preview-anchor="body/b1/r0"><td><p data-preview-anchor="body/b1/r0/c0/b0"><span data-source-start="17" data-source-end="20">ALD</span></p></td></tr></tbody></table><p data-preview-anchor="body/b2"><span data-source-start="9" data-source-end="16">P-after</span></p>';$('#source').value=['P-before','P-after','ALD'].join(String.fromCharCode(10));restoredParts.clear();last={mapping:{'[СКРЫТО-1]':'ALD'},candidates:[],counts:{'СКРЫТО':1},parts:[{t:'ph',s0:17,s1:20,orig:'ALD',s:'[СКРЫТО-1]'}],total:1,hintCount:0,warnings:[]};
  const formattedProjectionHandlesInterleavedBodyBlocks=renderLiveFormattedProjection()&&$('#anonymizedDocxPreview').textContent.includes('[СКРЫТО-1]');

  sourceFormatted.innerHTML='<table><tbody><tr data-preview-anchor="body/b0/r0"><td><p data-preview-anchor="body/b0/r0/c0/b0"><span data-source-start="0" data-source-end="1">A</span></p></td><td><p data-preview-anchor="body/b0/r0/c1/b0"><span data-source-start="2" data-source-end="3">B</span></p></td></tr></tbody></table>';$('#source').value=['A','B'].join(String.fromCharCode(10));restoredParts.clear();last={mapping:{'[СКРЫТО-1]':'cross-cell'},candidates:[],counts:{'СКРЫТО':1},parts:[{t:'ph',s0:0,s1:3,orig:['A','B'].join(String.fromCharCode(10)),s:'[СКРЫТО-1]'}],total:1,hintCount:0,warnings:[]};
  const formattedProjectionHidesCrossCellRange=renderLiveFormattedProjection()&&$('#anonymizedDocxPreview').textContent==='[СКРЫТО-1]';
  const markerStyle=getComputedStyle($('#anonymizedDocxPreview').querySelector('.formatted-projection-marker'));
  const formattedProjectionMarkerWraps=markerStyle.whiteSpace==='normal'&&markerStyle.overflowWrap==='anywhere';

  $('#source').value='ALD ООО ALD';last={mapping:{'[СКРЫТО-1]':'ALD'},candidates:[],counts:{'СКРЫТО':2},parts:[{t:'ph',s0:0,s1:3,orig:'ALD',s:'[СКРЫТО-1]'},{t:'text',s:' ООО '},{t:'ph',s0:8,s1:11,orig:'ALD',s:'[СКРЫТО-1]'}],total:2,hintCount:0,warnings:[]};const originalArrayFrom=Array.from;let sourceArrayConversions=0;Array.from=function(value,...args){if(value===$('#source').value)sourceArrayConversions++;return originalArrayFrom.call(Array,value,...args);};try{renderMirror();}finally{Array.from=originalArrayFrom;}const renderMirrorUsesOneSourceConversion=sourceArrayConversions===1;

  sourceFormatted.hidden=true;sourceFormatted.innerHTML='';await wait(50);filePreview=true;selected='synthetic-document';currentPreviewFormat='docx';$('#anonymizedDocxPreview').hidden=true;$('#richOutput').hidden=false;
  let formattedPreviewCalls=0;
  window.pywebview.api.anonymize_text=async()=>({mapping:{},parts:[],warnings:[],candidates:[],counts:{},total:0});
  window.pywebview.api.preview_anonymized_document=async()=>{formattedPreviewCalls++;return {format:'docx',rich_html:'<div style="height:2400px">deferred formatted output '+formattedPreviewCalls+'</div>'};};
  await anonymizeText();await wait(80);
  const formattedPreviewDeferredInTextMode=formattedPreviewCalls===0;
  $('#showAnonymizedFormatted').click();await waitFor(()=>formattedPreviewCalls===1&&!$('#anonymizedDocxPreview').hidden&&$('#anonymizedDocxPreview').textContent.includes('deferred formatted output'));
  const formattedPreviewPreparedText=$('#anonymizedDocxPreview').textContent,formattedPreviewPreparedHidden=$('#anonymizedDocxPreview').hidden;
  const formattedPreviewPreparedOnDemand=formattedPreviewCalls===1&&!formattedPreviewPreparedHidden&&formattedPreviewPreparedText.includes('deferred formatted output');
  const cachedRules=$('#rules').value;
  $('#rules').value='cache probe => СКРЫТО';await anonymizeText();await wait(50);$('#showAnonymizedFormatted').click();await wait(80);
  $('#rules').value=cachedRules;await anonymizeText();await wait(50);$('#showAnonymizedFormatted').click();await wait(80);
  const formattedPreviewReusesMatchingSettingsCache=formattedPreviewCalls===2&&$('#anonymizedDocxPreview').textContent.includes('deferred formatted output 1');

  let resolveStaleFormattedPreview;window.pywebview.api.preview_anonymized_document=()=>new Promise(resolve=>{resolveStaleFormattedPreview=resolve;});window.pywebview.api.anonymize_text=async()=>({mapping:{},parts:[],warnings:[],candidates:[],counts:{},total:0});$('#anonymizedDocxPreview').innerHTML='';$('#anonymizedDocxPreview').hidden=true;$('#richOutput').hidden=false;filePreview=true;selected='stale-preview-document';currentPreviewFormat='docx';const stalePreviewRequest=showAnonymizedFormattedPreview();await wait(40);await anonymizeText();resolveStaleFormattedPreview({format:'docx',rich_html:'<p>stale preview</p>'});await stalePreviewRequest;const staleFormattedPreviewReenablesButton=!$('#showAnonymizedFormatted').disabled;

  let resolveFirstPreview,resolveSecondPreview,overlappingPreviewCalls=0;window.pywebview.api.preview_anonymized_document=()=>new Promise(resolve=>{overlappingPreviewCalls++;if(overlappingPreviewCalls===1)resolveFirstPreview=resolve;else resolveSecondPreview=resolve;});$('#anonymizedDocxPreview').innerHTML='';$('#anonymizedDocxPreview').hidden=true;$('#richOutput').hidden=false;filePreview=true;selected='overlapping-preview-document';currentPreviewFormat='docx';const firstPreviewRequest=showAnonymizedFormattedPreview();await wait(40);const secondPreviewRequest=showAnonymizedFormattedPreview();await wait(40);resolveFirstPreview({format:'docx',rich_html:'<p>first preview</p>'});await wait(40);const stalePreviewKeepsLoading=$('#showAnonymizedFormatted').disabled;resolveSecondPreview({format:'docx',rich_html:'<p>second preview</p>'});await Promise.all([firstPreviewRequest,secondPreviewRequest]);const overlappingPreviewReenablesAfterLatest=stalePreviewKeepsLoading&&!$('#showAnonymizedFormatted').disabled&&$('#anonymizedDocxPreview').textContent.includes('second preview');

  $('#source').value='scroll preservation';filePreview=true;selected='synthetic-scroll-document';currentPreviewFormat='docx';
  const formattedOutput=$('#anonymizedDocxPreview');formattedOutput.innerHTML='<div style="height:2400px">old formatted output</div>';setAnonymizedPreviewMode(true);formattedOutput.scrollTop=520;
  window.pywebview.api.anonymize_text=async()=>({mapping:{},parts:[],warnings:[],candidates:[],counts:{},total:0});
  window.pywebview.api.preview_anonymized_document=async()=>({format:'docx',rich_html:'<div style="height:2400px">new formatted output</div>'});
  const scrollBeforeRebuild=formattedOutput.scrollTop,capturedOutputPosition=previewScrollPosition(activeAnonymizedPreview());await anonymizeText();await wait(80);$('#showAnonymizedFormatted').click();await wait(100);
  const scrollAfterRebuild=formattedOutput.scrollTop;
  const formattedScrollPositionPreserved=Math.abs(scrollAfterRebuild-scrollBeforeRebuild)<=1;

  $('#rules').value='';sourceFormatted.hidden=false;sourceFormatted.innerHTML='<p data-preview-anchor="body/b0"><span data-source-start="0" data-source-end="6">Повтор</span></p><p data-preview-anchor="body/b1"><span data-source-start="7" data-source-end="13">Повтор</span></p><p data-preview-anchor="body/b2"><span data-source-start="14" data-source-end="20">Повтор</span></p>';formattedOutput.hidden=false;output.hidden=true;$('#source').value=['Повтор','Повтор','Повтор'].join(String.fromCharCode(10));filePreview=true;selected='repeated-rule-document';currentPreviewFormat='docx';last={mapping:{},candidates:[],counts:{},parts:[{t:'text',s:$('#source').value}],total:0,hintCount:0,warnings:[]};renderOutput();await wait();window.pywebview.api.save_profile=async()=>({ok:true});window.pywebview.api.anonymize_text=async()=>({mapping:{'[СКРЫТО-1]':'Повтор'},candidates:[],counts:{'СКРЫТО':3},parts:[{t:'ph',s0:0,s1:6,orig:'Повтор',s:'[СКРЫТО-1]'},{t:'text',s:String.fromCharCode(10)},{t:'ph',s0:7,s1:13,orig:'Повтор',s:'[СКРЫТО-1]'},{t:'text',s:String.fromCharCode(10)},{t:'ph',s0:14,s1:20,orig:'Повтор',s:'[СКРЫТО-1]'}],total:3,hintCount:0,warnings:[]});$('#source').setSelectionRange(0,6);$('#source').dispatchEvent(new Event('select'));await wait(80);click('[data-dictionary-add="rule"]');await waitFor(()=>[...formattedOutput.querySelectorAll('.formatted-projection-marker')].length===3&&formattedOutput.textContent.includes('[СКРЫТО-1]')&&!formattedOutput.textContent.includes('Повтор'),250);
  const selectedRuleMarkerCount=[...formattedOutput.querySelectorAll('.formatted-projection-marker')].length,selectedRuleFormattedText=formattedOutput.textContent;
  const selectedRuleMasksEveryOccurrence=!formattedOutput.hidden&&output.hidden&&selectedRuleMarkerCount===3&&!selectedRuleFormattedText.includes('Повтор');

  return {mixedIgnored,sourceSelectionActionable,sourceSelectionMirrored,sourceSelectionKeepsLeftScroll,sourceSelectionKeepsFormattedView,selectedAddMatchesHide,sourceSelectionUnchangedMirrored,sourceSelectionUnchangedHtml,sourceSelectionUnchangedCurrent,sourceSelectionUnchangedRange,reviewOptionsHaveFourTooltipOnlyRows,markerRejected,whitespaceRejected,emptyHiddenWhenRulesExist,editConfirmed,emptyBottomAligned,failedSaveHonest,failedSaveSurvivesSettingsChange,queueKeepPersists,queueHideFailureVisible,queueHidePersists,successfulPersistence,profileTabSynchronized,sourceFormattedScrollPositionPreserved,formattedProjectionUpdatesLive,formattedProjectionUpdatesOnSettingsChange,formattedProjectionKeepsUnicodeOffsets,formattedProjectionHandlesInterleavedBodyBlocks,formattedProjectionHidesCrossCellRange,formattedProjectionMarkerWraps,renderMirrorUsesOneSourceConversion,formattedProjectionRendered,formattedProjectionHtml,formattedProjectionMapSize,formattedProjectionPartCount,sourceScrollBeforeRebuild,sourceScrollAfterRebuild,formattedPreviewDeferredInTextMode,formattedPreviewPreparedOnDemand,formattedPreviewPreparedText,formattedPreviewReusesMatchingSettingsCache,staleFormattedPreviewReenablesButton,overlappingPreviewReenablesAfterLatest,formattedPreviewCalls,formattedPreviewText:$('#anonymizedDocxPreview').textContent,formattedScrollPositionPreserved,selectedRuleMasksEveryOccurrence,selectedRuleMarkerCount,selectedRuleFormattedText,scrollBeforeRebuild,capturedOutputPosition,scrollAfterRebuild,dialogContained,keyboardListbox,categoryInventory,narrowNoOverflow,desktopGeometry,geometryMetrics,language:document.documentElement.lang};
})()`);
const failed = Object.entries(result).filter(([, value])=>value===false).map(([key])=>key);
const ok = Object.entries(result).filter(([, value])=>typeof value==='boolean').every(([, value])=>value);
const payload = ok ? { ok, failed, ...result } : { ok, failed, formattedPreviewCalls:result.formattedPreviewCalls, formattedPreviewText:result.formattedPreviewText, formattedPreviewPreparedText:result.formattedPreviewPreparedText, formattedPreviewPreparedHidden:result.formattedPreviewPreparedHidden, selectedRuleMarkerCount:result.selectedRuleMarkerCount, selectedRuleFormattedText:result.selectedRuleFormattedText, sourceSelectionKeepsFormattedView:result.sourceSelectionKeepsFormattedView, language:result.language };
console.log(JSON.stringify(payload));
ws.close();
if (!ok) process.exitCode = 1;
