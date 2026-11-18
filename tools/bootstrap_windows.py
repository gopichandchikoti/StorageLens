"""Fetch the official .NET SDK into this repo's ignored build-tools directory."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
tools = root / 'work' / 'tooling'
tools.mkdir(parents=True, exist_ok=True)
metadata_url = 'https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/10.0/releases.json'
with urllib.request.urlopen(metadata_url, timeout=60) as response:
    metadata = json.load(response)
sdk_version = json.loads((root/'global.json').read_text())['sdk']['version']
release, sdk = next((r, s) for r in metadata['releases'] for s in r.get('sdks', [])
                    if s['version'] == sdk_version)
asset = next(f for f in sdk['files'] if f['rid'] == 'win-x64' and f['url'].endswith('.zip'))
archive = tools / ('dotnet-sdk-' + sdk['version'] + '.zip')
if not archive.exists():
    print('Downloading official .NET SDK ' + sdk['version'], flush=True)
    with urllib.request.urlopen(asset['url'], timeout=120) as response, archive.open('wb') as output:
        total = 0
        while chunk := response.read(512 * 1024):
            total += len(chunk)
            if total > 600 * 1024 * 1024:
                raise RuntimeError('SDK download exceeds the build-tool bound')
            output.write(chunk)
with archive.open('rb') as bundle_file:
    if hashlib.file_digest(bundle_file, 'sha512').hexdigest().lower() != asset['hash'].lower():
        raise RuntimeError('Official SDK SHA-512 did not match')
destination = tools / 'dotnet'
if not (destination / 'dotnet.exe').exists():
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError('Unsafe SDK archive entry')
        bundle.extractall(destination)
receipt = {'sdk': sdk['version'], 'runtime': release['runtime']['version'], 'url': asset['url'],
           'sha512': asset['hash'], 'metadata': metadata_url}
(tools / 'dotnet-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print('Verified .NET SDK '+sdk['version']+' is ready.', flush=True)
