"""Check native identities and prepare only fixed-name public preview assets."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/release'

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def command(args):
    return subprocess.check_output([str(a) for a in args],text=True,cwd=ROOT)

def main():
    kind=sys.argv[1];product=json.loads((ROOT/'product.json').read_text())
    OUT.mkdir(parents=True,exist_ok=True)
    report={'version':product['version'],'commit':os.environ.get('GITHUB_SHA','local'),
        'runUrl':f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','gopichandchikoti/StorageLens')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','local')}",
        'platform':kind}
    if kind=='windows':
        source=ROOT/'artifacts/downloads'/f"StorageLens-Setup-{product['version']}-preview-win-x64.exe"
        for path in (ROOT/'artifacts/windows/publish').rglob('*'):
            if path.is_file() and (path.suffix.lower() in {'.db','.sqlite','.sqlite3','.jks','.keystore','.p12','.pfx'} or path.name=='inventory.json'):
                raise ValueError('Private state or signing file in Windows package')
        receipt=ROOT/'artifacts/verification'/product['version']/'windows-installed-ci/installer-verified.json'
        verified=json.loads(receipt.read_text())
        assert verified['version']==product['version'] and verified['installerUninstall'] and verified['scanDataPreserved']
        name='StorageLens-Setup.exe';report.update(signing='Unsigned Windows preview',verified=verified)
    elif kind=='android':
        source=ROOT/'Android/app/build/outputs/apk/debug/app-debug.apk'
        sdk=Path(os.environ['ANDROID_HOME']);tools=sdk/'build-tools/36.0.0'
        aapt=tools/('aapt.exe' if os.name=='nt' else 'aapt')
        badging=command([aapt,'dump','badging',source])
        assert f"name='{product['androidApplicationId']}.preview'" in badging
        assert f"versionName='{product['version']}'" in badging
        assert f"versionCode='{product['androidVersionCode']}'" in badging
        assert "sdkVersion:'30'" in badging and "targetSdkVersion:'36'" in badging
        assert "uses-permission: name='android.permission.INTERNET'" not in badging
        java=Path(os.environ['JAVA_HOME'])/'bin'/('java.exe' if os.name=='nt' else 'java')
        signature=command([java,'-jar',tools/'lib/apksigner.jar','verify','--verbose','--print-certs',source])
        fingerprint=re.search(r'certificate SHA-256 digest: ([a-fA-F0-9]{64})',signature).group(1).lower()
        expected=os.environ.get('EXPECTED_ANDROID_CERT_SHA256')
        if os.environ.get('STORAGELENS_SIGNING_STORE_FILE'):
            assert expected and fingerprint==expected.lower(),'Preview signer mismatch'
        with zipfile.ZipFile(source) as bundle:
            assert not any(n.endswith(('.jks','.keystore','.p12','.pfx','.sqlite3')) for n in bundle.namelist())
        instrumentation=(ROOT/'artifacts/verification/android-ci/instrumentation.log').read_text()
        assert re.search(r'OK \(\d+ tests?\)',instrumentation)
        name='StorageLens-Android.apk';report.update(signing='Dedicated preview certificate; debuggable build',
            androidVersionCode=product['androidVersionCode'],applicationId=product['androidApplicationId']+'.preview',
            certificateSha256=fingerprint,api35Instrumentation=True)
    else:raise ValueError('Choose windows or android')
    shutil.copy2(source,OUT/name)
    report.update(asset=name,sha256=digest(OUT/name),bytes=source.stat().st_size)
    (OUT/(kind+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(kind,'preview identity and package checks passed.')

if __name__=='__main__':main()
