$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
function Checked-Python {
    & python @args
    if($LASTEXITCODE){throw 'Python build or verification failed.'}
}
Checked-Python @('tools/bootstrap_windows.py')
Checked-Python @('-m','venv','work/python-build')
& work/python-build/Scripts/python.exe -m pip install --require-hashes -r Windows/requirements-build.txt
if($LASTEXITCODE){throw 'Locked Windows build-tool installation failed.'}

# The official compiler is pinned and installed only on the ephemeral CI runner.
$innoUrl='https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
$innoHash='8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'
$innoInstaller=Join-Path $root 'work/innosetup-ci.exe'
Invoke-WebRequest -Uri $innoUrl -OutFile $innoInstaller
if((Get-FileHash -LiteralPath $innoInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne $innoHash){throw 'Inno Setup digest mismatch.'}
$innoPath=Join-Path $root 'work/tooling/inno'
$install=Start-Process -FilePath $innoInstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="'+$innoPath+'"')) -WindowStyle Hidden -Wait -PassThru
if($install.ExitCode){throw 'CI compiler installation failed.'}
$env:STORAGELENS_ISCC=Join-Path $innoPath 'ISCC.exe'

$runtimeLocations=@("${env:ProgramFiles(x86)}/Microsoft/EdgeWebView/Application/*/msedgewebview2.exe","$env:LOCALAPPDATA/Microsoft/EdgeWebView/Application/*/msedgewebview2.exe")
if(-not($runtimeLocations | Where-Object {Test-Path $_})){
    $runtime=Join-Path $root 'work/WebView2RuntimeInstaller.exe'
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $runtime
    $signature=Get-AuthenticodeSignature -LiteralPath $runtime
    if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){throw 'WebView2 installer identity verification failed.'}
    $installed=Start-Process -FilePath $runtime -ArgumentList @('/silent','/install') -WindowStyle Hidden -Wait -PassThru
    if($installed.ExitCode -notin @(0,3010)){throw 'CI WebView2 runtime installation failed.'}
}
Checked-Python @('tools/prepare_platforms.py')
Checked-Python @('tools/check_source.py')
Checked-Python @('-m','unittest','discover','-s','tests','-p','test_*.py','-v')
Checked-Python @('tools/build_windows.py')
Checked-Python @('tests/verify_packaged_backend.py')
Checked-Python @('tools/verify_windows_install.py','ci')
Checked-Python @('tools/ci_assets.py','windows')
