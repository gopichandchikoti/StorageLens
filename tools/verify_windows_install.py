"""Install/run/uninstall the local preview in owned test folders only."""
import json
from pathlib import Path
import subprocess
import sys
import time
import winreg

ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'product.json').read_text())['version']
RUN=sys.argv[1] if len(sys.argv)>1 else ''
if RUN and (len(RUN)>24 or not all(c.isalnum() or c=='-' for c in RUN)):
    raise SystemExit('Use a short alphanumeric verification tag.')
SUFFIX=VERSION+('-'+RUN if RUN else '')
TARGET=ROOT/'work'/('installer-qa-'+SUFFIX)
DATA=ROOT/'work'/('installer-qa-data-'+SUFFIX)
CAPTURES=ROOT/'artifacts'/'verification'/VERSION/('windows-installed'+('-'+RUN if RUN else ''))
KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{9E7C92F2-086E-4CA3-BE86-51D57620E107}_is1'

def registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
            return winreg.QueryValueEx(key,'InstallLocation')[0]
    except FileNotFoundError: return None

def run(args,timeout=600):
    subprocess.run([str(a) for a in args],cwd=ROOT,check=True,timeout=timeout)

def main():
    if registration() or TARGET.exists() or DATA.exists():
        raise SystemExit('Refusing to overwrite an existing installation or test-data folder.')
    assert TARGET.resolve().is_relative_to((ROOT/'work').resolve())
    run([sys.executable,ROOT/'tests/seed_desktop.py',DATA])
    version=json.loads((ROOT/'product.json').read_text())['version']
    setup=ROOT/'artifacts/downloads'/f'StorageLens-Setup-{version}-preview-win-x64.exe'
    run([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',
         '/DIR='+str(TARGET),'/LOG='+str(ROOT/'work/installer-install.log')])
    assert (TARGET/'StorageLens.exe').is_file()
    assert Path(registration()).resolve()==TARGET.resolve()
    print('Isolated per-user installation passed.',flush=True)
    run([TARGET/'StorageLens.exe','--data-dir',DATA,'--verify',CAPTURES])
    report=json.loads((CAPTURES/'verified.json').read_text())
    assert report['completed'] and report['initialWindowState']=='Maximized'
    assert set(report['modes'])=={'quick','deep'}
    assert not report['narrowOverflow']
    state=DATA/'storage.sqlite3'; assert state.is_file()
    before=state.stat().st_size
    run([TARGET/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
         '/LOG='+str(ROOT/'work/installer-uninstall.log')])
    deadline=time.monotonic()+120
    while (TARGET/'StorageLens.exe').exists() and time.monotonic()<deadline: time.sleep(.25)
    assert not (TARGET/'StorageLens.exe').exists()
    assert registration() is None
    assert state.is_file() and state.stat().st_size==before
    report.update(installerInstall=True,installerUninstall=True,scanDataPreserved=True)
    (CAPTURES/'installer-verified.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Installed UI checks, uninstall and scan-data preservation passed.',flush=True)

if __name__=='__main__': main()
