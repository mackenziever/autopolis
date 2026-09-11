# INVENTARIO DIPENDENZE

## Core obbligatorio
- Python >= 3.11: runtime e asyncio.
- NumPy >= 2,<3: prossimità e feature vectors.
- MessagePack >= 1,<2: event log binario.

## Test
- pytest >= 8,<10.

## Opzionali
- uvloop: event loop ottimizzato su Linux/WSL2.
- rustworkx: algoritmi graph nativi.
- USearch: indice vettoriale embedded.
- Polars: conversione analytics Parquet.
- pyzmq: feed live PUB/SUB.
- LiteLLM: client/proxy compatibile con il formato chat-completion standard.

## Runtime modello esterno
vLLM o SGLang non sono dipendenze del core e vanno gestiti come servizio
separato. Il simulatore comunica soltanto con un endpoint compatibile con il formato chat-completion standard.

## Regola di aggiornamento
Aggiornare una dipendenza in un branch separato, eseguire test, due replay di
determinismo, benchmark e scansione vulnerabilità prima del merge.
