"""Guardia di regressione permanente sul determinismo cross-processo.

Consiglio esterno (2026-09-11, "4. Separazione fase pura/impura + test
di determinismo"): il tick loop di engine/tick_engine.py e' gia' sequenziale
per costruzione (`for a in self.agents: await a.step(...)` su una lista fissa,
non concorrente), quindi una riscrittura completa Plan/Resolve/Commit e' stata
scartata come alto rischio a fronte di un beneficio ormai marginale — i bug
reali di oggi (world/room_board.py e agents/cognitive.py.reflect(), entrambi
causati da iterazione su `set` sensibile a PYTHONHASHSEED, non da riordino di
agenti) sono gia' corretti e verificati. Questo test e' la parte a basso
rischio/alto valore del punto 4: una rete di sicurezza permanente contro
future regressioni della stessa classe (qualunque nuova iterazione su un
`set`/`dict` non ordinato che finisca nel replay).

PYTHONHASHSEED e' fissato all'avvio dell'interprete: non puo' essere cambiato
a runtime nello stesso processo, quindi il confronto va fatto fra due
sottoprocessi con env diverse (stesso approccio usato manualmente in sessione
per verificare i due bugfix di oggi)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from telemetry.logger import replay_digest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_sim(log_path: Path, *, seed: int, hash_seed: str) -> None:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    cmd = [
        sys.executable,
        "main.py",
        "--agents",
        "4",
        "--ticks",
        "600",
        "--seed",
        str(seed),
        "--fast",
        "--log",
        str(log_path),
        "--checkpoint",
        str(log_path.with_suffix(".checkpoint.msgpack")),
        "--manifest",
        str(log_path.with_suffix(".manifest.json")),
        "--no-mayor",  # provider cloud: mai nel path di un test di determinismo
    ]
    result = subprocess.run(
        cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, (
        f"main.py fallito (hash_seed={hash_seed}):\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.slow
def test_replay_bit_identical_across_different_pythonhashseed():
    """Stesso seed di simulazione, PYTHONHASHSEED diverso -> digest replay identico.

    Avrebbe intercettato entrambi i bug di determinismo corretti oggi (ordine
    di iterazione di un set() infiltrato nella scelta/risposta cache, prima
    del fix in world/room_board.py e agents/cognitive.py)."""
    with tempfile.TemporaryDirectory() as tmp:
        log_a = Path(tmp) / "run_a.msgpack"
        log_b = Path(tmp) / "run_b.msgpack"
        _run_sim(log_a, seed=42, hash_seed="0")
        _run_sim(log_b, seed=42, hash_seed="1337")
        digest_a = replay_digest(str(log_a))
        digest_b = replay_digest(str(log_b))
        assert digest_a == digest_b, (
            "Divergenza di replay fra hash-seed diversi: nondeterminismo nascosto "
            "(probabile iterazione su set/dict non ordinato finita nel path decisionale)."
        )
