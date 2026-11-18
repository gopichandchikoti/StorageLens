# Compatibility launcher for the local Web version.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Web\Start-StorageLens.ps1')
