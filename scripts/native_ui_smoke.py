"""Native WebView/CSP/clipboard smoke using synthetic data and temporary storage."""
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from local_anonymizer.app import AppApi
from local_anonymizer.csp_bridge import configure_csp_bridge


def main():
    import webview
    result = {'ok': False, 'error': 'native bridge timeout'}
    with tempfile.TemporaryDirectory(prefix='anonymizer-native-ui-') as temporary:
        root = Path(temporary)
        api = AppApi(root / 'data')
        # This API is exposed only by this disposable test, never by the product.
        def complete(payload):
            result.clear()
            result.update(payload)
            threading.Timer(0.3, window.destroy).start()
        api.complete = complete
        (root / 'probe.html').write_text('''<!doctype html><html><head>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'">
<script src="probe.js" defer></script></head><body>Native synthetic smoke</body></html>''', encoding='utf-8')
        (root / 'probe.js').write_text('''
window.addEventListener('pywebviewready', async () => {
 try {
  const api=window.pywebview.api;
  const sample='Synthetic clipboard Привет 2026';
  await api.write_clipboard_text(sample);
  if ((await api.read_clipboard_text()).text !== sample) throw Error('clipboard mismatch');
  if (await api.get_language() !== 'ru') throw Error('language mismatch');
  const anonymized=await api.anonymize_text('synthetic@example.com');
  if (!anonymized.text || anonymized.text.includes('synthetic@example.com')) throw Error('anonymization failed');
  const restored=await api.restore_text(anonymized.text,anonymized.mapping);
  if(restored.text!=='synthetic@example.com') throw Error('restore failed');
  await api.complete({ok:true, strict_csp_bridge:true, native_clipboard:true, restore:true, language:true});
 } catch(error) { await window.pywebview.api.complete({ok:false,error:String(error)}); }
});
''', encoding='utf-8')
        window = webview.create_window('Native CSP smoke', (root / 'probe.html').as_uri(), js_api=api)
        api.set_window(window)
        configure_csp_bridge(window)
        timer = threading.Timer(90, window.destroy)
        timer.start()
        try:
            webview.start(debug=False, private_mode=True)
        finally:
            timer.cancel()
            api.service.storage.connection.close()
        print(json.dumps(result))
        return 0 if result.get('ok') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
