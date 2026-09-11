# Civitas spatial native (Rust / PyO3)

Contratto per il modulo opzionale `civitas_spatial`. Finché il crate non è
compilato, `make_spatial_backend(..., backend="rust")` fa fallback silenzioso
alla baseline Python (`tests/test_spatial_golden.py`).

## API richiesta

```python
def astar(
    blocked: list[tuple[int, int]],
    width: int,
    height: int,
    start: tuple[int, int],
    goal: tuple[int, int],
    diagonal: bool,
) -> list[tuple[int, int]]:
    """Percorso incluso start; se irraggiungibile ritorna [start]."""

def all_pairs_near(
    ids: list[str],
    xy: list[tuple[float, float]],
    radius: float,
) -> list[tuple[str, str]]:
    """Coppie (a,b) con a<b lessicografico sugli id, distanza euclidea <= radius."""
```

## Gate di accettazione

1. `pytest tests/test_spatial_golden.py` deve passare con backend `python`.
2. Con estensione caricata, ripeti i golden: stessi `astar` e `pairs` del JSON in
   `tests/golden/spatial_seed42.json`.
3. Nessuna chiamata nativa nel path LLM; solo spatial.

## Build (quando il crate esiste)

```bash
maturin develop -m native/civitas_spatial/Cargo.toml
python -c "import civitas_spatial; print(civitas_spatial)"
```
