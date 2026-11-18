"""Create a labeled synthetic native-UI fixture; never copies the user's database."""
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
data=Path(sys.argv[1]).resolve()
if not data.is_relative_to(ROOT/'work'): raise SystemExit('Use a fixture below work/.')
data.mkdir(parents=True,exist_ok=True)
os.environ['STORAGELENS_DATA_DIR']=str(data)
sys.path.insert(0,str(ROOT/'Web'))
import storage

with storage.connect() as connection:
    if connection.execute('SELECT COUNT(*) FROM scans').fetchone()[0]: raise SystemExit('Fixture already populated.')
    volumes=[v for v in storage.volumes() if v['drive']=='C:']
    sid=connection.execute('INSERT INTO scans(started,finished,status,volumes,files,folders,mode,roots) VALUES(?,?,?,?,?,?,?,?)',
        (storage.now(),storage.now(),'complete',json.dumps(volumes),3,3,'quick',json.dumps(['C:\\']))).lastrowid
    nodes=[('C:\\','',24576),('C:\\StorageLens synthetic fixture','C:\\',16384),
           ('C:\\StorageLens synthetic fixture\\data','C:\\StorageLens synthetic fixture',16384)]
    for path,parent,amount in nodes:
        connection.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid,path,parent,'C:',path.count('\\'),amount,amount,0,0,3,0,0))
    app={'name':'StorageLens synthetic UI fixture','version':'1.0.0','publisher':'Local test data',
         'source':'registry','location':'C:\\StorageLens synthetic fixture','reportedBytes':16384,
         'systemComponent':False,'key':'fixture'}
    connection.execute('INSERT INTO apps VALUES(?,?)',(sid,json.dumps(app)))
print('Synthetic desktop fixture created: '+str(data))
