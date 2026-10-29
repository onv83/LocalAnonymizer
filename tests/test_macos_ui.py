"""Cross-platform active UI contracts; no archive executables are required."""
import re
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from local_anonymizer.app import AppApi, INDEX_ASSET, ENGLISH_INDEX_ASSET, asset_path

ASSETS = Path(__file__).parents[1] / 'src/local_anonymizer/assets'

@pytest.mark.parametrize('entry', [INDEX_ASSET, ENGLISH_INDEX_ASSET])
def test_native_copy_and_command_enter(entry):
    html = (ASSETS / entry).read_text(encoding='utf-8')
    script = re.search(r'<script[^>]+src="([^"]+\.js)"', html).group(1)
    js = (ASSETS / script).read_text(encoding='utf-8')
    copy = next(line for line in js.splitlines() if line.startswith("$('#copy').onclick="))
    keyboard = next(line for line in js.splitlines() if line.startswith("document.addEventListener('keydown'"))
    harness = """
const assert=require('node:assert/strict');
const nodes={copy:{},fileStatus:{textContent:''}};
const $=id=>nodes[id.slice(1)];
let copied='', listener, previewFullscreen=false, anonymizedPreviewFullscreen=false;
const document={addEventListener:(_,fn)=>listener=fn};
const outputText=()=> 'Synthetic text';
const pywebview={api:{write_clipboard_text:async text=>{copied=text;return {ok:true}}}};
""" + copy + '\n' + keyboard + """
(async()=>{
 await nodes.copy.onclick(); assert.equal(copied,'Synthetic text');
 let clicks=0; nodes.copy.click=()=>clicks++;
 for(const modifier of ['metaKey','ctrlKey']){let prevented=false;listener({key:'Enter',[modifier]:true,preventDefault(){prevented=true}});assert.equal(prevented,true)}
 assert.equal(clicks,2);
 pywebview.api.write_clipboard_text=async()=>{throw Error('PRIVATE_PATH')};
 await nodes.copy.onclick(); assert.ok(nodes.fileStatus.textContent);assert.ok(!nodes.fileStatus.textContent.includes('PRIVATE_PATH'));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(['node','-e',harness],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "'unsafe-eval'" not in html
    assert "script-src 'self';" in html

@pytest.mark.parametrize('language,entry',[('ru',INDEX_ASSET),('en',ENGLISH_INDEX_ASSET)])
def test_language_navigation_uses_native_window(tmp_path, language, entry):
    api = AppApi(tmp_path)
    window = Mock()
    api.set_window(window)
    assert api.set_language(language)['language'] == language
    window.load_url.assert_called_once_with(str(asset_path(entry)))
    assert api.get_language() == language
