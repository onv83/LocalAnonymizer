const wsUrl = process.argv[2];
const viewportWidth = Number(process.argv[3] || 900);
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
  width: viewportWidth,
  height: 900,
  deviceScaleFactor: 1,
  mobile: false,
});
await evaluate(`new Promise((resolve,reject)=>{let attempts=0;const ready=()=>{if(document.querySelector('#reviewTitle')&&document.querySelector('#workflowStatusBar'))return resolve(true);if(++attempts>100)return reject(new Error('production DOM did not load'));setTimeout(ready,25)};ready()})`);

const result = await evaluate(`(() => {
  const style = element => {
    const value = getComputedStyle(element);
    return {
      fontFamily: value.fontFamily,
      fontSize: value.fontSize,
      fontWeight: value.fontWeight,
      lineHeight: value.lineHeight,
      letterSpacing: value.letterSpacing,
      textTransform: value.textTransform,
    };
  };
  const titleSelectors = [
    '#anonymizationSettings>summary',
    '#reviewTitle',
    '#restoreFileHeading',
    '.usage-guide>summary',
    '#selftestSection>summary',
    '#detectionCategories>summary',
  ];
  const controlSelectors = [
    '#settingsTab-rules',
    '#reviewPrev',
    '#chooseRestoreFile',
    '#applyNow',
  ];
  const titleStyles = titleSelectors.map(selector => ({ selector, style: style(document.querySelector(selector)) }));
  const controlStyles = controlSelectors.map(selector => ({ selector, style: style(document.querySelector(selector)) }));
  const documentHost = document.querySelector('#docxPreview');
  documentHost.hidden = false;
  documentHost.innerHTML = '<span id="documentTypographyProbe" style="font-family:Courier New,monospace;font-size:18pt;font-weight:600;line-height:1.8">Synthetic document text</span>';
  const documentStyle = style(document.querySelector('#documentTypographyProbe'));
  const equalStyles = entries => entries.every(entry => JSON.stringify(entry.style) === JSON.stringify(entries[0].style));
  const equalControlTypography = entries => {
    const comparable = value => ({
      fontFamily: value.fontFamily,
      fontSize: value.fontSize,
      lineHeight: value.lineHeight,
      letterSpacing: value.letterSpacing,
      textTransform: value.textTransform,
    });
    return entries.every(entry => JSON.stringify(comparable(entry.style)) === JSON.stringify(comparable(entries[0].style)));
  };
  return {
    innerWidth: window.innerWidth,
    noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
    titleStyles,
    controlStyles,
    titlesEqual: equalStyles(titleStyles),
    controlsEqual: equalControlTypography(controlStyles),
    documentStyle,
  };
})()`);
result.ok = result.innerWidth === viewportWidth
  && result.noHorizontalOverflow
  && result.titlesEqual
  && result.controlsEqual
  && result.titleStyles[0].style.fontSize === '15px'
  && result.titleStyles[0].style.fontWeight === '700'
  && result.titleStyles[0].style.lineHeight === '19.5px'
  && result.titleStyles[0].style.letterSpacing === 'normal'
  && result.titleStyles[0].style.textTransform === 'none'
  && result.controlStyles[0].style.fontSize === '13px'
  && result.documentStyle.fontFamily.toLowerCase().includes('courier new')
  && result.documentStyle.fontSize === '24px'
  && result.documentStyle.fontWeight === '600'
  && result.documentStyle.lineHeight === '43.2px';
console.log(JSON.stringify(result));
await send('Browser.close');
ws.close();
if (!result.ok) process.exitCode = 1;
