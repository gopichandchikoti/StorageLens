"""Isolated real-file fixture for non-destructive native move-dialog verification."""
import json
import os
from pathlib import Path
import secrets
import sys
ROOT=Path(__file__).resolve().parents[1]
data=Path(sys.argv[1]).resolve()
if not data.is_relative_to(ROOT/'work') or data.exists():raise SystemExit('Use fresh owned data below work/.')
data.mkdir(parents=True)
os.environ['STORAGELENS_DATA_DIR']=str(data)
sys.path.insert(0,str(ROOT/'Web'))
import config
import storage
source=Path.home()/'Documents'/('StorageLensMoveUI-'+secrets.token_hex(5))
source.mkdir();(source/'sample-song.txt').write_bytes(b'StorageLens synthetic UI fixture\n'*256)
other=next(v['drive']+'\\' for v in storage.volumes() if v['drive']!=str(source)[:2])
parent=Path(other)/('StorageLensMoveUI-'+secrets.token_hex(5));parent.mkdir()
config.INVENTORY.write_text('{"apps":[]}',encoding='utf-8')
storage.scan(roots=[str(source)],refresh=False,mode='quick')
(data/'move-ui-fixture.json').write_text(json.dumps({'source':str(source),'parent':str(parent)}),encoding='utf-8')
print('Owned UI fixture ready; no personal files were scanned or moved.')
