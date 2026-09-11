# Abilita Docker Desktop + servizio engine all'avvio di Windows.
# Esegui in PowerShell come Amministratore:
#   powershell -ExecutionPolicy Bypass -File scripts\enable_docker_autostart.ps1

$ErrorActionPreference = "Stop"

$settings = Join-Path $env:APPDATA "Docker\settings-store.json"
if (Test-Path $settings) {
    $json = Get-Content $settings -Raw | ConvertFrom-Json
    $json.AutoStart = $true
    $json | ConvertTo-Json -Depth 20 | Set-Content -Path $settings -Encoding utf8
    Write-Host "[OK] Docker Desktop AutoStart=true ($settings)"
} else {
    Write-Warning "settings-store.json non trovato: $settings"
}

$svc = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
if ($svc) {
    Set-Service -Name "com.docker.service" -StartupType Automatic
    if ($svc.Status -ne "Running") {
        Start-Service -Name "com.docker.service"
    }
    Write-Host "[OK] com.docker.service -> Automatic (stato: $((Get-Service com.docker.service).Status))"
} else {
    Write-Warning "Servizio com.docker.service non trovato. Docker Desktop e' installato?"
}

$desktop = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
if (Test-Path $desktop) {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $runKey -Name "Docker Desktop" -Value "`"$desktop`""
    Write-Host "[OK] Run key HKCU: Docker Desktop"
} else {
    Write-Warning "Docker Desktop.exe non trovato in Program Files"
}

Write-Host ""
Write-Host "Dopo un reboot, Docker dovrebbe avviarsi da solo."
Write-Host "Per Civitas persistente dopo l'engine:"
Write-Host "  cd <repo>; docker compose up -d --build"
