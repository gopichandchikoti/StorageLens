"""Prepare the official Gradle wrapper without copying a sibling app's identity."""
import hashlib
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
ANDROID=ROOT/'Android'

def download(url, limit=1024*1024):
    with urllib.request.urlopen(url, timeout=60) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError('Wrapper download bound exceeded')
    return data

base='https://raw.githubusercontent.com/gradle/gradle/v8.14.3/'
for name in ['gradlew','gradlew.bat','gradle/wrapper/gradle-wrapper.jar']:
    destination=ANDROID/name
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists(): destination.write_bytes(download(base+name))
expected=download('https://services.gradle.org/distributions/gradle-8.14.3-wrapper.jar.sha256').decode().strip()
if hashlib.sha256((ANDROID/'gradle/wrapper/gradle-wrapper.jar').read_bytes()).hexdigest()!=expected:
    raise ValueError('Gradle wrapper checksum mismatch')
dist=download('https://services.gradle.org/distributions/gradle-8.14.3-bin.zip.sha256').decode().strip()
properties=('distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n'
 'distributionUrl=https\\://services.gradle.org/distributions/gradle-8.14.3-bin.zip\n'
 f'distributionSha256Sum={dist}\nnetworkTimeout=60000\nvalidateDistributionUrl=true\n'
 'zipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n')
(ANDROID/'gradle/wrapper/gradle-wrapper.properties').write_text(properties,encoding='utf-8')
print('Official Gradle 8.14.3 wrapper and distribution checksums verified.')
