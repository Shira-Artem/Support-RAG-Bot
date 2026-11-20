param(
    [Parameter(Mandatory=$true)][string]$CrmRoot,
    [Parameter(Mandatory=$true)][string]$RagPython,
    [Parameter(Mandatory=$true)][string]$RagEnvFile,
    [switch]$Pilot
)
$ErrorActionPreference = 'Stop'
$ragRoot = Split-Path -Parent $PSScriptRoot
$crmPath = (Resolve-Path -LiteralPath $CrmRoot).Path
$ragPythonPath = (Resolve-Path -LiteralPath $RagPython).Path
$baseEnv = (Resolve-Path -LiteralPath $RagEnvFile).Path
$serviceEnv = Join-Path $ragRoot '.local/integration.env'
$crmEnv = Join-Path $crmPath '.local/crm.env'
$crmPython = Join-Path $crmPath '.venv/Scripts/python.exe'
foreach ($path in @($serviceEnv, $crmEnv, $crmPython)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing prepared local resource: $path" }
}
docker start crm-rag-mysql | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Prepared isolated MySQL container is unavailable; follow the runbook.' }
function Start-ServiceIfAbsent($port, $python, $arguments, $directory, $stem) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 5
        if ($health.status -ne 'ok') { throw "Service on $port is not healthy" }
        Write-Output "Healthy service already listening on $port"
        return
    }
    $logRoot = Join-Path $directory '.local'
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot "$stem.stdout.log") -RedirectStandardError (Join-Path $logRoot "$stem.stderr.log") -PassThru
    $process.Id | Set-Content -LiteralPath (Join-Path $logRoot "$stem.pid")
    Write-Output "Started $stem launcher PID $($process.Id)"
}
# Quote paths for the Windows native argument parser. No secret values in argv.
Start-ServiceIfAbsent 8091 $ragPythonPath @('-X','utf8','scripts/run_support_api.py','--env-file',('"'+$baseEnv+'"'),'--service-env-file',('"'+$serviceEnv+'"')) $ragRoot 'api'
$crmArguments = @('-X','utf8','tools/run_rag_support.py','--env-file',('"'+$crmEnv+'"'))
if ($Pilot) { $crmArguments += @('--telegram-env-file', ('"'+$baseEnv+'"')) }
Start-ServiceIfAbsent 8092 $crmPython $crmArguments $crmPath 'crm'
if ($Pilot) {
    $oldPoller = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*.local/kb-authoritative/start_bot.py*' }
    if ($oldPoller) { throw 'Previous RAG poller is active. Stop it before starting the authorized CRM pilot.' }
    $pilotPoller = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*tools/run_rag_pilot_bot.py*' }
    if (-not $pilotPoller) {
        $pilotProcess = Start-Process -FilePath $crmPython -ArgumentList @('-X','utf8','tools/run_rag_pilot_bot.py','--env-file',('"'+$crmEnv+'"'),'--rag-env-file',('"'+$baseEnv+'"')) -WorkingDirectory $crmPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $crmPath '.local/pilot.stdout.log') -RedirectStandardError (Join-Path $crmPath '.local/pilot.stderr.log') -PassThru
        $pilotProcess.Id | Set-Content -LiteralPath (Join-Path $crmPath '.local/pilot.pid')
        Write-Output "Started CRM Telegram pilot launcher PID $($pilotProcess.Id)"
    } else { Write-Output 'CRM Telegram pilot already running' }
}
Write-Output 'Services are starting; check /healthz. To refresh the one-hour manual chat link:'
Write-Output "& `"$crmPython`" -X utf8 `"$crmPath/tools/create_rag_demo.py`" --env-file `"$crmEnv`""
