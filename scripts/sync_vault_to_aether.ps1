# Sync vault Civitas → mirror Aether (Windows PowerShell)
# Uso: .\scripts\sync_vault_to_aether.ps1
# Esclude .obsidian (config locale Obsidian).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Source = Join-Path $Root "vault"
$Dest = "D:\AETHER-VAULT\04-PROJECTS\civitas"

if (-not (Test-Path $Source)) {
  throw "Vault sorgente non trovato: $Source"
}

if (-not (Test-Path $Dest)) {
  New-Item -ItemType Directory -Path $Dest -Force | Out-Null
  Write-Host "[ok] creato $Dest"
}

Write-Host "[..] sync $Source -> $Dest (exclude .obsidian)"

$robocopy = Get-Command robocopy -ErrorAction SilentlyContinue
if ($robocopy) {
  # ROBOCOPY: 0-7 = success; /MIR mirror, /XD exclude dirs
  & robocopy $Source $Dest /MIR /XD .obsidian /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
  $rc = $LASTEXITCODE
  if ($rc -ge 8) {
    throw "robocopy failed with exit code $rc"
  }
  Write-Host "[ok] robocopy completato (exit $rc)"
} else {
  Write-Host "[warn] robocopy non trovato, uso xcopy"
  & xcopy $Source $Dest /E /I /Y /Q /EXCLUDE:(Join-Path $env:TEMP "civitas_xcopy_exclude.txt") 2>$null
  "@.obsidian@" | Set-Content -Encoding ascii (Join-Path $env:TEMP "civitas_xcopy_exclude.txt")
  # xcopy fallback: copy tree manually excluding .obsidian
  Get-ChildItem -Path $Source -Recurse -File | Where-Object {
    $_.FullName -notmatch '\\\.obsidian\\'
  } | ForEach-Object {
    $rel = $_.FullName.Substring($Source.Length).TrimStart('\')
    $target = Join-Path $Dest $rel
    $dir = Split-Path $target -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $_.FullName $target -Force
  }
  Write-Host "[ok] xcopy-style copy completato"
}

$fileCount = (Get-ChildItem -Path $Dest -Recurse -File | Measure-Object).Count
Write-Host "[ok] mirror Aether: $Dest ($fileCount files)"
