$ErrorActionPreference = 'Stop'
$appUrl = 'http://127.0.0.1:8766'
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri ($appUrl + '/api/summary') -TimeoutSec 2
    if ($response.StatusCode -eq 200 -and $response.Content -match '"token"') { Start-Process $appUrl; exit }
} catch {}
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) { Write-Host 'Python 3 is required. Install Python, then run this launcher again.'; Read-Host 'Press Enter'; exit 1 }
$repository = Split-Path -Parent $PSScriptRoot
& $pythonCommand.Source (Join-Path $repository 'tools\prepare_platforms.py')
if ($LASTEXITCODE) { throw 'StorageLens resource preparation failed.' }
$quotedScript = '"' + (Join-Path $PSScriptRoot 'app.py') + '"'
$processArguments = @($quotedScript, '--open')
$logDirectory = Join-Path $repository '.data'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Start-Process -FilePath $pythonCommand.Source -ArgumentList $processArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardError (Join-Path $logDirectory 'server-errors.log')
