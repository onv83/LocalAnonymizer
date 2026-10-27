const wsUrl = process.argv[2];
const workspaceWidth = Number(process.argv[3] || 900);
const useSystemClipboard = process.argv[4] === '--system-clipboard';
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
await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++callId;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
};
await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', {
  width: workspaceWidth, height: 900, deviceScaleFactor: 1, mobile: false,
});
if (useSystemClipboard) {
  await send('Browser.setPermission', { permission: { name: 'clipboard-read' }, setting: 'granted' });
  await send('Browser.setPermission', { permission: { name: 'clipboard-write' }, setting: 'granted' });
}
await evaluate(`new Promise((resolve,reject)=>{let attempts=0;const ready=()=>{if(['source','richOutput','docxPreview','anonymizedDocxPreview'].every(id=>document.querySelector('#'+id))&&typeof last!=='undefined'&&last&&typeof restoredParts!=='undefined'&&typeof restoredParts.clear==='function')return resolve(true);if(++attempts>100)return reject(new Error('preview DOM did not load'));setTimeout(ready,25)};ready()})`);
await evaluate(`(() => {
  const source=document.querySelector('#source');
  source.value='AAA SELECTED BBB';
  source.style.cssText+=';font:18px/24px monospace;white-space:pre';
  const rich=document.querySelector('#richOutput');
  rich.innerHTML='<span data-select-start>AAA </span><button class="mark-replacement" data-part="0">[NAME-1]</button><span data-select-end> BBB</span>';
  rich.style.cssText+=';font-size:18px;line-height:24px';
  const formatted='<div style="font-size:18px;line-height:24px;white-space:nowrap"><span data-select-start>AAA </span><strong>SELECTED</strong><span data-select-end> BBB</span></div>';
  for(const id of ['docxPreview','anonymizedDocxPreview']){
    const pane=document.querySelector('#'+id);
    pane.innerHTML=formatted;
  }
  last.parts=[{t:'ph',secret:false,orig:'synthetic-value'}];
  restoredParts.clear();
  window.__copySelection='';
  window.__copyTrusted=false;
  document.addEventListener('copy',event=>{
    const active=document.activeElement;
    window.__copySelection=active?.tagName==='TEXTAREA'
      ? active.value.slice(active.selectionStart,active.selectionEnd)
      : String(window.getSelection());
    window.__copyTrusted=event.isTrusted;
    if (!${useSystemClipboard ? 'true' : 'false'}) event.preventDefault();
  },true);
  return true;
})()`);

async function mouseDrag(selector, textarea = false) {
  const point = await evaluate(`(() => {
    const selector=${JSON.stringify(selector)};
    const textPreview=document.querySelector('#textPreview');
    const sourceFormatted=document.querySelector('#docxPreview');
    const rich=document.querySelector('#richOutput');
    const anonymizedFormatted=document.querySelector('#anonymizedDocxPreview');
    if(selector==='#source'){textPreview.hidden=false;sourceFormatted.hidden=true;}
    if(selector==='#docxPreview'){textPreview.hidden=true;sourceFormatted.hidden=false;}
    if(selector==='#richOutput'){rich.hidden=false;anonymizedFormatted.hidden=true;}
    if(selector==='#anonymizedDocxPreview'){rich.hidden=true;anonymizedFormatted.hidden=false;}
    const element=document.querySelector(selector);
    element.scrollIntoView({block:'center'});
    if(${textarea}){
      const bounds=element.getBoundingClientRect(),style=getComputedStyle(element);
      const canvas=document.createElement('canvas'),context=canvas.getContext('2d');context.font=style.font;
      const character=context.measureText('M').width,paddingLeft=parseFloat(style.paddingLeft)||0,paddingTop=parseFloat(style.paddingTop)||0;
      return {x:bounds.left+paddingLeft+character*4,y:bounds.top+paddingTop+12,x2:bounds.left+paddingLeft+character*12,y2:bounds.top+paddingTop+12};
    }
    const first=element.querySelector('[data-select-start]').firstChild,last=element.querySelector('[data-select-end]').firstChild;
    const startRange=document.createRange();startRange.setStart(first,1);startRange.setEnd(first,2);
    const endRange=document.createRange();endRange.setStart(last,last.length-2);endRange.setEnd(last,last.length-1);
    const start=startRange.getBoundingClientRect(),end=endRange.getBoundingClientRect();
    return {x:start.left,y:start.top+start.height/2,x2:end.right,y2:end.top+end.height/2};
  })()`);
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  for (let step = 1; step <= 12; step++) {
    await send('Input.dispatchMouseEvent', {
      type: 'mouseMoved',
      x: point.x + (point.x2 - point.x) * step / 12,
      y: point.y + (point.y2 - point.y) * step / 12,
      button: 'left', buttons: 1,
    });
  }
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x2, y: point.y2, button: 'left', clickCount: 1 });
  const selected = await evaluate(textarea
    ? `(() => {const e=document.querySelector(${JSON.stringify(selector)});return e.value.slice(e.selectionStart,e.selectionEnd)})()`
    : 'String(window.getSelection())');
  await evaluate("window.__copySelection='';window.__copyTrusted=false");
  await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: 2, windowsVirtualKeyCode: 67, nativeVirtualKeyCode: 67, key: 'c', code: 'KeyC' });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: 2, windowsVirtualKeyCode: 67, nativeVirtualKeyCode: 67, key: 'c', code: 'KeyC' });
  await evaluate('new Promise(resolve=>setTimeout(resolve,40))');
  return {
    selector,
    selected,
    eventSelection: await evaluate('window.__copySelection'),
    clipboard: useSystemClipboard
      ? await evaluate('navigator.clipboard.readText()')
      : await evaluate('window.__copySelection'),
    trustedCopy: await evaluate('window.__copyTrusted'),
  };
}

const results = [];
for (const [selector, textarea] of [['#source', true], ['#richOutput', false], ['#docxPreview', false], ['#anonymizedDocxPreview', false]]) {
  results.push(await mouseDrag(selector, textarea));
}
const markerChangedDuringSelection = await evaluate('restoredParts.has(0)');
const markerPoint = await evaluate(`(() => {
  window.getSelection().removeAllRanges();
  document.querySelector('#richOutput').hidden=false;
  document.querySelector('#anonymizedDocxPreview').hidden=true;
  const bounds=document.querySelector('#richOutput .mark-replacement').getBoundingClientRect();
  return {x:bounds.left+bounds.width/2,y:bounds.top+bounds.height/2};
})()`);
await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: markerPoint.x, y: markerPoint.y, button: 'left', clickCount: 1 });
await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: markerPoint.x, y: markerPoint.y, button: 'left', clickCount: 1 });
const markerClickStillWorks = await evaluate('restoredParts.has(0)');
const viewportWidth = await evaluate('window.innerWidth');
const ok = viewportWidth === workspaceWidth
  && results.every(result => result.selected.length > 2
    && result.selected.length < 16
    && result.selected === result.eventSelection
    && result.selected === result.clipboard
    && result.trustedCopy)
  && !markerChangedDuringSelection && markerClickStillWorks;
console.log(JSON.stringify({ ok, workspaceWidth, viewportWidth, systemClipboard:useSystemClipboard, results, markerChangedDuringSelection, markerClickStillWorks }));
await send('Browser.close');
ws.close();
if (!ok) process.exitCode = 1;
