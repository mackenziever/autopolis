"""Registro append-only, framed MessagePack, riproducibile bit-per-bit.

Formato:
  4 byte unsigned big-endian = lunghezza payload
  N byte MessagePack
Ogni frame e' autonomo: un crash perde al massimo l'ultimo frame incompleto.
"""
from __future__ import annotations
import os, struct
from typing import Iterator, Dict, Any
import msgpack

SCHEMA_VERSION = 1

class BinaryTelemetryLogger:
    def __init__(self, path: str, metadata: dict, flush_every: int = 30):
        self.path, self.flush_every, self.count = path, flush_every, 0
        self.bytes_written = 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.f = open(path, "wb", buffering=1024*1024)
        self._write({"record":"header","schema":SCHEMA_VERSION,"metadata":metadata})

    def _write(self, obj: Dict[str,Any]):
        payload = msgpack.packb(obj, use_bin_type=True, strict_types=False)
        frame = struct.pack(">I", len(payload)) + payload
        self.f.write(frame)
        self.bytes_written += len(frame)

    def log_tick(self, tick: int, sim_time: float, events: list[dict]):
        # Nessun timestamp wall-clock/duration nel log autorevole: stesso input => stessi byte.
        self._write({"record":"tick","tick":tick,"sim_time":sim_time,"events":events})
        self.count += 1
        if self.count % self.flush_every == 0: self.f.flush()

    def close(self):
        if not self.f.closed:
            self._write({"record":"footer","ticks":self.count})
            self.f.flush(); os.fsync(self.f.fileno()); self.f.close()

    def __enter__(self): return self
    def __exit__(self,*_): self.close()


def iter_records(path: str, tolerate_truncated: bool = False) -> Iterator[dict]:
    with open(path,"rb") as f:
        while True:
            h=f.read(4)
            if not h: return
            if len(h)!=4:
                if tolerate_truncated: return
                raise IOError("Header frame troncato")
            n=struct.unpack(">I",h)[0]
            if n > 256*1024*1024: raise IOError(f"Frame irragionevole: {n} byte")
            p=f.read(n)
            if len(p)!=n:
                if tolerate_truncated: return
                raise IOError("Payload frame troncato")
            yield msgpack.unpackb(p,raw=False,strict_map_key=False)


def replay_digest(path: str) -> str:
    import hashlib
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
