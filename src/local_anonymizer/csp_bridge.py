"""Narrow pywebview 6 bridge compatibility with strict WebKit CSP.

Upstream creates API methods with new Function and returns bridge values via
Window.evaluate_js (which wraps code in eval). Neither is necessary. Keep the
native transport and serialization, use lexical closures, and bypass eval only
for upstream's bridge-return statements. No CSP or document policy is relaxed.
"""
from functools import wraps
import re

# Only the complete literal callback statement emitted by pywebview 6 util._call.
# JSON is escaped by upstream for a single-quoted JS string; no expressions,
# comments, extra statements, prototype paths, or non-numeric IDs are accepted.
_CALLBACK = re.compile(
    r'window\.pywebview\._returnValuesCallbacks\["(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"\]'
    r'\["[0-9]+"\]\(\{(?:isError: true, )?value: '
    r"'(?:\\['\\]|[^'\\\r\n\u2028\u2029])*'\}\)", re.ASCII
)


def _is_literal_callback(script):
    match = _CALLBACK.fullmatch(script)
    return bool(match) and not any(
        part in {'__proto__', 'prototype', 'constructor'}
        for part in match['name'].split('.')
    )

API_FACTORY = r"""
window.pywebview._createApi = function(funcList) {
  const bridge = window.pywebview;
  for (const element of funcList) {
    const name = element.func;
    const parts = name.split('.');
    const leaf = parts.pop();
    let object = bridge.api;
    for (const part of parts) {
      if (['__proto__', 'prototype', 'constructor'].includes(part)) throw Error('Invalid API');
      if (!Object.prototype.hasOwnProperty.call(object, part)) object[part] = {};
      object = object[part];
    }
    if (['__proto__', 'prototype', 'constructor'].includes(leaf)) throw Error('Invalid API');
    bridge._returnValuesCallbacks[name] = {};
    object[leaf] = function(...args) {
      const id = (Math.random() + '').substring(2);
      const promise = new Promise((resolve, reject) => bridge._checkValue(name, resolve, reject, id));
      bridge._jsApiCallback(name, args, id);
      return promise;
    };
  }
};
"""


def configure_csp_bridge(window, util=None):
    """Configure before webview.start; never modify dependency files on disk."""
    if util is None:
        import webview.util as util
    if getattr(util.load_js_files, '_local_csp_bridge', False) is not True:
        original_loader = util.load_js_files

        @wraps(original_loader)
        def load_js_files(*args, **kwargs):
            code, finish = original_loader(*args, **kwargs)
            return code + '\n' + API_FACTORY, finish

        load_js_files._local_csp_bridge = True
        util.load_js_files = load_js_files

    if getattr(window.evaluate_js, '_local_csp_bridge', False) is not True:
        original_evaluate = window.evaluate_js

        @wraps(original_evaluate)
        def evaluate_js(script, callback=None):
            if callback is None and _is_literal_callback(script):
                return window.run_js(script)
            return original_evaluate(script, callback=callback)

        evaluate_js._local_csp_bridge = True
        window.evaluate_js = evaluate_js
