"""Record dependency identities and local artifact digests without private state."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    dependencies=[]
    lock=json.loads((ROOT/'Windows/StorageLens/packages.lock.json').read_text())
    for target,packages in lock['dependencies'].items():
        for name,record in packages.items():
            dependencies.append({'ecosystem':'NuGet','name':name,'version':record.get('resolved'), 'target':target})
    for line in (ROOT/'Android/app/gradle.lockfile').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            component=line.split('=')[0].split(':')
            if len(component)==3: dependencies.append({'ecosystem':'Maven','name':':'.join(component[:2]),'version':component[2]})
    for line in (ROOT/'Windows/requirements-build.txt').read_text().splitlines():
        name,version=line.split(' --hash=')[0].split('==')
        dependencies.append({'ecosystem':'PyPI','name':name,'version':version,'scope':'build/bootloader'})
    dependencies.append({'ecosystem':'runtime','name':'CPython','version':platform.python_version()})
    dependencies.append({'ecosystem':'runtime','name':'.NET Desktop','version':'10.0.15'})
    output=ROOT/'artifacts/downloads'; output.mkdir(parents=True,exist_ok=True)
    manifest={'format':'StorageLens dependency inventory v1','generatedAt':datetime.now(timezone.utc).isoformat(),
        'product':json.loads((ROOT/'product.json').read_text()),
        'sourceRevision':'uncommitted local working tree; user index preserved',
        'publication':'local preview only','dependencies':dependencies,
        'limitations':'Dependency inventory, not a signed SBOM or build attestation. Android transitive dependencies follow the lockfile; external WebView2 runtime updates independently.'}
    (output/'dependency-inventory.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    version=manifest['product']['version']
    artifacts=sorted(p for p in output.iterdir() if p.name=='dependency-inventory.json' or
        (p.suffix in {'.exe','.apk','.md'} and ('-'+version+'-') in p.name))
    hashes=['%s  %s'%(hashlib.sha256(p.read_bytes()).hexdigest(),p.name) for p in artifacts]
    (output/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='utf-8')
    print('Dependency inventory and SHA-256 digests written for',len(artifacts),'files.')

if __name__=='__main__': main()
