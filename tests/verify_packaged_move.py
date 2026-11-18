"""Exercise the delivered helper's move API on tiny, generated cross-drive fixtures."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Web'))
import storage

def main():
    tag=secrets.token_hex(6)
    state=ROOT/'work'/('packaged-move-'+tag);state.mkdir(parents=True)
    sourceBase=Path.home()/'Documents'/('StorageLensMovePackage-'+tag);sourceBase.mkdir()
    source=sourceBase/'Generated test media';source.mkdir()
    content=b'StorageLens generated move fixture. No personal files.\n'*128
    (source/'sample.txt').write_bytes(content)
    Path(str(source/'sample.txt')+':Zone.Identifier').write_bytes(b'[ZoneTransfer]\r\nZoneId=3\r\n')
    other=next(v['drive']+'\\' for v in storage.volumes() if v['drive']!=str(source)[:2])
    destination=Path(other)/('StorageLensMovePackage-'+tag);destination.mkdir()
    secret=secrets.token_hex(32);token='';base=''
    process=subprocess.Popen([str(ROOT/'artifacts/windows/publish/backend/StorageLens.Backend.exe'),
        '--port','0','--ready-file',str(state/'ready.json')],
        env={**os.environ,'STORAGELENS_DATA_DIR':str(state),'STORAGELENS_SESSION_TOKEN':secret},
        creationflags=subprocess.CREATE_NO_WINDOW)
    def request(path,body=None,authenticated=True):
        headers={'X-StorageLens-Session':secret} if authenticated else {}
        if body is not None:headers.update({'Content-Type':'application/json','X-StorageLens-Token':token})
        req=urllib.request.Request(base+'/api/'+path,headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    def wait_progress(path):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            result=request(path)
            if (path=='move/status' and not result['active']) or (path=='progress' and result['status'] in ['complete','failed']):return result
            time.sleep(.1)
        raise AssertionError('Owned fixture operation did not finish')
    try:
        deadline=time.monotonic()+60
        while not (state/'ready.json').exists() and time.monotonic()<deadline:time.sleep(.1)
        receipt=json.loads((state/'ready.json').read_text());base=receipt['url'];assert receipt['pid']==process.pid
        try:request('move/status',authenticated=False);raise AssertionError('Unauthenticated move endpoint accepted')
        except urllib.error.HTTPError as error:assert error.code==403
        token=request('summary')['token']
        request('scan',{'roots':[str(source)],'mode':'quick'})
        assert wait_progress('progress')['status']=='complete'
        listing=request('move/folders?path='+urllib.parse.quote(str(destination)))
        assert listing['path']==str(destination)
        review=request('move/preview',{'paths':[str(source)],'parent':str(destination),'name':'Verified copy'})
        assert review['immediateSpaceFreed']==0
        try:request('move/start',{'ticket':review['ticket'],'confirmation':'MOVE','agreed':False});raise AssertionError('Agreement bypass')
        except urllib.error.HTTPError as error:assert error.code==400
        request('move/start',{'ticket':review['ticket'],'confirmation':'MOVE','agreed':True})
        job=wait_progress('move/status');assert job['status']=='complete',job
        copied=Path(job['destination'])/source.name/'sample.txt'
        assert copied.read_bytes()==content
        assert Path(str(copied)+':Zone.Identifier').read_bytes()==b'[ZoneTransfer]\r\nZoneId=3\r\n'
        assert not source.exists() and job['recycled']==[str(source)]
        assert job['copiesVerified'] and job['immediateSpaceFreed']==0
        assert request('move/history')[0]['id']==job['id']
        report={'passed':True,'version':request('health')['version'],'authenticatedApi':True,
            'agreementEnforced':True,'crossDriveCopy':True,'sha256Verified':True,'namedStreamsPreserved':True,
            'originalRecycled':True,'immediateSpaceFreed':0,
            'fixtureBytes':len(content),'scope':'Only the generated fixture was recycled. Its tiny recovery copy remains in Windows Recycle Bin; no personal file was moved.'}
        out=ROOT/'artifacts/verification/moves';out.mkdir(parents=True,exist_ok=True)
        (out/'packaged-move.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    finally:
        if base and token:
            try:request('shutdown',{})
            except Exception:pass
        try:process.wait(30)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        for owned in [sourceBase,destination]:
            assert owned.name=='StorageLensMovePackage-'+tag
            assert owned.parent!=owned
            shutil.rmtree(owned)

if __name__=='__main__':main()
