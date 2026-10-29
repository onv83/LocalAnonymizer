"""The native bridge must work without permitting dynamic code generation."""
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

from local_anonymizer.csp_bridge import configure_csp_bridge, API_FACTORY


def test_api_factory_without_dynamic_code():
    script = """
const assert = require('node:assert/strict');
global.window = {pywebview:{api:{},_returnValuesCallbacks:{}}};
const bridge=window.pywebview;
bridge._checkValue=(name,resolve,reject,id)=>{bridge._returnValuesCallbacks[name][id]=resolve};
bridge._jsApiCallback=(name,args,id)=>{assert.deepEqual(args,['synthetic']);bridge._returnValuesCallbacks[name][id]('OK')};
global.Function=()=>{throw Error('CSP violation')};
""" + API_FACTORY + """
bridge._createApi([{func:'copy',params:['text']}]);
bridge.api.copy('synthetic').then(result=>assert.equal(result,'OK')).catch(()=>{process.exitCode=1});
"""
    completed = subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert completed.returncode == 0, completed.stderr


def test_bridge_changes_only_callback_evaluation():
    window=SimpleNamespace(evaluate_js=Mock(return_value='original'),run_js=Mock(return_value='native'))
    util=SimpleNamespace(load_js_files=Mock(return_value=('INITIAL','FINISH')))
    configure_csp_bridge(window,util)
    code,finish=util.load_js_files(window,'cocoa')
    assert code == 'INITIAL\n'+API_FACTORY
    assert finish == 'FINISH'
    callback="window.pywebview._returnValuesCallbacks[\"copy\"][\"123\"]({value: '\"x\"'})"
    assert window.evaluate_js(callback) == 'native'
    window.run_js.assert_called_once_with(callback)
    assert window.evaluate_js('1+2') == 'original'
    window.evaluate_js('1+2',callback=lambda x:x)
    assert window.run_js.call_count == 1
    configure_csp_bridge(window,util)
    assert util.load_js_files(window,'cocoa')[0].count(API_FACTORY)==1


def test_callback_prefix_cannot_execute_additional_code():
    window=SimpleNamespace(evaluate_js=Mock(return_value='original'),run_js=Mock())
    util=SimpleNamespace(load_js_files=Mock(return_value=('', '')))
    configure_csp_bridge(window,util)
    valid = "window.pywebview._returnValuesCallbacks[\"copy\"][\"123\"]({value: '\"x\"'})"
    for script in (valid+';alert(1)', valid.replace('123', 'bad-id'),
                   valid.replace("'\"x\"'", "alert(1)"),
                   valid.replace('copy', '__proto__'),
                   valid.replace("'\"x\"'", "'x');alert(1);//'")):
        assert window.evaluate_js(script) == 'original'
    window.run_js.assert_not_called()
