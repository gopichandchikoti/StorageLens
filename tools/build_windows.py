"""Build the native host, self-contained scanner and per-user Windows installer."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT/'artifacts'/'windows'

def run(args, **kwargs):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True, **kwargs)

def main():
    run([sys.executable, ROOT/'tools'/'prepare_platforms.py'])
    product = json.loads((ROOT/'product.json').read_text())
    dotnet = Path(os.environ.get('STORAGELENS_DOTNET', ROOT/'work'/'tooling'/'dotnet'/'dotnet.exe'))
    python = ROOT/'work'/'python-build'/'Scripts'/'python.exe'
    if not dotnet.is_file() or not python.is_file():
        raise SystemExit('Install the documented local .NET SDK and locked Python build tools first.')
    env = {**os.environ, 'DOTNET_ROOT': str(dotnet.parent), 'DOTNET_CLI_TELEMETRY_OPTOUT':'1',
           'DOTNET_NOLOGO':'1', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1'}
    project = ROOT/'Windows'/'StorageLens'/'StorageLens.csproj'
    publish = ARTIFACTS/'publish'
    # This directory contains generated program files only. A clean publish
    # prevents stale bundled executables or runtime files reaching the installer.
    if publish.exists():
        if publish.is_symlink() or not publish.resolve().is_relative_to(ARTIFACTS.resolve()):
            raise ValueError('Unexpected Windows publish directory')
        shutil.rmtree(publish)
    run([dotnet, 'publish', project, '-c', 'Release', '-r', 'win-x64', '--self-contained', 'true',
         '-p:PublishSingleFile=false',
         '-p:RestoreLockedMode=true',
         '-p:Version='+product['version'], '-o', publish], env=env)
    source = ROOT/'Web'
    data = ['index.html','app.js','enhancements.js','design.js','style.css','inventory.ps1',
            'recycle.ps1','Recycle.cs','product.json','public','content-fallback.js','moves.js','moves.css']
    data.extend(n for n in ['platform.js','security.ps1'] if (source/n).exists())
    args = [python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--noconsole',
            '--name','StorageLens.Backend','--distpath',ARTIFACTS/'backend-dist',
            '--workpath',ROOT/'work'/'pyinstaller','--specpath',ROOT/'work',
            '--icon',ROOT/'Windows'/'StorageLens'/'Assets'/'StorageLens.ico']
    for name in data:
        destination = 'public' if name=='public' else '.'
        args.extend(['--add-data',str(source/name)+os.pathsep+destination])
    args.append(source/'app.py')
    run(args)
    shutil.copytree(ARTIFACTS/'backend-dist'/'StorageLens.Backend', publish/'backend', dirs_exist_ok=True)
    if (ROOT/'THIRD_PARTY_NOTICES.md').exists():
        shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', publish/'THIRD_PARTY_NOTICES.md')
        shutil.copytree(ROOT/'licenses', publish/'licenses', dirs_exist_ok=True)
    # Never leave an earlier build's debug symbols in an installer.
    for symbol in publish.rglob('*.pdb'):
        if symbol.resolve().is_relative_to(publish.resolve()):
            symbol.unlink()
    inno = Path(os.environ.get('STORAGELENS_ISCC', str(Path(os.environ['LOCALAPPDATA'])/
                'Programs'/'Inno Setup 6'/'ISCC.exe')))
    run([inno, '/DAppVersion='+product['version'], '/DPublishDirectory='+str(publish),
         ROOT/'Windows'/'installer'/'StorageLens.iss'])
    print('Windows installer built in artifacts/downloads.', flush=True)

if __name__ == '__main__':
    main()
