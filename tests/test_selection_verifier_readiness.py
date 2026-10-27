import re
import subprocess
from pathlib import Path


def test_selection_verifier_waits_for_script_state_not_only_early_dom():
    text = (Path(__file__).parents[1] / 'scripts/verify_text_selection.mjs').read_text(encoding='utf-8')
    expression = re.search(r'await evaluate\(`(new Promise.*?)`\);', text, re.S).group(1)
    program = """
const vm=require('node:vm');
const context={document:{querySelector:()=>({})},setTimeout};
setTimeout(()=>{context.last={parts:[]};context.restoredParts=new Set()},50);
""" + f"const ready=vm.runInNewContext({expression!r},context);\n" + """
ready.then(()=>{if(!context.last||!context.restoredParts)throw new Error('Selection verifier starts before app script initialization');
console.log('ready after script initialization')}).catch(e=>{console.error(e.message);process.exitCode=1});
"""
    completed = subprocess.run(['node', '-e', program], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
