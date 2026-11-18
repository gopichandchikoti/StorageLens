"""Query OSV for pinned Python build and Android dependency identities."""
import json
from pathlib import Path
import urllib.request
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]

def main():
    queries=[]
    for line in (ROOT/'Windows/requirements-build.txt').read_text().splitlines():
        name,version=line.split(' --hash=')[0].split('==')
        queries.append({'package':{'ecosystem':'PyPI','name':name},'version':version})
    for line in (ROOT/'Android/app/gradle.lockfile').read_text().splitlines():
        if not line or line.startswith('#') or '=' not in line:continue
        parts=line.split('=')[0].split(':')
        if len(parts)==3: queries.append({'package':{'ecosystem':'Maven','name':':'.join(parts[:2])},'version':parts[2]})
    request=urllib.request.Request('https://api.osv.dev/v1/querybatch',
        data=json.dumps({'queries':queries}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=45) as response:
        raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('Oversized advisory response')
        results=json.loads(raw)['results']
    if len(results)!=len(queries):raise ValueError('Incomplete advisory response')
    affected=[{'dependency':query,'advisories':result['vulns']}
        for query,result in zip(queries,results) if result.get('vulns')]
    report={'source':'https://api.osv.dev/v1/querybatch','queriedAt':datetime.now(timezone.utc).isoformat(),
        'dependenciesChecked':len(queries),'affected':affected,
        'limits':'Pinned Python/Android dependencies only; excludes runtime binaries, external WebView, OS and unlisted build tools. No findings is not a security certification.'}
    target=ROOT/'artifacts/verification';target.mkdir(parents=True,exist_ok=True)
    (target/'dependency-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'dependenciesChecked':len(queries),'affectedDependencies':len(affected)}))
    return 1 if affected else 0

if __name__=='__main__':raise SystemExit(main())
