$ErrorActionPreference='Stop'
try {
    $status=Get-MpComputerStatus -ErrorAction Stop
    [pscustomobject]@{
        available=$true
        realtime=[bool]$status.RealTimeProtectionEnabled
        antivirus=[bool]$status.AntivirusEnabled
        signaturesUpdated=[string]$status.AntivirusSignatureLastUpdated
        quickScanFinished=[string]$status.QuickScanEndTime
    } | ConvertTo-Json -Compress
} catch {
    [pscustomobject]@{available=$false; realtime=$null; antivirus=$null} | ConvertTo-Json -Compress
}
