"""Restoration failures must not leave a pending-looking status or leak paths."""
import re
import subprocess
from pathlib import Path

import pytest
from local_anonymizer.app import INDEX_ASSET, ENGLISH_INDEX_ASSET


@pytest.mark.parametrize('entry', [INDEX_ASSET, ENGLISH_INDEX_ASSET])
def test_restore_rejection_is_reported_without_private_error_details(entry):
    assets = Path(__file__).parents[1] / 'src/local_anonymizer/assets'
    html = (assets / entry).read_text(encoding='utf-8')
    script = re.search(r'<script[^>]+src="([^"]+\.js)"', html).group(1)
    js = (assets / script).read_text(encoding='utf-8')
    start = js.index('async function restoreMatchedFile()')
    end = js.index("$('#chooseRestoreFile').onclick", start)
    function = js[start:end]
    harness = """
const nodes={restoreFile:{disabled:false},restoreStatus:{textContent:''},fileStatus:{textContent:''}};
const $=id=>nodes[id.slice(1)];
const pywebview={api:{restore_matched_file:async()=>{throw new Error('PRIVATE_INTERNAL_PATH')}}};
""" + function + """
(async()=>{await restoreMatchedFile();
if(!nodes.restoreStatus.textContent || nodes.restoreStatus.textContent !== nodes.fileStatus.textContent) throw new Error('Failure status missing');
if(nodes.restoreStatus.textContent.includes('PRIVATE_INTERNAL_PATH')) throw new Error('Internal error leaked');
console.log('restore failure safely reported');
})().catch(e=>{console.error(e.message);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
