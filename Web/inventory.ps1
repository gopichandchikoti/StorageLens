param([string]$OutputPath = (Join-Path $PSScriptRoot 'inventory.json'))
$ErrorActionPreference = 'SilentlyContinue'
$paths = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
$apps = @(Get-ItemProperty -Path $paths | Where-Object DisplayName | ForEach-Object {
    [pscustomobject]@{ name=$_.DisplayName; version=$_.DisplayVersion; publisher=$_.Publisher; location=$_.InstallLocation; installDate=$_.InstallDate; reportedBytes=([long]$_.EstimatedSize * 1024); uninstall=$_.UninstallString; systemComponent=[bool]$_.SystemComponent; source='registry'; key=$_.PSChildName }
})
$packages = @(Get-AppxPackage | ForEach-Object {
    [pscustomobject]@{ name=$_.Name; version=[string]$_.Version; publisher=$_.PublisherDisplayName; location=$_.InstallLocation; installDate=''; reportedBytes=0; uninstall='Manage through Windows Settings > Apps'; systemComponent=[bool]$_.IsFramework; source='Windows package'; key=$_.PackageFullName }
})
$disks = @(Get-CimInstance Win32_LogicalDisk | Where-Object DriveType -In 2,3 | ForEach-Object {
    [pscustomobject]@{ drive=$_.DeviceID; label=$_.VolumeName; size=[long]$_.Size; free=[long]$_.FreeSpace; type=$_.DriveType }
})
[pscustomobject]@{ apps=@($apps)+@($packages); volumes=$disks } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
