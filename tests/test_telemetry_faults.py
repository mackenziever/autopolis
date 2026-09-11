import struct

import pytest

from telemetry.logger import BinaryTelemetryLogger, iter_records


def create(path):
    with BinaryTelemetryLogger(str(path), {"test": True}, 1) as log:
        for t in range(5):
            log.log_tick(t, float(t), [{"type": "snapshot", "tick": t}])


def test_truncated_replay_strict_and_tolerant(tmp_path):
    p = tmp_path / "x.msgpack"
    create(p)
    raw = p.read_bytes()
    p.write_bytes(raw[:-7])
    with pytest.raises(IOError):
        list(iter_records(str(p)))
    recs = list(iter_records(str(p), tolerate_truncated=True))
    assert recs[0]["record"] == "header"
    assert sum(r.get("record") == "tick" for r in recs) == 5


def test_absurd_frame_rejected(tmp_path):
    p = tmp_path / "bad.msgpack"
    p.write_bytes(struct.pack(">I", 300 * 1024 * 1024))
    with pytest.raises(IOError, match="irragionevole"):
        list(iter_records(str(p)))
