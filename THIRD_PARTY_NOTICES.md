# Third-party notices

StorageLens preview contains original application code and the following runtime
components. Full notices are included in `licenses/`; their terms govern those
components. No license to unrelated portfolio applications or their assets is implied.

| Component | Version used | Terms / notice |
| --- | --- | --- |
| CPython | 3.13.15 | PSF and bundled notices, `licenses/Python.txt` |
| PyInstaller bootloader | 6.22.3 | GPL with the bootloader exception, `licenses/PyInstaller.txt`; application code is not relicensed by bundling |
| .NET desktop runtime | 10.0.15 | MIT and bundled notices, `licenses/DotNet*.txt` |
| Microsoft Edge WebView2 SDK | 1.0.4314.35 | Microsoft terms and notices, `licenses/WebView2*.txt` |
| AndroidX WebKit / Activity | 1.14.0 / 1.11.0 | Apache 2.0 and transitive AndroidX dependencies; see Gradle lockfile and `licenses/Apache-2.0.txt` |

Microsoft Edge WebView2 Runtime is a separately installed and updated Microsoft
component, not an embedded browser distribution in this installer. The user is
directed to Microsoft's official runtime installer if it is unavailable.

Build-only tools include .NET SDK 10.0.404, Gradle 8.14.3 (Apache 2.0), Android Gradle
Plugin 8.13.0 (Apache 2.0), Android SDK build tools, and Inno Setup (6.7.3 locally;
7.1.1 pinned in CI). The Gradle
wrapper is distributed under Apache 2.0. Android instrumentation/JUnit dependencies
are used only in the separate test APK, not in the delivered app APK.

Runtime and build dependencies are recorded in `Windows/StorageLens/packages.lock.json`,
`Windows/requirements-build.txt`, and `Android/app/gradle.lockfile`. The build's
dependency manifest and output hashes accompany the local download artifacts.

StorageLens is an unsigned Windows / preview-signed Android download. Public GitHub
previews use a dedicated persistent Android preview certificate; unconfigured local
builds use Android Debug. No public store, commercial distribution, production
signing identity or project-wide source license has been configured by this task.
