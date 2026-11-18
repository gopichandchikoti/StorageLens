"""Run the shipped helper on isolated metadata fixtures, without shell cleanup."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'work'/'packaged-backend-qa'

def main():
    if HOME.exists(): raise SystemExit('Use a fresh owned test directory; previous evidence is preserved.')
    fixture=HOME/'files'; fixture.mkdir(parents=True)
    nested=fixture/'child'; nested.mkdir()
    (fixture/'one.bin').write_bytes(bytes(8192)); (nested/'two.bin').write_bytes(bytes(16384))
    os.link(fixture/'one.bin',fixture/'hardlink.bin')
    secret=secrets.token_hex(32)
    env={**os.environ,'STORAGELENS_DATA_DIR':str(HOME/'data'),'STORAGELENS_SESSION_TOKEN':secret}
    ready=HOME/'ready.json'
    helper=ROOT/'artifacts/windows/publish/backend/StorageLens.Backend.exe'
    process=subprocess.Popen([str(helper),'--port','0','--ready-file',str(ready)],env=env,
        creationflags=subprocess.CREATE_NO_WINDOW)
    base=''; token=''
    def request(path,body=None,auth=True):
        headers={'X-StorageLens-Session':secret} if auth else {}
        if body is not None:
            headers.update({'X-StorageLens-Token':token,'Content-Type':'application/json'})
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    try:
        deadline=time.monotonic()+90
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
        receipt=json.loads(ready.read_text()); assert receipt['pid']==process.pid
        base=receipt['url']
        try: request('/api/health',auth=False);raise AssertionError('Missing session accepted')
        except urllib.error.HTTPError as error: assert error.code==403
        assert request('/api/health')['platform']=='windows'
        token=request('/api/summary')['token']
        records=[]
        for mode in ['quick','deep']:
            assert request('/api/scan',{'mode':mode,'roots':[str(fixture)]})['started']
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                progress=request('/api/progress')
                if progress['status'] in ['complete','failed','cancelled']:break
                time.sleep(.25)
            assert progress['status']=='complete',progress.get('error',progress['status'])
            record=request('/api/folders?'+urllib.parse.urlencode({'path':str(fixture)}))['node']
            assert record['logical']==32768
            records.append({'mode':mode,'logical':record['logical'],'allocated':record['allocated']})
        assert records[1]['allocated']<records[1]['logical']
        assert isinstance(request('/api/apps'),list)
        report={'sessionRequired':True,'packagedScanModes':records,'applicationInventory':True,'passed':True}
        dest=ROOT/'artifacts/verification';dest.mkdir(parents=True,exist_ok=True)
        (dest/'packaged-backend.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Packaged helper session denial, Quick/Deep scans, hard links and inventory passed.',flush=True)
    finally:
        if base and token:
            try: request('/api/shutdown',{})
            except Exception: pass
        try: process.wait(30)
        except subprocess.TimeoutExpired: process.kill();process.wait()

if __name__=='__main__':main()
