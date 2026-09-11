# INIZIA DA QUI

Questo archivio contiene il progetto completo **Civitas Full Core**, il codice
sorgente, i test, il viewer, Docker, un replay di esempio e l'audit tecnico.

## 1. Installazione
```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / WSL2
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Verifica immediata
```bash
pytest -q
python inspect_replay.py data/sample_replay.msgpack
```

## 3. Nuova simulazione
```bash
python main.py --agents 50 --ticks 600 --hz 15 --seed 42 \
  --log data/simulation_replay.msgpack
```

## 4. Audit riproducibile
```bash
python run_audit.py
```
Gli esiti vengono salvati in `audit/runtime/`.

## 5. Checkpoint
```bash
python main.py --fast --ticks 600 --checkpoint-every 100 \
  --checkpoint data/simulation.checkpoint.msgpack
python main.py --fast --ticks 1200 \
  --resume data/simulation.checkpoint.msgpack \
  --log data/recovered.msgpack
```

## 6. Visualizzazione
Apri `viewer/replay_viewer.html` (2D) o `viewer/viewer_3d.html` (3D) e carica un
`.msgpack`. Oppure E2E:

```bash
pip install playwright
python -m playwright install chromium
pytest -q tests/e2e
```

## 7. Ops bridge (audit/sim fuori dal tick)
```bash
python ops/civitas_ops.py audit
```

## Documentazione
- `README.md`: manuale tecnico e operativo.
- `audit/SCOPO.md`: missione, obiettivi e limiti.
- `audit/ARCHITETTURA.md`: flussi e contratti.
- `audit/QUALITA_E_TEST.md`: prove e risultati.
- `audit/PRESTAZIONI.md`: budget e colli di bottiglia.
- `audit/SICUREZZA_E_PRIVACY.md`: rischi e mitigazioni.
- `audit/RUNBOOK.md`: gestione operativa e incidenti.
- `audit/CHECKLIST.md`: ciò che è presente e ciò che resta da fare.
- `audit/GAP_INVENTORY.md`: inventario gap.
- `audit/AUDIT_SUMMARY.json`: riepilogo machine-readable.
- `audit/MANIFEST_SHA256.txt`: integrità dei file.
