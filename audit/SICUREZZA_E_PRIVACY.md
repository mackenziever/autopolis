# AUDIT SICUREZZA, PRIVACY E AFFIDABILITÀ

## Superfici di attacco
- Endpoint LLM/compatibile con il formato chat-completion standard.
- File `llm_trace.jsonl` e replay caricati dal viewer.
- Endpoint ZMQ, se esposto fuori da localhost.
- Immagini Docker e dipendenze Python.

## Controlli presenti
- Scelte LLM validate contro una allow-list.
- Pensieri troncati a 400 caratteri + sanitizzazione PII.
- Timeout e concorrenza limitata per l'LLM.
- Dimensione massima frame replay: 256 MiB.
- Nessuna esecuzione di contenuto proveniente dal modello.
- Fallback locale in caso di errore.
- Gateway opzionale TLS/Auth + rate-limit (`security/llm_gateway.py`).
- HMAC sidecar dei replay (`CIVITAS_REPLAY_HMAC_KEY`, `--sign-replay`).
- ZMQ solo loopback salvo `CIVITAS_ZMQ_ALLOW_PUBLIC=1`.
- Secrets solo da environment; masking in log/errori.
- Manifest operativo del run (sidecar JSON).
- CVE scan via `pip-audit` in CI (`scripts/scan_cve.py`).

## Controlli da aggiungere prima di Internet/produzione
- Certificati TLS gestiti (CA/Let's Encrypt) davanti al gateway.
- Rate limit per tenant multi-host oltre single-process.
- Retention policy dei pensieri e dei trace LLM.
- Network policy host firewall: sim → solo gateway LLM.
- Registry scanning continuo delle immagini Docker.

## Privacy
Le persone incluse sono sintetiche. Non importare dati reali o conversazioni
personali senza una base giuridica, minimizzazione, retention e controllo accessi.

## Affidabilità
La baseline è single-process. Checkpoint atomici (`engine/checkpoint.py`)
consentono ripresa mid-run con verifica SHA-256 e fingerprint. Per Internet:
healthcheck formale, metriche Prometheus e recovery testato in CI.
