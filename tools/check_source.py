"""Focused source hygiene gate. Reports rule IDs/paths, never matching values."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_platforms import content_check

RULES = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE' + r' KEY-----'),
    'aws-access-id': re.compile(r'AKIA[A-Z0-9]{16}'),
    'github-token': re.compile(r'ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{70,}'),
    'stripe-live-key': re.compile(r'sk_live_[A-Za-z0-9]{20,}'),
    'slack-token': re.compile(r'xox[baprs]-[A-Za-z0-9-]{20,}'),
}
SOURCE_ROOTS = ['Web', 'Windows', 'Android', 'public', 'tests', 'tools', 'docs', '.github', 'licenses']
SKIP = {'bin','obj','build','.gradle','__pycache__','.git'}
EXTENSIONS = {'.py','.ps1','.cs','.json','.js','.html','.css','.md','.txt','.iss','.gradle','.xml','.yml','.yaml','.properties','.cmd','.bat'}

def findings(source):
    return [key for key, rule in RULES.items() if rule.search(source)]

def main():
    controls = {'private-key':'-----BEGIN '+'PRIVATE KEY-----', 'aws-access-id':'AKIA'+'A'*16,
        'github-token':'ghp_'+'B'*36, 'stripe-live-key':'sk_live_'+'C'*24,
        'slack-token':'xoxb-'+'D'*24}
    for key, sample in controls.items():
        assert key in findings(sample), key
    assert not findings('StorageLens uses no cloud credentials.')
    content_check()
    files = [p for directory in SOURCE_ROOTS for p in (ROOT/directory).rglob('*')
             if p.is_file() and not SKIP.intersection(p.relative_to(ROOT).parts)]
    files += [p for p in ROOT.iterdir() if p.is_file() and p.name != 'inventory.json']
    checked = 0; failed = []
    for path in files:
        if path.suffix.lower() not in EXTENSIONS or path.name in {'local.properties','keystore.properties'}:
            continue
        source = path.read_text(encoding='utf-8-sig')
        checked += 1
        if path.suffix == '.py': ast.parse(source, str(path.relative_to(ROOT)))
        if path.suffix == '.json': json.loads(source)
        for rule in findings(source): failed.append({'rule':rule,'path':str(path.relative_to(ROOT))})
    for item in failed: print(json.dumps(item))
    # Inspect history read-only as well; never echo matching credential values.
    history = subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=ROOT,capture_output=True).returncode == 0
    history_checked=0
    if history:
        objects=subprocess.check_output(['git','rev-list','--objects','--all'],cwd=ROOT,text=True)
        for entry in objects.splitlines():
            oid,_,name=entry.partition(' ')
            if not name or Path(name).suffix.lower() not in EXTENSIONS:continue
            kind=subprocess.check_output(['git','cat-file','-t',oid],cwd=ROOT,text=True).strip()
            if kind!='blob':continue
            raw=subprocess.check_output(['git','cat-file','blob',oid],cwd=ROOT)
            if len(raw)>2*1024*1024:continue
            history_checked+=1
            for rule in findings(raw.decode('utf-8',errors='replace')):
                item={'rule':rule,'path':name,'scope':'git-history'}
                failed.append(item);print(json.dumps(item))
    print(json.dumps({'checkedTextFiles':checked,'positiveControls':len(controls),
        'findings':len(failed),'historyPresent':history,'historyTextBlobs':history_checked,
        'scope':'source working tree and available Git history; pattern scan only'}))
    return 1 if failed else 0

if __name__=='__main__': raise SystemExit(main())
