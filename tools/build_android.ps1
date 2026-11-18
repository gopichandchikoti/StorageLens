param([switch]$Test,[switch]$UpdateLocks)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$javaHome=$env:JAVA_HOME
if(-not $javaHome){
    $javaCommand=(Get-Command java.exe).Source
    $javaHome=Split-Path -Parent (Split-Path -Parent $javaCommand)
}
$sdk=$env:ANDROID_HOME
if(-not $sdk){$sdk=Join-Path $env:USERPROFILE 'Documents\Codex\android-sdk'}
if(-not(Test-Path -LiteralPath (Join-Path $sdk 'platforms\android-36\android.jar'))){throw 'Android SDK 36 is required; set ANDROID_HOME.'}
$env:JAVA_HOME=$javaHome
$env:ANDROID_HOME=$sdk
Push-Location $root
try {
    & python tools/prepare_platforms.py
    if($LASTEXITCODE){throw 'Shared resource validation failed.'}
    & python tools/bootstrap_android.py
    if($LASTEXITCODE){throw 'Gradle wrapper verification failed.'}
    $properties='sdk.dir='+$sdk.Replace('\','/').Replace(':','\:')+"`n"
    [IO.File]::WriteAllText((Join-Path $root 'Android\local.properties'),$properties,(New-Object Text.UTF8Encoding($false)))
    Push-Location (Join-Path $root 'Android')
    try {
        $tasks=@('assembleDebug','assembleAndroidTest','testDebugUnitTest','lintDebug','--console=plain')
        if($UpdateLocks){$tasks+='--write-locks'}
        if($Test){$tasks+= 'connectedDebugAndroidTest'}
        & '.\gradlew.bat' @tasks
        if($LASTEXITCODE){throw 'Android build or checks failed.'}
    } finally {Pop-Location}
    $output=Join-Path $root 'artifacts\downloads'
    $product=Get-Content -LiteralPath (Join-Path $root 'product.json') -Raw | ConvertFrom-Json
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'Android\app\build\outputs\apk\debug\app-debug.apk') -Destination (Join-Path $output ('StorageLens-'+$product.version+'-preview-android.apk')) -Force
    Write-Output 'Installable development-signed APK is in artifacts/downloads.'
}finally{Pop-Location}
