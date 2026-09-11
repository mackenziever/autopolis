# Bootstrap FreeLLMAPI + Alveare + Civitas LLM (Windows PowerShell)
# Uso: .\scripts\bootstrap_freellm_stack.ps1
# Dopo l'avvio: apri http://127.0.0.1:3001 → Keys → aggiungi provider free-tier
# → copia unified key in CIVITAS_LLM_API_KEY (file .env.llm o env utente).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$envFile = Join-Path $Root ".env.freellmapi"
if (-not (Test-Path $envFile)) {
  $key = python -c "import secrets; print(secrets.token_hex(32))"
  @"
ENCRYPTION_KEY=$key
PORT=3001
HOST_BIND=127.0.0.1
"@ | Set-Content -Encoding ascii $envFile
  Write-Host "[ok] creato .env.freellmapi con ENCRYPTION_KEY"
} else {
  Write-Host "[ok] riuso .env.freellmapi esistente"
}

# Carica ENCRYPTION_KEY per compose interpolate
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $k, $v = $_.Split('=', 2)
  [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
}

Write-Host "[..] docker compose --profile llm up -d --build"
docker compose --profile llm up -d --build

Write-Host "[..] attendo FreeLLM /api/ping ..."
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:3001/api/ping" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { Start-Sleep -Seconds 3 }
}
if (-not $ok) { throw "FreeLLMAPI non risponde su :3001" }
Write-Host "[ok] FreeLLMAPI live http://127.0.0.1:3001"

try {
  $h = Invoke-RestMethod -Uri "http://127.0.0.1:9200/health" -TimeoutSec 5
  Write-Host "[ok] Alveare $($h | ConvertTo-Json -Compress)"
} catch {
  Write-Host "[warn] Alveare non ancora pronto: $_"
}

$llmEnv = Join-Path $Root ".env.llm"
if (-not (Test-Path $llmEnv)) {
  @"
CIVITAS_LLM_API_BASE=http://127.0.0.1:3001/v1
CIVITAS_LLM_MODEL=openai/auto
CIVITAS_LLM_API_KEY=
CIVITAS_ALVEARE_URL=http://127.0.0.1:9200
"@ | Set-Content -Encoding ascii $llmEnv
  Write-Host "[ok] creato .env.llm — INSERISCI la unified key da dashboard Keys"
}

Write-Host @"

=== PROSSIMO PASSO (obbligatorio per inferenza REALE) ===
1. Apri http://127.0.0.1:3001
2. Login / setup account server
3. Keys → aggiungi almeno 1–2 provider free (Groq, Google, Mistral, OpenRouter, …)
4. Copia la unified API key (freellmapi-...) in .env.llm come CIVITAS_LLM_API_KEY
5. Avvia sim host:
   `$env:CIVITAS_LLM_API_KEY='freellmapi-...'
   python main.py --fast --llm --agents 8 --ticks 600 --alveare-url http://127.0.0.1:9200 --cognitive-worker --log data/simulation_replay_llm.msgpack
Oppure: docker compose --profile llm up -d simulator-llm  (dopo aver esportato la key)

Senza provider keys FreeLLM risponde ma non ha upstream → gli agenti cadono in fallback deterministico.
"@
