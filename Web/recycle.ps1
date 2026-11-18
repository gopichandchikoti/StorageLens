$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    Add-Type -Path (Join-Path $PSScriptRoot 'Recycle.cs')
    $recycled = [StorageLensNative.RecycleBridge]::Recycle([string]$request.path)
    @{ recycled=$true; recycledPath=$recycled } | ConvertTo-Json -Compress
} catch {
    @{ error=$_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
